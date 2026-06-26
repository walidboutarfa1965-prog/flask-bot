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

load_dotenv()
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

# =============================================
# 0. تهيئة MetaTrader 5 (اتصال حقيقي)
# =============================================

# بيانات تسجيل الدخول - يمكنك تعديلها هنا أو عبر متغيرات البيئة
MT5_LOGIN = int(os.getenv('MT5_LOGIN', 262946340))
MT5_PASSWORD = os.getenv('MT5_PASSWORD', 'Mama1965.')
MT5_SERVER = os.getenv('MT5_SERVER', 'Exness-MT5Trial16')

# متغير لتخزين حالة الاتصال
mt5_connected = False
mt5 = None

def initialize_mt5():
    """محاولة الاتصال بـ MetaTrader 5"""
    global mt5, mt5_connected
    
    try:
        # محاولة استيراد MetaTrader5
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
                print("⚠️ MT5 غير مثبت - سيتم استخدام بيانات وهمية")
                return False
        
        if mt5 is None:
            return False
        
        # محاولة الاتصال بـ MT5
        print(f"🔍 محاولة الاتصال بـ MT5...")
        print(f"   📌 Login: {MT5_LOGIN}")
        print(f"   📌 Server: {MT5_SERVER}")
        
        # تهيئة MT5 مع بيانات الدخول
        initialized = mt5.initialize(
            login=MT5_LOGIN,
            password=MT5_PASSWORD,
            server=MT5_SERVER
        )
        
        if initialized:
            mt5_connected = True
            print("✅ تم الاتصال بـ MT5 بنجاح!")
            
            # جلب معلومات الحساب
            account_info = mt5.account_info()
            if account_info:
                print(f"   📊 الحساب: {account_info.login}")
                print(f"   💰 الرصيد: {account_info.balance:.2f}")
                print(f"   📈 Equity: {account_info.equity:.2f}")
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

# محاولة الاتصال عند بدء التشغيل
mt5_connected = initialize_mt5()

# =============================================
# استيراد الاستراتيجية (بعد تهيئة MT5)
# =============================================

# استيراد الاستراتيجية الجديدة
try:
    from strategy import SmartTradingBot
    from analysis import *
    from risk_manager import TradeManager
    print("✅ تم استيراد ملفات الاستراتيجية بنجاح")
except ImportError as e:
    print(f"⚠️ خطأ في استيراد الملفات: {e}")
    print("تأكد من وجود analysis.py, risk_manager.py, strategy.py في نفس المجلد")
    SmartTradingBot = None
    TradeManager = None

# =============================================
# تهيئة البوت الجديد
# =============================================
try:
    if SmartTradingBot is not None:
        smart_bot = SmartTradingBot(initial_balance=10000)
        print("✅ تم تهيئة SmartTradingBot بنجاح")
    else:
        smart_bot = None
        print("⚠️ SmartTradingBot غير معرف")
except NameError:
    print("⚠️ SmartTradingBot غير معرف - تأكد من وجود strategy.py")
    smart_bot = None

# =============================================
# 1. Bot Settings (Exness Only)
# =============================================
BROKER_TYPE = 'exness'
client = None

# =============================================
# 2. Investing.com Functions
# =============================================

def get_investing_id(symbol, asset_type="Currency"):
    try:
        from investiny import search_assets
        results = search_assets(query=symbol, limit=1, type=asset_type)
        if results:
            return int(results[0]["ticker"])
        return None
    except Exception as e:
        logging.error(f"❌ Error getting Investing ID: {e}")
        return None

def get_investing_data(symbol, from_date="01/01/2024", to_date="01/06/2024"):
    try:
        from investiny import historical_data
        investing_id = get_investing_id(symbol)
        if not investing_id:
            return None
        data = historical_data(
            investing_id=investing_id,
            from_date=from_date,
            to_date=to_date
        )
        return data
    except Exception as e:
        logging.error(f"❌ Error fetching data from Investing.com: {e}")
        return None

def check_investing_connection():
    """Check if Investing.com API is accessible"""
    try:
        from investiny import search_assets
        results = search_assets(query="EUR/USD", limit=1, type="Currency")
        if results and len(results) > 0:
            logging.info("✅ Investing.com API is accessible")
            return True
        
        url = 'https://www.investing.com/rss/news_14.rss'
        response = requests.get(url, timeout=5)
        if response.status_code == 200:
            logging.info("✅ Investing.com RSS is accessible")
            return True
            
        return False
    except Exception as e:
        logging.error(f"❌ Investing.com connection failed: {e}")
        return False

