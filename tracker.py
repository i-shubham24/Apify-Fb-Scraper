import requests
import os
import json
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
    response = requests.post(url, json=payload)
    print(f"Telegram API Response: {response.status_code} - {response.text}")

def process_scraped_data(items: list):
    print(f"Processing {len(items)} items received from Apify.")
    for item in items:
        # Safety check: skip if the item is not a valid dictionary object
        if not isinstance(item, dict):
            print(f"Skipping non-dict item type: {type(item)}")
            continue

        listing_id = str(item.get("id", item.get("postId", "")))
        title = item.get("title", "No Title")
        raw_price = item.get("price")
        listing_url = item.get("url", "")
        description = item.get("description", "")

        if not raw_price or not listing_id:
            continue

        try:
            price = float(raw_price)
        except (ValueError, TypeError):
            continue

        # Query Supabase to see if the listing exists
        response = supabase.table("listings").select("price, status").eq("id", listing_id).execute()
        
        if len(response.data) == 0:
            # Analyze with Gemini to filter out scams
            analysis_json = analyze_listing(title, description)
            try:
                analysis = json.loads(analysis_json)
            except Exception as e:
                print(f"JSON parse error from Gemini: {e}")
                analysis = {"is_scam": False, "battery_health": "N/A", "storage": "N/A", "condition_notes": "Analyzed"}
            
            if analysis.get("is_scam"):
                print(f"Filtered out potential scam: {title}")
                continue
            
            # Insert new listing into Supabase
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
                f"🔋 Battery: {analysis.get('battery_health')}\n"
                f"💾 Storage: {analysis.get('storage')}\n"
                f"⚠️ Condition: {analysis.get('condition_notes')}"
            )
            send_telegram_alert(alert, listing_id, listing_url)

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
                    f"🏷️ Old Price: <s>₹{old_price:,.2f}</s>\n"
                    f"🔥 New Price: <b>₹{price:,.2f}</b>\n"
                    f"📊 Status: {current_status}"
                )
                send_telegram_alert(alert, listing_id, listing_url)