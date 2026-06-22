import os
from flask import Flask, request, jsonify, render_template_string
from binance.client import Client
from datetime import datetime
import logging
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

# =============================================
# إعدادات Binance
# =============================================
API_KEY = os.getenv('BINANCE_API_KEY')
API_SECRET = os.getenv('BINANCE_API_SECRET')
TESTNET = os.getenv('BINANCE_TESTNET', 'false').lower() == 'true'

try:
    if TESTNET:
        client = Client(API_KEY, API_SECRET, testnet=True)
    else:
        client = Client(API_KEY, API_SECRET)
    balance = client.get_asset_balance(asset='USDT')
    logging.info(f"✅ الرصيد: {float(balance['free']):.2f} USDT")
except Exception as e:
    logging.error(f"❌ فشل الاتصال: {e}")
    client = None

# =============================================
# بيانات البوت (قابلة للتعديل من الواجهة)
# =============================================
trades = []
total_trades = 0
winning_trades = 0

# إعدادات البوت (مخزنة مؤقتاً)
bot_settings = {
    'default_quantity': 0.001,
    'max_trades': 5,  # عدد الصفقات عند تأكيد الاتجاه
    'symbols': ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'XAUUSD'],  # أزواج التداول
    'broker_name': 'Binance',
    'broker_code': 'BINANCE',
    'broker_password': '',
    'funding_company': 'None'
}