def fetch_news_investiny():
    """Fetch news from Investing.com RSS with fallback"""
    try:
        url = 'https://www.investing.com/rss/news_14.rss'
        feed = feedparser.parse(url)
        
        if feed.entries:
            news = []
            keywords = ['fed', 'interest', 'cpi', 'nonfarm', 'gdp', 'pmi', 'rate']
            for entry in feed.entries[:10]:
                title = entry.title.lower()
                impact_score = sum(1 for kw in keywords if kw in title)
                news.append({
                    'title': entry.title,
                    'summary': entry.summary[:200] if hasattr(entry, 'summary') else '',
                    'date': entry.get('published', ''),
                    'impact': 'high' if impact_score >= 2 else 'medium' if impact_score >= 1 else 'low',
                    'link': entry.get('link', '')
                })
            logging.info(f"✅ Fetched {len(news)} news from Investing.com")
            return news
        
        alt_url = 'https://feeds.finance.yahoo.com/rss/2.0/headline?s=^GSPC'
        alt_feed = feedparser.parse(alt_url)
        if alt_feed.entries:
            news = []
            for entry in alt_feed.entries[:5]:
                news.append({
                    'title': entry.title,
                    'summary': entry.summary[:200] if hasattr(entry, 'summary') else '',
                    'date': entry.get('published', ''),
                    'impact': 'medium',
                    'link': entry.get('link', '')
                })
            logging.info(f"✅ Fetched {len(news)} news from Yahoo Finance (fallback)")
            return news
            
        return []
    except Exception as e:
        logging.error(f"❌ Error fetching news: {e}")
        return []

def get_news_risk():
    news = fetch_news_investiny()
    risk = sum(2 for item in news if item.get('impact') == 'high')
    return min(risk, 10)

def get_investing_price(symbol):
    try:
        data = get_investing_data(symbol, 
                                  from_date=(datetime.now() - timedelta(days=1)).strftime("%d/%m/%Y"),
                                  to_date=datetime.now().strftime("%d/%m/%Y"))
        if data is not None and len(data) > 0:
            return float(data['close'].iloc[-1])
        return None
    except:
        return None

# =============================================
# 3. Bot Data
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
    'confirmation_candles': 2,
    'min_trend_strength': 0.6,
}

# =============================================
# 4. Trade Manager (Legacy)
# =============================================

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

# =============================================
# 5. Market Analysis
# =============================================

def get_klines(symbol, interval, limit=100):
    """جلب البيانات من MT5 أو مصدر آخر"""
    global mt5_connected, mt5
    
    # إذا كان MT5 متصلاً، استخدمه
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
                logging.info(f"✅ جلب {len(df)} شمعة من {symbol} على فريم {interval}")
                return df
            else:
                logging.warning(f"⚠️ لا توجد بيانات لـ {symbol} على فريم {interval}")
                return None
        except Exception as e:
            logging.error(f"❌ خطأ في جلب البيانات من MT5: {e}")
            return None
    
    # إذا لم يكن MT5 متصلاً، استخدم بيانات وهمية
    logging.warning(f"⚠️ MT5 غير متصل - استخدام بيانات وهمية لـ {symbol}")
    return generate_mock_data(symbol, interval, limit)

def generate_mock_data(symbol, interval, limit=100):
    """توليد بيانات وهمية للاختبار"""
    try:
        # توليد بيانات وهمية
        np.random.seed(42)
        dates = pd.date_range(start=datetime.now() - timedelta(hours=limit), periods=limit, freq='1h')
        base_price = 1.2000 if 'USD' in symbol else 100.0 if 'BTC' in symbol else 2000.0
        
        prices = base_price + np.cumsum(np.random.randn(limit) * 0.001)
        df = pd.DataFrame({
            'open': prices[:-1] if len(prices) > 1 else prices,
            'high': prices + np.abs(np.random.randn(limit) * 0.001),
            'low': prices - np.abs(np.random.randn(limit) * 0.001),
            'close': prices,
            'volume': np.random.randint(1000, 5000, limit)
        }, index=dates)
        
        if len(df) > 1:
            df = df.iloc[:-1]  # إزالة الصف الأخير للتطابق
        
        logging.info(f"ℹ️ تم توليد {len(df)} شمعة وهمية لـ {symbol}")
        return df
    except Exception as e:
        logging.error(f"❌ خطأ في توليد البيانات الوهمية: {e}")
        return None

