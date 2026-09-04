import requests
import os
import json
import time
import re
from dotenv import load_dotenv
from database import supabase
from gemini_analyzer import analyze_listing

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

def send_telegram_alert(text: str, listing_id: str, listing_url: str, image_url: str = None):
    keyboard = {
        "inline_keyboard": [
            [{"text": "🔗 View Listing", "url": listing_url}],
            [
                {"text": "💬 Mark Contacted", "callback_data": f"status:CONTACTED:{listing_id}"},
                {"text": "✅ Purchased", "callback_data": f"status:PURCHASED:{listing_id}"}
            ],
            [{"text": "📋 Copy Offer Template", "callback_data": f"offer:{listing_id}"}]
        ]
    }

    # Use sendPhoto if a valid image preview exists, otherwise fallback to sendMessage
    if image_url and image_url.startswith("http"):
        url = f"https://api.telegram.org/bot{TOKEN}/sendPhoto"
        payload = {
            "chat_id": CHAT_ID,
            "photo": image_url,
            "caption": text,
            "parse_mode": "HTML",
            "reply_markup": keyboard
        }
    else:
        url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
        payload = {
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "reply_markup": keyboard
        }
        
    response = requests.post(url, json=payload)
    print(f"Telegram API Response: {response.status_code}")

def process_scraped_data(items: list):
    print(f"Processing {len(items)} items in the background...")
    
    for item in items:
        try:
            if not isinstance(item, dict):
                continue

            listing_id = str(item.get("id") or item.get("listingId") or item.get("postId") or "")
            title = item.get("title") or item.get("marketplace_listing_title") or "No Title"
            listing_url = item.get("url") or f"https://www.facebook.com/marketplace/item/{listing_id}"
            description = item.get("description", "")
            
            # Extract image thumbnail URL from various possible Apify schemas
            image_url = (
                item.get("image") or 
                item.get("thumbnailUrl") or 
                item.get("primary_image", {}).get("uri") or 
                (item.get("images", [{}])[0] if isinstance(item.get("images"), list) and len(item.get("images")) > 0 else None)
            )
            if isinstance(image_url, dict):
                image_url = image_url.get("uri") or image_url.get("url")

            raw_price = item.get("price") or item.get("formatted_price") or item.get("listing_price")

            if not raw_price or not listing_id:
                continue

            if isinstance(raw_price, str):
                cleaned_price = re.sub(r'[^\d.]', '', raw_price)
                price = float(cleaned_price) if cleaned_price else 0.0
            elif isinstance(raw_price, dict): 
                price = float(raw_price.get("amount", raw_price.get("value", 0)))
            else:
                price = float(raw_price)
                
            if price == 0.0:
                continue

            response = supabase.table("listings").select("price, status, title").eq("id", listing_id).execute()
            
            if len(response.data) == 0:
                print(f"Sending to Gemini for analysis: {title}")
                time.sleep(4.5) 
                
                analysis = {}
                try:
                    analysis_json = analyze_listing(title, description, price)
                    analysis = json.loads(analysis_json)
                except Exception as e:
                    print(f"Gemini API Error for '{title}': {e}")
                    analysis = {
                        "is_scam": False,
                        "is_broken": False,
                        "is_target_brand": True,
                        "battery_health": "N/A", 
                        "storage": "N/A", 
                        "estimated_market_value": price,
                        "deal_score": 5,
                        "condition_notes": "API Error / Manual review needed."
                    }
                
                if analysis.get("is_scam") or analysis.get("is_broken") or not analysis.get("is_target_brand"):
                    print(f"Filtered out listing: {title}")
                    continue
                
                market_val = analysis.get("estimated_market_value", price)
                deal_score = analysis.get("deal_score", 5)

                supabase.table("listings").insert({
                    "id": listing_id,
                    "title": title,
                    "price": price,
                    "url": listing_url,
                    "status": "NEW"
                }).execute()

                print(f"New deal saved & alerting Telegram: {title}")
                alert = (
                    f"🔥 <b>New Deal Alert! (Score: {deal_score}/10)</b>\n\n"
                    f"📱 <b>{title}</b>\n"
                    f"💰 Listed: <b>${price:,.2f} CAD</b>\n"
                    f"📊 Est. Market Value: ~${market_val:,.2f} CAD\n\n"
                    f"🤖 <b>AI Insights:</b>\n"
                    f"🔋 Battery: {analysis.get('battery_health', 'N/A')}\n"
                    f"💾 Storage: {analysis.get('storage', 'N/A')}\n"
                    f"⚠️ Condition: {analysis.get('condition_notes', 'N/A')}"
                )
                send_telegram_alert(alert, listing_id, listing_url, image_url)

            else:
                existing_data = response.data[0]
                old_price = float(existing_data["price"])
                current_status = existing_data["status"]
                
                if price < old_price:
                    discount = ((old_price - price) / old_price) * 100
                    supabase.table("listings").update({"price": price}).eq("id", listing_id).execute()
                    supabase.table("price_history").insert({
                        "listing_id": listing_id,
                        "old_price": old_price,
                        "new_price": price
                    }).execute()
                    
                    print(f"Price drop detected for {title}")
                    alert = (
                        f"📉 <b>Price Drop Alert! (-{discount:.1f}%)</b>\n\n"
                        f"📱 {title}\n"
                        f"🏷️ Old Price: <s>${old_price:,.2f} CAD</s>\n"
                        f"🔥 New Price: <b>${price:,.2f} CAD</b>\n"
                        f"📊 Status: {current_status}"
                    )
                    send_telegram_alert(alert, listing_id, listing_url, image_url)

        except Exception as e:
            print(f"Critical error processing listing: {e}")
            continue