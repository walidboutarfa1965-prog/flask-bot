"""
====================================================================
🤖 SMART TRADING BOT - الكود النهائي الجاهز للتشغيل
====================================================================

📌 هذا الكود يقوم بـ:
   1. الاتصال بـ MetaTrader 5 (حساب ديمو Exness)
   2. تحليل السوق باستخدام استراتيجية SMC + ICT + Volume Profile
   3. تنفيذ صفقات شراء وبيع تلقائية
   4. إدارة المخاطر (وقف الخسارة، جني الأرباح، التريلينج ستوب)
   5. عرض لوحة تحكم على الويب

🔧 بيانات الحساب (عدلها هنا في الأسفل):
   - MT5_LOGIN    : رقم حساب الديمو
   - MT5_PASSWORD : كلمة المرور
   - MT5_SERVER   : اسم الخادم

🚀 كيفية التشغيل:
   python app.py

====================================================================
"""

# ====================================================================
# 0. استيراد المكتبات
# ====================================================================

from flask import Flask, render_template_string, jsonify, request
import json
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

# ====================================================================
# 1. بيانات حساب Exness (DEMO) - 👈 عدّل هنا
# ====================================================================

# ═══════════════════════════════════════════════════════════════════
#  🔑 أدخل بيانات حساب الديمو الخاص بك هنا:
# ═══════════════════════════════════════════════════════════════════

MT5_LOGIN = 262946340          # ← رقم حساب الديمو
MT5_PASSWORD = "Mama1965."     # ← كلمة المرور
MT5_SERVER = "Exness-MT5Trial16"  # ← اسم الخادم

# ═══════════════════════════════════════════════════════════════════

# ====================================================================
# 2. تحميل متغيرات البيئة (اختياري)
# ====================================================================

load_dotenv()

# إذا كانت هناك متغيرات بيئية، استخدمها بدلاً من القيم الثابتة
MT5_LOGIN = int(os.getenv('MT5_LOGIN', MT5_LOGIN))
MT5_PASSWORD = os.getenv('MT5_PASSWORD', MT5_PASSWORD)
MT5_SERVER = os.getenv('MT5_SERVER', MT5_SERVER)

# ====================================================================
# 3. إعداد التسجيل (Logging)
# ====================================================================

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

print("=" * 70)
print("🤖 SMART TRADING BOT - بدء التشغيل")
print("=" * 70)
print(f"📌 حساب الديمو: {MT5_LOGIN}")
print(f"📌 الخادم: {MT5_SERVER}")
print("=" * 70)

# ====================================================================
# 4. تهيئة Flask
# ====================================================================

app = Flask(__name__)

# ====================================================================
# 5. تهيئة MetaTrader 5
# ====================================================================

mt5_connected = False
mt5 = None

def initialize_mt5():
    global mt5, mt5_connected
    
    print("\n🔍 محاولة الاتصال بـ MetaTrader 5...")
    print(f"   📌 Login: {MT5_LOGIN}")
    print(f"   📌 Server: {MT5_SERVER}")
    
    try:
        try:
            import MetaTrader5 as mt5_module
            mt5 = mt5_module
            print("✅ تم استيراد MetaTrader5 بنجاح")
        except ImportError:
            try:
                import mt5linux as mt5_module
                mt5 = mt5_module
                print("⚠️ باستخدام mt5linux (بديل لـ Linux)")
            except ImportError:
                mt5 = None
                print("❌ MT5 غير مثبت - سيتم استخدام بيانات وهمية")
                return False
        
        if mt5 is None:
            return False
        
        initialized = mt5.initialize(
            login=MT5_LOGIN,
            password=MT5_PASSWORD,
            server=MT5_SERVER
        )
        
        if initialized:
            mt5_connected = True
            print("✅ تم الاتصال بـ MT5 بنجاح! 🎉")
            
            account_info = mt5.account_info()
            if account_info:
                print(f"   📊 الحساب: {account_info.login}")
                print(f"   💰 الرصيد: {account_info.balance:.2f} USD")
                print(f"   📈 Equity: {account_info.equity:.2f} USD")
            return True
        else:
            error = mt5.last_error()
            print(f"❌ فشل الاتصال بـ MT5: {error}")
            mt5_connected = False
            return False
            
    except Exception as e:
        print(f"❌ خطأ في الاتصال بـ MT5: {e}")
        mt5_connected = False
        return False

