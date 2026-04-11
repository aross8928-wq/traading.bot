from flask import Flask, jsonify
import threading, time, requests, pandas as pd, os

app = Flask(__name__)

SYMBOLS = [
    "BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT",
    "XRPUSDT","ADAUSDT","DOGEUSDT","AVAXUSDT",
    "MATICUSDT","LINKUSDT"
]

state = {"coins":[],"logs":[]}

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
    reason="No setup"
    entry="-"; stop="-"; tp="-"; order="-"
    score=0
    zone="-"

    if trend_ok:

        score += 40

        if distance < 1.2:
            score += 30

            zone = round(row1["ema50"],2)

            if price > prev_high:

                score += 30

                signal="BUY"
                reason="Breakout + good structure"

                entry=round(price,2)
                stop=round(price-atr,2)
                tp=round(price+(price-stop)*2,2)

                order="OCO"

        else:
            signal="LATE"
            reason="Too extended"
            score -= 20

    else:
        signal="NO TRADE"
        reason="Bear trend"
        score -= 50

    score = max(0, min(100, score))

    prob = round(score * 0.8,1)

    return {
        "symbol":symbol,
        "price":round(price,2),
        "trend":"BULL" if trend_ok else "BEAR",
        "signal":signal,
        "reason":reason,
        "entry":entry,
        "stop":stop,
        "tp":tp,
        "order":order,
        "score":score,
        "prob":prob,
        "zone":zone,
        "chart":df1h["close"].tail(50).tolist()
    }
def run_bot():
    while True:
        coins=[]
        for s in SYMBOLS:
            data=analyze(s)
            if data: coins.append(data)

        state["coins"]=coins
        log("Scan complete")
        time.sleep(15)

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
    .buy{color:#0f0} .wait{color:#ff0} .no{color:#f00}
    canvas{max-width:400px}
    </style>
    </head>
    <body>

    <h1>📊 PRO Trading Dashboard</h1>

    <table>
    <thead>
    <tr>
    <th>Coin</th><th>Price</th><th>Trend</th>
    <th>Signal</th><th>Reason</th>
    <th>Entry</th><th>SL</th><th>TP</th><th>Order</th>
    <th>Chart</th>
    </tr>
    </thead>
    <tbody id="table"></tbody>
    </table>

    <h3>Logs</h3>
    <div id="logs"></div>

    <script>
    async function load(){
        let r=await fetch('/data'); let d=await r.json();
        let html="";

        d.coins.forEach(c=>{
            let cls="wait";
            if(c.signal=="BUY")cls="buy";
            if(c.signal=="NO TRADE")cls="no";

            html+=`
            <tr>
            <td>${c.symbol}</td>
            <td>${c.price}</td>
            <td>${c.trend}</td>
            <td class="${cls}">${c.signal}</td>
            <td>${c.reason}</td>
            <td>${c.entry}</td>
            <td>${c.stop}</td>
            <td>${c.tp}</td>
            <td>${c.order}</td>
            <td><canvas id="${c.symbol}"></canvas></td>
            </tr>`;
        });

        document.getElementById("table").innerHTML=html;

        d.coins.forEach(c=>{
            new Chart(document.getElementById(c.symbol),{
                type:'line',
                data:{labels:c.chart, datasets:[{data:c.chart, borderColor:'#0f0'}]},
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
