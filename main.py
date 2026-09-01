from fastapi import FastAPI, Request
from tracker import process_scraped_data
from database import init_db
import sqlite3
import requests
import os
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

app = FastAPI()

@app.on_event("startup")
def startup_event():
    init_db()

@app.post("/webhook/apify")
async def apify_webhook(request: Request):
    payload = await request.json()
    dataset_id = payload.get("resource", {}).get("defaultDatasetId")
    
    if dataset_id:
        # Fetch the actual items from Apify
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
        callback_data = callback["data"]  # e.g., "status:CONTACTED:12345"

        _, new_status, listing_id = callback_data.split(":")

        conn = sqlite3.connect("marketplace.db")
        cursor = conn.cursor()
        cursor.execute("UPDATE listings SET status = ? WHERE id = ?", (new_status, listing_id))
        conn.commit()
        conn.close()

        # Acknowledge in Telegram UI
        ack_url = f"https://api.telegram.org/bot{TOKEN}/answerCallbackQuery"
        requests.post(ack_url, json={"callback_query_id": callback_id, "text": f"Status updated to {new_status}"})

    return {"status": "ok"}