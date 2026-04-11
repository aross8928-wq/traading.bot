from flask import Flask, jsonify
import threading, time, requests, pandas as pd, os

app = Flask(__name__)

SYMBOLS = [
    "BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT",
    "XRPUSDT","ADAUSDT","DOGEUSDT","AVAXUSDT",
    "MATICUSDT","LINKUSDT"
]

BALANCE = 5000
RISK = 0.0075
MAX_POS = 3
RR = 2

state = {
    "coins":[],
    "logs":[],
    "balance":BALANCE,
    "positions":[]
}

def log(msg):
    print(msg)
    state["logs"].insert(0, msg)
    state["logs"]=state["logs"][:50]

def get_klines(symbol, interval):
    try:
        r=requests.get("https://api.binance.us/api/v3/klines",
        params={"symbol":symbol,"interval":interval,"limit":200},timeout=10)
        df=pd.DataFrame(r.json())
        df=df[[1,2,3,4]]
        df.columns=["open","high","low","close"]
        return df.astype(float)
    except:
        return None

def analyze(symbol):

    df1h=get_klines(symbol,"1h")
    df4h=get_klines(symbol,"4h")

    if df1h is None or df4h is None:
        return None

    df1h["ema50"]=df1h["close"].ewm(span=50).mean()
    df4h["ema50"]=df4h["close"].ewm(span=50).mean()
    df4h["ema200"]=df4h["close"].ewm(span=200).mean()

    df1h["high_roll"]=df1h["high"].rolling(20).max()
    df1h["atr"]=(df1h["high"]-df1h["low"]).rolling(14).mean()

    row1=df1h.iloc[-1]
    row4=df4h.iloc[-1]

    price=row1["close"]
    atr=row1["atr"]

    trend_ok = row4["ema50"] > row4["ema200"]
    distance = (price - row1["ema50"]) / atr if atr > 0 else 0

    prev_high=df1h["high_roll"].iloc[-2]

    signal="WAIT"
    entry=None; stop=None; tp=None
    score=0

    if trend_ok:
        score += 40

        if distance < 1.2:
            score += 30

            if price > prev_high:
                score += 30
                signal="BUY"
                entry=price
                stop=price-atr
                tp=price+(price-stop)*RR

        else:
            signal="LATE"
            score -= 20

    else:
        signal="NO TRADE"
        score -= 50

    score = max(0, min(100, score))

    return {
        "symbol":symbol,
        "price":round(price,2),
        "signal":signal,
        "entry":entry,
        "stop":stop,
        "tp":tp,
        "score":score,
        "chart":df1h["close"].tail(50).tolist()
    }

# ================= TRADING =================
def open_trade(data):
    if len(state["positions"]) >= MAX_POS:
        return

    if data["score"] < 70:
        return

    risk_amt = state["balance"] * RISK
    risk = data["entry"] - data["stop"]

    if risk <= 0:
        return

    size = risk_amt / risk

    trade = {
        "symbol": data["symbol"],
        "entry": data["entry"],
        "stop": data["stop"],
        "tp": data["tp"],
        "size": size
    }

    state["positions"].append(trade)

    log(f"🚀 OPEN {data['symbol']} @ {round(data['entry'],2)}")

def update_trades(price_map):
    closed = []

    for t in state["positions"]:
        price = price_map.get(t["symbol"], t["entry"])

        if price <= t["stop"] or price >= t["tp"]:
            pnl = (price - t["entry"]) * t["size"]
            state["balance"] += pnl

            log(f"❌ CLOSE {t['symbol']} PnL {round(pnl,2)}")

            closed.append(t)

    for c in closed:
        state["positions"].remove(c)

# ================= LOOP =================
def run_bot():
    while True:
        coins=[]
        prices={}

        for s in SYMBOLS:
            data=analyze(s)
            if data:
                coins.append(data)
                prices[s]=data["price"]

                if data["signal"]=="BUY":
                    open_trade(data)

        update_trades(prices)

        state["coins"]=coins

        log(f"Balance: {round(state['balance'],2)} | Trades: {len(state['positions'])}")

        time.sleep(15)

# ================= WEB =================
@app.route("/")
def home():
    return """
    <html>
    <head>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
    body { background:#111;color:#eee;font-family:Arial;padding:20px }
    table { width:100%; border-collapse:collapse }
    td,th { padding:8px; border-bottom:1px solid #333 }
    .buy{color:#0f0} .late{color:#ff8800} .no{color:#f00}
    </style>
    </head>
    <body>

    <h1>🚀 Trading Bot (Auto Mode)</h1>

    <h3>Balance: <span id="bal"></span></h3>
    <h3>Open Trades: <span id="trades"></span></h3>

    <table>
    <thead>
    <tr>
    <th>Coin</th><th>Price</th><th>Signal</th><th>Score</th><th>Chart</th>
    </tr>
    </thead>
    <tbody id="table"></tbody>
    </table>

    <h3>Logs</h3>
    <div id="logs"></div>

    <script>
    async function load(){
        let r=await fetch('/data'); let d=await r.json();

        document.getElementById("bal").innerText=d.balance.toFixed(2);
        document.getElementById("trades").innerText=d.positions.length;

        let html="";
        d.coins.forEach(c=>{
            html+=`
            <tr>
            <td>${c.symbol}</td>
            <td>${c.price}</td>
            <td>${c.signal}</td>
            <td>${c.score}</td>
            <td><canvas id="${c.symbol}"></canvas></td>
            </tr>`;
        });

        document.getElementById("table").innerHTML=html;

        d.coins.forEach(c=>{
            new Chart(document.getElementById(c.symbol),{
                type:'line',
                data:{labels:c.chart,datasets:[{data:c.chart,borderColor:'#0f0'}]},
                options:{plugins:{legend:{display:false}},scales:{x:{display:false}}}
            });
        });

        document.getElementById("logs").innerHTML=
        d.logs.map(x=>"<div>"+x+"</div>").join("");
    }

    setInterval(load,3000);
    </script>

    </body>
    </html>
    """

@app.route("/data")
def data():
    return jsonify(state)

threading.Thread(target=run_bot,daemon=True).start()
app.run(host="0.0.0.0",port=int(os.environ.get("PORT",3000)))
