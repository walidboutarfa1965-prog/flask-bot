from flask import Flask, render_template_string, jsonify, request
import os
import time
import threading
import logging
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from dotenv import load_dotenv
import requests
import feedparser

# ============================================================
# 📦 استيراد MetaTrader5
# ============================================================

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
    print("✅ تم استيراد MetaTrader5 بنجاح")
except ImportError:
    MT5_AVAILABLE = False
    print("❌ MetaTrader5 غير مثبت")
    mt5 = None

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# ============================================================
# 🔑 بيانات الاتصال - 👈 عدّل هنا
# ============================================================

MT5_ACCOUNT = 262946340
MT5_PASSWORD = "Mama1965."
MT5_SERVER = "Exness-MT5Trial16"

# ============================================================
# 🔗 حالة الاتصالات
# ============================================================

mt5_connected = False
investing_connected = False
exness_connected = False

account_balance = 0.0
account_equity = 0.0
open_positions = []
trade_history_list = []

# ============================================================
# 🔌 دوال الاتصال
# ============================================================

def connect_mt5():
    """الاتصال بـ MetaTrader 5"""
    global mt5_connected, exness_connected, account_balance, account_equity, open_positions, trade_history_list
    
    if not MT5_AVAILABLE:
        mt5_connected = False
        exness_connected = False
        return False
    
    try:
        # إنهاء أي اتصال سابق
        mt5.shutdown()
        time.sleep(1)
        
        # تهيئة الاتصال
        if not mt5.initialize():
            logger.error(f"❌ فشل تهيئة MT5: {mt5.last_error()}")
            mt5_connected = False
            exness_connected = False
            return False
        
        # تسجيل الدخول
        if not mt5.login(MT5_ACCOUNT, password=MT5_PASSWORD, server=MT5_SERVER):
            logger.error(f"❌ فشل تسجيل الدخول: {mt5.last_error()}")
            mt5_connected = False
            exness_connected = False
            return False
        
        mt5_connected = True
        exness_connected = True
        logger.info("✅ تم الاتصال بـ MT5 و Exness بنجاح!")
        
        # جلب معلومات الحساب
        account_info = mt5.account_info()
        if account_info:
            account_balance = account_info.balance
            account_equity = account_info.equity
            logger.info(f"💰 الرصيد: {account_balance:.2f} | Equity: {account_equity:.2f}")
        
        # جلب الصفقات المفتوحة
        update_positions()
        update_history()
        
        return True
        
    except Exception as e:
        logger.error(f"❌ خطأ في الاتصال: {e}")
        mt5_connected = False
        exness_connected = False
        return False

def update_positions():
    """تحديث الصفقات المفتوحة"""
    global open_positions
    open_positions = []
    if mt5_connected:
        try:
            positions = mt5.positions_get()
            if positions:
                for pos in positions:
                    open_positions.append({
                        'symbol': pos.symbol,
                        'type': 'BUY' if pos.type == 0 else 'SELL',
                        'entry_price': pos.price_open,
                        'current_price': pos.price_current,
                        'profit': pos.profit,
                        'volume': pos.volume,
                        'stop_loss': pos.sl,
                        'take_profit': pos.tp,
                    })
        except Exception as e:
            logger.error(f"❌ خطأ في جلب الصفقات: {e}")

def update_history():
    """تحديث سجل الصفقات"""
    global trade_history_list
    trade_history_list = []
    if mt5_connected:
        try:
            from_date = datetime.now() - timedelta(days=30)
            deals = mt5.history_deals_get(from_date, datetime.now())
            if deals:
                for deal in deals[-20:]:
                    trade_history_list.append({
                        'time': datetime.fromtimestamp(deal.time).strftime('%Y-%m-%d %H:%M'),
                        'symbol': deal.symbol,
                        'type': 'BUY' if deal.type == 0 else 'SELL',
                        'price': deal.price,
                        'volume': deal.volume,
                        'profit': deal.profit,
                    })
        except Exception as e:
            logger.error(f"❌ خطأ في جلب السجل: {e}")

def check_investing():
    """التحقق من اتصال Investing.com"""
    global investing_connected
    try:
        url = 'https://www.investing.com/rss/news_14.rss'
        response = requests.get(url, timeout=5)
        investing_connected = response.status_code == 200
        if investing_connected:
            logger.info("✅ Investing.com متصل")
        else:
            logger.warning("⚠️ Investing.com غير متصل")
    except:
        investing_connected = False
        logger.warning("⚠️ Investing.com غير متصل")

