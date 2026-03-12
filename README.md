# Crypto Screener Bot — Railway Deploy Guide

## Files
- `main.py` — Main bot script
- `requirements.txt` — Python dependencies
- `Procfile` — Process definition
- `railway.json` — Railway config

---

## Deploy Steps (Railway — Free, 24/7)

### Step 1 — GitHub pe upload karo
1. GitHub.com pe jaao → New repository banao → naam: `crypto-screener-bot`
2. Yeh saare files upload karo (main.py, requirements.txt, Procfile, railway.json)

### Step 2 — Railway pe deploy karo
1. railway.app pe jaao → **Login with GitHub**
2. **New Project** → **Deploy from GitHub repo** → apna repo select karo
3. Deploy automatically shuru ho jaayega

### Step 3 — Environment Variables set karo (IMPORTANT)
Railway dashboard me jaao → apna project → **Variables** tab → Add karo:

| Variable       | Value                        |
|----------------|------------------------------|
| BOT_TOKEN      | `1234567890:ABCdef...`       |
| CHAT_ID        | `123456789`                  |
| SCAN_INTERVAL  | `120`  (2 min, change karo)  |
| ALERT_COOLDOWN | `1800` (30 min cooldown)     |

### Step 4 — Done!
- **Deploy** tab me logs dikhenge
- Telegram pe startup message aayega: "🚀 Crypto Screener Started!"
- Har 2 minute me 1m scan hoga — PC band ho toh bhi!

---

## Notes
- Railway free tier: 500 hours/month (enough for 24/7)
- Bot automatically restart hoga agar crash ho
- SCAN_INTERVAL kam karo = zyada frequent alerts (minimum 60 recommended)
- ALERT_COOLDOWN = same coin ka dobara alert kitne seconds baad (1800 = 30 min)
