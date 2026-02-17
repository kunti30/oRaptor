import os
import requests
import pandas as pd
import yfinance as yf
import pytz
from datetime import datetime
import json
import matplotlib.pyplot as plt

# ==============================
# CONFIG
# ==============================

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

PAIRS = {
    "GOLD": {"ticker": "XAUUSD=X", "risk": 1.0},
    "USDJPY": {"ticker": "JPY=X", "risk": 0.7},
    "BTC": {"ticker": "BTC-USD", "risk": 1.0},
    "ETH": {"ticker": "ETH-USD", "risk": 0.8}
}

R_MULTIPLIER = 1.7
SESSION_ALERT_FILE = "session_alert.json"
STATS_FILE = "stats.json"

# ==============================
# TELEGRAM FUNCTION
# ==============================

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message}
    requests.post(url, data=payload)

# ==============================
# SESSION CONTROL
# ==============================

def get_session():
    now = datetime.utcnow().hour
    if 6 <= now < 12:
        return "London"
    elif 12 <= now < 21:
        return "New York"
    else:
        return "Asia"

def session_already_alerted(pair, session):
    if not os.path.exists(SESSION_ALERT_FILE):
        return False
    with open(SESSION_ALERT_FILE, "r") as f:
        data = json.load(f)
    return data.get(pair) == session

def save_session(pair, session):
    if os.path.exists(SESSION_ALERT_FILE):
        with open(SESSION_ALERT_FILE, "r") as f:
            data = json.load(f)
    else:
        data = {}
    data[pair] = session
    with open(SESSION_ALERT_FILE, "w") as f:
        json.dump(data, f)

# ==============================
# STATS SYSTEM
# ==============================

def load_stats():
    if not os.path.exists(STATS_FILE):
        return {"balance": 10000, "wins":0, "losses":0, "streak_loss":0, "equity":[10000]}
    with open(STATS_FILE, "r") as f:
        return json.load(f)

def save_stats(stats):
    with open(STATS_FILE, "w") as f:
        json.dump(stats, f)

# ==============================
# SIGNAL LOGIC
# ==============================

def generate_signal(df, pair):
    df["ema_fast"] = df["Close"].ewm(span=20).mean()
    df["ema_slow"] = df["Close"].ewm(span=50).mean()
    signal = None

    # EMA crossover
    if df["ema_fast"].iloc[-1] > df["ema_slow"].iloc[-1]:
        signal = "BUY"
    elif df["ema_fast"].iloc[-1] < df["ema_slow"].iloc[-1]:
        signal = "SELL"

    # Crypto filter
    if pair in ["BTC", "ETH"] and signal:
        last_close = df["Close"].iloc[-1]
        prev_close = df["Close"].iloc[-2]
        body_pct = abs(last_close - prev_close) / prev_close * 100
        rsi = pd.Series(df["Close"]).diff().fillna(0).rolling(14).apply(lambda x: (x[x>0].sum()/(abs(x).sum()+1e-9))*100).iloc[-1]

        if body_pct < 0.5:  # candle terlalu kecil → abaikan
            signal = None
        elif signal=="BUY" and rsi < 60:  # momentum tidak cukup
            signal = None
        elif signal=="SELL" and rsi > 40:
            signal = None

    return signal

# ==============================
# CORRELATION FILTER GOLD/USDJPY
# ==============================

def correlation_block(pair, signal, open_positions):
    if pair == "GOLD" and "USDJPY" in open_positions:
        if open_positions["USDJPY"] == signal:
            return True
    if pair == "USDJPY" and "GOLD" in open_positions:
        if open_positions["GOLD"] == signal:
            return True
    return False

# ==============================
# MAIN ENGINE
# ==============================

def run():
    session = get_session()
    stats = load_stats()
    open_positions = {}

    for pair, config in PAIRS.items():
        # Session alert check
        if session_already_alerted(pair, session):
            continue

        df = yf.download(config["ticker"], period="5d", interval="15m")
        if df.empty:
            continue

        signal = generate_signal(df, pair)
        if not signal:
            continue

        # Correlation filter only for GOLD/USDJPY
        if correlation_block(pair, signal, open_positions):
            continue

        price = df["Close"].iloc[-1]
        sl = price * 0.998 if signal=="BUY" else price*1.002
        tp = price + (price - sl)*R_MULTIPLIER if signal=="BUY" else price - (sl - price)*R_MULTIPLIER

        risk = config["risk"]
        if stats["streak_loss"] >= 2:
            risk /= 2

        # Telegram institutional style
        message = f"""
══════════════════════════
EXECUTION NOTICE
══════════════════════════

Instrument   : {pair}
Session      : {session}
Strategy     : {"Volatility Expansion (A+)" if pair in ['GOLD','USDJPY'] else "Crypto Momentum (A+)"}

Direction    : {signal}
Entry Price  : {price:.2f}
Stop Loss    : {sl:.2f}
Take Profit  : {tp:.2f}

Risk per Trade : {risk:.2f}%
R-Multiple     : 1 : {R_MULTIPLIER}
Position Mode  : {"Reduced" if stats["streak_loss"] >= 2 else "Normal"}

Timestamp (UTC): {datetime.utcnow()}
══════════════════════════
"""
        send_telegram(message)
        open_positions[pair] = signal
        save_session(pair, session)

# ==============================
# RUN
# ==============================

if __name__ == "__main__":
    run()
