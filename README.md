# DropHunter

This is a personal fun project so as to make my life easier when I buy games. The idea is to give the Bot some games to track and notify when the price is at the lowest. 
It will be a Python-powered AI assistant that helps gamers make smarter purchase decisions by tracking game prices and providing buy recommendations. It integrates the [IsThereAnyDeal API](https://isthereanydeal.com/) to fetch the latest game details, pricing history, and discounts. It also supports AI-driven real-time query handling via Groq function calling, and delivers notifications via Telegram or Discord bots.

---

## 🔧 Features

- 🏷️ Fetch historical and current game pricing using IsThereAnyDeal API
- 🤖 AI-based function calling with Groq for real-time game data
- 📈 Intelligent buy recommendations based on price history trends
- ⏰ Scheduled as a GitHub Actions cron job for daily or periodic checks
- 📲 Sends deal notifications and user-triggered queries via Telegram or Discord

---

## 🧠 Architecture Overview

- **Backend:** Python
- **Scheduler:** GitHub Actions (Cron)
- **APIs Used:**
  - [IsThereAnyDeal API](https://isthereanydeal.com/)
  - [Groq API](https://groq.com/)
- **Notifications:** Telegram Bot or Discord Webhook/Bot
- **AI Functions:** Function calling to get live pricing or recommendations

---

## 🗂 Project Structure (Planned)

├── bot/ # Telegram/Discord bot integration
├── cron/ # GitHub cron job scripts
├── ai/ # Groq function-calling setup
├── data/ # Game metadata, logs, etc.
├── utils/ # Helper functions for API requests and processing
├── main.py # Main entry script
├── requirements.txt
└── README.md

