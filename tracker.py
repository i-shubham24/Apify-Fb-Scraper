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
    requests.post(url, json=payload)

def process_scraped_data(items: list):
    for item in items:
        # Safety check: skip if the item is not a valid dictionary object
        if not isinstance(item, dict):
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

        # 1. Query Supabase to see if the listing exists
        response = supabase.table("listings").select("price, status").eq("id", listing_id).execute()
        
        if len(response.data) == 0:
            # Analyze with Gemini first to skip scams
            analysis_json = analyze_listing(title, description)
            analysis = json.loads(analysis_json)
            
            if analysis.get("is_scam"):
                continue
            
            # Insert new listing into Supabase
            supabase.table("listings").insert({
                "id": listing_id,
                "title": title,
                "price": price,
                "url": listing_url,
                "status": "NEW"
            }).execute()

            alert = (
                f"🆕 <b>New Listing Alert!</b>\n\n"
                f"📱 <b>{title}</b>\n"
                f"💰 <b>${price:,.2f}</b>\n\n"
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
                
                alert = (
                    f"📉 <b>Price Drop Alert! (-{discount:.1f}%)</b>\n\n"
                    f"📱 {title}\n"
                    f"🏷️ Old Price: <s>${old_price:,.2f}</s>\n"
                    f"🔥 New Price: <b>${price:,.2f}</b>\n"
                    f"📊 Status: {current_status}"
                )
                send_telegram_alert(alert, listing_id, listing_url)