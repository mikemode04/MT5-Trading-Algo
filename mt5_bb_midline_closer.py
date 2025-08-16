import MetaTrader5 as mt5
import pandas as pd
import time

# === PARAMETERE ===
TIMEFRAME = mt5.TIMEFRAME_M30
BB_PERIOD = 20
SLEEP_INTERVAL = 0.5
POST_CLOSE_DELAY = 2

# === INITIALISERING ===
if not mt5.initialize():
    print("MT5 init feil:", mt5.last_error())
    quit()

def get_midband(symbol):
    rates = mt5.copy_rates_from_pos(symbol, TIMEFRAME, 0, BB_PERIOD + 1)
    if rates is None or len(rates) < BB_PERIOD:
        return None
    df = pd.DataFrame(rates)
    sma_series = df['close'].rolling(BB_PERIOD).mean()
    mid = sma_series.iloc[-1]  # <- Dette gir garantert én float-verdi
    return float(mid) if pd.notnull(mid) else None


def close_position_direct(pos):
    symbol = pos.symbol
    ticket = pos.ticket
    volume = pos.volume
    order_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
    price = mt5.symbol_info_tick(symbol).bid if order_type == mt5.ORDER_TYPE_SELL else mt5.symbol_info_tick(symbol).ask

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": volume,
        "type": order_type,
        "position": ticket,  # <- kritisk: refererer til aktiv posisjon
        "price": price,
        "deviation": 10,
        "magic": 0,
        "comment": "Close via BB midband",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    if result.retcode == mt5.TRADE_RETCODE_DONE:
        print(f"[OK] Lukket posisjon {ticket} ({symbol}) til pris {price}")
        time.sleep(POST_CLOSE_DELAY)
        return True
    else:
        print(f"[FEIL] Klarte ikke lukke {symbol} (ticket {ticket}): {result.retcode}")
        return False

def track_and_close_positions():
    while True:
        positions = mt5.positions_get()
        if not positions:
            print("Ingen åpne posisjoner.")
        else:
            for pos in positions:
                symbol = pos.symbol
                tick = mt5.symbol_info_tick(symbol)
                if not tick:
                    print(f"[FEIL] Ingen tick-data for {symbol}")
                    continue

                price = tick.bid if pos.type == mt5.ORDER_TYPE_BUY else tick.ask
                midband = get_midband(symbol)
                if midband is None:
                    print(f"[ADVARSEL] Mangler midtbånd for {symbol}")
                    continue

                # === Korrekt lukkelogikk ===
                if pos.type == mt5.ORDER_TYPE_BUY and price >= midband:
                    print(f"[LONG] Pris {price:.5f} ≥ midtbånd {midband:.5f} → LUKKER")
                    close_position_direct(pos)
                elif pos.type == mt5.ORDER_TYPE_SELL and price <= midband:
                    print(f"[SHORT] Pris {price:.5f} ≤ midtbånd {midband:.5f} → LUKKER")
                    close_position_direct(pos)
                else:
                    print(f"[{symbol}] Pris: {price:.5f} | Midtbånd: {midband:.5f} → Holder åpen")

        time.sleep(SLEEP_INTERVAL)

# === START ===
track_and_close_positions()
