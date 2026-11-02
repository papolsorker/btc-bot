import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
import time
import requests
from datetime import datetime

# --- Render Web Service Port Binding ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b"Bot is alive and running!")

def run_dummy_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
    server.serve_forever()

threading.Thread(target=run_dummy_server, daemon=True).start()
# ---------------------------------------

# ----------------- কনফিগারেশন -----------------
BOT_TOKEN = "9031478970:AAEREznuQIuggHGG3IMa3Lp_Zxn62MtpmYg"
CHAT_ID = "8431903206"
SYMBOL = "BTCUSDT"
TIMEFRAME = "5m"

BINANCE_ENDPOINTS = [
    "https://api.binance.com",
    "https://api1.binance.com",
    "https://api2.binance.com",
    "https://api3.binance.com"
]
# ----------------------------------------------

def fetch_binance_data(endpoint_path):
    for base_url in BINANCE_ENDPOINTS:
        url = f"{base_url}{endpoint_path}"
        try:
            res = requests.get(url, timeout=12)
            if res.status_code == 200:
                return res.json()
        except requests.exceptions.RequestException:
            continue
    return None

def calculate_ema(prices, period):
    if len(prices) < period:
        return None
    multiplier = 2 / (period + 1)
    ema = [sum(prices[:period]) / period]
    for price in prices[period:]:
        ema.append((price - ema[-1]) * multiplier + ema[-1])
    return ema[-1]

def calculate_rsi(prices, period=14):
    if len(prices) < period + 1:
        return 50.0
    deltas = [prices[i+1] - prices[i] for i in range(len(prices)-1)]
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]
    
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))

def get_market_analysis(symbol="BTCUSDT"):
    try:
        kline_res = fetch_binance_data(f"/api/v3/klines?symbol={symbol}&interval={TIMEFRAME}&limit=50")
        if not kline_res:
            print("বাইনান্স ক্যান্ডেল ডেটা লোড হতে ব্যর্থ হয়েছে।")
            return None
        
        curr_k = kline_res[-1]
        prev_k = kline_res[-2]
        prev2_k = kline_res[-3]
        prev3_k = kline_res[-4]

        curr_open = float(curr_k[1])
        curr_price = float(curr_k[4])
        curr_vol = float(curr_k[5])

        prev_open = float(prev_k[1])
        prev_high = float(prev_k[2])
        prev_low = float(prev_k[3])
        prev_close = float(prev_k[4])

        prev2_open = float(prev2_k[1])
        prev2_close = float(prev2_k[4])

        prev3_open = float(prev3_k[1])
        prev3_close = float(prev3_k[4])

        close_prices = [float(k[4]) for k in kline_res]
        ema_9 = calculate_ema(close_prices, 9)
        ema_21 = calculate_ema(close_prices, 21)
        rsi = calculate_rsi(close_prices, 14)

        trades_res = fetch_binance_data(f"/api/v3/trades?symbol={symbol}&limit=500")
        if trades_res:
            buy_vol = sum([float(t['qty']) for t in trades_res if not t['isBuyerMaker']])
            sell_vol = sum([float(t['qty']) for t in trades_res if t['isBuyerMaker']])
            bs_ratio = (buy_vol / sell_vol) if sell_vol > 0 else 1.0
            delta = buy_vol - sell_vol
        else:
            bs_ratio = 1.0
            delta = 0.0

        depth_res = fetch_binance_data(f"/api/v3/depth?symbol={symbol}&limit=20")
        if depth_res:
            bid_vol = sum([float(b[1]) for b in depth_res.get('bids', [])])
            ask_vol = sum([float(a[1]) for a in depth_res.get('asks', [])])
            imbalance = ((bid_vol - ask_vol) / (bid_vol + ask_vol) * 100) if (bid_vol + ask_vol) > 0 else 0.0
        else:
            imbalance = 0.0

        detected_patterns = []
        bullish_score = 0
        bearish_score = 0

        prev_body = abs(prev_close - prev_open)
        prev_is_green = prev_close >= prev_open
        lower_wick = (prev_open - prev_low) if prev_is_green else (prev_close - prev_low)
        upper_wick = (prev_high - prev_close) if prev_is_green else (prev_high - prev_open)

        if lower_wick > (prev_body * 1.8) and lower_wick > upper_wick:
            bullish_score += 15
            detected_patterns.append("Hammer Rejection")
        elif upper_wick > (prev_body * 1.8) and upper_wick > lower_wick:
            bearish_score += 15
            detected_patterns.append("Shooting Star Rejection")

        prev2_is_green = prev2_close >= prev2_open
        prev3_is_green = prev3_close >= prev3_open

        if prev_is_green and prev2_is_green and prev3_is_green:
            bullish_score += 15
            detected_patterns.append("3-Bull Streak")
        elif not prev_is_green and not prev2_is_green and not prev3_is_green:
            bearish_score += 15
            detected_patterns.append("3-Bear Streak")
        elif prev_is_green and prev2_is_green:
            bullish_score += 8
        elif not prev_is_green and not prev2_is_green:
            bearish_score += 8

        curr_body = abs(curr_price - curr_open)
        curr_is_green = curr_price >= curr_open

        if curr_is_green and not prev_is_green and curr_body > prev_body and curr_price > prev_open:
            bullish_score += 20
            detected_patterns.append("Bullish Engulfing")
        elif not curr_is_green and prev_is_green and curr_body > prev_body and curr_price < prev_open:
            bearish_score += 20
            detected_patterns.append("Bearish Engulfing")

        past_volumes = [float(k[5]) for k in kline_res[-6:-1]]
        avg_vol = sum(past_volumes) / len(past_volumes) if past_volumes else 1.0
        projected_vol = curr_vol * 2.0

        if projected_vol > avg_vol * 1.25:
            if curr_is_green:
                bullish_score += 15
                detected_patterns.append("High Volume (Bullish)")
            else:
                bearish_score += 15
                detected_patterns.append("High Volume (Bearish)")

        if curr_price > curr_open:
            bullish_score += 15
        else:
            bearish_score += 15

        if ema_9 and ema_21:
            if ema_9 > ema_21:
                bullish_score += 15
            else:
                bearish_score += 15

        if 50 < rsi < 70:
            bullish_score += 15
        elif 30 < rsi <= 50:
            bearish_score += 15
        elif rsi >= 70:
            bearish_score += 10
        elif rsi <= 30:
            bullish_score += 10

        if bs_ratio >= 1.2 and delta > 0:
            bullish_score += 20
        elif bs_ratio <= 0.8 and delta < 0:
            bearish_score += 20
        else:
            bullish_score += 5
            bearish_score += 5

        if imbalance > 10:
            bullish_score += 10
        elif imbalance < -10:
            bearish_score += 10

        total_score = bullish_score + bearish_score
        bull_prob = round((bullish_score / total_score) * 100) if total_score > 0 else 50
        bear_prob = round((bearish_score / total_score) * 100) if total_score > 0 else 50

        if bull_prob >= 58:
            prediction = "🟢 CANDLE CLOSE: UP"
            confidence = f"{bull_prob}% Probability"
        elif bear_prob >= 58:
            prediction = "🔴 CANDLE CLOSE: DOWN"
            confidence = f"{bear_prob}% Probability"
        else:
            prediction = "⚠️ SIDEWAYS / CAUTION"
            confidence = f"Bull: {bull_prob}% | Bear: {bear_prob}%"

        pattern_summary = ", ".join(detected_patterns) if detected_patterns else "Normal Price Action"
        trend_status = "Bullish (EMA 9 Up)" if (ema_9 and ema_21 and ema_9 > ema_21) else "Bearish (EMA 9 Down)"

        return {
            "open_price": curr_open,
            "current_price": curr_price,
            "rsi": round(rsi, 1),
            "ema_trend": trend_status,
            "bs_ratio": round(bs_ratio, 2),
            "delta": round(delta, 4),
            "imbalance": round(imbalance, 2),
            "patterns": pattern_summary,
            "prev_status": "Bullish (Green)" if prev_is_green else "Bearish (Red)",
            "prediction": prediction,
            "confidence": confidence
        }
    except Exception as e:
        print(f"অ্যানালাইসিস ত্রুটি: {e}")
        return None