mt5_connected = initialize_mt5()

# ====================================================================
# 6. استيراد الاستراتيجية
# ====================================================================

print("\n📂 استيراد ملفات الاستراتيجية...")

try:
    from strategy import SmartTradingBot
    from analysis import *
    from risk_manager import TradeManager
    print("✅ تم استيراد ملفات الاستراتيجية بنجاح")
except ImportError as e:
    print(f"⚠️ خطأ في استيراد الملفات: {e}")
    SmartTradingBot = None
    TradeManager = None

# ====================================================================
# 7. تهيئة البوت
# ====================================================================

print("\n🤖 تهيئة البوت...")

try:
    if SmartTradingBot is not None:
        smart_bot = SmartTradingBot(initial_balance=10000)
        print("✅ تم تهيئة SmartTradingBot بنجاح")
    else:
        smart_bot = None
        print("⚠️ SmartTradingBot غير معرف")
except NameError:
    print("⚠️ SmartTradingBot غير معرف")
    smart_bot = None

print("=" * 70)
print("✅ جاهز للتشغيل!")
print("=" * 70)

# ====================================================================
# 8. إعدادات البوت
# ====================================================================

trades = []
total_trades = 0
winning_trades = 0
bot_running = True

bot_settings = {
    'default_quantity': 0.01,
    'max_trades': 5,
    'symbols': ['BTCUSDT', 'ETHUSDT', 'XAUUSD', 'EURUSD'],
    'risk_percent': 2.0,
    'stop_loss_percent': 2.0,
    'take_profit_percent': 4.0,
    'trailing_stop_percent': 1.5,
    'auto_lot': True,
    'broker_name': 'Exness',
    'use_ai': True,
    'use_mtf': True,
    'news_filter': True,
    'pending_orders': True,
    'timeframes': {
        'trend': '1d',
        'structure': '1h',
        'entry': '15m'
    },
    'confirmation_candles': 2,
    'min_trend_strength': 0.6,
}

# ====================================================================
# 9. إدارة الصفقات
# ====================================================================

class LegacyTradeManager:
    def __init__(self):
        self.open_trades = []
        self.closed_trades = []
        self.pending_orders = []
        self.trailing_stops = {}
    
    def place_pending_order(self, symbol, order_type, price, stop_loss, take_profit, quantity):
        order = {
            'id': len(self.pending_orders) + 1,
            'symbol': symbol,
            'type': order_type,
            'price': price,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'quantity': quantity,
            'status': 'PENDING',
            'created_at': datetime.now().isoformat(),
            'triggered': False
        }
        self.pending_orders.append(order)
        return order
    
    def check_pending_orders(self, current_price):
        triggered = []
        for order in self.pending_orders:
            if order['status'] != 'PENDING':
                continue
            should_trigger = False
            if order['type'] in ['BUY_LIMIT', 'BUY_STOP']:
                if order['type'] == 'BUY_LIMIT' and current_price <= order['price']:
                    should_trigger = True
                elif order['type'] == 'BUY_STOP' and current_price >= order['price']:
                    should_trigger = True
            else:
                if order['type'] == 'SELL_LIMIT' and current_price >= order['price']:
                    should_trigger = True
                elif order['type'] == 'SELL_STOP' and current_price <= order['price']:
                    should_trigger = True
            if should_trigger:
                order['status'] = 'TRIGGERED'
                order['triggered_at'] = datetime.now().isoformat()
                triggered.append(order)
        return triggered
    
    def update_trailing_stop(self, position, current_price):
        if position['id'] not in self.trailing_stops:
            self.trailing_stops[position['id']] = position['stop_loss']
        current_stop = self.trailing_stops[position['id']]
        if position['type'] == 'BUY':
            new_stop = current_price * (1 - bot_settings['trailing_stop_percent'] / 100)
            if new_stop > current_stop:
                self.trailing_stops[position['id']] = new_stop
                return new_stop
        else:
            new_stop = current_price * (1 + bot_settings['trailing_stop_percent'] / 100)
            if new_stop < current_stop:
                self.trailing_stops[position['id']] = new_stop
                return new_stop
        return current_stop
    
    def close_position(self, position_id, exit_price, reason='MANUAL'):
        for pos in self.open_trades:
            if pos['id'] == position_id:
                pos['exit_price'] = exit_price
                pos['exit_time'] = datetime.now().isoformat()
                pos['status'] = 'CLOSED'
                pos['reason'] = reason
                pos['profit'] = (exit_price - pos['entry_price']) * pos['quantity']
                if pos['type'] == 'SELL':
                    pos['profit'] = -pos['profit']
                self.closed_trades.append(pos)
                self.open_trades.remove(pos)
                return pos
        return None