def identify_trend(df):
    if df is None or len(df) < 50:
        return {'trend': 'Sideways', 'strength': 0.0}
    ema_20 = df['close'].ewm(span=20, adjust=False).mean()
    ema_50 = df['close'].ewm(span=50, adjust=False).mean()
    ema_200 = df['close'].ewm(span=200, adjust=False).mean()
    last = df['close'].iloc[-1]
    strength = 0.0
    trend = 'Sideways'
    if last > ema_50.iloc[-1] > ema_200.iloc[-1]:
        trend = 'Uptrend'
        strength = (last - ema_50.iloc[-1]) / ema_50.iloc[-1]
    elif last < ema_50.iloc[-1] < ema_200.iloc[-1]:
        trend = 'Downtrend'
        strength = (ema_50.iloc[-1] - last) / ema_50.iloc[-1]
    return {'trend': trend, 'strength': min(strength * 10, 1.0)}

def analyze_market_full(symbol):
    """تحليل السوق باستخدام الاستراتيجية الجديدة"""
    result = {
        'symbol': symbol,
        'trend': 'Sideways',
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
    
    # التحقق من الاتصال بـ MT5
    if not mt5_connected:
        result['reason'] = "⚠️ MT5 غير متصل - تحليل باستخدام بيانات وهمية"
        # استخدام تحليل مبسط بالبيانات الوهمية
        data = get_klines(symbol, '1h', 100)
        if data is not None:
            trend = identify_trend(data)
            result['trend'] = trend['trend']
            result['trend_strength'] = trend['strength']
            result['signal'] = 'BUY' if trend['trend'] == 'Uptrend' else 'SELL' if trend['trend'] == 'Downtrend' else 'NEUTRAL'
            result['confidence'] = trend['strength']
            result['reason'] = f"تحليل مبسط (بيانات وهمية): {trend['trend']}"
        return result
    
    # إذا كان MT5 متصلاً والاستراتيجية متاحة
    try:
        if smart_bot is not None:
            # جلب البيانات من MT5
            data_h4 = get_klines(symbol, '4h', 100)
            data_h1 = get_klines(symbol, '1h', 100)
            data_m15 = get_klines(symbol, '15m', 100)
            
            if data_h4 is not None and data_h1 is not None and data_m15 is not None:
                # استخدام البوت الجديد
                decision = smart_bot.get_trading_decision(data_h4, data_h1, data_m15)
                
                if decision['decision'] == 'BUY':
                    result['signal'] = 'BUY'
                    result['entry_price'] = decision['entry']
                    result['stop_loss'] = decision['stop']
                    result['take_profit'] = decision['entry'] + (decision['entry'] - decision['stop']) * 2
                    result['confidence'] = decision['trigger']['conditions_met'] / 9
                    result['trend'] = decision['trend']['direction']
                    result['reason'] = f"SMC+ICT: {decision['trigger']['conditions_met']}/9 شروط متحققة"
                elif decision['decision'] == 'SELL':
                    result['signal'] = 'SELL'
                    result['entry_price'] = decision['entry']
                    result['stop_loss'] = decision['stop']
                    result['take_profit'] = decision['entry'] - (decision['stop'] - decision['entry']) * 2
                    result['confidence'] = decision['trigger']['conditions_met'] / 9
                    result['trend'] = decision['trend']['direction']
                    result['reason'] = f"SMC+ICT: {decision['trigger']['conditions_met']}/9 شروط متحققة"
                else:
                    result['signal'] = 'NEUTRAL'
                    result['reason'] = f"انتظار: {decision.get('reason', 'لا توجد إشارة')}"
            else:
                # استخدام التحليل التقليدي كبديل
                data = get_klines(symbol, '1h', 100)
                if data is not None:
                    trend = identify_trend(data)
                    result['trend'] = trend['trend']
                    result['trend_strength'] = trend['strength']
                    result['signal'] = 'BUY' if trend['trend'] == 'Uptrend' else 'SELL' if trend['trend'] == 'Downtrend' else 'NEUTRAL'
                    result['confidence'] = trend['strength']
                    result['reason'] = f"تحليل تقليدي (بيانات MT5): {trend['trend']}"
        else:
            # استخدام التحليل التقليدي
            data = get_klines(symbol, '1h', 100)
            if data is not None:
                trend = identify_trend(data)
                result['trend'] = trend['trend']
                result['trend_strength'] = trend['strength']
                result['signal'] = 'BUY' if trend['trend'] == 'Uptrend' else 'SELL' if trend['trend'] == 'Downtrend' else 'NEUTRAL'
                result['confidence'] = trend['strength']
                result['reason'] = f"تحليل تقليدي (بيانات MT5): {trend['trend']}"
                
    except Exception as e:
        logging.error(f"❌ تحليل السوق فشل: {e}")
        result['reason'] = f"خطأ: {str(e)[:50]}"
    
    return result

# =============================================
# 6. Order Execution
# =============================================

def execute_trade(symbol, action, entry_price, stop_loss, take_profit, quantity=None):
    global total_trades, winning_trades
    if not bot_running:
        return {'error': 'Bot is stopped'}
    
    # التحقق من الاتصال بـ MT5
    if not mt5_connected:
        logging.warning("⚠️ MT5 غير متصل - لا يمكن تنفيذ الصفقة")
        return {'error': 'MT5 not connected'}
    
    if quantity is None:
        balance = 10000
        risk_amount = balance * (bot_settings['risk_percent'] / 100)
        risk_distance = abs(entry_price - stop_loss)
        if risk_distance == 0:
            risk_distance = 0.01
        quantity = round(risk_amount / risk_distance, 3)
        if quantity <= 0:
            quantity = 0.001
    
    # تنفيذ الصفقة عبر MT5
    try:
        order_type = mt5.ORDER_TYPE_BUY if action == 'BUY' else mt5.ORDER_TYPE_SELL
        
        # إعداد الطلب
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
        
        # إرسال الطلب
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
                'pending_order': False,
                'trailing_stop_activated': False,
                'profit': None,
                'order_id': result.order
            }
            trades.append(trade)
            legacy_manager.open_trades.append(trade)
            total_trades += 1
            logging.info(f"✅ صفقة {action} تم تنفيذها بنجاح: {symbol} @ {entry_price}")
            return trade
        else:
            error_msg = f"فشل تنفيذ الصفقة: {result.retcode}"
            logging.error(f"❌ {error_msg}")
            return {'error': error_msg}
            
    except Exception as e:
        logging.error(f"❌ خطأ في تنفيذ الصفقة: {e}")
        return {'error': str(e)}