# =============================================
# HTML Template للواجهة المتطورة
# =============================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ar">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🤖 بوت التداول المتطور</title>
    <style>
        * { margin:0; padding:0; box-sizing:border-box; }
        body { font-family:'Segoe UI',sans-serif; background:#0a0e17; color:#e0e0e0; padding:20px; }
        .container { max-width:1400px; margin:0 auto; }
        h1 { text-align:center; color:#00d4ff; font-size:2.2rem; margin-bottom:30px; }
        .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:15px; margin-bottom:25px; }
        .card { background:#111927; border-radius:12px; padding:15px; border:1px solid #1a2a3a; }
        .card .label { color:#7a8a9e; font-size:0.8rem; text-transform:uppercase; }
        .card .value { font-size:1.5rem; font-weight:bold; margin-top:8px; }
        .green { color:#00e676; } .red { color:#ff5252; } .blue { color:#00d4ff; } .gold { color:#ffd700; } .purple { color:#b388ff; }
        .section { background:#111927; border-radius:12px; padding:15px; border:1px solid #1a2a3a; margin-bottom:20px; }
        .section h2 { color:#00d4ff; font-size:1.1rem; margin-bottom:12px; }
        .flex { display:flex; gap:10px; flex-wrap:wrap; align-items:center; }
        .flex-column { display:flex; flex-direction:column; gap:10px; }
        input, select { padding:8px 12px; border-radius:8px; border:1px solid #1a2a3a; background:#0d1520; color:#e0e0e0; min-width:150px; }
        .btn { padding:8px 20px; border:none; border-radius:8px; font-weight:bold; cursor:pointer; }
        .btn-primary { background:#00d4ff; color:#0a0e17; }
        .btn-success { background:#00e676; color:#0a0e17; }
        .btn-danger { background:#ff5252; color:#0a0e17; }
        .btn-warning { background:#ffd700; color:#0a0e17; }
        table { width:100%; border-collapse:collapse; }
        th { text-align:left; padding:10px; color:#7a8a9e; border-bottom:2px solid #1a2a3a; font-size:0.75rem; text-transform:uppercase; }
        td { padding:10px; border-bottom:1px solid #1a2a3a; }
        .buy { color:#00e676; } .sell { color:#ff5252; }
        .status-badge { display:inline-block; padding:4px 12px; border-radius:20px; font-size:0.8rem; background:#00e67620; color:#00e676; border:1px solid #00e67640; }
        .last-update { color:#4a5a6e; font-size:0.8rem; }
        .footer { text-align:center; margin-top:30px; color:#4a5a6e; font-size:0.8rem; }
        .mt-10 { margin-top:10px; }
        .symbol-tag { display:inline-block; background:#1a2a3a; padding:4px 12px; border-radius:20px; margin:3px; font-size:0.8rem; }
        .symbol-tag .remove { cursor:pointer; color:#ff5252; margin-left:5px; }
        .settings-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(200px,1fr)); gap:15px; }
        .settings-item label { display:block; color:#7a8a9e; font-size:0.8rem; margin-bottom:5px; }
        .settings-item input, .settings-item select { width:100%; }
        .broker-box { background:#0d1520; border-radius:8px; padding:12px; border:1px solid #1a2a3a; }
        .broker-box .label { color:#7a8a9e; font-size:0.7rem; text-transform:uppercase; }
        .broker-box .value { color:#e0e0e0; font-size:1rem; margin-top:4px; }
    </style>
</head>
<body>
<div class="container">
    <h1>🤖 بوت التداول المتطور</h1>
    
    <!-- بطاقات المعلومات -->
    <div class="grid">
        <div class="card"><div class="label">📊 الحالة</div><div class="value"><span class="status-badge">🟢 يعمل</span></div></div>
        <div class="card"><div class="label">💰 الرصيد</div><div class="value blue">{{ balance }} USDT</div></div>
        <div class="card"><div class="label">📈 الصفقات</div><div class="value gold">{{ total_trades }}</div></div>
        <div class="card"><div class="label">🏆 النجاح</div><div class="value green">{{ win_rate }}%</div></div>
        <div class="card"><div class="label">📊 الحد الأقصى للصفقات</div><div class="value purple">{{ max_trades }}</div></div>
    </div>

    <!-- الإعدادات المتقدمة -->
    <div class="section">
        <h2>⚙️ الإعدادات المتقدمة</h2>
        <form method="POST" action="/update_settings">
            <div class="settings-grid">
                <div class="settings-item">
                    <label>📊 الحد الأقصى للصفقات</label>
                    <input type="number" name="max_trades" value="{{ max_trades }}" min="1" max="20">
                </div>
                <div class="settings-item">
                    <label>📊 حجم الصفقة الافتراضي</label>
                    <input type="number" name="default_quantity" value="{{ default_quantity }}" step="0.0001" min="0.0001">
                </div>
                <div class="settings-item">
                    <label>➕ إضافة زوج جديد</label>
                    <div class="flex">
                        <input type="text" name="new_symbol" placeholder="مثل: XAUUSD" style="flex:1;">
                        <button type="submit" name="action" value="add_symbol" class="btn btn-primary">➕</button>
                    </div>
                </div>
            </div>
            <div class="mt-10">
                <label>📊 الأزواج المتاحة:</label>
                <div id="symbols_container">
                    {% for symbol in symbols %}
                    <span class="symbol-tag">{{ symbol }} <span class="remove" onclick="removeSymbol('{{ symbol }}')">✕</span></span>
                    {% endfor %}
                </div>
            </div>
            <div class="mt-10">
                <button type="submit" name="action" value="save_settings" class="btn btn-success">💾 حفظ الإعدادات</button>
            </div>
        </form>
    </div>

    <!-- معلومات الوسيط وشركة التمويل -->
    <div class="section">
        <h2>🏢 معلومات الوسيط / شركة التمويل</h2>
        <form method="POST" action="/update_broker">
            <div class="settings-grid">
                <div class="settings-item">
                    <label>🏢 اسم الوسيط</label>
                    <input type="text" name="broker_name" value="{{ broker_name }}" placeholder="مثل: Binance">
                </div>
                <div class="settings-item">
                    <label>🔑 رمز الوسيط</label>
                    <input type="text" name="broker_code" value="{{ broker_code }}" placeholder="مثل: BINANCE">
                </div>
                <div class="settings-item">
                    <label>🔒 كلمة المرور</label>
                    <input type="password" name="broker_password" value="{{ broker_password }}" placeholder="كلمة المرور">
                </div>
                <div class="settings-item">
                    <label>🏢 شركة التمويل</label>
                    <input type="text" name="funding_company" value="{{ funding_company }}" placeholder="مثل: FTMO">
                </div>
            </div>
            <div class="mt-10">
                <button type="submit" class="btn btn-warning">💾 حفظ بيانات الوسيط</button>
            </div>
        </form>
        <div class="mt-10 broker-box">
            <div class="label">📋 معلومات الوسيط الحالية:</div>
            <div class="value">🏢 {{ broker_name }} | 🔑 {{ broker_code }} | 🏢 {{ funding_company }}</div>
        </div>
    </div>

    <!-- أمر يدوي -->
    <div class="section">
        <h2>📤 أمر يدوي</h2>
        <form method="POST" action="/order">
            <div class="flex">
                <select name="action"><option value="BUY">🟢 شراء</option><option value="SELL">🔴 بيع</option></select>
                <select name="symbol">{% for s in symbols %}<option>{{ s }}</option>{% endfor %}</select>
                <input type="number" name="quantity" value="{{ default_quantity }}" step="0.0001" style="width:100px;">
                <button type="submit" class="btn btn-primary">🚀 تنفيذ</button>
            </div>
        </form>
    </div>

    <!-- سجل الصفقات -->
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

    <div class="footer">🚀 بوت التداول المتطور | 24/7</div>
</div>

<script>
function removeSymbol(symbol) {
    fetch('/remove_symbol', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({symbol: symbol})
    }).then(() => location.reload());
}
</script>
</body>
</html>
"""

# =============================================
# الصفحة الرئيسية
# =============================================
@app.route('/')
def index():
    balance = 0
    try:
        if client:
            bal = client.get_asset_balance(asset='USDT')
            balance = float(bal['free'])
    except:
        pass
    
    win_rate = round((winning_trades / total_trades * 100) if total_trades > 0 else 0, 1)
    
    return render_template_string(
        HTML_TEMPLATE,
        balance=f"{balance:.2f}",
        total_trades=total_trades,
        win_rate=win_rate,
        trades=trades,
        last_update=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        max_trades=bot_settings['max_trades'],
        default_quantity=bot_settings['default_quantity'],
        symbols=bot_settings['symbols'],
        broker_name=bot_settings['broker_name'],
        broker_code=bot_settings['broker_code'],
        broker_password=bot_settings['broker_password'],
        funding_company=bot_settings['funding_company']
    )

# =============================================
# تحديث الإعدادات
# =============================================
@app.route('/update_settings', methods=['POST'])
def update_settings():
    global bot_settings
    action = request.form.get('action', '')
    
    if action == 'add_symbol':
        new_symbol = request.form.get('new_symbol', '').upper()
        if new_symbol and new_symbol not in bot_settings['symbols']:
            bot_settings['symbols'].append(new_symbol)
    elif action == 'save_settings':
        bot_settings['max_trades'] = int(request.form.get('max_trades', 5))
        bot_settings['default_quantity'] = float(request.form.get('default_quantity', 0.001))
    
    return index()

# =============================================
# تحديث بيانات الوسيط
# =============================================
@app.route('/update_broker', methods=['POST'])
def update_broker():
    global bot_settings
    bot_settings['broker_name'] = request.form.get('broker_name', 'Binance')
    bot_settings['broker_code'] = request.form.get('broker_code', 'BINANCE')
    bot_settings['broker_password'] = request.form.get('broker_password', '')
    bot_settings['funding_company'] = request.form.get('funding_company', 'None')
    return index()

# =============================================
# حذف زوج
# =============================================
@app.route('/remove_symbol', methods=['POST'])
def remove_symbol():
    global bot_settings
    data = request.get_json()
    symbol = data.get('symbol', '').upper()
    if symbol in bot_settings['symbols']:
        bot_settings['symbols'].remove(symbol)
    return jsonify({"status": "success"})

# =============================================
# أمر يدوي
# =============================================
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

# =============================================
# استقبال الإشارات (Webhook)
# =============================================
@app.route('/webhook', methods=['POST'])
def webhook():
    global trades, total_trades
    try:
        data = request.get_json()
        symbol = data.get('symbol', 'BTCUSDT')
        action = data.get('action')
        quantity = data.get('quantity', bot_settings['default_quantity'])
        if client and action in ['BUY', 'SELL']:
            price = float(client.get_symbol_ticker(symbol=symbol)['price'])
            client.create_order(symbol=symbol, side=action, type='MARKET', quantity=quantity)
            trades.append({'time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"), 'type': action, 'symbol': symbol, 'price': price, 'quantity': quantity})
            total_trades += 1
            return jsonify({"status": "success"}), 200
    except Exception as e:
        logging.error(f"❌ خطأ: {e}")
    return jsonify({"status": "error"}), 400

# =============================================
# تشغيل الخادم
# =============================================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
