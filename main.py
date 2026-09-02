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
    return {"status": "Bot is awake and running!"}

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
                # Run in background to prevent Render from timing out the webhook
                background_tasks.add_task(process_scraped_data, items)
            else:
                print(f"Apify returned a non-list response: {items}")
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
            # Ignore clicks on the disabled status button
            if callback_data == "none":
                requests.post(f"https://api.telegram.org/bot{TOKEN}/answerCallbackQuery", json={"callback_query_id": callback_id})
                return {"status": "ok"}

            _, new_status, listing_id = callback_data.split(":")

            # 1. Update database
            supabase.table("listings").update({"status": new_status}).eq("id", listing_id).execute()

            # 2. Acknowledge the callback immediately to stop the loading spinner
            requests.post(f"https://api.telegram.org/bot{TOKEN}/answerCallbackQuery", json={
                "callback_query_id": callback_id, 
                "text": f"Status updated to {new_status}!"
            })

            # 3. Dynamically update the Telegram UI buttons on the card
            listing_url = message.get("reply_markup", {}).get("inline_keyboard", [[{}]])[0][0].get("url", "")
            
            updated_keyboard = {
                "inline_keyboard": [
                    [{"text": "🔗 View Listing", "url": listing_url}],
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
            requests.post(f"https://api.telegram.org/bot{TOKEN}/answerCallbackQuery", json={
                "callback_query_id": callback_id, "text": "Error updating status."
            })

    return {"status": "ok"}