def trading_loop():
    global winning_trades
    while True:
        if not bot_running:
            time.sleep(5)
            continue
        try:
            # التحقق من الاتصال بـ MT5
            if not mt5_connected:
                logging.warning("⚠️ MT5 غير متصل - التداول متوقف")
                time.sleep(30)
                # محاولة إعادة الاتصال
                global mt5_connected
                mt5_connected = initialize_mt5()
                continue
            
            for symbol in bot_settings['symbols']:
                analysis = analyze_market_full(symbol)
                if analysis['signal'] != 'NEUTRAL' and len([t for t in trades if t['status'] == 'OPEN']) < bot_settings['max_trades']:
                    if bot_settings['news_filter']:
                        news_risk = get_news_risk()
                        if news_risk >= 6:
                            continue
                    existing = [t for t in trades if t['symbol'] == symbol and t['status'] == 'OPEN']
                    if existing:
                        continue
                    trade = execute_trade(
                        symbol,
                        analysis['signal'],
                        analysis['entry_price'],
                        analysis['stop_loss'],
                        analysis['take_profit']
                    )
                    if 'error' not in trade:
                        logging.info(f"📊 New trade: {trade['symbol']} {trade['type']} at {trade['entry_price']}")
                time.sleep(1)
        except Exception as e:
            logging.error(f"❌ Trading loop error: {e}")
        time.sleep(10)

