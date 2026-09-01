import sqlite3
import requests
import os
import json
from dotenv import load_dotenv
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
    conn = sqlite3.connect("marketplace.db")
    cursor = conn.cursor()

    for item in items:
        listing_id = str(item.get("id", item.get("postId", "")))
        title = item.get("title", "No Title")
        raw_price = item.get("price")
        listing_url = item.get("url", "")
        description = item.get("description", "")

        if not raw_price or not listing_id:
            continue

        price = float(raw_price)

        cursor.execute("SELECT price, status FROM listings WHERE id = ?", (listing_id,))
        row = cursor.fetchone()

        if row is None:
            # 1. NEW LISTING
            cursor.execute(
                "INSERT INTO listings (id, title, price, url) VALUES (?, ?, ?, ?)",
                (listing_id, title, price, listing_url)
            )
            
            # Analyze with Gemini
            analysis_json = analyze_listing(title, description)
            analysis = json.loads(analysis_json)
            
            # Skip scams
            if analysis.get("is_scam"):
                continue

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
            old_price, current_status = row
            if price < old_price:
                # 2. PRICE DROP
                discount = ((old_price - price) / old_price) * 100
                cursor.execute("UPDATE listings SET price = ? WHERE id = ?", (price, listing_id))
                
                alert = (
                    f"📉 <b>Price Drop Alert! (-{discount:.1f}%)</b>\n\n"
                    f"📱 {title}\n"
                    f"🏷️ Old Price: <s>${old_price:,.2f}</s>\n"
                    f"🔥 New Price: <b>${price:,.2f}</b>\n"
                    f"📊 Status: {current_status}"
                )
                send_telegram_alert(alert, listing_id, listing_url)

    conn.commit()
    conn.close()