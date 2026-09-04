from fastapi import FastAPI, Request, BackgroundTasks
from database import supabase
from tracker import process_scraped_data
import requests
import os
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
APIFY_API_TOKEN = os.getenv("APIFY_API_TOKEN")

app = FastAPI()

@app.on_event("startup")
async def set_bot_commands():
    commands = [
        {"command": "deals", "description": "View 5 latest tracked listings"},
        {"command": "watchlist", "description": "View active uncontacted items"},
        {"command": "apple", "description": "View latest iPhone listings"},
        {"command": "samsung", "description": "View latest Samsung listings"},
        {"command": "pixel", "description": "View latest Google Pixel listings"},
        {"command": "contacted", "description": "View deals marked as contacted"},
        {"command": "purchased", "description": "View successfully purchased deals"},
        {"command": "stats", "description": "View pipeline database statistics"},
        {"command": "help", "description": "Show help menu"}
    ]
    url = f"https://api.telegram.org/bot{TOKEN}/setMyCommands"
    try:
        requests.post(url, json={"commands": commands})
        print("Telegram bot commands registered successfully!")
    except Exception as e:
        print(f"Failed to register bot commands: {e}")

@app.get("/")
async def health_check():
    return {"status": "Canadian Marketplace Bot is active!"}

@app.api_route("/webhook/apify", methods=["GET", "POST"])
async def apify_webhook(request: Request, background_tasks: BackgroundTasks):
    if request.method == "GET":
        return {"status": "Apify webhook endpoint is active"}
        
    payload = await request.json()
    dataset_id = payload.get("resource", {}).get("defaultDatasetId")
    
    if dataset_id:
        dataset_url = f"https://api.apify.com/v2/datasets/{dataset_id}/items?clean=true"
        headers = {"Authorization": f"Bearer {APIFY_API_TOKEN}"} if APIFY_API_TOKEN else {}
        response = requests.get(dataset_url, headers=headers)
        
        try:
            items = response.json()
            if isinstance(items, list):
                print(f"Queuing {len(items)} items for background processing...")
                background_tasks.add_task(process_scraped_data, items)
        except Exception as e:
            print(f"Failed to queue dataset: {e}")
        
    return {"status": "ok"}

