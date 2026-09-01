from fastapi import FastAPI, Request
from database import supabase
from tracker import process_scraped_data
import requests
import os
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

app = FastAPI()

@app.get("/")
async def health_check():
    return {"status": "Bot is awake and running!"}

@app.api_route("/webhook/apify", methods=["GET", "POST"])
async def apify_webhook(request: Request):
    if request.method == "GET":
        return {"status": "Apify webhook endpoint is active"}
        
    payload = await request.json()
    dataset_id = payload.get("resource", {}).get("defaultDatasetId")
    
    if dataset_id:
        dataset_url = f"https://api.apify.com/v2/datasets/{dataset_id}/items?clean=true"
        items = requests.get(dataset_url).json()
        process_scraped_data(items)
        
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