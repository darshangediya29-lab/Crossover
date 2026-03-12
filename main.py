import os
import time
import requests
import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(message)s',
    datefmt='%H:%M:%S'
)
log = logging.getLogger(__name__)

# ── Config from environment variables ──────────────────
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
# Multiple chat IDs supported — comma separated e.g. "111111,222222,-100333333"
CHAT_IDS  = [cid.strip() for cid in os.environ.get("CHAT_ID", "").split(",") if cid.strip()]
INTERVAL  = int(os.environ.get("SCAN_INTERVAL", "120").split()[0])  # seconds
COOLDOWN  = int(os.environ.get("ALERT_COOLDOWN", "1800").split()[0])  # seconds

BINANCE   = "https://api.binance.com/api/v3"
BATCH     = 10

alerted_map = {}  # key -> timestamp

# ── Helpers ─────────────────────────────────────────────
def fmt_price(p):
    if p >= 1000: return f"{p:.2f}"
    if p >= 1:    return f"{p:.4f}"
    if p >= 0.01: return f"{p:.5f}"
    return f"{p:.8f}"

def calc_sma(arr, period):
    if len(arr) < period:
        return None
    return sum(arr[-period:]) / period

def send_telegram(text):
    if not CHAT_IDS:
        log.error("No CHAT_ID configured")
        return False
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    success_count = 0
    for cid in CHAT_IDS:
        try:
            r = requests.post(url, json={"chat_id": cid, "text": text, "parse_mode": "HTML"}, timeout=10)
            d = r.json()
            if d.get("ok"):
                success_count += 1
            else:
                log.error(f"Telegram error (chat {cid}): {d.get('description')}")
        except Exception as e:
            log.error(f"Telegram send failed (chat {cid}): {e}")
        time.sleep(0.1)  # small gap between recipients
    return success_count > 0

# ── Get top 500 USDT pairs ───────────────────────────────
def get_top_pairs(limit=500):
    try:
        r = requests.get(f"{BINANCE}/ticker/24hr", timeout=15)
        data = r.json()
        filtered = [
            t for t in data
            if t["symbol"].endswith("USDT")
            and not any(x in t["symbol"].replace("USDT","") for x in ["UP","DOWN","BULL","BEAR","3L","3S","5L","5S"])
        ]
        filtered.sort(key=lambda x: float(x["quoteVolume"]), reverse=True)
        return [t["symbol"] for t in filtered[:limit]]
    except Exception as e:
        log.error(f"Failed to get pairs: {e}")
        return []

# ── Analyze one symbol on given interval ─────────────────
def analyze(symbol, interval="1m"):
    try:
        r = requests.get(
            f"{BINANCE}/klines",
            params={"symbol": symbol, "interval": interval, "limit": 215},
            timeout=10
        )
        klines = r.json()
        if not isinstance(klines, list) or len(klines) < 202:
            return None

        opens  = [float(k[1]) for k in klines]
        highs  = [float(k[2]) for k in klines]
        lows   = [float(k[3]) for k in klines]
        closes = [float(k[4]) for k in klines]
        hlc4   = [(opens[i]+highs[i]+lows[i]+closes[i])/4 for i in range(len(klines))]

        n = len(hlc4)
        sma50     = calc_sma(hlc4, 50)
        sma200    = calc_sma(hlc4, 200)
        sma50high = calc_sma(highs, 50)
        if not sma50 or not sma200 or not sma50high:
            return None

        # Check last 2 candles — covers timing gap between scans
        idx = n - 2  # second last (just closed candle)
        if idx < 200:
            return None

        # Check ago=1 and ago=2 to avoid missing signals between scan cycles
        signal = None
        ago_found = 0
        for back in [1, 2]:
            check_idx = n - 1 - back
            if check_idx < 200:
                break
            s50_curr  = calc_sma(hlc4[:check_idx+1], 50)
            s200_curr = calc_sma(hlc4[:check_idx+1], 200)
            s50_prev  = calc_sma(hlc4[:check_idx], 50)
            s200_prev = calc_sma(hlc4[:check_idx], 200)
            if not s50_curr or not s200_curr or not s50_prev or not s200_prev:
                continue
            if s50_prev <= s200_prev and s50_curr > s200_curr:
                signal = "BULLISH"; ago_found = back; break
            elif s50_prev >= s200_prev and s50_curr < s200_curr:
                signal = "BEARISH"; ago_found = back; break

        if not signal:
            return None

        current_price = closes[-1]
        dist = abs(current_price - sma50high) / sma50high * 100
        is_pullback = 0.05 <= dist <= 0.2

        return {
            "sym": symbol.replace("USDT", ""),
            "price": current_price,
            "sma50": sma50,
            "sma200": sma200,
            "sma50high": sma50high,
            "signal": signal,
            "ago": ago_found,
            "is_pullback": is_pullback,
            "dist": dist,
            "interval": interval,
        }
    except Exception as e:
        log.debug(f"Error analyzing {symbol}: {e}")
        return None

