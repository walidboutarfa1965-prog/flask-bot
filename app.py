import os
from flask import Flask, request, jsonify, render_template_string
from binance.client import Client
from datetime import datetime
import logging
from dotenv import load_dotenv
import feedparser
import hashlib
import threading
import time
import schedule

load_dotenv()
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

# =============================================
# 1. إعدادات Binance
# =============================================
API_KEY = os.getenv('BINANCE_API_KEY')
API_SECRET = os.getenv('BINANCE_API_SECRET')
TESTNET = os.getenv('BINANCE_TESTNET', 'false').lower() == 'true'

try:
    if TESTNET:
        client = Client(API_KEY, API_SECRET, testnet=True)
        logging.info("✅ تم الاتصال بـ Binance Testnet")
    else:
        client = Client(API_KEY, API_SECRET)
        logging.info("✅ تم الاتصال بـ Binance")
    balance = client.get_asset_balance(asset='USDT')
    logging.info(f"💰 الرصيد: {float(balance['free']):.2f} USDT")
except Exception as e:
    logging.error(f"❌ فشل الاتصال: {e}")
    client = None

# =============================================
# 2. بيانات البوت (قابلة للتعديل)
# =============================================
trades = []
total_trades = 0
winning_trades = 0
daily_loss = 0
trades_today = 0

bot_settings = {
    # إعدادات التداول
    'default_quantity': 0.001,
    'max_trades': 5,
    'symbols': ['BTCUSDT', 'ETHUSDT', 'BNBUSDT', 'XAUUSD'],
    
    # إدارة المخاطر
    'risk_percent': 1.0,
    'stop_loss_percent': 2.0,
    'take_profit_percent': 4.0,
    'trailing_stop_percent': 1.5,
    'max_daily_loss': 5.0,
    
    # بيانات الوسيط
    'broker_name': 'Binance',
    'broker_code': 'BINANCE',
    'broker_password': '',
    'funding_company': 'None',
    
    # تحليل الأخبار
    'use_news_filter': True,
    'news_impact_threshold': 'high',
}

# =============================================
# 3. وظائف إدارة المخاطر
# =============================================
def get_account_balance():
    try:
        if client:
            balance = client.get_asset_balance(asset='USDT')
            return float(balance['free'])
    except:
        pass
    return 10000

def calculate_position_size(symbol, action, price, stop_loss_price):
    account_balance = get_account_balance()
    risk_amount = account_balance * (bot_settings['risk_percent'] / 100)
    risk_distance = abs(price - stop_loss_price)
    if risk_distance == 0:
        risk_distance = 0.01
    position_size = risk_amount / risk_distance
    return round(position_size, 3)

def execute_order_with_risk(symbol, action):
    try:
        price = float(client.get_symbol_ticker(symbol=symbol)['price'])
        
        if action == 'BUY':
            stop_loss_price = price * (1 - bot_settings['stop_loss_percent'] / 100)
            take_profit_price = price * (1 + bot_settings['take_profit_percent'] / 100)
        else:
            stop_loss_price = price * (1 + bot_settings['stop_loss_percent'] / 100)
            take_profit_price = price * (1 - bot_settings['take_profit_percent'] / 100)
        
        quantity = calculate_position_size(symbol, action, price, stop_loss_price)
        if quantity <= 0:
            quantity = 0.001
        
        order = client.create_order(
            symbol=symbol,
            side=action,
            type='MARKET',
            quantity=quantity
        )
        
        trades.append({
            'time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'type': action,
            'symbol': symbol,
            'price': price,
            'quantity': quantity,
            'stop_loss': stop_loss_price,
            'take_profit': take_profit_price,
            'risk_percent': bot_settings['risk_percent']
        })
        return order
    except Exception as e:
        logging.error(f"❌ فشل تنفيذ الأمر: {e}")
        return None

# =============================================
# 4. تحليل الأخبار
# =============================================
def fetch_news():
    try:
        url = 'https://www.investing.com/rss/news_14.rss'
        feed = feedparser.parse(url)
        news = []
        high_impact_keywords = ['fed', 'interest rate', 'cpi', 'nonfarm', 'employment', 'gdp', 'pmi']
        for entry in feed.entries[:10]:
            title = entry.title.lower()
            impact_score = sum(1 for kw in high_impact_keywords if kw in title)
            news.append({
                'title': entry.title,
                'summary': entry.summary[:200],
                'date': entry.published,
                'impact': 'high' if impact_score >= 2 else 'medium' if impact_score >= 1 else 'low'
            })
        return news
    except Exception as e:
        logging.error(f"❌ فشل جلب الأخبار: {e}")
        return []

