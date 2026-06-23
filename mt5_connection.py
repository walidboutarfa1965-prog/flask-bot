import MetaTrader5 as mt5
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
        """
        تهيئة الاتصال بـ MetaTrader 5
        - account: رقم الحساب
        - password: كلمة المرور
        - server: اسم السيرفر
        """
        self.account = account if account else ACCOUNT
        self.password = password if password else PASSWORD
        self.server = server if server else SERVER
        self.connected = False
    
    def connect(self):
        """الاتصال بـ MT5"""
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
            else:
                self.connected = True
                logging.info("✅ تم الاتصال بـ MT5 (بدون تسجيل دخول)")
                return True
                
        except Exception as e:
            logging.error(f"❌ خطأ في الاتصال: {e}")
            return False
    
    def disconnect(self):
        """فصل الاتصال بـ MT5"""
        mt5.shutdown()
        self.connected = False
        logging.info("✅ تم فصل الاتصال بـ MT5")
    
    def get_balance(self):
        """الحصول على رصيد الحساب"""
        if not self.connected:
            self.connect()
        account_info = mt5.account_info()
        return account_info.balance if account_info else 0
    
    def get_price(self, symbol):
        """الحصول على السعر الحالي"""
        if not self.connected:
            self.connect()
        tick = mt5.symbol_info_tick(symbol)
        return tick.ask if tick else 0
    
    def get_account_info(self):
        """الحصول على معلومات الحساب كاملة"""
        if not self.connected:
            self.connect()
        return mt5.account_info()
    
    def place_order(self, symbol, action, volume, stop_loss=None, take_profit=None, comment="Bot"):
        """تنفيذ أمر شراء أو بيع"""
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
            return None
    
    def close_position(self, position):
        """إغلاق صفقة مفتوحة"""
        if not self.connected:
            self.connect()
        
        try:
            action = mt5.ORDER_TYPE_SELL if position.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
            
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": position.symbol,
                "volume": position.volume,
                "type": action,
                "position": position.ticket,
                "price": mt5.symbol_info_tick(position.symbol).ask if action == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(position.symbol).bid,
                "deviation": 20,
                "magic": 234000,
                "comment": "Close by Bot",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            
            result = mt5.order_send(request)
            if result.retcode == mt5.TRADE_RETCODE_DONE:
                logging.info(f"✅ تم إغلاق الصفقة: {position.symbol}")
                return result
            else:
                logging.error(f"❌ فشل الإغلاق: {result.comment}")
                return None
                
        except Exception as e:
            logging.error(f"❌ خطأ في الإغلاق: {e}")
            return None

if __name__ == "__main__":
    connector = MT5Connector()
    if connector.connect():
        print("✅ تم الاتصال بـ MT5 بنجاح!")
        balance = connector.get_balance()
        print(f"💰 الرصيد: {balance}")
        connector.disconnect()
    else:
        print("❌ فشل الاتصال بـ MT5")
