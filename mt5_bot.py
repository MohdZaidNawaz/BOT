import time
from datetime import datetime

import MetaTrader5 as mt5
import pandas as pd

from new import generate_signals


# --------------------------------------------------------------------------
# CONFIG - edit these for your setup
# --------------------------------------------------------------------------

# Demo account connection details
DEMO_LOGIN = 505837650
DEMO_PASSWORD = "Kx-cPi8x"
DEMO_SERVER = "MetaQuotes-Demo"

SYMBOL = "XAUUSD"
TIMEFRAME = mt5.TIMEFRAME_M5      # e.g. M1, M5, M15, H1
LOT_SIZE = 0.10
MAGIC_NUMBER = 123456             # unique ID so this bot only manages its own trades
STOP_LOSS_PIPS = 30
TAKE_PROFIT_PIPS = 30
BARS_TO_FETCH = 5000              # how much history to pull each check
POLL_SECONDS = 30                 # how often to check for a new candle

UT_KEY_VALUE = 2.0
UT_ATR_PERIOD = 1
HMA_PERIOD = 31
ORB_START = "10:10"
ORB_END = "10:15"


# --------------------------------------------------------------------------
# MT5 CONNECTION
# --------------------------------------------------------------------------

def connect(login: int = None, password: str = None, server: str = None) -> bool:
    """
    Initializes connection to the running MT5 terminal.
    If login/password/server are omitted, it uses whatever account
    is already logged into the terminal.
    """
    if login and password and server:
        ok = mt5.initialize(login=login, password=password, server=server)
    else:
        ok = mt5.initialize()

    if not ok:
        print("MT5 initialize() failed:", mt5.last_error())
        return False

    print("Connected to MT5:", mt5.account_info())
    return True


def shutdown():
    mt5.shutdown()


# --------------------------------------------------------------------------
# DATA
# --------------------------------------------------------------------------

def fetch_ohlc(symbol: str, timeframe, n_bars: int) -> pd.DataFrame:
    """Pulls the last n_bars candles from MT5 and returns an OHLC DataFrame."""
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, n_bars)
    if rates is None or len(rates) == 0:
        raise RuntimeError(f"No data returned for {symbol}: {mt5.last_error()}")

    df = pd.DataFrame(rates)
    df["time"] = pd.to_datetime(df["time"], unit="s")
    df.set_index("time", inplace=True)
    df.rename(columns={"tick_volume": "volume"}, inplace=True)
    return df[["open", "high", "low", "close", "volume"]]


# --------------------------------------------------------------------------
# ORDER MANAGEMENT
# --------------------------------------------------------------------------

def get_open_position(symbol: str):
    """Returns the bot's open position on this symbol, if any (by magic number)."""
    positions = mt5.positions_get(symbol=symbol)
    if positions is None:
        return None
    for p in positions:
        if p.magic == MAGIC_NUMBER:
            return p
    return None


def close_position(position):
    """Closes an existing position."""
    symbol = position.symbol
    tick = mt5.symbol_info_tick(symbol)
    order_type = mt5.ORDER_TYPE_SELL if position.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
    price = tick.bid if order_type == mt5.ORDER_TYPE_SELL else tick.ask

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": position.volume,
        "type": order_type,
        "position": position.ticket,
        "price": price,
        "deviation": 10,
        "magic": MAGIC_NUMBER,
        "comment": "close by signal flip",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(request)
    print("Close result:", result)
    return result


def open_position(symbol: str, direction: str):
    """
    Opens a new market position.
    direction: 'buy' or 'sell'
    """
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        print(f"Symbol {symbol} not found")
        return None

    point = symbol_info.point
    tick = mt5.symbol_info_tick(symbol)

    if direction == "buy":
        order_type = mt5.ORDER_TYPE_BUY
        price = tick.ask
        sl = price - STOP_LOSS_PIPS * point * 10
        tp = price + TAKE_PROFIT_PIPS * point * 10
    else:
        order_type = mt5.ORDER_TYPE_SELL
        price = tick.bid
        sl = price + STOP_LOSS_PIPS * point * 10
        tp = price - TAKE_PROFIT_PIPS * point * 10

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": LOT_SIZE,
        "type": order_type,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": 10,
        "magic": MAGIC_NUMBER,
        "comment": "UT_HMA_ORB signal",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(request)
    print("Open result:", result)
    return result


# --------------------------------------------------------------------------
# MAIN LOOP
# --------------------------------------------------------------------------

def run():
    if not connect():
        return

    last_bar_time = None

    try:
        while True:
            df = fetch_ohlc(SYMBOL, TIMEFRAME, BARS_TO_FETCH)
            latest_bar_time = df.index[-1]

            # Only act once per new closed candle (avoid re-triggering mid-bar)
            if latest_bar_time != last_bar_time:
                last_bar_time = latest_bar_time

                signals = generate_signals(
                    df,
                    ut_key_value=UT_KEY_VALUE,
                    ut_atr_period=UT_ATR_PERIOD,
                    hma_period=HMA_PERIOD,
                    orb_start=ORB_START,
                    orb_end=ORB_END,
                )
                latest = signals.iloc[-1]

                position = get_open_position(SYMBOL)

                print(
                    f"[{datetime.now()}] bar={latest_bar_time} "
                    f"close={latest['close']:.5f} "
                    f"long={latest['long_signal']} short={latest['short_signal']} "
                    f"open_position={'yes' if position else 'no'}"
                )

                if latest["long_signal"]:
                    if position and position.type == mt5.ORDER_TYPE_SELL:
                        close_position(position)
                        position = None
                    if not position:
                        open_position(SYMBOL, "buy")

                elif latest["short_signal"]:
                    if position and position.type == mt5.ORDER_TYPE_BUY:
                        close_position(position)
                        position = None
                    if not position:
                        open_position(SYMBOL, "sell")

            time.sleep(POLL_SECONDS)

    except KeyboardInterrupt:
        print("Stopped by user.")
    finally:
        shutdown()


if __name__ == "__main__":
    if DEMO_SERVER == "YOUR_DEMO_SERVER":
        print("Set DEMO_SERVER to your broker's MT5 demo server before running this bot.")
    else:
        if connect(login=DEMO_LOGIN, password=DEMO_PASSWORD, server=DEMO_SERVER):
            run()
