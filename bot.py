import os
import requests
import pandas as pd
import yfinance as yf
from datetime import datetime
import json
import matplotlib.pyplot as plt

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

PAIRS = {
    "GOLD": {"ticker": "XAUUSD=X", "risk": 1.0},
    "USDJPY": {"ticker": "JPY=X", "risk": 0.7}
}

R_MULTIPLIER = 1.7
SESSION_ALERT_FILE = "session_alert.json"
STATS_FILE = "stats.json"

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message}
    requests.post(url, data=payload)

def get_session():
    now = datetime.utcnow().hour
    if 6 <= now < 12:
        return "London"
    elif 12 <= now < 21:
        return "New York"
    else:
        return "Asia"

def session_already_alerted(session):
    if not os.path.exists(SESSION_ALERT_FILE):
        return False
    with open(SESSION_ALERT_FILE, "r") as f:
        data = json.load(f)
    return data.get("session") == session

def save_session(session):
    with open(SESSION_ALERT_FILE, "w") as f:
        json.dump({"session": session}, f)

def load_stats():
    if not os.path.exists(STATS_FILE):
        return {"balance": 10000, "wins": 0, "losses": 0, "streak_loss": 0, "equity": [10000]}
    with open(STATS_FILE, "r") as f:
        return json.load(f)

def generate_signal(df):
    df["ema_fast"] = df["Close"].ewm(span=20).mean()
    df["ema_slow"] = df["Close"].ewm(span=50).mean()
    if df["ema_fast"].iloc[-1] > df["ema_slow"].iloc[-1]:
        return "BUY"
    elif df["ema_fast"].iloc[-1] < df["ema_slow"].iloc[-1]:
        return "SELL"
    return None

def correlation_block(pair, signal, open_positions):
    if pair == "GOLD" and "USDJPY" in open_positions:
        if open_positions["USDJPY"] == signal:
            return True
    if pair == "USDJPY" and "GOLD" in open_positions:
        if open_positions["GOLD"] == signal:
            return True
    return False

def run():
    session = get_session()
    if session_already_alerted(session):
        return
    stats = load_stats()
    open_positions = {}
    for pair, config in PAIRS.items():
        df = yf.download(config["ticker"], period="5d", interval="15m")
        if df.empty:
            continue
        signal = generate_signal(df)
        if not signal:
            continue
        if correlation_block(pair, signal, open_positions):
            continue
        price = df["Close"].iloc[-1]
        sl = price * 0.998 if signal == "BUY" else price * 1.002
        tp = price + (price - sl) * R_MULTIPLIER if signal == "BUY" else price - (sl - price) * R_MULTIPLIER
        risk = config["risk"]
        if stats["streak_loss"] >= 2:
            risk = risk / 2
        message = f"""
══════════════════════════
EXECUTION NOTICE
══════════════════════════
Instrument   : {pair}
Session      : {session}
Direction    : {signal}
Entry Price  : {price:.3f}
Stop Loss    : {sl:.3f}
Take Profit  : {tp:.3f}
Risk per Trade : {risk:.2f}%
R-Multiple     : 1 : {R_MULTIPLIER}
Position Mode  : {"Reduced" if stats["streak_loss"] >= 2 else "Normal"}
Timestamp (UTC): {datetime.utcnow()}
══════════════════════════
"""
        send_telegram(message)
        open_positions[pair] = signal
    save_session(session)

if __name__ == "__main__":
    run()