def get_news_risk():
    news = fetch_news()
    risk_score = 0
    for item in news:
        if item['impact'] == 'high':
            risk_score += 2
    return min(risk_score, 10)

# =============================================
# 5. Bookmap Integration (محاكاة)
# =============================================
class BookmapAnalyzer:
    def __init__(self):
        self.bids = {}
        self.asks = {}
        self.liquidity_zones = []
    
    def on_depth(self, is_bid, price, size):
        if is_bid:
            self.bids[price] = size
        else:
            self.asks[price] = size
    
    def get_liquidity_zones(self):
        # تحليل مناطق السيولة (محاكاة)
        zones = []
        if self.bids:
            max_bid = max(self.bids.items(), key=lambda x: x[1])
            zones.append({'type': 'bid', 'price': max_bid[0], 'size': max_bid[1]})
        if self.asks:
            max_ask = max(self.asks.items(), key=lambda x: x[1])
            zones.append({'type': 'ask', 'price': max_ask[0], 'size': max_ask[1]})
        return zones

bookmap = BookmapAnalyzer()

# =============================================
# 6. واجهة HTML المتكاملة
# =============================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ar">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🤖 بوت التداول المتكامل V10</title>
    <style>
        * { margin:0; padding:0; box-sizing:border-box; }
        body { font-family:'Segoe UI',sans-serif; background:#0a0e17; color:#e0e0e0; padding:15px; }
        .container { max-width:1400px; margin:0 auto; }
        h1 { text-align:center; color:#00d4ff; font-size:2rem; margin-bottom:25px; }
        .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:15px; margin-bottom:20px; }
        .card { background:#111927; border-radius:12px; padding:15px; border:1px solid #1a2a3a; }
        .card .label { color:#7a8a9e; font-size:0.75rem; text-transform:uppercase; }
        .card .value { font-size:1.3rem; font-weight:bold; margin-top:8px; }
        .green { color:#00e676; } .red { color:#ff5252; } .blue { color:#00d4ff; } .gold { color:#ffd700; } .purple { color:#b388ff; }
        .section { background:#111927; border-radius:12px; padding:15px; border:1px solid #1a2a3a; margin-bottom:15px; }
        .section h2 { color:#00d4ff; font-size:1rem; margin-bottom:10px; }
        .flex { display:flex; gap:10px; flex-wrap:wrap; align-items:center; }
        input, select { padding:8px 12px; border-radius:8px; border:1px solid #1a2a3a; background:#0d1520; color:#e0e0e0; }
        .btn { padding:8px 18px; border:none; border-radius:8px; font-weight:bold; cursor:pointer; }
        .btn-primary { background:#00d4ff; color:#0a0e17; }
        .btn-success { background:#00e676; color:#0a0e17; }
        .btn-danger { background:#ff5252; color:#0a0e17; }
        .btn-warning { background:#ffd700; color:#0a0e17; }
        table { width:100%; border-collapse:collapse; }
        th { text-align:left; padding:8px; color:#7a8a9e; border-bottom:2px solid #1a2a3a; font-size:0.7rem; text-transform:uppercase; }
        td { padding:8px; border-bottom:1px solid #1a2a3a; font-size:0.9rem; }
        .buy { color:#00e676; } .sell { color:#ff5252; }
        .status-badge { display:inline-block; padding:4px 12px; border-radius:20px; font-size:0.8rem; background:#00e67620; color:#00e676; border:1px solid #00e67640; }
        .last-update { color:#4a5a6e; font-size:0.7rem; }
        .footer { text-align:center; margin-top:20px; color:#4a5a6e; font-size:0.8rem; }
        .mt-10 { margin-top:10px; }
        .settings-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:12px; }
        .settings-item label { display:block; color:#7a8a9e; font-size:0.75rem; margin-bottom:4px; }
        .settings-item input, .settings-item select { width:100%; }
        .symbol-tag { display:inline-block; background:#1a2a3a; padding:4px 12px; border-radius:20px; margin:3px; font-size:0.8rem; }
        .symbol-tag .remove { cursor:pointer; color:#ff5252; margin-left:5px; }
        .news-item { background:#0d1520; padding:8px 12px; border-radius:8px; margin:5px 0; border-left:3px solid #00d4ff; }
        .news-item .impact-high { border-left-color:#ff5252; }
        .news-item .impact-medium { border-left-color:#ffd700; }
        .news-item .impact-low { border-left-color:#4a5a6e; }
        .broker-box { background:#0d1520; border-radius:8px; padding:12px; border:1px solid #1a2a3a; }
        .broker-box .label { color:#7a8a9e; font-size:0.7rem; text-transform:uppercase; }
    </style>
</head>
<body>
<div class="container">
    <h1>🤖 بوت التداول المتكامل V10</h1>
    
    <div class="grid">
        <div class="card"><div class="label">📊 الحالة</div><div class="value"><span class="status-badge">🟢 يعمل</span></div></div>
        <div class="card"><div class="label">💰 الرصيد</div><div class="value blue">{{ balance }} USDT</div></div>
        <div class="card"><div class="label">📈 الصفقات</div><div class="value gold">{{ total_trades }}</div></div>
        <div class="card"><div class="label">🏆 النجاح</div><div class="value green">{{ win_rate }}%</div></div>
        <div class="card"><div class="label">📊 الحد الأقصى</div><div class="value purple">{{ max_trades }}</div></div>
        <div class="card"><div class="label">⚠️ المخاطرة</div><div class="value purple">{{ risk_percent }}%</div></div>
    </div>

    <!-- إدارة المخاطر -->
    <div class="section">
        <h2>⚠️ إدارة المخاطر</h2>
        <form method="POST" action="/update_risk">
            <div class="settings-grid">
                <div class="settings-item">
                    <label>📊 نسبة المخاطرة (%)</label>
                    <input type="number" name="risk_percent" value="{{ risk_percent }}" step="0.5" min="0.5" max="5">
                </div>
                <div class="settings-item">
                    <label>🛑 Stop Loss (%)</label>
                    <input type="number" name="stop_loss_percent" value="{{ stop_loss_percent }}" step="0.5" min="1" max="10">
                </div>
                <div class="settings-item">
                    <label>🎯 Take Profit (%)</label>
                    <input type="number" name="take_profit_percent" value="{{ take_profit_percent }}" step="0.5" min="1" max="20">
                </div>
                <div class="settings-item">
                    <label>🔀 Trailing Stop (%)</label>
                    <input type="number" name="trailing_stop_percent" value="{{ trailing_stop_percent }}" step="0.5" min="0.5" max="5">
                </div>
            </div>
            <div class="mt-10">
                <button type="submit" class="btn btn-warning">💾 حفظ المخاطر</button>
            </div>
        </form>
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
                    <label>📊 حجم الصفقة</label>
                    <input type="number" name="default_quantity" value="{{ default_quantity }}" step="0.0001">
                </div>
                <div class="settings-item">
                    <label>➕ إضافة زوج</label>
                    <div class="flex">
                        <input type="text" name="new_symbol" placeholder="XAUUSD" style="flex:1;">
                        <button type="submit" name="action" value="add_symbol" class="btn btn-primary">➕</button>
                    </div>
                </div>
            </div>
            <div class="mt-10">
                <label>📊 الأزواج:</label>
                <div>
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

    <!-- بيانات الوسيط -->
    <div class="section">
        <h2>🏢 بيانات الوسيط / شركة التمويل</h2>
        <form method="POST" action="/update_broker">
            <div class="settings-grid">
                <div class="settings-item">
                    <label>🏢 اسم الوسيط</label>
                    <input type="text" name="broker_name" value="{{ broker_name }}">
                </div>
                <div class="settings-item">
                    <label>🔑 رمز الوسيط</label>
                    <input type="text" name="broker_code" value="{{ broker_code }}">
                </div>
                <div class="settings-item">
                    <label>🔒 كلمة المرور</label>
                    <input type="password" name="broker_password" value="{{ broker_password }}">
                </div>
                <div class="settings-item">
                    <label>🏢 شركة التمويل</label>
                    <input type="text" name="funding_company" value="{{ funding_company }}">
                </div>
            </div>
            <div class="mt-10">
                <button type="submit" class="btn btn-warning">💾 حفظ الوسيط</button>
            </div>
        </form>
        <div class="mt-10 broker-box">
            <div class="label">📋 معلومات الوسيط الحالية:</div>
            <div>🏢 {{ broker_name }} | 🔑 {{ broker_code }} | 🏢 {{ funding_company }}</div>
        </div>
    </div>

    <!-- تحليل الأخبار -->
    <div class="section">
        <h2>📰 آخر الأخبار</h2>
        <div>
            {% for item in news %}
            <div class="news-item impact-{{ item.impact }}">
                <strong>{{ item.title }}</strong><br>
                <small style="color:#7a8a9e;">{{ item.date[:25] }} | التأثير: {{ item.impact.upper() }}</small>
            </div>
            {% else %}
            <div style="color:#4a5a6e;">لا توجد أخبار</div>
            {% endfor %}
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
            <thead><tr><th>الوقت</th><th>النوع</th><th>الزوج</th><th>السعر</th><th>الحجم</th><th>Stop Loss</th><th>Take Profit</th></tr></thead>
            <tbody>
                {% for t in trades[-15:]|reverse %}
                <tr><td>{{ t.time }}</td><td class="{{ 'buy' if t.type == 'BUY' else 'sell' }}">{{ t.type }}</td><td>{{ t.symbol }}</td><td>{{ t.price }}</td><td>{{ t.quantity }}</td><td>{{ t.stop_loss if t.stop_loss else '-' }}</td><td>{{ t.take_profit if t.take_profit else '-' }}</td></tr>
                {% else %}
                <tr><td colspan="7" style="text-align:center;color:#4a5a6e;">لا توجد صفقات</td></tr>
                {% endfor %}
            </tbody>
        </table>
        <div class="mt-10"><a href="/" class="btn btn-primary">🔄 تحديث</a></div>
    </div>

    <div class="footer">🚀 بوت التداول المتكامل V10 | 24/7 | تم التطوير بالكامل</div>
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
# 7. Routes
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
    news = fetch_news()
    
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
        risk_percent=bot_settings['risk_percent'],
        stop_loss_percent=bot_settings['stop_loss_percent'],
        take_profit_percent=bot_settings['take_profit_percent'],
        trailing_stop_percent=bot_settings['trailing_stop_percent'],
        broker_name=bot_settings['broker_name'],
        broker_code=bot_settings['broker_code'],
        broker_password=bot_settings['broker_password'],
        funding_company=bot_settings['funding_company'],
        news=news
    )

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

@app.route('/update_risk', methods=['POST'])
def update_risk():
    global bot_settings
    bot_settings['risk_percent'] = float(request.form.get('risk_percent', 1.0))
    bot_settings['stop_loss_percent'] = float(request.form.get('stop_loss_percent', 2.0))
    bot_settings['take_profit_percent'] = float(request.form.get('take_profit_percent', 4.0))
    bot_settings['trailing_stop_percent'] = float(request.form.get('trailing_stop_percent', 1.5))
    return index()

@app.route('/update_broker', methods=['POST'])
def update_broker():
    global bot_settings
    bot_settings['broker_name'] = request.form.get('broker_name', 'Binance')
    bot_settings['broker_code'] = request.form.get('broker_code', 'BINANCE')
    bot_settings['broker_password'] = request.form.get('broker_password', '')
    bot_settings['funding_company'] = request.form.get('funding_company', 'None')
    return index()

@app.route('/remove_symbol', methods=['POST'])
def remove_symbol():
    global bot_settings
    data = request.get_json()
    symbol = data.get('symbol', '').upper()
    if symbol in bot_settings['symbols']:
        bot_settings['symbols'].remove(symbol)
    return jsonify({"status": "success"})

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
        quantity = data.get('quantity', bot_settings['default_quantity'])
        
        if client and action in ['BUY', 'SELL']:
            price = float(client.get_symbol_ticker(symbol=symbol)['price'])
            result = execute_order_with_risk(symbol, action)
            if result:
                trades.append({
                    'time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    'type': action,
                    'symbol': symbol,
                    'price': price,
                    'quantity': quantity,
                    'stop_loss': result.get('stop_loss') if result else None,
                    'take_profit': result.get('take_profit') if result else None
                })
                total_trades += 1
                return jsonify({"status": "success"}), 200
    except Exception as e:
        logging.error(f"❌ خطأ: {e}")
    return jsonify({"status": "error"}), 400

# =============================================
# 8. تشغيل الخادم
# =============================================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
import os
from flask import Flask, request, jsonify, render_template_string
from binance.client import Client
from datetime import datetime
import logging
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

# ... باقي الكود (routes, functions, etc.)

# =============================================
# أخبار Investing.com (تمت الإضافة في النهاية)
# =============================================
import feedparser

def get_investing_news():
    try:
        url = 'https://www.investing.com/rss/news_14.rss'
        feed = feedparser.parse(url)
        news_list = []
        for entry in feed.entries[:10]:
            news_list.append({
                'title': entry.title,
                'summary': entry.summary[:200] if hasattr(entry, 'summary') else '',
                'date': entry.get('published', ''),
                'link': entry.get('link', '')
            })
        return news_list
    except:
        return []

def has_important_news():
    news = get_investing_news()
    keywords = ['fed', 'interest', 'cpi', 'nonfarm', 'gdp', 'rate']
    for item in news:
        title = item['title'].lower()
        for word in keywords:
            if word in title:
                return True, item['title']
    return False, None

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
