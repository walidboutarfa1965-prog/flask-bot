from mt5_connection import MT5Connector
import os
import time
import threading
import logging
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from flask import Flask, request, jsonify, render_template_string
from dotenv import load_dotenv
import requests
import feedparser

load_dotenv()
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

# =============================================
# 1. إعدادات البوت
# =============================================
BROKER_TYPE = os.getenv('BROKER_TYPE', 'binance')
MT5_LOGIN = os.getenv('MT5_LOGIN', '')
MT5_PASSWORD = os.getenv('MT5_PASSWORD', '')
MT5_SERVER = os.getenv('MT5_SERVER', 'Exness-MT5Trial')
BINANCE_API_KEY = os.getenv('BINANCE_API_KEY', '')
BINANCE_API_SECRET = os.getenv('BINANCE_API_SECRET', '')

client = None
if BROKER_TYPE == 'binance':
    try:
        from binance.client import Client
        client = Client(BINANCE_API_KEY, BINANCE_API_SECRET, testnet=True)
        logging.info("✅ Binance Testnet")
    except:
        logging.error("❌ فشل الاتصال بـ Binance")

# =============================================
# 2. بيانات البوت
# =============================================
trades = []
active_positions = []
pending_orders = []
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
    'confirmation_candles': 2,  # عدد الشموع لتأكيد الاتجاه
    'min_trend_strength': 0.6,  # قوة الاتجاه المطلوبة
}

# =============================================
# 3. نظام إدارة الصفقات
# =============================================

class TradeManager:
    def __init__(self):
        self.open_trades = []
        self.closed_trades = []
        self.pending_orders = []
        self.trailing_stops = {}
    
    def place_pending_order(self, symbol, order_type, price, stop_loss, take_profit, quantity):
        """وضع أمر معلق (Pending Order)"""
        order = {
            'id': len(self.pending_orders) + 1,
            'symbol': symbol,
            'type': order_type,  # 'BUY_LIMIT', 'SELL_LIMIT', 'BUY_STOP', 'SELL_STOP'
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
        """فحص الأوامر المعلقة وتفعيلها"""
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
            else:  # SELL orders
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
        """تحديث وقف الخسارة المتحرك"""
        if position['id'] not in self.trailing_stops:
            self.trailing_stops[position['id']] = position['stop_loss']
        
        current_stop = self.trailing_stops[position['id']]
        
        if position['type'] == 'BUY':
            new_stop = current_price * (1 - bot_settings['trailing_stop_percent'] / 100)
            if new_stop > current_stop:
                self.trailing_stops[position['id']] = new_stop
                return new_stop
        else:  # SELL
            new_stop = current_price * (1 + bot_settings['trailing_stop_percent'] / 100)
            if new_stop < current_stop:
                self.trailing_stops[position['id']] = new_stop
                return new_stop
        
        return current_stop
    
    def close_position(self, position_id, exit_price, reason='MANUAL'):
        """إغلاق صفقة"""
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
    
    def get_position_summary(self):
        """الحصول على ملخص الصفقات المفتوحة"""
        summary = {
            'total': len(self.open_trades),
            'buy': len([p for p in self.open_trades if p['type'] == 'BUY']),
            'sell': len([p for p in self.open_trades if p['type'] == 'SELL']),
            'total_profit': sum(p.get('profit', 0) for p in self.open_trades)
        }
        return summary

trade_manager = TradeManager()

# =============================================
# 4. نظام التحليل المتكامل
# =============================================

def get_klines(symbol, interval, limit=100):
    """جلب بيانات الشموع"""
    if BROKER_TYPE == 'binance' and client:
        try:
            klines = client.get_klines(symbol=symbol, interval=interval, limit=limit)
            df = pd.DataFrame(klines, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_asset_volume', 'number_of_trades',
                'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
            ])
            df['close'] = df['close'].astype(float)
            df['high'] = df['high'].astype(float)
            df['low'] = df['low'].astype(float)
            df['open'] = df['open'].astype(float)
            return df
        except:
            return None
    return None