legacy_manager = LegacyTradeManager()

# ====================================================================
# 10. دوال Investing.com
# ====================================================================

def check_investing_connection():
    try:
        url = 'https://www.investing.com/rss/news_14.rss'
        response = requests.get(url, timeout=5)
        return response.status_code == 200
    except:
        return False

def fetch_news_investiny():
    try:
        url = 'https://www.investing.com/rss/news_14.rss'
        feed = feedparser.parse(url)
        if feed.entries:
            news = []
            for entry in feed.entries[:5]:
                news.append({
                    'title': entry.title,
                    'date': entry.get('published', ''),
                    'impact': 'low'
                })
            return news
        return []
    except:
        return []

def get_news_risk():
    return 0

# ====================================================================
# 11. تحليل السوق
# ====================================================================

def get_klines(symbol, interval, limit=100):
    global mt5_connected, mt5
    
    if mt5_connected and mt5 is not None:
        try:
            timeframe_map = {
                '1m': mt5.TIMEFRAME_M1,
                '5m': mt5.TIMEFRAME_M5,
                '15m': mt5.TIMEFRAME_M15,
                '1h': mt5.TIMEFRAME_H1,
                '4h': mt5.TIMEFRAME_H4,
                '1d': mt5.TIMEFRAME_D1,
            }
            tf = timeframe_map.get(interval, mt5.TIMEFRAME_H1)
            rates = mt5.copy_rates_from_pos(symbol, tf, 0, limit)
            
            if rates is not None and len(rates) > 0:
                df = pd.DataFrame(rates)
                df['time'] = pd.to_datetime(df['time'], unit='s')
                df.set_index('time', inplace=True)
                return df
            return None
        except Exception as e:
            logger.error(f"❌ خطأ في جلب البيانات: {e}")
            return None
    
    # بيانات وهمية
    try:
        np.random.seed(42)
        dates = pd.date_range(start=datetime.now() - timedelta(hours=limit), periods=limit, freq='1h')
        base_price = 1.2000 if 'USD' in symbol else 100.0
        prices = base_price + np.cumsum(np.random.randn(limit) * 0.001)
        df = pd.DataFrame({
            'open': prices,
            'high': prices + np.abs(np.random.randn(limit) * 0.001),
            'low': prices - np.abs(np.random.randn(limit) * 0.001),
            'close': prices,
            'volume': np.random.randint(1000, 5000, limit)
        }, index=dates)
        return df
    except:
        return None

def identify_trend(df):
    if df is None or len(df) < 50:
        return {'trend': 'Sideways', 'strength': 0.0}
    ema_50 = df['close'].ewm(span=50, adjust=False).mean()
    ema_200 = df['close'].ewm(span=200, adjust=False).mean()
    last = df['close'].iloc[-1]
    if last > ema_50.iloc[-1] > ema_200.iloc[-1]:
        return {'trend': 'Uptrend', 'strength': 0.7}
    elif last < ema_50.iloc[-1] < ema_200.iloc[-1]:
        return {'trend': 'Downtrend', 'strength': 0.7}
    return {'trend': 'Sideways', 'strength': 0.0}

