import os
import requests
import pandas as pd
import yfinance as yf
from datetime import datetime
import json

# ==============================
# CONFIG
# ==============================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

PAIRS = {
    "GOLD": {"ticker": "XAUUSD=X", "risk": 1.0},
    "USDJPY": {"ticker": "JPY=X", "risk": 0.7},
    "BTCUSD": {"ticker": "BTC-USD", "risk": 1.2},
    "ETHUSD": {"ticker": "ETH-USD", "risk": 1.2}
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

def session_already_alerted(session):
    if not os.path.exists(SESSION_ALERT_FILE):
        return False
    with open(SESSION_ALERT_FILE, "r") as f:
        data = json.load(f)
    return data.get("session") == session

def save_session(session):
    with open(SESSION_ALERT_FILE, "w") as f:
        json.dump({"session": session}, f)

# ==============================
# STATS SYSTEM
# ==============================
def load_stats():
    if not os.path.exists(STATS_FILE):
        return {"balance":10000, "wins":0, "losses":0, "streak_loss":0, "equity":[10000]}
    with open(STATS_FILE, "r") as f:
        return json.load(f)

def save_stats(stats):
    with open(STATS_FILE, "w") as f:
        json.dump(stats, f)

# ==============================
# EQUITY CURVE
# ==============================
def generate_equity_curve(stats):
    import matplotlib.pyplot as plt
    plt.figure()
    plt.plot(stats["equity"])
    plt.title("Equity Curve")
    plt.xlabel("Trades")
    plt.ylabel("Balance")
    plt.savefig("equity.png")
    plt.close()

# ==============================
# SIGNAL LOGIC (EMA CROSS)
# ==============================
def generate_signal(df):
    df["ema20"] = df["Close"].ewm(span=20).mean()
    df["ema50"] = df["Close"].ewm(span=50).mean()
    if df["ema20"].iloc[-1] > df["ema50"].iloc[-1]:
        return "BUY"
    elif df["ema20"].iloc[-1] < df["ema50"].iloc[-1]:
        return "SELL"
    return None

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
# ALERT CANDLE TERAKHIR
# ==============================
def send_last_candle_status(pair, df):
    last = df.iloc[-1]
    message = f"""
══════════════════════════
BOT STATUS ALERT
══════════════════════════

Instrument   : {pair}
Last Candle  : {last.name} (UTC)
Open         : {last['Open']:.3f}
High         : {last['High']:.3f}
Low          : {last['Low']:.3f}
Close        : {last['Close']:.3f}

Bot Status   : ACTIVE
══════════════════════════
"""
    send_telegram(message)

# ==============================
# MAIN ENGINE
# ==============================
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

        # Kirim alert candle terakhir untuk tahu bot aktif
        send_last_candle_status(pair, df)

        signal = generate_signal(df)
        if not signal:
            continue

        # Filter korelasi GOLD & USDJPY
        if correlation_block(pair, signal, open_positions):
            continue

        price = df["Close"].iloc[-1]
        sl = price * 0.998 if signal == "BUY" else price * 1.002
        tp = price + (price - sl) * R_MULTIPLIER if signal == "BUY" else price - (sl - price) * R_MULTIPLIER

        risk = config["risk"]
        if stats["streak_loss"] >= 2:
            risk /= 2

        message = f"""
══════════════════════════
EXECUTION NOTICE
══════════════════════════

Instrument   : {pair}
Session      : {session}
Strategy     : Volatility Expansion (A+)

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

# ==============================
# RUN
# ==============================
if __name__ == "__main__":
    run()