def fetch_news():
    """جلب الأخبار من Investing.com"""
    try:
        url = 'https://www.investing.com/rss/news_14.rss'
        feed = feedparser.parse(url)
        news = []
        for entry in feed.entries[:5]:
            news.append({
                'title': entry.title,
                'date': entry.get('published', datetime.now().strftime('%Y-%m-%d %H:%M')),
            })
        return news
    except:
        return [{'title': 'تعذر جلب الأخبار', 'date': datetime.now().strftime('%Y-%m-%d %H:%M')}]

# ============================================================
# 📊 تحليل السوق (بيانات حقيقية)
# ============================================================

def get_market_analysis():
    """تحليل السوق باستخدام بيانات MT5"""
    if not mt5_connected:
        return {
            'trend': 'غير متصل',
            'signal': 'NEUTRAL',
            'confidence': 0,
            'reason': 'MT5 غير متصل'
        }
    
    try:
        rates = mt5.copy_rates_from_pos("EURUSD", mt5.TIMEFRAME_H1, 0, 100)
        if rates is None or len(rates) < 50:
            return {'trend': 'Sideways', 'signal': 'NEUTRAL', 'confidence': 0, 'reason': 'بيانات غير كافية'}
        
        df = pd.DataFrame(rates)
        close = df['close']
        ema_50 = close.ewm(span=50).mean().iloc[-1]
        ema_200 = close.ewm(span=200).mean().iloc[-1]
        last = close.iloc[-1]
        
        if last > ema_50 > ema_200:
            return {'trend': 'Uptrend', 'signal': 'BUY', 'confidence': 70, 'reason': 'اتجاه صاعد قوي'}
        elif last < ema_50 < ema_200:
            return {'trend': 'Downtrend', 'signal': 'SELL', 'confidence': 70, 'reason': 'اتجاه هابط قوي'}
        else:
            return {'trend': 'Sideways', 'signal': 'NEUTRAL', 'confidence': 30, 'reason': 'السوق جانبي'}
            
    except Exception as e:
        return {'trend': 'خطأ', 'signal': 'NEUTRAL', 'confidence': 0, 'reason': str(e)[:50]}