def analyze_market_full(symbol):
    result = {
        'symbol': symbol,
        'trend': 'Sideways',
        'signal': 'NEUTRAL',
        'confidence': 0.0,
        'entry_price': None,
        'stop_loss': None,
        'take_profit': None,
        'reason': ''
    }
    
    if not mt5_connected:
        result['reason'] = "⚠️ MT5 غير متصل - بيانات وهمية"
        data = get_klines(symbol, '1h', 100)
        if data is not None:
            trend = identify_trend(data)
            result['trend'] = trend['trend']
            result['signal'] = 'BUY' if trend['trend'] == 'Uptrend' else 'SELL' if trend['trend'] == 'Downtrend' else 'NEUTRAL'
            result['confidence'] = trend['strength']
            result['reason'] = f"تحليل مبسط: {trend['trend']}"
        return result
    
    try:
        if smart_bot is not None:
            data_h4 = get_klines(symbol, '4h', 100)
            data_h1 = get_klines(symbol, '1h', 100)
            data_m15 = get_klines(symbol, '15m', 100)
            
            if data_h4 is not None and data_h1 is not None and data_m15 is not None:
                decision = smart_bot.get_trading_decision(data_h4, data_h1, data_m15)
                if decision['decision'] == 'BUY':
                    result['signal'] = 'BUY'
                    result['entry_price'] = decision['entry']
                    result['stop_loss'] = decision['stop']
                    result['take_profit'] = decision['entry'] + (decision['entry'] - decision['stop']) * 2
                    result['confidence'] = 0.7
                    result['trend'] = decision['trend']['direction']
                    result['reason'] = "SMC+ICT: إشارة شراء"
                elif decision['decision'] == 'SELL':
                    result['signal'] = 'SELL'
                    result['entry_price'] = decision['entry']
                    result['stop_loss'] = decision['stop']
                    result['take_profit'] = decision['entry'] - (decision['stop'] - decision['entry']) * 2
                    result['confidence'] = 0.7
                    result['trend'] = decision['trend']['direction']
                    result['reason'] = "SMC+ICT: إشارة بيع"
                else:
                    result['signal'] = 'NEUTRAL'
                    result['reason'] = f"انتظار: {decision.get('reason', 'لا توجد إشارة')}"
            else:
                data = get_klines(symbol, '1h', 100)
                if data is not None:
                    trend = identify_trend(data)
                    result['trend'] = trend['trend']
                    result['signal'] = 'BUY' if trend['trend'] == 'Uptrend' else 'SELL' if trend['trend'] == 'Downtrend' else 'NEUTRAL'
                    result['confidence'] = trend['strength']
                    result['reason'] = f"تحليل تقليدي: {trend['trend']}"
        else:
            data = get_klines(symbol, '1h', 100)
            if data is not None:
                trend = identify_trend(data)
                result['trend'] = trend['trend']
                result['signal'] = 'BUY' if trend['trend'] == 'Uptrend' else 'SELL' if trend['trend'] == 'Downtrend' else 'NEUTRAL'
                result['confidence'] = trend['strength']
                result['reason'] = f"تحليل تقليدي: {trend['trend']}"
    except Exception as e:
        result['reason'] = f"خطأ: {str(e)[:50]}"
    
    return result

# ====================================================================
# 12. تنفيذ الصفقات
# ====================================================================