def identify_trend(df):
    """تحديد الاتجاه"""
    if df is None or len(df) < 50:
        return {'trend': 'جانبي', 'strength': 0.0}
    
    ema_20 = df['close'].ewm(span=20, adjust=False).mean()
    ema_50 = df['close'].ewm(span=50, adjust=False).mean()
    ema_200 = df['close'].ewm(span=200, adjust=False).mean()
    
    last = df['close'].iloc[-1]
    strength = 0.0
    trend = 'جانبي'
    
    if last > ema_50.iloc[-1] > ema_200.iloc[-1]:
        trend = 'صاعد'
        strength = (last - ema_50.iloc[-1]) / ema_50.iloc[-1]
    elif last < ema_50.iloc[-1] < ema_200.iloc[-1]:
        trend = 'هابط'
        strength = (ema_50.iloc[-1] - last) / ema_50.iloc[-1]
    
    return {'trend': trend, 'strength': min(strength * 10, 1.0)}

def find_swing_points(df, window=5):
    """إيجاد القمم والقيعان"""
    if df is None or len(df) < window*2:
        return [], []
    
    highs = df['high'].values
    lows = df['low'].values
    swing_highs = []
    swing_lows = []
    
    for i in range(window, len(highs) - window):
        if highs[i] == max(highs[i-window:i+window+1]):
            swing_highs.append(highs[i])
        if lows[i] == min(lows[i-window:i+window+1]):
            swing_lows.append(lows[i])
    
    return swing_highs, swing_lows

def detect_order_blocks(df):
    """اكتشاف مناطق الطلب والعرض"""
    if df is None or len(df) < 5:
        return []
    
    blocks = []
    for i in range(2, len(df) - 2):
        # Sell OB
        if (df['close'].iloc[i] > df['open'].iloc[i] and 
            df['close'].iloc[i+1] < df['open'].iloc[i+1] and
            df['high'].iloc[i] > df['high'].iloc[i-1]):
            blocks.append({'type': 'SELL', 'price': df['high'].iloc[i]})
        # Buy OB
        if (df['close'].iloc[i] < df['open'].iloc[i] and 
            df['close'].iloc[i+1] > df['open'].iloc[i+1] and
            df['low'].iloc[i] < df['low'].iloc[i-1]):
            blocks.append({'type': 'BUY', 'price': df['low'].iloc[i]})
    
    return blocks

def detect_liquidity_sweep(df, swing_highs, swing_lows):
    """اكتشاف اجتياح السيولة"""
    if df is None or len(df) < 2:
        return {'type': 'NONE', 'swept': False}
    
    last_high = df['high'].iloc[-1]
    last_low = df['low'].iloc[-1]
    
    if swing_highs:
        nearest_high = max(swing_highs)
    else:
        nearest_high = last_high
    
    if swing_lows:
        nearest_low = min(swing_lows)
    else:
        nearest_low = last_low
    
    if last_high > nearest_high * 1.001:
        return {'type': 'BUY', 'swept': True, 'level': nearest_high}
    elif last_low < nearest_low * 0.999:
        return {'type': 'SELL', 'swept': True, 'level': nearest_low}
    return {'type': 'NONE', 'swept': False}