# ── One scan cycle ───────────────────────────────────────
def scan_once():
    log.info("Starting scan...")
    pairs = get_top_pairs(100)
    if not pairs:
        log.warning("No pairs fetched, skipping.")
        return

    crossovers = 0
    alerts_sent = 0
    now = time.time()

    for interval in ["1m", "15m"]:
        log.info(f"Scanning {interval}...")
        for i in range(0, len(pairs), BATCH):
            batch = pairs[i:i+BATCH]
            for sym in batch:
                result = analyze(sym, interval)
                if not result:
                    continue

                crossovers += 1
                # cooldown key includes interval so 1m and 15m alerts are independent
                key = f"{result['sym']}_{result['signal']}_{interval}"

                # Cooldown check
                if key in alerted_map and now - alerted_map[key] < COOLDOWN:
                    continue

                alerted_map[key] = now
                alerts_sent += 1

                emoji  = "🟢" if result["signal"] == "BULLISH" else "🔴"
                label  = "GOLDEN CROSS ↑" if result["signal"] == "BULLISH" else "DEATH CROSS ↓"
                pb_tag = "\n⚡ <b>Pullback Setup!</b> Price near SMA50 High" if result["is_pullback"] else ""

                msg = (
                    f"{emoji} <b>{result['sym']}/USDT</b>\n"
                    f"Signal: <b>{label}</b>\n"
                    f"Price: <b>${fmt_price(result['price'])}</b>\n"
                    f"SMA50 (HLC4): {fmt_price(result['sma50'])}\n"
                    f"SMA200 (HLC4): {fmt_price(result['sma200'])}\n"
                    f"SMA50 High: {fmt_price(result['sma50high'])}\n"
                    f"Timeframe: {interval}\n"
                    f"Time: {datetime.utcnow().strftime('%H:%M:%S')} UTC"
                    f"{pb_tag}\n"
                    f"#cryptoscreener"
                )
                success = send_telegram(msg)
                if success:
                    log.info(f"Alert sent: {result['sym']} {result['signal']} {interval}")
                time.sleep(0.3)  # Telegram rate limit

            time.sleep(0.05)  # Binance rate limit between batches

    log.info(f"Scan done — {len(pairs)} pairs, {crossovers} crossovers, {alerts_sent} alerts sent")

# ── Main loop ────────────────────────────────────────────
def main():
    if not BOT_TOKEN or not CHAT_IDS:
        log.error("BOT_TOKEN and CHAT_ID environment variables are required!")
        return

    log.info(f"🚀 Crypto Screener started | Interval: {INTERVAL}s | Cooldown: {COOLDOWN}s | Recipients: {len(CHAT_IDS)}")
    send_telegram(
        f"🚀 <b>Crypto Screener Started!</b>\n"
        f"Scanning top 500 pairs on 1m\n"
        f"Interval: every {INTERVAL//60} min\n"
        f"Cooldown: {COOLDOWN//60} min per coin"
    )

    while True:
        try:
            scan_once()
        except Exception as e:
            log.error(f"Scan loop error: {e}")
            send_telegram(f"⚠️ Scanner error: {e}\nWill retry in {INTERVAL}s")

        log.info(f"Sleeping {INTERVAL}s...")
        time.sleep(INTERVAL)

if __name__ == "__main__":
    main()