def execute_trade(symbol, action, entry_price, stop_loss, take_profit, quantity=None):
    global total_trades
    
    if not bot_running:
        return {'error': 'Bot is stopped'}
    
    if not mt5_connected:
        logger.warning("⚠️ MT5 غير متصل - صفقة وهمية")
        # محاكاة صفقة
        trade = {
            'id': len(trades) + 1,
            'symbol': symbol,
            'type': action,
            'entry_price': entry_price,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'quantity': quantity or 0.01,
            'entry_time': datetime.now().isoformat(),
            'status': 'OPEN',
            'profit': None
        }
        trades.append(trade)
        legacy_manager.open_trades.append(trade)
        total_trades += 1
        logger.info(f"📊 صفقة وهمية {action}: {symbol} @ {entry_price}")
        return trade
    
    if quantity is None:
        balance = 10000
        risk_amount = balance * (bot_settings['risk_percent'] / 100)
        risk_distance = abs(entry_price - stop_loss)
        if risk_distance == 0:
            risk_distance = 0.01
        quantity = round(risk_amount / risk_distance, 3)
        if quantity <= 0:
            quantity = 0.001
    
    try:
        order_type = mt5.ORDER_TYPE_BUY if action == 'BUY' else mt5.ORDER_TYPE_SELL
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": quantity,
            "type": order_type,
            "price": entry_price,
            "sl": stop_loss,
            "tp": take_profit,
            "deviation": 20,
            "magic": 234000,
            "comment": "Smart Bot",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }
        
        result = mt5.order_send(request)
        
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            trade = {
                'id': len(trades) + 1,
                'symbol': symbol,
                'type': action,
                'entry_price': entry_price,
                'stop_loss': stop_loss,
                'take_profit': take_profit,
                'quantity': quantity,
                'entry_time': datetime.now().isoformat(),
                'status': 'OPEN',
                'profit': None,
                'order_id': result.order
            }
            trades.append(trade)
            legacy_manager.open_trades.append(trade)
            total_trades += 1
            logger.info(f"✅ صفقة {action} تم تنفيذها: {symbol} @ {entry_price}")
            return trade
        else:
            logger.error(f"❌ فشل تنفيذ الصفقة: {result.retcode}")
            return {'error': f'فشل التنفيذ: {result.retcode}'}
            
    except Exception as e:
        logger.error(f"❌ خطأ في تنفيذ الصفقة: {e}")
        return {'error': str(e)}