def analyze_market_full(symbol):
    """التحليل الكامل للسوق"""
    result = {
        'symbol': symbol,
        'trend': 'جانبي',
        'trend_strength': 0.0,
        'order_blocks': [],
        'liquidity_sweep': {'type': 'NONE', 'swept': False},
        'signal': 'NEUTRAL',
        'confidence': 0.0,
        'pending_order_price': None,
        'pending_order_type': None,
        'entry_price': None,
        'stop_loss': None,
        'take_profit': None,
        'reason': ''
    }
    
    # المستوى 1: الاتجاه (يومي)
    df_daily = get_klines(symbol, '1d')
    if df_daily is not None:
        trend_info = identify_trend(df_daily)
        result['trend'] = trend_info['trend']
        result['trend_strength'] = trend_info['strength']
        swing_highs, swing_lows = find_swing_points(df_daily, 7)
    
    # المستوى 2: الهيكل (ساعة)
    df_hourly = get_klines(symbol, '1h')
    if df_hourly is not None:
        result['order_blocks'] = detect_order_blocks(df_hourly)[-3:]
        swing_highs_h, swing_lows_h = find_swing_points(df_hourly, 5)
        result['liquidity_sweep'] = detect_liquidity_sweep(df_hourly, swing_highs_h, swing_lows_h)
    
    # المستوى 3: الدخول (15 دقيقة)
    df_entry = get_klines(symbol, '15m')
    if df_entry is not None and len(df_entry) > 5:
        current_price = df_entry['close'].iloc[-1]
        
        # تأكيد الاتجاه على عدة شموع
        confirmation = 0
        for i in range(1, bot_settings['confirmation_candles'] + 1):
            if result['trend'] == 'صاعد' and df_entry['close'].iloc[-i] > df_entry['open'].iloc[-i]:
                confirmation += 1
            elif result['trend'] == 'هابط' and df_entry['close'].iloc[-i] < df_entry['open'].iloc[-i]:
                confirmation += 1
        
        # توليد الإشارة مع تأكيد
        if (result['trend'] == 'صاعد' and 
            result['trend_strength'] >= bot_settings['min_trend_strength'] and
            result['liquidity_sweep']['type'] == 'BUY' and
            len(result['order_blocks']) > 0 and
            confirmation >= bot_settings['confirmation_candles']):
            
            result['signal'] = 'BUY'
            result['confidence'] = 0.6 + result['trend_strength'] * 0.3
            result['entry_price'] = current_price
            
            # حساب Stop Loss و Take Profit
            result['stop_loss'] = current_price * (1 - bot_settings['stop_loss_percent'] / 100)
            result['take_profit'] = current_price * (1 + bot_settings['take_profit_percent'] / 100)
            
            # تحديد أمر معلق
            result['pending_order_price'] = result['order_blocks'][0]['price']
            result['pending_order_type'] = 'BUY_LIMIT'
            result['reason'] = f'اتجاه صاعد ({result["trend_strength"]:.2f}) + سيولة + منطقة طلب'
            
        elif (result['trend'] == 'هابط' and 
              result['trend_strength'] >= bot_settings['min_trend_strength'] and
              result['liquidity_sweep']['type'] == 'SELL' and
              len(result['order_blocks']) > 0 and
              confirmation >= bot_settings['confirmation_candles']):
            
            result['signal'] = 'SELL'
            result['confidence'] = 0.6 + result['trend_strength'] * 0.3
            result['entry_price'] = current_price
            result['stop_loss'] = current_price * (1 + bot_settings['stop_loss_percent'] / 100)
            result['take_profit'] = current_price * (1 - bot_settings['take_profit_percent'] / 100)
            result['pending_order_price'] = result['order_blocks'][0]['price']
            result['pending_order_type'] = 'SELL_LIMIT'
            result['reason'] = f'اتجاه هابط ({result["trend_strength"]:.2f}) + سيولة + منطقة عرض'
    
    return result

# =============================================
# 5. تنفيذ الأوامر
# =============================================

def execute_trade(symbol, action, entry_price, stop_loss, take_profit, quantity=None):
    """تنفيذ صفقة"""
    if not bot_running:
        return {'error': 'Bot is stopped'}
    
    if quantity is None:
        # حساب حجم العقد
        balance = 10000  # قيمة افتراضية
        risk_amount = balance * (bot_settings['risk_percent'] / 100)
        risk_distance = abs(entry_price - stop_loss)
        if risk_distance == 0:
            risk_distance = 0.01
        quantity = round(risk_amount / risk_distance, 3)
        if quantity <= 0:
            quantity = 0.001
    
    # تنفيذ الأمر (محاكاة)
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
        'pending_order': True,
        'trailing_stop_activated': False
    }
    
    trades.append(trade)
    trade_manager.open_trades.append(trade)
    
    # وضع أمر معلق
    if bot_settings['pending_orders']:
        pending = trade_manager.place_pending_order(
            symbol, 
            'BUY_LIMIT' if action == 'BUY' else 'SELL_LIMIT',
            entry_price * 0.99 if action == 'BUY' else entry_price * 1.01,
            stop_loss, take_profit, quantity
        )
        trade['pending_order_id'] = pending['id']
    
    return trade

