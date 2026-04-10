from flask import Flask, jsonify
import threading, time, requests, pandas as pd

app = Flask(__name__)

# CONFIG
SYMBOLS = ["BTCUSDT","ETHUSDT","SOLUSDT"]
BALANCE = 5000
RISK = 0.0075
MAX_POS = 3
RR = 2

state = {
    "balance": BALANCE,
    "positions": [],
    "logs": []
}

def log(msg):
    print(msg)
    state["logs"].insert(0, msg)
    state["logs"] = state["logs"][:50]

def get_klines(symbol, interval):
    try:
        r = requests.get("https://api.binance.com/api/v3/klines",
                         params={"symbol":symbol,"interval":interval,"limit":200}, timeout=10)
        df = pd.DataFrame(r.json())
        df = df[[1,2,3,4]]
        df.columns = ["open","high","low","close"]
        return df.astype(float)
    except:
        return None

def ema(series, n):
    return series.ewm(span=n).mean()

def run_bot():
    while True:
        prices = {}

        for sym in SYMBOLS:
            df1h = get_klines(sym,"1h")
            df4h = get_klines(sym,"4h")

            if df1h is None or df4h is None:
                continue

            df1h["ema50"] = ema(df1h["close"],50)
            df4h["ema50"] = ema(df4h["close"],50)
            df4h["ema200"] = ema(df4h["close"],200)

            df1h["high_roll"] = df1h["high"].rolling(20).max()
            df1h["atr"] = (df1h["high"]-df1h["low"]).rolling(14).mean()

            row1 = df1h.iloc[-1]
            row4 = df4h.iloc[-1]

            price = row1["close"]
            prices[sym] = price

            if not (row4["ema50"] > row4["ema200"] and price > row4["ema50"]):
                continue

            prev_high = df1h["high_roll"].iloc[-2]

            if (price - row1["ema50"]) > row1["atr"] * 1.2:
                continue

            if price > prev_high and len(state["positions"]) < MAX_POS:

                entry = price
                stop = price - row1["atr"]
                tp = entry + (entry-stop)*RR

                risk_amt = state["balance"] * RISK
                size = risk_amt/(entry-stop) if entry>stop else 0

                if size <= 0:
                    continue

                state["positions"].append({
                    "symbol": sym,
                    "entry": entry,
                    "stop": stop,
                    "tp": tp,
                    "size": size
                })

                log(f"🚀 OPEN {sym} @ {round(entry,2)}")

        closed = []
        for p in state["positions"]:
            price = prices.get(p["symbol"], p["entry"])

            if price <= p["stop"] or price >= p["tp"]:
                pnl = (price - p["entry"]) * p["size"]
                state["balance"] += pnl
                log(f"❌ CLOSE {p['symbol']} PnL {round(pnl,2)}")
                closed.append(p)

        for c in closed:
            state["positions"].remove(c)

        time.sleep(10)


@app.route("/")
def home():
    return """
    <html>
    <head>
    <style>
    body { background:#111;color:#eee;font-family:Arial;padding:20px }
    .card {border:1px solid #333;padding:15px;margin:10px}
    </style>
    </head>
    <body>

    <h1>📊 Trading Bot</h1>

    <div class="card">
    Balance: <span id="balance"></span><br>
    Positions: <span id="pos"></span>
    </div>

    <div class="card">
    <h3>Logs</h3>
    <div id="logs"></div>
    </div>

    <script>
    async function update(){
        let r = await fetch('/data');
        let d = await r.json();

        document.getElementById('balance').innerText = d.balance.toFixed(2);
        document.getElementById('pos').innerText = d.positions.length;

        document.getElementById('logs').innerHTML =
            d.logs.map(x=>"<div>"+x+"</div>").join("");
    }

    setInterval(update,2000);
    </script>

    </body>
    </html>
    """

@app.route("/data")
def data():
    return jsonify(state)


threading.Thread(target=run_bot, daemon=True).start()

app.run(host="0.0.0.0", port=3000)