# =============================================
# 7. HTML Template
# =============================================

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ar">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🤖 Smart Trading Bot</title>
    <style>
        * { margin:0; padding:0; box-sizing:border-box; }
        body { font-family:'Segoe UI',sans-serif; background:#0a0e17; color:#e0e0e0; padding:15px; }
        .container { max-width:1200px; margin:0 auto; }
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
        .btn-stop { background:#ff1744; color:#fff; }
        .btn-start { background:#00e676; color:#0a0e17; }
        .btn-warning { background:#ffd700; color:#0a0e17; }
        .status-badge { display:inline-block; padding:4px 12px; border-radius:20px; font-size:0.8rem; }
        .status-online { background:#00e67620; color:#00e676; border:1px solid #00e67640; }
        .status-offline { background:#ff525220; color:#ff5252; border:1px solid #ff525240; }
        table { width:100%; border-collapse:collapse; }
        th { text-align:left; padding:8px; color:#7a8a9e; border-bottom:2px solid #1a2a3a; font-size:0.7rem; text-transform:uppercase; }
        td { padding:8px; border-bottom:1px solid #1a2a3a; font-size:0.9rem; }
        .buy { color:#00e676; } .sell { color:#ff5252; }
        .footer { text-align:center; margin-top:20px; color:#4a5a6e; font-size:0.8rem; }
        .mt-10 { margin-top:10px; }
        .settings-grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:12px; }
        .settings-item label { display:block; color:#7a8a9e; font-size:0.75rem; margin-bottom:4px; }
        .settings-item input { width:100%; padding:6px 10px; border-radius:6px; border:1px solid #1a2a3a; background:#0d1520; color:#e0e0e0; }
        .badge-smc { background:#7c4dff20; color:#7c4dff; padding:2px 10px; border-radius:12px; font-size:0.7rem; border:1px solid #7c4dff40; }
        .news-item { border-left:3px solid #4a5a6e; padding:8px 12px; margin:5px 0; background:#0d1520; border-radius:4px; }
    </style>
</head>
<body>
<div class="container">
    <h1>🤖 Smart Trading Bot <span class="badge-smc">SMC+ICT</span></h1>
    
    <div class="section">
        <div class="flex-between">
            <div>
                <span class="status-badge {{ 'status-online' if bot_running else 'status-offline' }}">
                    {{ '🟢 Bot Running' if bot_running else '🔴 Bot Stopped' }}
                </span>
                <span class="badge-smc" style="margin-left:10px;">🧠 SMC + ICT + Volume Profile</span>
                <span class="badge-smc" style="margin-left:10px;background:#00e67620;color:#00e676;">
                    MT5 {{ '✅ متصل' if mt5_available else '❌ غير متصل' }}
                </span>
            </div>
            <div>
                <form method="POST" action="/toggle_bot" style="display:inline;">
                    <button type="submit" class="btn {{ 'btn-stop' if bot_running else 'btn-start' }}">
                        {{ '⏹️ Stop Bot' if bot_running else '▶️ Start Bot' }}
                    </button>
                </form>
                <a href="/status" class="btn btn-primary" style="display:inline-block;text-decoration:none;">📊 Status</a>
            </div>
        </div>
    </div>

    <div class="grid">
        <div class="card"><div class="label">💰 Balance</div><div class="value blue">{{ balance }}</div></div>
        <div class="card"><div class="label">📈 Open Trades</div><div class="value gold">{{ open_trades }}</div></div>
        <div class="card"><div class="label">📊 Pending Orders</div><div class="value purple">{{ pending_count }}</div></div>
        <div class="card"><div class="label">🏆 Win Rate</div><div class="value green">{{ win_rate }}%</div></div>
        <div class="card"><div class="label">📰 News Risk</div><div class="value green">{{ news_risk }}/10</div></div>
    </div>

    <!-- Market Analysis -->
    <div class="section">
        <h2>📊 Market Analysis</h2>
        <div class="settings-grid">
            <div class="card"><div class="label">📈 Trend</div><div class="value">{{ analysis_trend }}</div></div>
            <div class="card"><div class="label">🎯 Signal</div><div class="value {{ 'green' if analysis_signal == 'BUY' else 'red' if analysis_signal == 'SELL' else 'gold' }}">{{ analysis_signal }}</div></div>
            <div class="card"><div class="label">📊 Confidence</div><div class="value">{{ analysis_confidence }}%</div></div>
            <div class="card"><div class="label">📋 Reason</div><div class="value">{{ analysis_reason }}</div></div>
        </div>
    </div>

    <!-- News -->
    <div class="section">
        <h2>📰 Latest News</h2>
        {% for item in news[:5] %}
        <div class="news-item" style="border-left-color: {{ '#ff5252' if item.impact == 'high' else '#ffd700' if item.impact == 'medium' else '#4a5a6e' }};">
            <strong>{{ item.title }}</strong><br>
            <small style="color:#7a8a9e;">{{ item.date[:25] }} | Impact: {{ item.impact.upper() }}</small>
        </div>
        {% else %}
        <div style="color:#4a5a6e;">No news available</div>
        {% endfor %}
    </div>

    <!-- Risk Management -->
    <div class="section">
        <h2>⚙️ Risk Management</h2>
        <form method="POST" action="/update_risk">
            <div class="settings-grid">
                <div class="settings-item">
                    <label>Risk %</label>
                    <input type="number" name="risk_percent" value="{{ risk_percent }}" step="0.5" min="0.5" max="10">
                </div>
                <div class="settings-item">
                    <label>Stop Loss %</label>
                    <input type="number" name="stop_loss_percent" value="{{ stop_loss_percent }}" step="0.5" min="1" max="10">
                </div>
                <div class="settings-item">
                    <label>Take Profit %</label>
                    <input type="number" name="take_profit_percent" value="{{ take_profit_percent }}" step="0.5" min="1" max="20">
                </div>
                <div class="settings-item">
                    <label>Trailing Stop %</label>
                    <input type="number" name="trailing_stop_percent" value="{{ trailing_stop_percent }}" step="0.5" min="0.5" max="5">
                </div>
            </div>
            <div class="mt-10"><button type="submit" class="btn btn-warning">💾 Save</button></div>
        </form>
    </div>

    <!-- Open Trades -->
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

    <!-- Trade History -->
    <div class="section">
        <h2>📋 Trade History</h2>
        <table>
            <thead><tr><th>Time</th><th>Symbol</th><th>Type</th><th>Price</th><th>Volume</th><th>Status</th></tr></thead>
            <tbody>
                {% for t in trades_history %}
                <tr><td>{{ t.entry_time }}</td><td>{{ t.symbol }}</td><td class="{{ 'buy' if t.type == 'BUY' else 'sell' }}">{{ t.type }}</td><td>{{ t.entry_price }}</td><td>{{ t.quantity }}</td><td>{{ t.status }}</td></tr>
                {% else %}
                <tr><td colspan="6" style="text-align:center;color:#4a5a6e;">No trades</td></tr>
                {% endfor %}
            </tbody>
        </table>
    </div>

    <div class="footer">🚀 Smart Trading Bot | SMC+ICT+Volume Profile | Exness Ready</div>
</div>
</body>
</html>
"""

# =============================================
# 8. Routes
# =============================================

@app.route('/')
def index():
    balance = 10000
    open_positions = [t for t in trades if t['status'] == 'OPEN']
    pending_orders_list = [o for o in legacy_manager.pending_orders if o['status'] == 'PENDING']
    
    # حساب نسبة الفوز
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
            return jsonify({'status': 'blocked', 'reason': f'Signal mismatch: {analysis["signal"]} != {action}'}), 200
        trade = execute_trade(symbol, action, analysis['entry_price'], analysis['stop_loss'], analysis['take_profit'])
        return jsonify({'status': 'success', 'trade': trade})
    except Exception as e:
        logging.error(f"❌ Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 400

@app.route('/status')
def status():
    """الحصول على حالة البوت"""
    return jsonify({
        'bot_running': bot_running,
        'mt5_connected': mt5_connected,
        'total_trades': total_trades,
        'winning_trades': winning_trades,
        'win_rate': round((winning_trades / total_trades * 100) if total_trades > 0 else 0, 1),
        'open_trades': len([t for t in trades if t['status'] == 'OPEN']),
        'pending_orders': len([o for o in legacy_manager.pending_orders if o['status'] == 'PENDING'])
    })

@app.route('/reconnect_mt5', methods=['POST'])
def reconnect_mt5():
    """محاولة إعادة الاتصال بـ MT5"""
    global mt5_connected
    mt5_connected = initialize_mt5()
    return jsonify({
        'status': 'success',
        'mt5_connected': mt5_connected,
        'message': 'MT5 reconnected' if mt5_connected else 'MT5 connection failed'
    })

# =============================================
# 9. Run Server
# =============================================

if __name__ == '__main__':
    # بدء حلقة التداول في خلفية
    thread = threading.Thread(target=trading_loop, daemon=True)
    thread.start()
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
