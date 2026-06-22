# mt5_connection.py
import MetaTrader5 as mt5
import logging

logging.basicConfig(level=logging.INFO)

class MT5Connector:
    def __init__(self, account=None, password=None, server=None):
        self.account = account
        self.password = password
        self.server = server
        self.connected = False
    
    def connect(self):
        try:
            if not mt5.initialize():
                logging.error(f"❌ فشل تهيئة MT5: {mt5.last_error()}")
                return False
            
            if self.account and self.password and self.server:
                if mt5.login(int(self.account), self.password, self.server):
                    logging.info(f"✅ تم الاتصال بـ MT5 بنجاح")
                    self.connected = True
                    account_info = mt5.account_info()
                    if account_info:
                        logging.info(f"💰 الرصيد: {account_info.balance:.2f} {account_info.currency}")
                    return True
                else:
                    logging.error(f"❌ فشل تسجيل الدخول: {mt5.last_error()}")
                    return False
            else:
                self.connected = True
                logging.info("✅ تم الاتصال بـ MT5")
                return True
        except Exception as e:
            logging.error(f"❌ خطأ: {e}")
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
    
    def place_order(self, symbol, action, volume, stop_loss=None, take_profit=None):
        if not self.connected:
            self.connect()
        try:
            price = self.get_price(symbol)
            if price == 0:
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
                "comment": f"Bot {action}",
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

if __name__ == "__main__":
    connector = MT5Connector()
    if connector.connect():
        balance = connector.get_balance()
        print(f"💰 الرصيد: {balance}")
        connector.disconnect()
      add mt5_connection
