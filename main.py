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

    # Handle inline button clicks (Callback Queries)
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

            # Handle Automated Seller Message Generator
            if callback_data.startswith("offer:"):
                _, listing_id = callback_data.split(":")
                res = supabase.table("listings").select("title, price").eq("id", listing_id).execute()
                if res.data:
                    item = res.data[0]
                    offer_text = f"Hi! Is this {item['title']} still available? Can you do ${float(item['price'])-20:,.0f} cash pickup today?"
                else:
                    offer_text = "Hi! Is this still available? Can you do cash pickup today?"

                requests.post(f"https://api.telegram.org/bot{TOKEN}/answerCallbackQuery", json={
                    "callback_query_id": callback_id, 
                    "text": "Offer template generated!"
                })
                # Send the copy-pasteable offer text back to the chat
                requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={
                    "chat_id": chat_id,
                    "text": f"📋 <b>Quick Offer Template (Tap to copy):</b>\n\n<code>{offer_text}</code>",
                    "parse_mode": "HTML"
                })
                return {"status": "ok"}

            # Handle Status Updates (Contacted / Purchased)
            _, new_status, listing_id = callback_data.split(":")
            supabase.table("listings").update({"status": new_status}).eq("id", listing_id).execute()

            requests.post(f"https://api.telegram.org/bot{TOKEN}/answerCallbackQuery", json={
                "callback_query_id": callback_id, 
                "text": f"Status updated to {new_status}!"
            })

            # Rebuild keyboard without action buttons, locking the current status
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

    # Handle Interactive Telegram Commands sent in chat text
    elif "message" in data:
        message = data["message"]
        chat_id = message.get("chat", {}).get("id")
        text = message.get("text", "").strip()

        if text.startswith("/stats"):
            try:
                total = supabase.table("listings").select("id", count="exact").execute().count or 0
                contacted = supabase.table("listings").select("id", count="exact").eq("status", "CONTACTED").execute().count or 0
                purchased = supabase.table("listings").select("id", count="exact").eq("status", "PURCHASED").execute().count or 0

                reply = (
                    f"📊 <b>Market Bot Statistics</b>\n\n"
                    f"📱 Total Tracked Listings: {total}\n"
                    f"💬 Contacted Sellers: {contacted}\n"
                    f"✅ Successfully Purchased: {purchased}"
                )
            except Exception as e:
                reply = f"Could not retrieve stats: {e}"

            requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={
                "chat_id": chat_id,
                "text": reply,
                "parse_mode": "HTML"
            })

        elif text.startswith("/help") or text.startswith("/start"):
            help_text = (
                f"🤖 <b>Canadian Marketplace Deal Bot</b>\n\n"
                f"Commands:\n"
                f"• /stats - View database pipeline statistics\n"
                f"• /help - Show this help menu\n\n"
                f"Deal alerts arrive automatically with AI Deal Scores and thumbnail previews!"
            )
            requests.post(f"https://api.telegram.org/bot{TOKEN}/sendMessage", json={
                "chat_id": chat_id,
                "text": help_text,
                "parse_mode": "HTML"
            })

    return {"status": "ok"}