from flask import Flask, jsonify
import threading, time, requests, pandas as pd, os

app = Flask(__name__)

# ================= CONFIG =================
SYMBOLS = [
    "BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT",
    "XRPUSDT","ADAUSDT","DOGEUSDT","AVAXUSDT",
    "MATICUSDT","LINKUSDT"
]

state = {
    "coins": [],
    "logs": []
}

# ================= CORE =================
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

def analyze(symbol):

    df1h = get_klines(symbol,"1h")
    df4h = get_klines(symbol,"4h")

    if df1h is None or df4h is None:
        return None

    df1h["ema50"] = df1h["close"].ewm(span=50).mean()
    df4h["ema50"] = df4h["close"].ewm(span=50).mean()
    df4h["ema200"] = df4h["close"].ewm(span=200).mean()

    df1h["high_roll"] = df1h["high"].rolling(20).max()
    df1h["atr"] = (df1h["high"]-df1h["low"]).rolling(14).mean()

    row1 = df1h.iloc[-1]
    row4 = df4h.iloc[-1]

    price = row1["close"]

    # TREND
    trend = "BULL" if row4["ema50"] > row4["ema200"] else "BEAR"

    # BREAKOUT
    prev_high = df1h["high_roll"].iloc[-2]

    signal = "WAIT"
    entry = "-"
    stop = "-"
    tp = "-"

    if trend == "BULL":

        if (price - row1["ema50"]) < row1["atr"] * 1.2:

            if price > prev_high:

                signal = "BUY"
                entry = round(price,2)
                stop = round(price - row1["atr"],2)
                tp = round(price + (price - (price - row1["atr"])) * 2,2)

            else:
                signal = "WAIT"

        else:
            signal = "OVEREXTENDED"

    else:
        signal = "NO TRADE"

    return {
        "symbol": symbol,
        "price": round(price,2),
        "trend": trend,
        "signal": signal,
        "entry": entry,
        "stop": stop,
        "tp": tp
    }

# ================= BOT LOOP =================
def run_bot():
    while True:
        coins = []

        for sym in SYMBOLS:
            data = analyze(sym)
            if data:
                coins.append(data)

        state["coins"] = coins

        log("Market scanned")

        time.sleep(15)

# ================= WEB =================
@app.route("/")
def home():
    return """
    <html>
    <head>
    <style>
    body { background:#111;color:#eee;font-family:Arial;padding:20px }
    table { width:100%; border-collapse:collapse }
    td,th { padding:10px; border-bottom:1px solid #333 }
    .buy { color:#0f0 }
    .wait { color:#ff0 }
    .no { color:#f00 }
    </style>
    </head>
    <body>

    <h1>📊 Trading Dashboard</h1>

    <table>
    <thead>
    <tr>
    <th>Symbol</th>
    <th>Price</th>
    <th>Trend</th>
    <th>Signal</th>
    <th>Entry</th>
    <th>Stop</th>
    <th>TP</th>
    </tr>
    </thead>
    <tbody id="table"></tbody>
    </table>

    <h3>Logs</h3>
    <div id="logs"></div>

    <script>
    async function load(){
        let r = await fetch('/data');
        let d = await r.json();

        let html = "";

        d.coins.forEach(c => {

            let cls = "wait";
            if(c.signal=="BUY") cls="buy";
            if(c.signal=="NO TRADE") cls="no";

            html += `
            <tr>
                <td>${c.symbol}</td>
                <td>${c.price}</td>
                <td>${c.trend}</td>
                <td class="${cls}">${c.signal}</td>
                <td>${c.entry}</td>
                <td>${c.stop}</td>
                <td>${c.tp}</td>
            </tr>`;
        });

        document.getElementById("table").innerHTML = html;

        document.getElementById("logs").innerHTML =
            d.logs.map(x=>"<div>"+x+"</div>").join("");
    }

    setInterval(load,2000);
    </script>

    </body>
    </html>
    """

@app.route("/data")
def data():
    return jsonify(state)

# ================= START =================
threading.Thread(target=run_bot, daemon=True).start()

app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 3000)))