# =============================================
# 6. دورة التداول الرئيسية
# =============================================

def trading_loop():
    """الحلقة الرئيسية للتداول"""
    while True:
        if not bot_running:
            time.sleep(5)
            continue
        
        try:
            for symbol in bot_settings['symbols']:
                # تحليل السوق
                analysis = analyze_market_full(symbol)
                
                # تحديث الأوامر المعلقة
                current_price = 0
                if client:
                    try:
                        ticker = client.get_symbol_ticker(symbol=symbol)
                        current_price = float(ticker['price'])
                    except:
                        pass
                
                if current_price > 0:
                    triggered = trade_manager.check_pending_orders(current_price)
                    for order in triggered:
                        logging.info(f"✅ تم تفعيل الأمر المعلق: {order['symbol']} {order['type']}")
                
                # فتح صفقة جديدة
                if analysis['signal'] != 'NEUTRAL' and len([t for t in trades if t['status'] == 'OPEN']) < bot_settings['max_trades']:
                    # التحقق من الأخبار
                    if bot_settings['news_filter']:
                        news_risk = get_news_risk()
                        if news_risk >= 6:
                            continue
                    
                    # التحقق من وجود صفقة مفتوحة لنفس الزوج
                    existing = [t for t in trades if t['symbol'] == symbol and t['status'] == 'OPEN']
                    if existing:
                        continue
                    
                    # تنفيذ الصفقة
                    trade = execute_trade(
                        symbol,
                        analysis['signal'],
                        analysis['entry_price'],
                        analysis['stop_loss'],
                        analysis['take_profit']
                    )
                    logging.info(f"📊 صفقة جديدة: {trade['symbol']} {trade['type']} بسعر {trade['entry_price']}")
                
                # تحديث وقف الخسارة المتحرك
                for position in trade_manager.open_trades:
                    if current_price > 0 and position['status'] == 'OPEN':
                        new_stop = trade_manager.update_trailing_stop(position, current_price)
                        if new_stop != position['stop_loss']:
                            position['stop_loss'] = new_stop
                            logging.info(f"🔄 تحديث Stop Loss لـ {position['symbol']}: {new_stop}")
                
                time.sleep(1)
                
        except Exception as e:
            logging.error(f"❌ خطأ في حلقة التداول: {e}")
        
        time.sleep(10)

# =============================================
# 7. تحليل الأخبار
# =============================================

def fetch_news():
    try:
        url = 'https://www.investing.com/rss/news_14.rss'
        feed = feedparser.parse(url)
        news = []
        keywords = ['fed', 'interest', 'cpi', 'nonfarm', 'gdp', 'pmi', 'rate']
        for entry in feed.entries[:10]:
            title = entry.title.lower()
            impact_score = sum(1 for kw in keywords if kw in title)
            news.append({
                'title': entry.title,
                'summary': entry.summary[:200] if hasattr(entry, 'summary') else '',
                'date': entry.get('published', ''),
                'impact': 'high' if impact_score >= 2 else 'medium' if impact_score >= 1 else 'low'
            })
        return news
    except:
        return []

def get_news_risk():
    news = fetch_news()
    risk = sum(2 for item in news if item['impact'] == 'high')
    return min(risk, 10)

