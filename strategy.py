"""
strategy.py - البوت الرئيسي الجامع لكل الفلاتر
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from analysis import *
from risk_manager import TradeManager

class SmartTradingBot:
    def __init__(self, initial_balance=10000):
        self.trade_manager = TradeManager(initial_balance, risk_per_trade=0.10)
        
        # إعدادات الأخبار
        self.news_times = [
            {'time': '15:30', 'impact': 'HIGH', 'name': 'NFP'},
            {'time': '20:00', 'impact': 'HIGH', 'name': 'FOMC'},
            {'time': '15:30', 'impact': 'HIGH', 'name': 'CPI'},
            {'time': '14:45', 'impact': 'HIGH', 'name': 'ECB'},
            {'time': '13:00', 'impact': 'HIGH', 'name': 'BOE'},
        ]
    
    def is_news_time(self):
        now = datetime.now()
        current_time = now.strftime('%H:%M')
        current_day = now.strftime('%A')
        
        if current_day == 'Friday':
            return True
        
        for news in self.news_times:
            news_time = datetime.strptime(news['time'], '%H:%M').time()
            current_time_obj = datetime.strptime(current_time, '%H:%M').time()
            
            time_diff = (datetime.combine(datetime.today(), current_time_obj) - 
                        datetime.combine(datetime.today(), news_time)).total_seconds() / 60
            
            if -30 <= time_diff <= 15:
                return True
        
        return False
    
    def fetch_data(self):
        """محاكاة جلب البيانات - استبدلها بـ API حقيقي"""
        np.random.seed(42)
        dates = pd.date_range(start='2024-01-01', periods=200, freq='1H')
        prices = 1.2000 + np.cumsum(np.random.randn(200) * 0.001)
        
        data = pd.DataFrame({
            'open': prices[:-1],
            'high': prices[:-1] + np.abs(np.random.randn(199) * 0.001),
            'low': prices[:-1] - np.abs(np.random.randn(199) * 0.001),
            'close': prices[1:],
            'volume': np.random.randint(1000, 5000, 199)
        }, index=dates[:-1])
        
        return data
    
    def analyze_trend(self, data):
        """تحليل الاتجاه (الفريم الكبير)"""
        ema_200 = calculate_ema(data, 200)
        rsi = calculate_rsi(data)
        swing_highs, swing_lows = find_swing_points(data)
        structure = detect_market_structure(swing_highs, swing_lows)
        
        is_uptrend = (
            data['close'].iloc[-1] > ema_200.iloc[-1] and
            structure == 'UPTREND' and
            rsi.iloc[-1] > 50
        )
        
        is_downtrend = (
            data['close'].iloc[-1] < ema_200.iloc[-1] and
            structure == 'DOWNTREND' and
            rsi.iloc[-1] < 50
        )
        
        accumulation = detect_accumulation_distribution(data)
        
        return {
            'direction': 'UPTREND' if is_uptrend else 'DOWNTREND' if is_downtrend else 'SIDEWAYS',
            'structure': structure,
            'ema_status': 'above' if data['close'].iloc[-1] > ema_200.iloc[-1] else 'below',
            'rsi': rsi.iloc[-1],
            'accumulation': accumulation,
            'swing_highs': swing_highs,
            'swing_lows': swing_lows
        }
    
    def analyze_zone(self, data, trend_info):
        """تحليل المنطقة (الفريم المتوسط)"""
        vp = find_volume_profile(data)
        poc = vp['poc']
        swing_highs, swing_lows = find_swing_points(data)
        fvg_zones = find_fvg(data)
        
        demand_zones = []
        supply_zones = []
        
        for i in range(len(data) - 10, len(data)):
            if data['low'].iloc[i] < data['low'].iloc[i-5] and data['volume'].iloc[i] > data['volume'].mean():
                demand_zones.append({
                    'price': data['low'].iloc[i],
                    'strength': data['volume'].iloc[i] / data['volume'].mean()
                })
            
            if data['high'].iloc[i] > data['high'].iloc[i-5] and data['volume'].iloc[i] > data['volume'].mean():
                supply_zones.append({
                    'price': data['high'].iloc[i],
                    'strength': data['volume'].iloc[i] / data['volume'].mean()
                })
        
        current_price = data['close'].iloc[-1]
        best_zone = None
        zone_type = None
        
        if trend_info['direction'] == 'UPTREND':
            for zone in demand_zones:
                if abs(zone['price'] - poc['price_low']) < 0.01:
                    best_zone = zone
                    zone_type = 'DEMAND'
                    break
        elif trend_info['direction'] == 'DOWNTREND':
            for zone in supply_zones:
                if abs(zone['price'] - poc['price_high']) < 0.01:
                    best_zone = zone
                    zone_type = 'SUPPLY'
                    break
        
        has_liquidity = (
            len(swing_highs) > 0 and abs(current_price - swing_highs[-1][1]) < 0.005
        ) or (
            len(swing_lows) > 0 and abs(current_price - swing_lows[-1][1]) < 0.005
        )
        
        return {
            'best_zone': best_zone,
            'zone_type': zone_type,
            'poc': poc,
            'has_fvg': len(fvg_zones) > 0,
            'has_liquidity': has_liquidity,
            'hvn': vp['hvn'],
            'lvn': vp['lvn']
        }
    
    def analyze_trigger(self, data, trend_info, zone_info):
        """تحليل التأكيد (الفريم الصغير)"""
        swing_highs, swing_lows = find_swing_points(data)
        choch = detect_choch(data, swing_highs, swing_lows)
        bos = detect_break_of_structure(data, swing_highs, swing_lows)
        liquidity_sweep = detect_liquidity_sweep(data, swing_highs, swing_lows)
        rsi_divergence = detect_rsi_divergence(data)
        pinbar = detect_pinbar(data)
        engulfing = detect_engulfing(data)
        
        avg_volume = data['volume'].mean()
        current_volume = data['volume'].iloc[-1]
        high_volume = current_volume > avg_volume * 1.5
        
        rsi = calculate_rsi(data).iloc[-1]
        rsi_confirmation = (
            (trend_info['direction'] == 'UPTREND' and rsi > 50) or
            (trend_info['direction'] == 'DOWNTREND' and rsi < 50)
        )
        
        fvg_zones = find_fvg(data)
        near_fvg = False
        current_price = data['close'].iloc[-1]
        for fvg in fvg_zones:
            if fvg['low'] <= current_price <= fvg['high']:
                near_fvg = True
                break
        
        if len(data) > 5:
            recent_high = data['high'].iloc[-6:-1].max()
            recent_low = data['low'].iloc[-6:-1].min()
            breakout = detect_true_breakout(
                data, 
                recent_high if trend_info['direction'] == 'UPTREND' else recent_low
            )
        else:
            breakout = None
        
        conditions_met = sum([
            choch is not None,
            bos is not None,
            liquidity_sweep is not None,
            rsi_divergence is not None,
            pinbar is not None or engulfing is not None,
            high_volume,
            rsi_confirmation,
            near_fvg,
            breakout == 'TRUE_BREAKOUT'
        ])
        
        is_confirmed = conditions_met >= 5 and trend_info['direction'] != 'SIDEWAYS'
        
        return {
            'choch': choch,
            'bos': bos,
            'liquidity_sweep': liquidity_sweep,
            'rsi_divergence': rsi_divergence,
            'pinbar': pinbar,
            'engulfing': engulfing,
            'high_volume': high_volume,
            'rsi_confirmation': rsi_confirmation,
            'near_fvg': near_fvg,
            'breakout': breakout,
            'conditions_met': conditions_met,
            'is_confirmed': is_confirmed
        }
    
    def get_trading_decision(self, data_4h, data_1h, data_15m):
        """الحصول على قرار التداول النهائي"""
        # الخطوة 1: تحليل الاتجاه (4 ساعات)
        trend = self.analyze_trend(data_4h)
        print(f"الاتجاه: {trend['direction']}")
        
        if trend['direction'] == 'SIDEWAYS':
            return {'decision': 'WAIT', 'reason': 'SIDEWAYS_MARKET'}
        
        # الخطوة 2: تحليل المنطقة (ساعة)
        zone = self.analyze_zone(data_1h, trend)
        print(f"المنطقة: {zone['zone_type']}")
        
        if zone['best_zone'] is None:
            return {'decision': 'WAIT', 'reason': 'NO_ZONE'}
        
        # الخطوة 3: تحليل التأكيد (15 دقيقة)
        trigger = self.analyze_trigger(data_15m, trend, zone)
        print(f"شروط التأكيد: {trigger['conditions_met']}/9")
        
        if not trigger['is_confirmed']:
            return {'decision': 'WAIT', 'reason': 'NO_TRIGGER'}
        
        if self.is_news_time():
            return {'decision': 'WAIT', 'reason': 'NEWS_TIME'}
        
        today = datetime.now().date()
        if self.trade_manager.last_trade_date == today:
            return {'decision': 'WAIT', 'reason': 'DAILY_TRADE_DONE'}
        
        current_price = data_15m['close'].iloc[-1]
        atr = calculate_atr(data_15m).iloc[-1]
        
        if trend['direction'] == 'UPTREND':
            entry = current_price
            stop = current_price - atr * 1.5
            decision = 'BUY'
        else:
            entry = current_price
            stop = current_price + atr * 1.5
            decision = 'SELL'
        
        return {
            'decision': decision,
            'entry': entry,
            'stop': stop,
            'trend': trend,
            'zone': zone,
            'trigger': trigger
        }
    
    def run_daily_cycle(self):
        """تشغيل دورة التداول اليومية"""
        print("="*70)
        print(f"🚀 Smart Trading Bot - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print("="*70)
        
        if self.trade_manager.is_trading_halted:
            if self.trade_manager.halt_until and datetime.now() < self.trade_manager.halt_until:
                print(f"⏸️ التداول متوقف حتى {self.trade_manager.halt_until.strftime('%Y-%m-%d')}")
                return
            else:
                self.trade_manager.is_trading_halted = False
                self.trade_manager.halt_until = None
        
        data_4h = self.fetch_data()
        data_1h = self.fetch_data()
        data_15m = self.fetch_data()
        
        decision = self.get_trading_decision(data_4h, data_1h, data_15m)
        
        if decision['decision'] in ['BUY', 'SELL']:
            is_buy = decision['decision'] == 'BUY'
            self.trade_manager.execute_trade(decision['entry'], decision['stop'], is_buy)
        else:
            print(f"⏳ انتظار: {decision['reason']}")
        
        return self.trade_manager.get_summary()