@app.post("/webhook/telegram")
async def telegram_webhook(request: Request):
    data = await request.json()

    if "callback_query" in data:
        callback = data["callback_query"]
        callback_id = callback["id"]
        callback_data = callback.get("data", "")
        message = callback.get("message", {})
        chat_id = message.get("chat", {}).get("id")
        message_id = message.get("message_id")

        try:
            if callback_data == "none":
                requests.post(f"https://api.telegram.org/bot{TOKEN}/answerCallbackQuery", json={"callback_query_id": callback_id})
                return {"status": "ok"}

            if callback_data.startswith("offer:"):
                _, listing_id = callback_data.split(":")
                res = supabase.table("listings").select("title, price").eq("id", listing_id).execute()
                if res.data:
                    item = res.data[0]
                    offer_text = f"Hi! Is this {item['title']} still available? Can you do ${float(item['price'])-20:,.0f} CAD cash pickup today?"
                else:
                    offer_text = "Hi! Is this still available? Can you do cash pickup today?"

                requests.post(f"https://api.telegram.org/bot{TOKEN}/answerCallbackQuery", json={
                    "callback_query_id": callback_id, 
                    "text": "Offer generated as a reply below!"
                })
                
                requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={
                    "chat_id": chat_id,
                    "reply_to_message_id": message_id,
                    "text": f"📋 <b>Quick Offer Template:</b>\n\n<code>{offer_text}</code>",
                    "parse_mode": "HTML"
                })
                return {"status": "ok"}

            _, new_status, listing_id = callback_data.split(":")
            supabase.table("listings").update({"status": new_status}).eq("id", listing_id).execute()

            requests.post(f"https://api.telegram.org/bot{TOKEN}/answerCallbackQuery", json={
                "callback_query_id": callback_id, 
                "text": f"Status updated to {new_status}!"
            })

            updated_keyboard = {
                "inline_keyboard": [
                    [{"text": f"✅ Status: {new_status}", "callback_data": "none"}]
                ]
            }
            requests.post(f"https://api.telegram.org/bot{TOKEN}/editMessageReplyMarkup", json={
                "chat_id": chat_id,
                "message_id": message_id,
                "reply_markup": updated_keyboard
            })

        except Exception as e:
            print(f"Error handling callback query: {e}")

    elif "message" in data:
        message = data["message"]
        chat_id = message.get("chat", {}).get("id")
        text = message.get("text", "").strip().lower()

        if text.startswith("/stats"):
            try:
                total = supabase.table("listings").select("id", count="exact").execute().count or 0
                new_count = supabase.table("listings").select("id", count="exact").eq("status", "NEW").execute().count or 0
                contacted = supabase.table("listings").select("id", count="exact").eq("status", "CONTACTED").execute().count or 0
                purchased = supabase.table("listings").select("id", count="exact").eq("status", "PURCHASED").execute().count or 0

                reply = (
                    f"📊 <b>Market Bot Statistics</b>\n\n"
                    f"📱 Total Tracked: {total}\n"
                    f"🔥 Active Watchlist: {new_count}\n"
                    f"💬 Contacted Sellers: {contacted}\n"
                    f"✅ Purchased: {purchased}"
                )
            except Exception as e:
                reply = f"Could not retrieve stats: {e}"

            requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={
                "chat_id": chat_id, "text": reply, "parse_mode": "HTML"
            })

        elif text.startswith("/deals"):
            try:
                res = supabase.table("listings").select("title, price, url").order("id", desc=True).limit(5).execute()
                if res.data:
                    reply = "🔥 <b>Latest Tracked Deals:</b>\n\n"
                    for item in res.data:
                        reply += f"• <a href='{item['url']}'>{item['title']}</a> - <b>${float(item['price']):,.2f} CAD</b>\n"
                else:
                    reply = "No deals found in database yet."
            except Exception as e:
                reply = f"Error fetching deals: {e}"

            requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={
                "chat_id": chat_id, "text": reply, "parse_mode": "HTML", "disable_web_page_preview": True
            })

        elif text.startswith("/apple"):
            try:
                res = supabase.table("listings").select("title, price, url").ilike("title", "%iphone%").order("id", desc=True).limit(5).execute()
                if res.data:
                    reply = "🍎 <b>Latest Apple iPhone Deals:</b>\n\n"
                    for item in res.data:
                        reply += f"• <a href='{item['url']}'>{item['title']}</a> - <b>${float(item['price']):,.2f} CAD</b>\n"
                else:
                    reply = "No iPhone listings found in database."
            except Exception as e:
                reply = f"Error fetching Apple deals: {e}"

            requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={
                "chat_id": chat_id, "text": reply, "parse_mode": "HTML", "disable_web_page_preview": True
            })

        elif text.startswith("/samsung"):
            try:
                res = supabase.table("listings").select("title, price, url").ilike("title", "%samsung%").order("id", desc=True).limit(5).execute()
                if res.data:
                    reply = "📱 <b>Latest Samsung Galaxy Deals:</b>\n\n"
                    for item in res.data:
                        reply += f"• <a href='{item['url']}'>{item['title']}</a> - <b>${float(item['price']):,.2f} CAD</b>\n"
                else:
                    reply = "No Samsung listings found in database."
            except Exception as e:
                reply = f"Error fetching Samsung deals: {e}"

            requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={
                "chat_id": chat_id, "text": reply, "parse_mode": "HTML", "disable_web_page_preview": True
            })

        elif text.startswith("/pixel"):
            try:
                res = supabase.table("listings").select("title, price, url").ilike("title", "%pixel%").order("id", desc=True).limit(5).execute()
                if res.data:
                    reply = "📸 <b>Latest Google Pixel Deals:</b>\n\n"
                    for item in res.data:
                        reply += f"• <a href='{item['url']}'>{item['title']}</a> - <b>${float(item['price']):,.2f} CAD</b>\n"
                else:
                    reply = "No Google Pixel listings found in database."
            except Exception as e:
                reply = f"Error fetching Pixel deals: {e}"

            requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={
                "chat_id": chat_id, "text": reply, "parse_mode": "HTML", "disable_web_page_preview": True
            })

        elif text.startswith("/watchlist"):
            try:
                res = supabase.table("listings").select("title, price, url").eq("status", "NEW").order("id", desc=True).limit(5).execute()
                if res.data:
                    reply = "📌 <b>Active Watchlist (Uncontacted):</b>\n\n"
                    for item in res.data:
                        reply += f"• <a href='{item['url']}'>{item['title']}</a> - <b>${float(item['price']):,.2f} CAD</b>\n"
                else:
                    reply = "No active listings currently in your watchlist."
            except Exception as e:
                reply = f"Error fetching watchlist: {e}"

            requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={
                "chat_id": chat_id, "text": reply, "parse_mode": "HTML", "disable_web_page_preview": True
            })

        elif text.startswith("/contacted"):
            try:
                res = supabase.table("listings").select("title, price, url").eq("status", "CONTACTED").limit(5).execute()
                if res.data:
                    reply = "💬 <b>Deals You Contacted:</b>\n\n"
                    for item in res.data:
                        reply += f"• <a href='{item['url']}'>{item['title']}</a> - <b>${float(item['price']):,.2f} CAD</b>\n"
                else:
                    reply = "No contacted deals recorded yet."
            except Exception as e:
                reply = f"Error fetching contacted items: {e}"

            requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={
                "chat_id": chat_id, "text": reply, "parse_mode": "HTML", "disable_web_page_preview": True
            })

        elif text.startswith("/purchased"):
            try:
                res = supabase.table("listings").select("title, price, url").eq("status", "PURCHASED").limit(5).execute()
                if res.data:
                    reply = "✅ <b>Successfully Purchased Deals:</b>\n\n"
                    for item in res.data:
                        reply += f"• <a href='{item['url']}'>{item['title']}</a> - <b>${float(item['price']):,.2f} CAD</b>\n"
                else:
                    reply = "No purchased deals recorded yet."
            except Exception as e:
                reply = f"Error fetching purchased items: {e}"

            requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={
                "chat_id": chat_id, "text": reply, "parse_mode": "HTML", "disable_web_page_preview": True
            })

        elif text.startswith("/help") or text.startswith("/start"):
            help_text = (
                f"🤖 <b>Canadian Marketplace Deal Bot</b>\n\n"
                f"<b>Commands Menu:</b>\n"
                f"• /deals - View latest tracked listings\n"
                f"• /apple - Filter latest iPhone deals\n"
                f"• /samsung - Filter latest Samsung deals\n"
                f"• /pixel - Filter latest Pixel deals\n"
                f"• /watchlist - View active uncontacted items\n"
                f"• /contacted - View contacted listings\n"
                f"• /purchased - View bought devices\n"
                f"• /stats - View database counts\n"
                f"• /help - Show this menu"
            )
            requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={
                "chat_id": chat_id, "text": help_text, "parse_mode": "HTML"
            })

    return {"status": "ok"}