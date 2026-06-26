"""
risk_manager.py - إدارة المخاطر والصفقات المتفرعة
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta

class TradeManager:
    def __init__(self, initial_balance=10000, risk_per_trade=0.10):
        self.balance = initial_balance
        self.initial_balance = initial_balance
        self.risk_per_trade = risk_per_trade
        self.trades = []
        self.consecutive_losses = 0
        self.max_consecutive_losses = 3
        self.weekly_loss = 0
        self.weekly_loss_limit = 0.20
        self.monthly_loss = 0
        self.monthly_loss_limit = 0.30
        self.last_trade_date = None
        self.is_trading_halted = False
        self.halt_until = None
        
        self.split_config = [
            {'ratio': 0.40, 'tp_multiplier': 1.5, 'stop_type': 'fixed', 'label': 'الصفقة الأولى'},
            {'ratio': 0.30, 'tp_multiplier': 3.0, 'stop_type': 'breakeven', 'label': 'الصفقة الثانية'},
            {'ratio': 0.30, 'tp_multiplier': 4.0, 'stop_type': 'trailing', 'label': 'الصفقة الثالثة'}
        ]
    
    def calculate_splits(self, entry_price, stop_price, is_buy=True):
        total_risk = self.balance * self.risk_per_trade
        stop_distance = abs(entry_price - stop_price)
        
        if stop_distance == 0:
            stop_distance = 0.001
        
        trades = []
        for config in self.split_config:
            risk_amount = total_risk * config['ratio']
            lot_size = risk_amount / stop_distance
            
            if is_buy:
                tp = entry_price + (stop_distance * config['tp_multiplier'])
                sl = stop_price if config['stop_type'] == 'fixed' else entry_price
            else:
                tp = entry_price - (stop_distance * config['tp_multiplier'])
                sl = stop_price if config['stop_type'] == 'fixed' else entry_price
            
            trades.append({
                'label': config['label'],
                'lot_size': round(lot_size, 4),
                'entry': entry_price,
                'stop_loss': round(sl, 5),
                'take_profit': round(tp, 5),
                'risk': risk_amount,
                'ratio': config['ratio'],
                'tp_multiplier': config['tp_multiplier'],
                'stop_type': config['stop_type'],
                'entry_triggered': False,
                'closed': False
            })
        
        return trades
    
    def check_risk_limits(self, is_win, loss_amount=0):
        if is_win:
            self.consecutive_losses = 0
        else:
            self.consecutive_losses += 1
            self.weekly_loss += loss_amount
            self.monthly_loss += loss_amount
        
        if self.consecutive_losses >= self.max_consecutive_losses:
            self.is_trading_halted = True
            self.halt_until = datetime.now() + timedelta(days=3)
            print(f"⚠️ {self.consecutive_losses} خسائر متتالية! إيقاف التداول حتى {self.halt_until.strftime('%Y-%m-%d')}")
            return False
        
        if self.weekly_loss >= self.initial_balance * self.weekly_loss_limit:
            self.is_trading_halted = True
            self.halt_until = datetime.now() + timedelta(days=7)
            print("⚠️ تجاوز حد الخسارة الأسبوعية (20%)! إيقاف التداول.")
            return False
        
        if self.monthly_loss >= self.initial_balance * self.monthly_loss_limit:
            self.is_trading_halted = True
            self.halt_until = datetime.now() + timedelta(days=30)
            print("⚠️ تجاوز حد الخسارة الشهرية (30%)! إيقاف البوت.")
            return False
        
        return True
    
    def reset_weekly_loss(self):
        self.weekly_loss = 0
    
    def execute_trade(self, entry_price, stop_price, is_buy=True):
        if self.is_trading_halted:
            if self.halt_until and datetime.now() < self.halt_until:
                print(f"⏸️ التداول متوقف حتى {self.halt_until.strftime('%Y-%m-%d')}")
                return None
            else:
                self.is_trading_halted = False
                self.halt_until = None
                self.consecutive_losses = 0
        
        today = datetime.now().date()
        if self.last_trade_date == today:
            print("⚠️ تم تنفيذ صفقة اليوم بالفعل!")
            return None
        
        trades = self.calculate_splits(entry_price, stop_price, is_buy)
        trades[0]['entry_triggered'] = True
        
        trade_record = {
            'date': datetime.now(),
            'entry': entry_price,
            'stop': stop_price,
            'is_buy': is_buy,
            'splits': trades,
            'status': 'OPEN',
            'result': None,
            'profit': 0
        }
        
        self.trades.append(trade_record)
        self.last_trade_date = today
        
        print(f"\n📊 صفقة اليوم {today.strftime('%Y-%m-%d')}")
        print(f"نوع: {'شراء' if is_buy else 'بيع'}")
        print(f"الدخول: {entry_price}")
        print(f"وقف الخسارة: {stop_price}")
        print(f"حجم المركز: {self.balance * self.risk_per_trade:.2f} دولار (10%)")
        
        return trade_record
    
    def update_trades(self, current_price):
        if not self.trades or self.trades[-1]['status'] == 'CLOSED':
            return
        
        trade = self.trades[-1]
        splits = trade['splits']
        entry = trade['entry']
        is_buy = trade['is_buy']
        
        if is_buy:
            current_r = (current_price - entry) / (entry - trade['stop']) if entry != trade['stop'] else 0
        else:
            current_r = (entry - current_price) / (trade['stop'] - entry) if entry != trade['stop'] else 0
        
        if current_r >= 1.0 and not splits[1]['entry_triggered']:
            splits[1]['entry_triggered'] = True
            splits[1]['stop_loss'] = entry
            print("🔄 تم فتح الصفقة الثانية (هدف 3R)")
        
        if current_r >= 1.5 and not splits[2]['entry_triggered']:
            splits[2]['entry_triggered'] = True
            print("🔄 تم فتح الصفقة الثالثة (هدف 4R) مع Trailing Stop")
        
        total_profit = 0
        all_closed = True
        
        for i, split in enumerate(splits):
            if split['closed'] or not split['entry_triggered']:
                all_closed = False
                continue
            
            target_r = split['tp_multiplier']
            if is_buy:
                if current_price >= entry + ((entry - trade['stop']) * target_r):
                    profit = split['lot_size'] * (current_price - entry)
                    total_profit += profit
                    split['closed'] = True
                    print(f"✅ {split['label']} حققت هدف {target_r}R")
                elif current_price <= split['stop_loss']:
                    loss = split['lot_size'] * (entry - current_price)
                    total_profit -= loss
                    split['closed'] = True
                    print(f"❌ {split['label']} ضربت وقف الخسارة")
                else:
                    all_closed = False
            else:
                if current_price <= entry - ((trade['stop'] - entry) * target_r):
                    profit = split['lot_size'] * (entry - current_price)
                    total_profit += profit
                    split['closed'] = True
                    print(f"✅ {split['label']} حققت هدف {target_r}R")
                elif current_price >= split['stop_loss']:
                    loss = split['lot_size'] * (current_price - entry)
                    total_profit -= loss
                    split['closed'] = True
                    print(f"❌ {split['label']} ضربت وقف الخسارة")
                else:
                    all_closed = False
        
        if all_closed:
            trade['status'] = 'CLOSED'
            trade['profit'] = total_profit
            self.balance += total_profit
            is_win = total_profit > 0
            self.check_risk_limits(is_win, abs(total_profit) if not is_win else 0)
            print(f"\n💰 ربح/خسارة الصفقة: {total_profit:.2f} دولار")
            print(f"💰 الرصيد الجديد: {self.balance:.2f} دولار")
    
    def get_summary(self):
        total_profit = self.balance - self.initial_balance
        win_trades = sum(1 for t in self.trades if t.get('profit', 0) > 0)
        loss_trades = sum(1 for t in self.trades if t.get('profit', 0) < 0)
        total_trades = len(self.trades)
        
        print("\n" + "="*60)
        print("📊 ملخص الأداء")
        print("="*60)
        print(f"الرصيد الابتدائي: {self.initial_balance:.2f} دولار")
        print(f"الرصيد الحالي: {self.balance:.2f} دولار")
        print(f"صافي الربح: {total_profit:.2f} دولار ({total_profit/self.initial_balance*100:.1f}%)")
        print(f"عدد الصفقات: {total_trades}")
        if total_trades > 0:
            print(f"الصفقات الرابحة: {win_trades} ({win_trades/total_trades*100:.1f}%)")
            print(f"الصفقات الخاسرة: {loss_trades} ({loss_trades/total_trades*100:.1f}%)")
        print("="*60)
        
        return {
            'balance': self.balance,
            'total_profit': total_profit,
            'roi': total_profit / self.initial_balance * 100,
            'win_rate': win_trades / total_trades * 100 if total_trades > 0 else 0,
            'trades': total_trades
        }
