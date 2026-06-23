try:
    import MetaTrader5 as mt5
except ImportError:
    import mt5linux as mt5
    print("⚠️ باستخدام mt5linux (بديل لـ Linux)")

import logging

logging.basicConfig(level=logging.INFO)

# =============================================
# بيانات الحساب (Exness)
# =============================================
ACCOUNT = 262946340
PASSWORD = 'Mama1965.'
SERVER = 'Exness-MT5Trial16'

class MT5Connector:
    def __init__(self, account=None, password=None, server=None):
        self.account = account if account else ACCOUNT
        self.password = password if password else PASSWORD
        self.server = server if server else SERVER
        self.connected = False
    
    def connect(self):
        try:
            if not mt5.initialize():
                logging.error("❌ فشل تهيئة MT5")
                return False
            if self.account and self.password and self.server:
                if mt5.login(int(self.account), self.password, self.server):
                    logging.info(f"✅ تم الاتصال بـ MT5 (الحساب: {self.account})")
                    self.connected = True
                    account_info = mt5.account_info()
                    if account_info:
                        logging.info(f"💰 الرصيد: {account_info.balance:.2f} {account_info.currency}")
                    return True
                else:
                    logging.error(f"❌ فشل تسجيل الدخول")
                    return False
            self.connected = True
            return True
        except Exception as e:
            logging.error(f"❌ خطأ في الاتصال: {e}")
            return False
    
    def disconnect(self):
        mt5.shutdown()
        self.connected = False
        logging.info("✅ تم فصل الاتصال بـ MT5")
    
    def get_balance(self):
        if not self.connected:
            self.connect()
        account_info = mt5.account_info()
        return account_info.balance if account_info else 0
    
    def get_price(self, symbol):
        if not self.connected:
            self.connect()
        tick = mt5.symbol_info_tick(symbol)
        return tick.ask if tick else 0
    
    def place_order(self, symbol, action, volume, stop_loss=None, take_profit=None, comment="Bot"):
        if not self.connected:
            self.connect()
        try:
            price = self.get_price(symbol)
            if price == 0:
                logging.error("❌ فشل الحصول على السعر")
                return None
            order_type = mt5.ORDER_TYPE_BUY if action == 'BUY' else mt5.ORDER_TYPE_SELL
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": volume,
                "type": order_type,
                "price": price,
                "sl": stop_loss,
                "tp": take_profit,
                "deviation": 20,
                "magic": 234000,
                "comment": comment,
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            result = mt5.order_send(request)
            if result.retcode == mt5.TRADE_RETCODE_DONE:
                logging.info(f"✅ {action} {symbol} | السعر: {price} | الحجم: {volume}")
                return result
            else:
                logging.error(f"❌ فشل التنفيذ: {result.comment}")
                return None
        except Exception as e:
            logging.error(f"❌ خطأ في التنفيذ: {e}")