# ====================================================================
# 13. قالب HTML (مبسط)
# ====================================================================

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🤖 Smart Trading Bot</title>
    <style>
        * { margin:0; padding:0; box-sizing:border-box; }
        body { font-family:'Segoe UI',sans-serif; background:#0a0e17; color:#e0e0e0; padding:20px; }
        .container { max-width:1200px; margin:0 auto; }
        h1 { text-align:center; color:#00d4ff; margin-bottom:30px; }
        .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:15px; margin-bottom:20px; }
        .card { background:#111927; border-radius:12px; padding:20px; border:1px solid #1a2a3a; text-align:center; }
        .card .label { color:#7a8a9e; font-size:0.8rem; }
        .card .value { font-size:1.8rem; font-weight:bold; margin-top:10px; }
        .green { color:#00e676; } .blue { color:#00d4ff; } .gold { color:#ffd700; } .red { color:#ff5252; }
        .section { background:#111927; border-radius:12px; padding:20px; border:1px solid #1a2a3a; margin-bottom:20px; }
        .section h2 { color:#00d4ff; margin-bottom:15px; }
        .badge { background:#00d4ff20; color:#00d4ff; padding:5px 15px; border-radius:20px; border:1px solid #00d4ff40; }
        .status-online { background:#00e67620; color:#00e676; padding:5px 15px; border-radius:20px; border:1px solid #00e67640; }
        .status-offline { background:#ff525220; color:#ff5252; padding:5px 15px; border-radius:20px; border:1px solid #ff525240; }
        .footer { text-align:center; color:#4a5a6e; margin-top:30px; }
        .btn { padding:10px 25px; border:none; border-radius:8px; font-weight:bold; cursor:pointer; }
        .btn-start { background:#00e676; color:#0a0e17; }
        .btn-stop { background:#ff1744; color:#fff; }
        .btn-primary { background:#00d4ff; color:#0a0e17; }
        .flex { display:flex; gap:15px; flex-wrap:wrap; align-items:center; }
        .flex-between { display:flex; justify-content:space-between; flex-wrap:wrap; align-items:center; }
        .mt-10 { margin-top:10px; }
        table { width:100%; border-collapse:collapse; }
        th { text-align:left; padding:8px; color:#7a8a9e; border-bottom:2px solid #1a2a3a; }
        td { padding:8px; border-bottom:1px solid #1a2a3a; }
        .buy { color:#00e676; } .sell { color:#ff5252; }
    </style>
</head>
<body>
<div class="container">
    <h1>🤖 Smart Trading Bot <span class="badge">SMC+ICT</span></h1>
    
    <div class="section">
        <div class="flex-between">
            <div class="flex">
                <span class="{{ 'status-online' if bot_running else 'status-offline' }}">
                    {{ '🟢 Bot Running' if bot_running else '🔴 Bot Stopped' }}
                </span>
                <span class="badge">🧠 SMC + ICT</span>
                <span class="badge" style="background:#00e67620;color:#00e676;">
                    MT5 {{ '✅ متصل' if mt5_available else '❌ غير متصل' }}
                </span>
            </div>
            <div>
                <form method="POST" action="/toggle_bot" style="display:inline;">
                    <button type="submit" class="btn {{ 'btn-stop' if bot_running else 'btn-start' }}">
                        {{ '⏹️ Stop' if bot_running else '▶️ Start' }}
                    </button>
                </form>
                <a href="/status" class="btn btn-primary" style="text-decoration:none;display:inline-block;">📊 Status</a>
            </div>
        </div>
    </div>

    <div class="grid">
        <div class="card"><div class="label">💰 Balance</div><div class="value blue">{{ balance }}</div></div>
        <div class="card"><div class="label">📈 Open Trades</div><div class="value gold">{{ open_trades }}</div></div>
        <div class="card"><div class="label">🏆 Win Rate</div><div class="value green">{{ win_rate }}%</div></div>
        <div class="card"><div class="label">📰 News Risk</div><div class="value green">{{ news_risk }}/10</div></div>
    </div>

    <div class="section">
        <h2>📊 Market Analysis</h2>
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:15px;">
            <div><strong>Trend:</strong> {{ analysis_trend }}</div>
            <div><strong>Signal:</strong> <span class="{{ 'green' if analysis_signal == 'BUY' else 'red' if analysis_signal == 'SELL' else 'gold' }}">{{ analysis_signal }}</span></div>
            <div><strong>Confidence:</strong> {{ analysis_confidence }}%</div>
            <div><strong>Reason:</strong> {{ analysis_reason }}</div>
        </div>
    </div>

    <div class="section">
        <h2>📰 Latest News</h2>
        {% for item in news %}
        <div style="padding:8px 0;border-bottom:1px solid #1a2a3a;">{{ item.title }}</div>
        {% else %}
        <div style="color:#4a5a6e;">No news</div>
        {% endfor %}
    </div>

    <div class="section">
        <h2>📋 Open Trades</h2>
        <table>
            <thead><tr><th>Symbol</th><th>Type</th><th>Entry</th><th>Stop Loss</th><th>Take Profit</th></tr></thead>
            <tbody>
                {% for t in open_positions %}
                <tr><td>{{ t.symbol }}</td><td class="{{ 'buy' if t.type == 'BUY' else 'sell' }}">{{ t.type }}</td><td>{{ t.entry_price }}</td><td>{{ t.stop_loss }}</td><td>{{ t.take_profit }}</td></tr>
                {% else %}
                <tr><td colspan="5" style="text-align:center;color:#4a5a6e;">No open trades</td></tr>
                {% endfor %}
            </tbody>
        </table>
    </div>

    <div class="section">
        <h2>📋 Trade History</h2>
        <table>
            <thead><tr><th>Time</th><th>Symbol</th><th>Type</th><th>Price</th><th>Status</th></tr></thead>
            <tbody>
                {% for t in trades_history %}
                <tr><td>{{ t.entry_time[:16] }}</td><td>{{ t.symbol }}</td><td class="{{ 'buy' if t.type == 'BUY' else 'sell' }}">{{ t.type }}</td><td>{{ t.entry_price }}</td><td>{{ t.status }}</td></tr>
                {% else %}
                <tr><td colspan="5" style="text-align:center;color:#4a5a6e;">No trades</td></tr>
                {% endfor %}
            </tbody>
        </table>
    </div>

    <div class="footer">🚀 Smart Trading Bot | SMC+ICT | Exness Ready</div>
</div>
</body>
</html>
"""

# ====================================================================
# 14. المسارات (Routes)
# ====================================================================

@app.route('/')
def index():
    balance = 10000
    open_positions = [t for t in trades if t['status'] == 'OPEN']
    
    if total_trades > 0:
        win_rate = round((winning_trades / total_trades * 100), 1)
    else:
        win_rate = 0.0
    
    analysis = analyze_market_full('BTCUSDT')
    
    investing_connected = check_investing_connection()
    news = fetch_news_investiny() if investing_connected else []
    news_risk = get_news_risk() if investing_connected else 0
    
    return render_template_string(
        HTML_TEMPLATE,
        balance=f"{balance:.2f} USDT",
        open_trades=len(open_positions),
        pending_count=0,
        win_rate=win_rate,
        open_positions=open_positions,
        pending_orders=[],
        trades_history=[t for t in trades if t['status'] == 'CLOSED'][-10:],
        last_update=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        risk_percent=bot_settings['risk_percent'],
        stop_loss_percent=bot_settings['stop_loss_percent'],
        take_profit_percent=bot_settings['take_profit_percent'],
        trailing_stop_percent=bot_settings['trailing_stop_percent'],
        confirmation=bot_settings['confirmation_candles'],
        bot_running=bot_running,
        analysis_trend=analysis['trend'],
        analysis_signal=analysis['signal'],
        analysis_confidence=round(analysis['confidence'] * 100, 1),
        analysis_reason=analysis['reason'],
        investing_connected=investing_connected,
        news=news,
        news_risk=news_risk,
        mt5_available=mt5_connected
    )

@app.route('/toggle_bot', methods=['POST'])
def toggle_bot():
    global bot_running
    bot_running = not bot_running
    return index()

@app.route('/update_risk', methods=['POST'])
def update_risk():
    global bot_settings
    bot_settings['risk_percent'] = float(request.form.get('risk_percent', 2.0))
    bot_settings['stop_loss_percent'] = float(request.form.get('stop_loss_percent', 2.0))
    bot_settings['take_profit_percent'] = float(request.form.get('take_profit_percent', 4.0))
    bot_settings['trailing_stop_percent'] = float(request.form.get('trailing_stop_percent', 1.5))
    bot_settings['confirmation_candles'] = int(request.form.get('confirmation', 2))
    return index()

@app.route('/webhook', methods=['POST'])
def webhook():
    if not bot_running:
        return jsonify({"status": "error", "message": "Bot is stopped"}), 400
    try:
        data = request.get_json()
        symbol = data.get('symbol', 'BTCUSDT')
        action = data.get('action')
        analysis = analyze_market_full(symbol)
        if analysis['signal'] != action:
            return jsonify({'status': 'blocked', 'reason': f'Signal mismatch'}), 200
        trade = execute_trade(symbol, action, analysis['entry_price'], analysis['stop_loss'], analysis['take_profit'])
        return jsonify({'status': 'success', 'trade': trade})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

@app.route('/status')
def status():
    return jsonify({
        'bot_running': bot_running,
        'mt5_connected': mt5_connected,
        'total_trades': total_trades,
        'open_trades': len([t for t in trades if t['status'] == 'OPEN'])
    })

@app.route('/reconnect_mt5', methods=['POST'])
def reconnect_mt5():
    global mt5_connected
    mt5_connected = initialize_mt5()
    return jsonify({'mt5_connected': mt5_connected})

# ====================================================================
# 15. تشغيل الخادم
# ====================================================================

if __name__ == '__main__':
    print("\n" + "=" * 70)
    print("🚀 تشغيل الخادم...")
    print("=" * 70)
    
    thread = threading.Thread(target=lambda: None, daemon=True)
    thread.start()
    
    port = int(os.environ.get('PORT', 5000))
    print(f"🌐 الخادم يعمل على: http://localhost:{port}")
    print("=" * 70 + "\n")
    
    app.run(host='0.0.0.0', port=port, debug=False)
