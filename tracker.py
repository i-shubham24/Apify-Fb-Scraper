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

def send_telegram_alert(text: str, listing_id: str, listing_url: str):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "reply_markup": {
            "inline_keyboard": [
                [{"text": "🔗 View Listing", "url": listing_url}],
                [{"text": "💬 Mark Contacted", "callback_data": f"status:CONTACTED:{listing_id}"}],
                [{"text": "✅ Purchased", "callback_data": f"status:PURCHASED:{listing_id}"}]
            ]
        }
    }
    requests.post(url, json=payload)

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
            
            raw_price = item.get("price") or item.get("formatted_price") or item.get("listing_price")

            if not raw_price or not listing_id:
                continue

            # Parse and clean the price string
            if isinstance(raw_price, str):
                cleaned_price = re.sub(r'[^\d.]', '', raw_price)
                price = float(cleaned_price) if cleaned_price else 0.0
            elif isinstance(raw_price, dict): 
                price = float(raw_price.get("amount", raw_price.get("value", 0)))
            else:
                price = float(raw_price)
                
            if price == 0.0:
                continue

            # Check if listing already exists in database
            response = supabase.table("listings").select("price, status").eq("id", listing_id).execute()
            
            if len(response.data) == 0:
                print(f"Sending to Gemini for analysis: {title}")
                time.sleep(4.5) # Respect Gemini API 15 RPM free tier limit
                
                # Protect against Gemini API 503 Crashes
                analysis = {}
                try:
                    analysis_json = analyze_listing(title, description)
                    analysis = json.loads(analysis_json)
                except Exception as e:
                    print(f"Gemini API Error for '{title}': {e}")
                    analysis = {
                        "is_scam": False,
                        "is_broken": False,
                        "is_target_brand": True, # Default to True so it isn't skipped on API failure
                        "battery_health": "N/A", 
                        "storage": "N/A", 
                        "condition_notes": "Gemini API unavailable. Manual review needed."
                    }
                
                # Apply the strict filtering rules
                is_scam = analysis.get("is_scam", False)
                is_broken = analysis.get("is_broken", False)
                is_target_brand = analysis.get("is_target_brand", True)

                if is_scam:
                    print(f"🚫 Rejected (Scam/Copy): {title}")
                    continue
                
                if is_broken:
                    print(f"🔧 Rejected (Broken/Defective): {title}")
                    continue
                    
                if not is_target_brand:
                    print(f"📱 Rejected (Wrong Brand): {title}")
                    continue
                
                # Insert the approved listing into Supabase
                supabase.table("listings").insert({
                    "id": listing_id,
                    "title": title,
                    "price": price,
                    "url": listing_url,
                    "status": "NEW"
                }).execute()

                print(f"New unique listing saved & alerting Telegram: {title}")
                alert = (
                    f"🆕 <b>New Listing Alert!</b>\n\n"
                    f"📱 <b>{title}</b>\n"
                    f"💰 <b>₹{price:,.2f}</b>\n\n"
                    f"🤖 <b>Gemini Analysis:</b>\n"
                    f"🔋 Battery: {analysis.get('battery_health', 'N/A')}\n"
                    f"💾 Storage: {analysis.get('storage', 'N/A')}\n"
                    f"⚠️ Condition: {analysis.get('condition_notes', 'N/A')}"
                )
                send_telegram_alert(alert, listing_id, listing_url)

            else:
                # Listing exists, check for a price drop
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
                        f"🏷️ Old Price: <s>₹{old_price:,.2f}</s>\n"
                        f"🔥 New Price: <b>₹{price:,.2f}</b>\n"
                        f"📊 Status: {current_status}"
                    )
                    send_telegram_alert(alert, listing_id, listing_url)

        except Exception as e:
            # Prevents a single bad phone data structure from breaking the loop
            print(f"Critical error processing listing '{item.get('title', 'Unknown')}': {e}")
            continue