# ============================================================
# 🎨 واجهة المستخدم
# ============================================================

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ar">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🤖 Smart Trading Bot</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: #0a0e17;
            color: #e0e0e0;
            padding: 20px;
            min-height: 100vh;
        }
        .container { max-width: 1400px; margin: 0 auto; }

        /* Header */
        .header {
            background: linear-gradient(135deg, #111927, #0a0e17);
            padding: 20px 30px;
            border-radius: 16px;
            border: 1px solid #1a2a3a;
            margin-bottom: 25px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            flex-wrap: wrap;
            gap: 15px;
        }
        .header h1 { color: #00d4ff; font-size: 28px; font-weight: 700; }
        .header .badge {
            background: #00d4ff20;
            color: #00d4ff;
            padding: 4px 15px;
            border-radius: 20px;
            font-size: 13px;
            border: 1px solid #00d4ff40;
        }
        .header .status-badge {
            padding: 8px 20px;
            border-radius: 25px;
            font-weight: 600;
            font-size: 14px;
        }
        .status-online { background: #00e67620; color: #00e676; border: 1px solid #00e67640; }
        .status-offline { background: #ff525220; color: #ff5252; border: 1px solid #ff525240; }

        /* Connections Bar */
        .connections-bar {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 12px;
            margin-bottom: 25px;
        }
        .connection-item {
            background: #111927;
            padding: 14px 20px;
            border-radius: 12px;
            border: 1px solid #1a2a3a;
            display: flex;
            justify-content: space-between;
            align-items: center;
            transition: all 0.3s;
        }
        .connection-item:hover { border-color: #2a3a4a; transform: translateY(-2px); }
        .connection-item .left { display: flex; align-items: center; gap: 10px; }
        .connection-item .icon { font-size: 22px; }
        .connection-item .name { font-weight: 500; color: #e0e0e0; }
        .status-connected {
            background: #00e67620;
            color: #00e676;
            padding: 4px 12px;
            border-radius: 15px;
            border: 1px solid #00e67640;
        }
        .status-disconnected {
            background: #ff525220;
            color: #ff5252;
            padding: 4px 12px;
            border-radius: 15px;
            border: 1px solid #ff525240;
        }

        /* Stats */
        .stats {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
            gap: 15px;
            margin-bottom: 25px;
        }
        .stat-card {
            background: #111927;
            padding: 18px 20px;
            border-radius: 12px;
            border: 1px solid #1a2a3a;
            text-align: center;
        }
        .stat-card .label { color: #7a8a9e; font-size: 13px; margin-bottom: 6px; }
        .stat-card .value { font-size: 26px; font-weight: 700; }
        .value-blue { color: #00d4ff; }
        .value-green { color: #00e676; }
        .value-gold { color: #ffd700; }
        .value-red { color: #ff5252; }

        /* Sections */
        .section {
            background: #111927;
            padding: 20px 25px;
            border-radius: 12px;
            border: 1px solid #1a2a3a;
            margin-bottom: 20px;
        }
        .section h2 {
            color: #00d4ff;
            font-size: 18px;
            margin-bottom: 15px;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .section h2 .badge-sm {
            font-size: 12px;
            background: #1a2a3a;
            padding: 2px 12px;
            border-radius: 15px;
            color: #7a8a9e;
        }
        .analysis-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
        }
        .analysis-item {
            background: #0d1520;
            padding: 15px;
            border-radius: 8px;
            border: 1px solid #1a2a3a;
        }
        .analysis-item .label {
            color: #7a8a9e;
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 1px;
        }
        .analysis-item .value {
            font-size: 18px;
            font-weight: 600;
            margin-top: 5px;
        }
        .signal-buy { color: #00e676; }
        .signal-sell { color: #ff5252; }
        .signal-neutral { color: #ffd700; }

        /* Buttons */
        .btn {
            padding: 10px 22px;
            border: none;
            border-radius: 8px;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s;
            font-size: 14px;
        }
        .btn:hover { transform: scale(1.02); opacity: 0.9; }
        .btn-stop { background: #ff1744; color: #fff; }
        .btn-start { background: #00e676; color: #0a0e17; }
        .btn-primary { background: #00d4ff; color: #0a0e17; }
        .btn-group { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }

        /* Tables */
        table { width: 100%; border-collapse: collapse; }
        th {
            text-align: left;
            padding: 12px;
            color: #7a8a9e;
            border-bottom: 2px solid #1a2a3a;
            font-size: 12px;
            text-transform: uppercase;
        }
        td { padding: 12px; border-bottom: 1px solid #1a2a3a; font-size: 14px; }
        .buy { color: #00e676; }
        .sell { color: #ff5252; }
        .profit-positive { color: #00e676; }
        .profit-negative { color: #ff5252; }

        /* News */
        .news-item {
            padding: 12px 15px;
            border-left: 3px solid #00d4ff;
            background: #0d1520;
            margin-bottom: 8px;
            border-radius: 4px;
        }
        .news-item .date { color: #7a8a9e; font-size: 12px; margin-top: 4px; }

        /* Footer */
        .footer {
            text-align: center;
            color: #4a5a6e;
            padding: 20px;
            border-top: 1px solid #1a2a3a;
            margin-top: 20px;
            font-size: 13px;
        }

        /* Responsive */
        @media (max-width: 768px) {
            .header { flex-direction: column; align-items: flex-start; }
            .connections-bar { grid-template-columns: 1fr 1fr; }
        }
        @media (max-width: 480px) {
            .connections-bar { grid-template-columns: 1fr; }
            .stats { grid-template-columns: 1fr; }
        }
    </style>
</head>
<body>
<div class="container">
    <!-- HEADER -->
    <div class="header">
        <div>
            <h1>🤖 Smart Trading Bot</h1>
            <span class="badge">SMC + ICT</span>
            <span class="badge" style="background:#00d4ff20;color:#00d4ff;border-color:#00d4ff40;">
                📊 بيانات حقيقية
            </span>
        </div>
        <div class="btn-group">
            <span class="status-badge {{ 'status-online' if bot_running else 'status-offline' }}">
                {{ '🟢 يعمل' if bot_running else '🔴 متوقف' }}
            </span>
            <form method="POST" action="/toggle_bot" style="display:inline;">
                <button type="submit" class="btn {{ 'btn-stop' if bot_running else 'btn-start' }}">
                    {{ '⏹️ إيقاف' if bot_running else '▶️ تشغيل' }}
                </button>
            </form>
            <a href="/status" class="btn btn-primary" style="text-decoration:none;display:inline-block;">📊 حالة</a>
            <form method="POST" action="/reconnect" style="display:inline;">
                <button type="submit" class="btn btn-primary">🔄 إعادة اتصال</button>
            </form>
        </div>
    </div>

    <!-- CONNECTIONS STATUS -->
    <div class="connections-bar">
        <div class="connection-item">
            <div class="left"><span class="icon">🏦</span><span class="name">Exness</span></div>
            <span class="{{ 'status-connected' if exness_connected else 'status-disconnected' }}">
                {{ '✅ متصل' if exness_connected else '❌ غير متصل' }}
            </span>
        </div>
        <div class="connection-item">
            <div class="left"><span class="icon">💻</span><span class="name">MetaTrader 5</span></div>
            <span class="{{ 'status-connected' if mt5_connected else 'status-disconnected' }}">
                {{ '✅ متصل' if mt5_connected else '❌ غير متصل' }}
            </span>
        </div>
        <div class="connection-item">
            <div class="left"><span class="icon">📰</span><span class="name">Investing.com</span></div>
            <span class="{{ 'status-connected' if investing_connected else 'status-disconnected' }}">
                {{ '✅ متصل' if investing_connected else '❌ غير متصل' }}
            </span>
        </div>
        <div class="connection-item">
            <div class="left"><span class="icon">📊</span><span class="name">TradingView</span></div>
            <span class="status-disconnected">❌ غير متصل</span>
        </div>
    </div>

    <!-- STATS -->
    <div class="stats">
        <div class="stat-card">
            <div class="label">💰 الرصيد</div>
            <div class="value value-blue">{{ "%.2f"|format(balance) }} USDT</div>
        </div>
        <div class="stat-card">
            <div class="label">📈 قيمة المحفظة</div>
            <div class="value value-gold">{{ "%.2f"|format(equity) }} USDT</div>
        </div>
        <div class="stat-card">
            <div class="label">📊 الصفقات المفتوحة</div>
            <div class="value value-gold">{{ open_positions_count }}</div>
        </div>
        <div class="stat-card">
            <div class="label">📰 مخاطر الأخبار</div>
            <div class="value value-green">0/10</div>
        </div>
    </div>

    <!-- MARKET ANALYSIS -->
    <div class="section">
        <h2>📊 تحليل السوق <span class="badge-sm">بيانات حقيقية من MT5</span></h2>
        <div class="analysis-grid">
            <div class="analysis-item">
                <div class="label">📈 الاتجاه</div>
                <div class="value">{{ analysis.trend }}</div>
            </div>
            <div class="analysis-item">
                <div class="label">🎯 الإشارة</div>
                <div class="value {{ 'signal-buy' if analysis.signal == 'BUY' else 'signal-sell' if analysis.signal == 'SELL' else 'signal-neutral' }}">
                    {{ analysis.signal }}
                </div>
            </div>
            <div class="analysis-item">
                <div class="label">📊 الثقة</div>
                <div class="value">{{ analysis.confidence }}%</div>
            </div>
            <div class="analysis-item">
                <div class="label">📋 السبب</div>
                <div class="value" style="font-size:14px;">{{ analysis.reason }}</div>
            </div>
        </div>
    </div>

    <!-- NEWS -->
    <div class="section">
        <h2>📰 آخر الأخبار <span class="badge-sm">Investing.com</span></h2>
        {% for item in news %}
        <div class="news-item">
            <div class="title">{{ item.title }}</div>
            <div class="date">{{ item.date }}</div>
        </div>
        {% endfor %}
    </div>

    <!-- OPEN POSITIONS -->
    <div class="section">
        <h2>📋 الصفقات المفتوحة</h2>
        <table>
            <thead>
                <tr>
                    <th>الزوج</th>
                    <th>النوع</th>
                    <th>سعر الدخول</th>
                    <th>السعر الحالي</th>
                    <th>وقف الخسارة</th>
                    <th>جني الربح</th>
                    <th>الربح</th>
                    <th>الحجم</th>
                </tr>
            </thead>
            <tbody>
                {% for pos in open_positions %}
                <tr>
                    <td>{{ pos.symbol }}</td>
                    <td class="{{ 'buy' if pos.type == 'BUY' else 'sell' }}">{{ pos.type }}</td>
                    <td>{{ "%.5f"|format(pos.entry_price) }}</td>
                    <td>{{ "%.5f"|format(pos.current_price) }}</td>
                    <td>{{ "%.5f"|format(pos.stop_loss) if pos.stop_loss else '-' }}</td>
                    <td>{{ "%.5f"|format(pos.take_profit) if pos.take_profit else '-' }}</td>
                    <td class="{{ 'profit-positive' if pos.profit > 0 else 'profit-negative' }}">{{ "%.2f"|format(pos.profit) }}</td>
                    <td>{{ pos.volume }}</td>
                </tr>
                {% else %}
                <tr>
                    <td colspan="8" style="text-align:center;color:#4a5a6e;">لا توجد صفقات مفتوحة</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>

    <!-- TRADE HISTORY -->
    <div class="section">
        <h2>📋 سجل الصفقات <span class="badge-sm">آخر 20 صفقة</span></h2>
        <table>
            <thead>
                <tr>
                    <th>الوقت</th>
                    <th>الزوج</th>
                    <th>النوع</th>
                    <th>السعر</th>
                    <th>الحجم</th>
                    <th>الربح</th>
                </tr>
            </thead>
            <tbody>
                {% for trade in trade_history %}
                <tr>
                    <td>{{ trade.time }}</td>
                    <td>{{ trade.symbol }}</td>
                    <td class="{{ 'buy' if trade.type == 'BUY' else 'sell' }}">{{ trade.type }}</td>
                    <td>{{ "%.5f"|format(trade.price) }}</td>
                    <td>{{ trade.volume }}</td>
                    <td class="{{ 'profit-positive' if trade.profit > 0 else 'profit-negative' }}">{{ "%.2f"|format(trade.profit) }}</td>
                </tr>
                {% else %}
                <tr>
                    <td colspan="6" style="text-align:center;color:#4a5a6e;">لا توجد صفقات سابقة</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>

    <!-- FOOTER -->
    <div class="footer">
        🚀 Smart Trading Bot | SMC + ICT | بيانات حقيقية من Exness MT5 | Investing.com
    </div>
</div>
</body>
</html>
"""

# ============================================================
# 🚀 المسارات (Routes)
# ============================================================

bot_running = True

@app.route('/')
def index():
    """الصفحة الرئيسية"""
    global account_balance, account_equity, open_positions, trade_history_list
    
    # تحديث البيانات إذا كان MT5 متصلاً
    if mt5_connected:
        try:
            account_info = mt5.account_info()
            if account_info:
                account_balance = account_info.balance
                account_equity = account_info.equity
            update_positions()
            update_history()
        except:
            pass
    
    # تحليل السوق
    analysis = get_market_analysis()
    
    # جلب الأخبار
    news = fetch_news()
    
    return render_template_string(
        HTML_TEMPLATE,
        mt5_connected=mt5_connected,
        exness_connected=exness_connected,
        investing_connected=investing_connected,
        bot_running=bot_running,
        balance=account_balance,
        equity=account_equity,
        open_positions_count=len(open_positions),
        open_positions=open_positions,
        trade_history=trade_history_list,
        analysis=analysis,
        news=news
    )

@app.route('/toggle_bot', methods=['POST'])
def toggle_bot():
    global bot_running
    bot_running = not bot_running
    return index()

@app.route('/status')
def status():
    return jsonify({
        'mt5_connected': mt5_connected,
        'exness_connected': exness_connected,
        'investing_connected': investing_connected,
        'bot_running': bot_running,
        'balance': account_balance,
        'equity': account_equity,
        'open_trades': len(open_positions)
    })

@app.route('/reconnect', methods=['POST'])
def reconnect():
    """إعادة الاتصال بجميع المنصات"""
    connect_mt5()
    check_investing()
    return index()

# ============================================================
# 🚀 تشغيل الخادم
# ============================================================

if __name__ == '__main__':
    print("=" * 70)
    print("🚀 SMART TRADING BOT - بيانات حقيقية")
    print("=" * 70)
    print(f"📌 حساب Exness: {MT5_ACCOUNT}")
    print(f"📌 الخادم: {MT5_SERVER}")
    print("=" * 70)
    
    # محاولة الاتصال
    connect_mt5()
    check_investing()
    
    print("\n📊 حالة الاتصالات:")
    print(f"   🏦 Exness: {'✅ متصل' if exness_connected else '❌ غير متصل'}")
    print(f"   💻 MT5: {'✅ متصل' if mt5_connected else '❌ غير متصل'}")
    print(f"   📰 Investing.com: {'✅ متصل' if investing_connected else '❌ غير متصل'}")
    
    if mt5_connected:
        print(f"\n💰 الرصيد: {account_balance:.2f} USDT")
        print(f"📈 قيمة المحفظة: {account_equity:.2f} USDT")
        print(f"📊 الصفقات المفتوحة: {len(open_positions)}")
    
    print("=" * 70)
    
    port = int(os.environ.get('PORT', 5000))
    print(f"🌐 الخادم يعمل على: http://localhost:{port}")
    print("=" * 70)
    
    app.run(host='0.0.0.0', port=port, debug=False)