def send_telegram_message(data):
    if not data:
        print("পাঠানোর মতো কোনো ডেটা নেই।")
        return

    change_sign = "+" if data['current_price'] >= data['open_price'] else ""
    price_diff = data['current_price'] - data['open_price']

    text = (
        f"⏱️ 5M ADVANCED CANDLE SIGNAL\n"
        f"(At 2m 30s Mark)\n\n"
        f"⏰ Time: {datetime.now().strftime('%H:%M:%S')}\n"
        f"💵 Candle Open: \${data['open_price']:,.2f}\n"
        f"📊 Mid-Candle: \${data['current_price']:,.2f} ({change_sign}{price_diff:,.2f})\n"
        f"🕯️ Prev Candle: {data['prev_status']}\n"
        f"🔍 Patterns: {data['patterns']}\n"
        f"📈 Trend: {data['ema_trend']}\n"
        f"⚡ RSI: {data['rsi']}\n"
        f"🔄 Buy/Sell Ratio: {data['bs_ratio']}\n"
        f"📦 Volume Delta: {data['delta']:+} BTC\n"
        f"🧱 Depth Imbalance: {data['imbalance']:+}%\n\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"👉 {data['prediction']}\n"
        f"🎯 Confidence: {data['confidence']}\n"
        f"⏳ Time Remaining: ২ মিনিট ৩০ সেকেন্ড বাকি\n"
        f"━━━━━━━━━━━━━━━━━━━"
    )

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": text}
    try:
        res = requests.post(url, json=payload, timeout=10)
        if res.status_code == 200:
            print("টেলিগ্রামে মেসেজ সফলভাবে পৌঁছেছে!")
        else:
            print(f"টেলিগ্রাম এরর: {res.text}")
    except Exception as e:
        print(f"মেসেজ পাঠাতে সমস্যা: {e}")

def wait_for_target_time():
    current_time = time.time()
    current_candle_start = (int(current_time) // 300) * 30
