# 📱 Marketplace AI Deal Hunter & Price Tracker

An automated end-to-end pipeline designed to monitor Facebook Marketplace listings in real time, filter out scams using Google Gemini, track historical price drops, and deliver interactive alerts directly to Telegram.

---

## ⚡ Features

- **Automated Web Scraping:** Scheduled and targeted Facebook Marketplace scraping using Apify actors.
- **AI-Powered Scam & Spec Analysis:** Evaluates listing titles and descriptions using the Gemini API to detect fake/replica listings, battery health, storage capacity, and cosmetic condition.
- **Price History & Drop Detection:** Persists unique listings in Supabase and triggers instant discount alerts when a seller drops their price.
- **Interactive Telegram UI:** Delivers formatted deal cards equipped with inline callback buttons to update listing statuses (`CONTACTED`, `PURCHASED`) in real time.
- **Fault-Tolerant Background Processing:** Built with FastAPI `BackgroundTasks` to handle webhooks asynchronously, bypass server timeouts, and prevent API rate-limit bottlenecks.

---

## 🛠️ Tech Stack

- **Scraper:** Apify (Facebook Marketplace Scraper Actor)
- **Backend:** FastAPI (Uvicorn) deployed on Render
- **Database:** Supabase (PostgreSQL)
- **AI / LLM:** Google Gemini API
- **Notifications & UI:** Telegram Bot API (Webhooks & Inline Keyboards)
