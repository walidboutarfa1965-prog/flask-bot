import os
from flask import Flask, request, jsonify, render_template_string
from binance.client import Client
from datetime import datetime
import logging
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

API_KEY = os.getenv('BINANCE_API_KEY')
API_SECRET = os.getenv('BINANCE_API_SECRET')
TESTNET = os.getenv('BINANCE_TESTNET', 'false').lower() == 'true'

try:
    client = Client(API_KEY, API_SECRET, testnet=TESTNET)
    balance = client.get_asset_balance(asset='USDT')
    logging.info(f"✅ الرصيد: {float(balance['free']):.2f} USDT")
except Exception as e:
    logging.error(f"❌ فشل الاتصال: {e}")
    client = None

trades = []
total_trades = 0
settings = {'default_quantity': 0.001, 'symbols': ['BTCUSDT', 'ETHUSDT'], 'broker': 'Binance'}

HTML = '''<!DOCTYPE html>
<html lang="ar">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🤖 بوت التداول</title>
    <style>
        * { margin:0; padding:0; box-sizing:border-box; }
        body { font-family:'Segoe UI',sans-serif; background:#0a0e17; color:#e0e0e0; padding:20px; }
        .container { max-width:1200px; margin:0 auto; }
        h1 { text-align:center; color:#00d4ff; font-size:2rem; margin-bottom:30px; }
        .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:15px; margin-bottom:25px; }
        .card { background:#111927; border-radius:12px; padding:15px; border:1px solid #1a2a3a; }
        .card .label { color:#7a8a9e; font-size:0.8rem; text-transform:uppercase; }
        .card .value { font-size:1.3rem; font-weight:bold; margin-top:8px; }
        .green { color:#00e676; } .red { color:#ff5252; } .blue { color:#00d4ff; } .gold { color:#ffd700; }
        .section { background:#111927; border-radius:12px; padding:15px; border:1px solid #1a2a3a; margin-bottom:20px; }
        .section h2 { color:#00d4ff; font-size:1rem; margin-bottom:12px; }
        .flex { display:flex; gap:10px; flex-wrap:wrap; align-items:center; }
        input, select { padding:8px 12px; border-radius:8px; border:1px solid #1a2a3a; background:#0d1520; color:#e0e0e0; }
        .btn { padding:8px 20px; border:none; border-radius:8px; font-weight:bold; cursor:pointer; }
        .btn-primary { background:#00d4ff; color:#0a0e17; }
        .btn-success { background:#00e676; color:#0a0e17; }
        table { width:100%; border-collapse:collapse; }
        th { text-align:left; padding:8px; color:#7a8a9e; border-bottom:2px solid #1a2a3a; font-size:0.7rem; text-transform:uppercase; }
        td { padding:8px; border-bottom:1px solid #1a2a3a; font-size:0.9rem; }
        .buy { color:#00e676; } .sell { color:#ff5252; }
        .status-badge { display:inline-block; padding:4px 12px; border-radius:20px; font-size:0.8rem; background:#00e67620; color:#00e676; border:1px solid #00e67640; }
        .last-update { color:#4a5a6e; font-size:0.7rem; }
        .footer { text-align:center; margin-top:30px; color:#4a5a6e; font-size:0.8rem; }
        .mt-10 { margin-top:10px; }
    </style>
</head>
<body>
<div class="container">
    <h1>🤖 بوت التداول</h1>
    <div class="grid">
        <div class="card"><div class="label">📊 الحالة</div><div class="value"><span class="status-badge">🟢 يعمل</span></div></div>
        <div class="card"><div class="label">💰 الرصيد</div><div class="value blue">{{ balance }} USDT</div></div>
        <div class="card"><div class="label">📈 الصفقات</div><div class="value gold">{{ total_trades }}</div></div>
    </div>
    <div class="section">
        <h2>⚙️ الإعدادات</h2>
        <form method="POST" action="/update">
            <div class="flex">
                <label>حجم الصفقة: <input type="number" name="quantity" value="{{ default_quantity }}" step="0.0001" style="width:100px;"></label>
                <button type="submit" class="btn btn-success">💾 حفظ</button>
            </div>
        </form>
    </div>
    <div class="section">
        <h2>📤 أمر يدوي</h2>
        <form method="POST" action="/order">
            <div class="flex">
                <select name="action"><option value="BUY">شراء</option><option value="SELL">بيع</option></select>
                <select name="symbol">{% for s in symbols %}<option>{{ s }}</option>{% endfor %}</select>
                <input type="number" name="quantity" value="{{ default_quantity }}" step="0.0001" style="width:100px;">
                <button type="submit" class="btn btn-primary">🚀 تنفيذ</button>
            </div>
        </form>
    </div>
    <div class="section">
        <h2>📋 سجل الصفقات <span class="last-update">{{ last_update }}</span></h2>
        <table>
            <thead><tr><th>الوقت</th><th>النوع</th><th>الزوج</th><th>السعر</th><th>الحجم</th></tr></thead>
            <tbody>
                {% for t in trades[-15:]|reverse %}
                <tr><td>{{ t.time }}</td><td class="{{ 'buy' if t.type == 'BUY' else 'sell' }}">{{ t.type }}</td><td>{{ t.symbol }}</td><td>{{ t.price }}</td><td>{{ t.quantity }}</td></tr>
                {% else %}
                <tr><td colspan="5" style="text-align:center;color:#4a5a6e;">لا توجد صفقات</td></tr>
                {% endfor %}
            </tbody>
        </table>
        <div class="mt-10"><a href="/" class="btn btn-primary">🔄 تحديث</a></div>
    </div>
    <div class="footer">🚀 بوت التداول | 24/7</div>
</div>
</body>
</html>'''

@app.route('/')
def index():
    balance = 0
    try:
        if client:
            bal = client.get_asset_balance(asset='USDT')
            balance = float(bal['free'])
    except: pass
    return render_template_string(HTML, balance=f"{balance:.2f}", total_trades=total_trades,
                                  trades=trades, last_update=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                                  default_quantity=settings['default_quantity'], symbols=settings['symbols'])

@app.route('/update', methods=['POST'])
def update():
    settings['default_quantity'] = float(request.form.get('quantity', 0.001))
    return index()

@app.route('/order', methods=['POST'])
def order():
    global trades, total_trades
    try:
        symbol = request.form.get('symbol', 'BTCUSDT')
        action = request.form.get('action')
        quantity = float(request.form.get('quantity', 0.001))
        if client:
            price = float(client.get_symbol_ticker(symbol=symbol)['price'])
            order = client.create_order(symbol=symbol, side=action, type='MARKET', quantity=quantity)
            trades.append({'time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 'type': action, 'symbol': symbol, 'price': price, 'quantity': quantity})
            total_trades += 1
    except Exception as e:
        logging.error(f"❌ خطأ: {e}")
    return index()

@app.route('/webhook', methods=['POST'])
def webhook():
    global trades, total_trades
    try:
        data = request.get_json()
        symbol = data.get('symbol', 'BTCUSDT')
        action = data.get('action')
        quantity = data.get('quantity', settings['default_quantity'])
        if client and action in ['BUY', 'SELL']:
            price = float(client.get_symbol_ticker(symbol=symbol)['price'])
            client.create_order(symbol=symbol, side=action, type='MARKET', quantity=quantity)
            trades.append({'time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 'type': action, 'symbol': symbol, 'price': price, 'quantity': quantity})
            total_trades += 1
            return jsonify({"status": "success"}), 200
    except Exception as e:
        logging.error(f"❌ خطأ: {e}")
    return jsonify({"status": "error"}), 400

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
