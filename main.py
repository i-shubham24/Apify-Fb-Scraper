from fastapi import FastAPI, Request
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
async def apify_webhook(request: Request):
    if request.method == "GET":
        return {"status": "Apify webhook endpoint is active"}
        
    payload = await request.json()
    print(f"Webhook payload received: {payload}")
    
    dataset_id = payload.get("resource", {}).get("defaultDatasetId")
    
    if dataset_id:
        dataset_url = f"https://api.apify.com/v2/datasets/{dataset_id}/items?clean=true"
        
        # Apply the token to the request headers to fix the 403 Permission Error
        headers = {}
        if APIFY_API_TOKEN:
            headers["Authorization"] = f"Bearer {APIFY_API_TOKEN}"
        else:
            print("WARNING: APIFY_API_TOKEN is not set in environment variables.")
            
        response = requests.get(dataset_url, headers=headers)
        print(f"Apify Dataset Status: {response.status_code}")
        
        try:
            items = response.json()
            if isinstance(items, list):
                print(f"Processing {len(items)} items received from Apify.")
                process_scraped_data(items)
            else:
                print(f"Apify returned a non-list response: {items}")
        except Exception as e:
            print(f"Failed to parse dataset JSON: {e}")
        
    return {"status": "ok"}

@app.post("/webhook/telegram")
async def telegram_webhook(request: Request):
    data = await request.json()

    if "callback_query" in data:
        callback = data["callback_query"]
        callback_id = callback["id"]
        callback_data = callback["data"]

        _, new_status, listing_id = callback_data.split(":")

        supabase.table("listings").update({"status": new_status}).eq("id", listing_id).execute()

        ack_url = f"https://api.telegram.org/bot{TOKEN}/answerCallbackQuery"
        requests.post(ack_url, json={"callback_query_id": callback_id, "text": f"Status updated to {new_status}"})

    return {"status": "ok"}