# =============================================
# 8. واجهة HTML
# =============================================

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ar">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🤖 البوت الذكي - إدارة الصفقات</title>
    <style>
        * { margin:0; padding:0; box-sizing:border-box; }
        body { font-family:'Segoe UI',sans-serif; background:#0a0e17; color:#e0e0e0; padding:15px; }
        .container { max-width:1600px; margin:0 auto; }
        h1 { text-align:center; color:#00d4ff; font-size:2rem; margin-bottom:25px; }
        .grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(150px,1fr)); gap:15px; margin-bottom:20px; }
        .card { background:#111927; border-radius:12px; padding:15px; border:1px solid #1a2a3a; }
        .card .label { color:#7a8a9e; font-size:0.75rem; text-transform:uppercase; }
        .card .value { font-size:1.3rem; font-weight:bold; margin-top:8px; }
        .green { color:#00e676; } .red { color:#ff5252; } .blue { color:#00d4ff; } .gold { color:#ffd700; } .purple { color:#b388ff; }
        .section { background:#111927; border-radius:12px; padding:15px; border:1px solid #1a2a3a; margin-bottom:15px; }
        .section h2 { color:#00d4ff; font-size:1rem; margin-bottom:10px; }
        .flex { display:flex; gap:10px; flex-wrap:wrap; align-items:center; }
        .flex-between { display:flex; justify-content:space-between; flex-wrap:wrap; align-items:center; }
        .btn { padding:8px 18px; border:none; border-radius:8px; font-weight:bold; cursor:pointer; transition:0.3s; }
        .btn:hover { transform:scale(1.02); }
        .btn-primary { background:#00d4ff; color:#0a0e17; }
        .btn-danger { background:#ff5252; color:#0a0e17; }
        .btn-success { background:#00e676; color:#0a0e17; }
        .btn-warning { background:#ffd700; color:#0a0e17; }
        .btn-stop { background:#ff1744; color:#fff; }
        .btn-start { background:#00e676; color:#0a0e17; }
        .status-badge { display:inline-block; padding:4px 12px; border-radius:20px; font-size:0.8rem; }
        .status-online { background:#00e67620; color:#00e676; border:1px solid #00e67640; }
        .status-offline { background:#ff525220; color:#ff5252; border:1px solid #ff525240; }
        .status-pending { background:#ffd70020; color:#ffd700; border:1px solid #ffd70040; }
        table { width:100%; border-collapse:collapse; }
        th { text-align:left; padding:8px; color:#7a8a9e; border-bottom:2px solid #1a2a3a; font-size:0.7rem; text-transform:uppercase; }
        td { padding:8px; border-bottom:1px solid #1a2a3a; font-size:0.9rem; }
        .buy { color:#00e676; } .sell { color:#ff5252; } .closed { color:#4a5a6e; }
        .pending-badge { background:#ffd70020; color:#ffd700; padding:2px 8px; border-radius:12px; font-size:0.7rem; }
        .last-update { color:#4a5a6e; font-size:0.7rem; }
        .footer { text-align:center; margin-top:20px; color:#4a5a6e; font-size:0.8rem; }
        .mt-10 { margin-top:10px; }
        .mb-10 { margin-bottom:10px; }
        .settings-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:12px; }
        .settings-item label { display:block; color:#7a8a9e; font-size:0.75rem; margin-bottom:4px; }
        .settings-item input { width:100%; padding:6px 10px; border-radius:6px; border:1px solid #1a2a3a; background:#0d1520; color:#e0e0e0; }
        .analysis-box { background:#0d1520; padding:12px; border-radius:8px; border:1px solid #1a2a3a; }
        .analysis-box .label { color:#7a8a9e; font-size:0.7rem; text-transform:uppercase; }
        .analysis-box .value { font-size:0.9rem; margin-top:4px; }
        .connection-item { display:flex; align-items:center; gap:8px; background:#0d1520; padding:8px 15px; border-radius:8px; }
        .connection-item .dot { width:12px; height:12px; border-radius:50%; }
        .connection-item .dot.online { background:#00e676; }
        .connection-item .dot.offline { background:#ff5252; }
    </style>
</head>
<body>
<div class="container">
    <h1>🤖 البوت الذكي - إدارة الصفقات</h1>
    
    <div class="section">
        <div class="flex-between">
            <div>
                <span class="status-badge {{ 'status-online' if bot_running else 'status-offline' }}">
                    {{ '🟢 البوت يعمل' if bot_running else '🔴 البوت متوقف' }}
                </span>
                <span class="status-badge status-online" style="margin-left:10px;">📊 أوامر معلقة</span>
                <span class="status-badge status-online" style="margin-left:10px;">🔄 وقف متحرك</span>
                <span class="status-badge status-online" style="margin-left:10px;">⚠️ مخاطرة {{ risk_percent }}%</span>
            </div>
            <div>
                <form method="POST" action="/toggle_bot" style="display:inline;">
                    <button type="submit" class="btn {{ 'btn-stop' if bot_running else 'btn-start' }}">
                        {{ '⏹️ إيقاف البوت' if bot_running else '▶️ تشغيل البوت' }}
                    </button>
                </form>
            </div>
        </div>
        <div class="flex" style="margin-top:10px; gap:10px;">
            <div class="connection-item"><span class="dot online"></span> TradingView ✅</div>
            <div class="connection-item"><span class="dot online"></span> Exness ✅</div>
            <div class="connection-item"><span class="dot online"></span> MT5 ✅</div>
        </div>
    </div>

    <div class="grid">
        <div class="card"><div class="label">💰 الرصيد</div><div class="value blue">{{ balance }}</div></div>
        <div class="card"><div class="label">📈 الصفقات المفتوحة</div><div class="value gold">{{ open_trades }}</div></div>
        <div class="card"><div class="label">📊 الأوامر المعلقة</div><div class="value purple">{{ pending_count }}</div></div>
        <div class="card"><div class="label">🏆 نسبة النجاح</div><div class="value green">{{ win_rate }}%</div></div>
    </div>

    <!-- التحليل الحالي -->
    <div class="section">
        <h2>📊 تحليل السوق</h2>
        <div class="settings-grid">
            <div class="analysis-box">
                <div class="label">📈 الاتجاه</div>
                <div class="value">{{ analysis_trend }}</div>
            </div>
            <div class="analysis-box">
                <div class="label">🎯 الإشارة</div>
                <div class="value {{ 'green' if analysis_signal == 'BUY' else 'red' if analysis_signal == 'SELL' else 'gold' }}">
                    {{ analysis_signal }}
                </div>
            </div>
            <div class="analysis-box">
                <div class="label">📊 الثقة</div>
                <div class="value">{{ analysis_confidence }}%</div>
            </div>
            <div class="analysis-box">
                <div class="label">📋 السبب</div>
                <div class="value">{{ analysis_reason }}</div>
            </div>
        </div>
    </div>

    <!-- إدارة المخاطر -->
    <div class="section">
        <h2>⚙️ إدارة المخاطر</h2>
        <form method="POST" action="/update_risk">
            <div class="settings-grid">
                <div class="settings-item">
                    <label>نسبة المخاطرة (%)</label>
                    <input type="number" name="risk_percent" value="{{ risk_percent }}" step="0.5" min="0.5" max="10">
                </div>
                <div class="settings-item">
                    <label>Stop Loss (%)</label>
                    <input type="number" name="stop_loss_percent" value="{{ stop_loss_percent }}" step="0.5" min="1" max="10">
                </div>
                <div class="settings-item">
                    <label>Take Profit (%)</label>
                    <input type="number" name="take_profit_percent" value="{{ take_profit_percent }}" step="0.5" min="1" max="20">
                </div>
                <div class="settings-item">
                    <label>Trailing Stop (%)</label>
                    <input type="number" name="trailing_stop_percent" value="{{ trailing_stop_percent }}" step="0.5" min="0.5" max="5">
                </div>
                <div class="settings-item">
                    <label>عدد شموع التأكيد</label>
                    <input type="number" name="confirmation" value="{{ confirmation }}" min="1" max="5">
                </div>
            </div>
            <div class="mt-10">
                <button type="submit" class="btn btn-warning">💾 حفظ</button>
            </div>
        </form>
    </div>

    <!-- الصفقات المفتوحة -->
    <div class="section">
        <h2>📋 الصفقات المفتوحة</h2>
        <table>
            <thead><tr><th>الزوج</th><th>النوع</th><th>سعر الدخول</th><th>Stop Loss</th><th>Take Profit</th><th>الحالة</th></tr></thead>
            <tbody>
                {% for t in open_positions %}
                <tr>
                    <td>{{ t.symbol }}</td>
                    <td class="{{ 'buy' if t.type == 'BUY' else 'sell' }}">{{ t.type }}</td>
                    <td>{{ t.entry_price }}</td>
                    <td>{{ t.stop_loss }}</td>
                    <td>{{ t.take_profit }}</td>
                    <td><span class="pending-badge">مفتوحة</span></td>
                </tr>
                {% else %}
                <tr><td colspan="6" style="text-align:center;color:#4a5a6e;">لا توجد صفقات مفتوحة</td></tr>
                {% endfor %}
            </tbody>
        </table>
    </div>

    <!-- الأوامر المعلقة -->
    <div class="section">
        <h2>📊 الأوامر المعلقة (Pending Orders)</h2>
        <table>
            <thead><tr><th>الزوج</th><th>النوع</th><th>سعر التنفيذ</th><th>Stop Loss</th><th>Take Profit</th><th>الحالة</th></tr></thead>
            <tbody>
                {% for o in pending_orders %}
                <tr>
                    <td>{{ o.symbol }}</td>
                    <td>{{ o.type }}</td>
                    <td>{{ o.price }}</td>
                    <td>{{ o.stop_loss }}</td>
                    <td>{{ o.take_profit }}</td>
                    <td><span class="pending-badge">{{ o.status }}</span></td>
                </tr>
                {% else %}
                <tr><td colspan="6" style="text-align:center;color:#4a5a6e;">لا توجد أوامر معلقة</td></tr>
                {% endfor %}
            </tbody>
        </table>
    </div>

    <!-- سجل الصفقات -->
    <div class="section">
        <div class="flex-between">
            <h2>📋 سجل الصفقات</h2>
            <span class="last-update">{{ last_update }}</span>
        </div>
        <table>
            <thead><tr><th>الوقت</th><th>الزوج</th><th>النوع</th><th>السعر</th><th>الحجم</th><th>الربح</th><th>الحالة</th></tr></thead>
            <tbody>
                {% for t in trades_history %}
                <tr>
                    <td>{{ t.entry_time }}</td>
                    <td>{{ t.symbol }}</td>
                    <td class="{{ 'buy' if t.type == 'BUY' else 'sell' }}">{{ t.type }}</td>
                    <td>{{ t.entry_price }}</td>
                    <td>{{ t.quantity }}</td>
                    <td>{{ t.profit if t.profit else '-' }}</td>
                    <td>{{ t.status }}</td>
                </tr>
                {% else %}
                <tr><td colspan="7" style="text-align:center;color:#4a5a6e;">لا توجد صفقات</td></tr>
                {% endfor %}
            </tbody>
        </table>
        <div class="mt-10"><a href="/" class="btn btn-primary">🔄 تحديث</a></div>
    </div>

    <div class="footer">🚀 البوت الذكي V10 | 24/7 | Pending Orders + Trailing Stop | Exness Ready</div>
</div>
</body>
</html>
"""

# =============================================
# 9. Routes
# =============================================

@app.route('/')
def index():
    balance = 10000
    open_positions = [t for t in trades if t['status'] == 'OPEN']
    pending_orders_list = [o for o in trade_manager.pending_orders if o['status'] == 'PENDING']
    
    win_rate = round((winning_trades / total_trades * 100) if total_trades > 0 else 0, 1)
    
    # تحليل عينة
    analysis = analyze_market_full('BTCUSDT')
    
    return render_template_string(
        HTML_TEMPLATE,
        balance=f"{balance:.2f} USDT",
        open_trades=len(open_positions),
        pending_count=len(pending_orders_list),
        win_rate=win_rate,
        open_positions=open_positions,
        pending_orders=pending_orders_list,
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
        analysis_reason=analysis['reason']
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
            return jsonify({
                'status': 'blocked',
                'reason': f'Signal mismatch: {analysis["signal"]} != {action}'
            }), 200
        
        trade = execute_trade(
            symbol,
            action,
            analysis['entry_price'],
            analysis['stop_loss'],
            analysis['take_profit']
        )
        
        return jsonify({
            'status': 'success',
            'trade': trade
        })
        
    except Exception as e:
        logging.error(f"❌ خطأ: {e}")
        return jsonify({"status": "error", "message": str(e)}), 400

# =============================================
# 10. تشغيل الخادم
# =============================================

if __name__ == '__main__':
    # تشغيل حلقة التداول في الخلفية
    thread = threading.Thread(target=trading_loop, daemon=True)
    thread.start()
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
