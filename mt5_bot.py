import os
import time
from datetime import datetime

import MetaTrader5 as mt5
import pandas as pd

from new import generate_signals


# ==========================================================================
# CONFIGURATION
# ==========================================================================

SYMBOL = "XAUUSD"

TIMEFRAME = mt5.TIMEFRAME_M1

LOT_SIZE = 0.10

MAGIC_NUMBER = 123456


# --------------------------------------------------------------------------
# SL / TP
#
# EXACTLY from your MQL5:
#
# Stop loss = ATR x 10
# Take profit = ATR x 200
# --------------------------------------------------------------------------

SL_ATR_MULTIPLIER = 10.0
TP_ATR_MULTIPLIER = 200.0


# --------------------------------------------------------------------------
# UT BOT
# --------------------------------------------------------------------------

UT_KEY_VALUE = 2.0

UT_ATR_PERIOD = 1


# --------------------------------------------------------------------------
# HMA
# --------------------------------------------------------------------------

HMA_PERIOD = 31


# --------------------------------------------------------------------------
# ORB
# --------------------------------------------------------------------------

ORB_START = "10:10"
ORB_END = "10:15"


# --------------------------------------------------------------------------
# HISTORY
# --------------------------------------------------------------------------

BARS_TO_FETCH = 3000


# --------------------------------------------------------------------------
# LOOP
# --------------------------------------------------------------------------

POLL_SECONDS = 30


# --------------------------------------------------------------------------
# CUSTOM BACKTEST PERIOD
# --------------------------------------------------------------------------

USE_CUSTOM_PERIOD = False

START_DATE = pd.Timestamp(
    "2026-01-01 00:00:00"
)

END_DATE = pd.Timestamp(
    "2026-12-31 23:59:00"
)


# ==========================================================================
# MT5 LOGIN
# ==========================================================================
#
# IMPORTANT:
#
# Do NOT put your real password directly in this file.
#
# Set these environment variables instead:
#
#   MT5_LOGIN
#   MT5_PASSWORD
#   MT5_SERVER
#
# ==========================================================================

DEMO_LOGIN = int(
    os.getenv("MT5_LOGIN", "0")
)

DEMO_PASSWORD = os.getenv(
    "MT5_PASSWORD",
    ""
)

DEMO_SERVER = os.getenv(
    "MT5_SERVER",
    ""
)


# ==========================================================================
# MT5 CONNECTION
# ==========================================================================

def connect(
    login=None,
    password=None,
    server=None,
):
    """
    Connect to MetaTrader 5.

    If credentials are supplied, login with them.

    Otherwise connect to the currently
    logged-in MT5 terminal.
    """

    # --------------------------------------------------------------
    # Credential login
    # --------------------------------------------------------------

    if login and password and server:

        print(
            f"Connecting to MT5 account {login} "
            f"on server '{server}'..."
        )

        success = mt5.initialize(
            login=login,
            password=password,
            server=server,
        )

    # --------------------------------------------------------------
    # Existing terminal login
    # --------------------------------------------------------------

    else:

        print(
            "Connecting to the currently "
            "logged-in MT5 terminal..."
        )

        success = mt5.initialize()

    # --------------------------------------------------------------
    # Connection failed
    # --------------------------------------------------------------

    if not success:

        print(
            "MT5 initialize() failed:"
        )

        print(
            mt5.last_error()
        )

        return False

    # --------------------------------------------------------------
    # Account information
    # --------------------------------------------------------------

    account = mt5.account_info()

    if account is None:

        print(
            "Connected to MT5, but "
            "account_info() returned None."
        )

        print(
            mt5.last_error()
        )

        mt5.shutdown()

        return False

    print()
    print("=" * 70)
    print("MT5 CONNECTION SUCCESSFUL")
    print("=" * 70)

    print(
        "Login   :",
        account.login
    )

    print(
        "Server  :",
        account.server
    )

    print(
        "Balance :",
        account.balance
    )

    print(
        "Equity  :",
        account.equity
    )

    print("=" * 70)
    print()

    return True


# ==========================================================================
# SHUTDOWN
# ==========================================================================

def shutdown():
    mt5.shutdown()

    print(
        "MT5 connection closed."
    )


# ==========================================================================
# SYMBOL SETUP
# ==========================================================================

def prepare_symbol(symbol):
    """
    Make sure the symbol exists and is visible.
    """

    info = mt5.symbol_info(symbol)

    if info is None:

        print(
            f"Symbol '{symbol}' was not found."
        )

        return False

    if not info.visible:

        print(
            f"{symbol} is not visible. "
            "Selecting it..."
        )

        if not mt5.symbol_select(
            symbol,
            True,
        ):

            print(
                f"Could not select {symbol}"
            )

            return False

    return True


# ==========================================================================
# DATA
# ==========================================================================

def fetch_ohlc(
    symbol,
    timeframe,
    n_bars,
):
    """
    Fetch CLOSED candles only.

    MQL5 uses:

        CopyRates(
            _Symbol,
            PERIOD_CURRENT,
            1,
            total,
            rates
        );

    Therefore Python also starts from position 1.

    Position 0 = currently forming candle
    Position 1 = latest CLOSED candle
    """

    rates = mt5.copy_rates_from_pos(
        symbol,
        timeframe,
        1,
        n_bars,
    )

    if rates is None:

        raise RuntimeError(
            f"MT5 returned no rates: "
            f"{mt5.last_error()}"
        )

    if len(rates) == 0:

        raise RuntimeError(
            f"No OHLC data returned for "
            f"{symbol}: {mt5.last_error()}"
        )

    df = pd.DataFrame(rates)

    # --------------------------------------------------------------
    # Convert Unix timestamp
    # --------------------------------------------------------------

    df["time"] = pd.to_datetime(
        df["time"],
        unit="s",
    )

    df.set_index(
        "time",
        inplace=True,
    )

    # --------------------------------------------------------------
    # Rename volume
    # --------------------------------------------------------------

    df.rename(
        columns={
            "tick_volume": "volume"
        },
        inplace=True,
    )

    required_columns = [
        "open",
        "high",
        "low",
        "close",
        "volume",
    ]

    return df[
        required_columns
    ]


# ==========================================================================
# CUSTOM PERIOD
# ==========================================================================

def in_custom_period(bar_time):
    """
    Same purpose as MQL5 InCustomPeriod().
    """

    if not USE_CUSTOM_PERIOD:
        return True

    timestamp = pd.Timestamp(
        bar_time
    )

    return (
        timestamp >= START_DATE
        and
        timestamp <= END_DATE
    )


# ==========================================================================
# GET OPEN POSITION
# ==========================================================================

def get_open_position(symbol):
    """
    Find the bot's position using MAGIC_NUMBER.

    This is slightly safer than blindly managing
    every position on the symbol.
    """

    positions = mt5.positions_get(
        symbol=symbol
    )

    if positions is None:
        return None

    for position in positions:

        if (
            position.magic
            == MAGIC_NUMBER
        ):
            return position

    return None


# ==========================================================================
# PRICE NORMALIZATION
# ==========================================================================

def normalize_price(
    symbol,
    price,
):
    """
    Normalize price to the symbol's digits.
    """

    info = mt5.symbol_info(
        symbol
    )

    if info is None:
        return price

    return round(
        price,
        info.digits,
    )


# ==========================================================================
# CLOSE POSITION
# ==========================================================================

def close_position(position):
    """
    Close an existing position.

    Equivalent to:

        trade.PositionClose(_Symbol)
    """

    symbol = position.symbol

    tick = mt5.symbol_info_tick(
        symbol
    )

    if tick is None:

        print(
            "Could not get tick for",
            symbol,
        )

        return None

    # --------------------------------------------------------------
    # If existing position is BUY,
    # close using SELL.
    #
    # If existing position is SELL,
    # close using BUY.
    # --------------------------------------------------------------

    if (
        position.type
        == mt5.POSITION_TYPE_BUY
    ):

        order_type = (
            mt5.ORDER_TYPE_SELL
        )

        price = tick.bid

    else:

        order_type = (
            mt5.ORDER_TYPE_BUY
        )

        price = tick.ask

    request = {

        "action":
            mt5.TRADE_ACTION_DEAL,

        "symbol":
            symbol,

        "volume":
            position.volume,

        "type":
            order_type,

        "position":
            position.ticket,

        "price":
            price,

        "deviation":
            10,

        "magic":
            MAGIC_NUMBER,

        "comment":
            "close by signal flip",

        "type_time":
            mt5.ORDER_TIME_GTC,

        "type_filling":
            mt5.ORDER_FILLING_IOC,
    }

    print()
    print(
        "Closing position:",
        position.ticket,
    )

    result = mt5.order_send(
        request
    )

    print(
        "Close result:",
        result,
    )

    return result


# ==========================================================================
# OPEN POSITION
# ==========================================================================

def open_position(
    symbol,
    direction,
    current_atr,
):
    """
    Open BUY or SELL.

    MQL5:

        slDistance =
            currentAtr * InpSLAtrMultiplier;

        tpDistance =
            currentAtr * InpTPAtrMultiplier;
    """

    # --------------------------------------------------------------
    # Symbol
    # --------------------------------------------------------------

    symbol_info = mt5.symbol_info(
        symbol
    )

    if symbol_info is None:

        print(
            f"Symbol {symbol} not found."
        )

        return None

    # --------------------------------------------------------------
    # Tick
    # --------------------------------------------------------------

    tick = mt5.symbol_info_tick(
        symbol
    )

    if tick is None:

        print(
            f"No tick data for {symbol}"
        )

        return None

    # --------------------------------------------------------------
    # Validate ATR
    # --------------------------------------------------------------

    if (
        current_atr is None
        or pd.isna(current_atr)
        or current_atr <= 0
    ):

        print(
            "Invalid ATR:",
            current_atr,
        )

        return None

    # --------------------------------------------------------------
    # EXACT MQL5 DISTANCES
    # --------------------------------------------------------------

    sl_distance = (
        current_atr
        * SL_ATR_MULTIPLIER
    )

    tp_distance = (
        current_atr
        * TP_ATR_MULTIPLIER
    )

    # --------------------------------------------------------------
    # BUY
    # --------------------------------------------------------------

    if direction == "buy":

        order_type = (
            mt5.ORDER_TYPE_BUY
        )

        price = tick.ask

        sl = (
            price
            - sl_distance
        )

        tp = (
            price
            + tp_distance
        )

    # --------------------------------------------------------------
    # SELL
    # --------------------------------------------------------------

    elif direction == "sell":

        order_type = (
            mt5.ORDER_TYPE_SELL
        )

        price = tick.bid

        sl = (
            price
            + sl_distance
        )

        tp = (
            price
            - tp_distance
        )

    else:

        raise ValueError(
            "direction must be 'buy' or 'sell'"
        )

    # --------------------------------------------------------------
    # Normalize prices
    # --------------------------------------------------------------

    price = normalize_price(
        symbol,
        price,
    )

    sl = normalize_price(
        symbol,
        sl,
    )

    tp = normalize_price(
        symbol,
        tp,
    )

    # --------------------------------------------------------------
    # Build request
    # --------------------------------------------------------------

    request = {

        "action":
            mt5.TRADE_ACTION_DEAL,

        "symbol":
            symbol,

        "volume":
            LOT_SIZE,

        "type":
            order_type,

        "price":
            price,

        "sl":
            sl,

        "tp":
            tp,

        "deviation":
            10,

        "magic":
            MAGIC_NUMBER,

        "comment":
            "UT_HMA_ORB signal",

        "type_time":
            mt5.ORDER_TIME_GTC,

        "type_filling":
            mt5.ORDER_FILLING_IOC,
    }

    print()
    print("=" * 70)

    print(
        f"OPEN {direction.upper()}"
    )

    print(
        "Symbol :",
        symbol,
    )

    print(
        "Volume :",
        LOT_SIZE,
    )

    print(
        "ATR    :",
        current_atr,
    )

    print(
        "Price  :",
        price,
    )

    print(
        "SL     :",
        sl,
    )

    print(
        "TP     :",
        tp,
    )

    print("=" * 70)

    # --------------------------------------------------------------
    # Send order
    # --------------------------------------------------------------

    result = mt5.order_send(
        request
    )

    print(
        "Open result:",
        result,
    )

    return result


# ==========================================================================
# SIGNAL PROCESSING
# ==========================================================================

def process_signal(
    df,
    latest_bar_time,
):
    """
    Calculate indicators and process the
    latest CLOSED candle.
    """

    # --------------------------------------------------------------
    # Custom period
    # --------------------------------------------------------------

    if not in_custom_period(
        latest_bar_time
    ):

        print(
            f"{latest_bar_time} "
            "outside custom period."
        )

        return

    # --------------------------------------------------------------
    # Generate indicators
    # --------------------------------------------------------------

    signals = generate_signals(
        df,

        ut_key_value=
            UT_KEY_VALUE,

        ut_atr_period=
            UT_ATR_PERIOD,

        hma_period=
            HMA_PERIOD,

        orb_start=
            ORB_START,

        orb_end=
            ORB_END,
    )

    # --------------------------------------------------------------
    # Latest CLOSED candle
    # --------------------------------------------------------------

    latest = signals.iloc[-1]

    # --------------------------------------------------------------
    # Extract values
    # --------------------------------------------------------------

    close_price = float(
        latest["close"]
    )

    current_atr = float(
        latest["atr"]
    )

    long_signal = bool(
        latest["long_signal"]
    )

    short_signal = bool(
        latest["short_signal"]
    )

    # --------------------------------------------------------------
    # Print diagnostics
    # --------------------------------------------------------------

    print()
    print("-" * 70)

    print(
        f"Bar       : {latest_bar_time}"
    )

    print(
        f"Close     : {close_price:.5f}"
    )

    print(
        f"ATR       : {current_atr:.5f}"
    )

    print(
        f"UT Buy    : {bool(latest['ut_buy'])}"
    )

    print(
        f"UT Sell   : {bool(latest['ut_sell'])}"
    )

    print(
        f"HMA       : {latest['hma']}"
    )

    print(
        f"HMA Rising: {bool(latest['hma_rising'])}"
    )

    print(
        f"ORB High  : {latest['orb_high']}"
    )

    print(
        f"ORB Low   : {latest['orb_low']}"
    )

    print(
        f"LONG      : {long_signal}"
    )

    print(
        f"SHORT     : {short_signal}"
    )

    # --------------------------------------------------------------
    # Current bot position
    # --------------------------------------------------------------

    position = get_open_position(
        SYMBOL
    )

    print(
        "Position  :",
        "YES" if position else "NO",
    )

    print("-" * 70)

    # ==================================================================
    # LONG SIGNAL
    # ==================================================================

    if long_signal:

        # --------------------------------------------------------------
        # Existing SELL
        # --------------------------------------------------------------

        if (
            position is not None
            and
            position.type
            == mt5.POSITION_TYPE_SELL
        ):

            result = close_position(
                position
            )

            # Only consider it closed if MT5
            # confirms successful execution.
            if (
                result is None
                or
                result.retcode
                not in (
                    mt5.TRADE_RETCODE_DONE,
                    mt5.TRADE_RETCODE_DONE_PARTIAL,
                )
            ):

                print(
                    "SELL close failed. "
                    "New BUY will NOT be opened."
                )

                return

            position = None

        # --------------------------------------------------------------
        # Open BUY
        # --------------------------------------------------------------

        if position is None:

            open_position(
                SYMBOL,
                "buy",
                current_atr,
            )

    # ==================================================================
    # SHORT SIGNAL
    # ==================================================================

    elif short_signal:

        # --------------------------------------------------------------
        # Existing BUY
        # --------------------------------------------------------------

        if (
            position is not None
            and
            position.type
            == mt5.POSITION_TYPE_BUY
        ):

            result = close_position(
                position
            )

            if (
                result is None
                or
                result.retcode
                not in (
                    mt5.TRADE_RETCODE_DONE,
                    mt5.TRADE_RETCODE_DONE_PARTIAL,
                )
            ):

                print(
                    "BUY close failed. "
                    "New SELL will NOT be opened."
                )

                return

            position = None

        # --------------------------------------------------------------
        # Open SELL
        # --------------------------------------------------------------

        if position is None:

            open_position(
                SYMBOL,
                "sell",
                current_atr,
            )


# ==========================================================================
# MAIN BOT LOOP
# ==========================================================================

def run():
    """
    Main trading loop.

    Only processes a new CLOSED candle once.
    """

    if not prepare_symbol(
        SYMBOL
    ):

        return

    last_bar_time = None

    print()
    print("=" * 70)
    print("UT + HMA + ORB MT5 PYTHON BOT")
    print("=" * 70)

    print(
        "Symbol           :",
        SYMBOL,
    )

    print(
        "Timeframe        : M5",
    )

    print(
        "Lot size         :",
        LOT_SIZE,
    )

    print(
        "Magic number     :",
        MAGIC_NUMBER,
    )

    print(
        "UT key value     :",
        UT_KEY_VALUE,
    )

    print(
        "UT ATR period    :",
        UT_ATR_PERIOD,
    )

    print(
        "HMA period       :",
        HMA_PERIOD,
    )

    print(
        "ORB              :",
        f"{ORB_START} - {ORB_END}",
    )

    print(
        "SL ATR multiplier:",
        SL_ATR_MULTIPLIER,
    )

    print(
        "TP ATR multiplier:",
        TP_ATR_MULTIPLIER,
    )

    print("=" * 70)

    try:

        while True:

            try:

                # ------------------------------------------------------
                # Fetch CLOSED candles
                # ------------------------------------------------------

                df = fetch_ohlc(
                    SYMBOL,
                    TIMEFRAME,
                    BARS_TO_FETCH,
                )

                if len(df) < 50:

                    print(
                        "Not enough bars."
                    )

                    time.sleep(
                        POLL_SECONDS
                    )

                    continue

                # ------------------------------------------------------
                # Latest CLOSED candle
                # ------------------------------------------------------

                latest_bar_time = (
                    df.index[-1]
                )

                # ------------------------------------------------------
                # Only process once per candle
                # ------------------------------------------------------

                if (
                    latest_bar_time
                    != last_bar_time
                ):

                    last_bar_time = (
                        latest_bar_time
                    )

                    process_signal(
                        df,
                        latest_bar_time,
                    )

                # ------------------------------------------------------
                # Wait
                # ------------------------------------------------------

                time.sleep(
                    POLL_SECONDS
                )

            except Exception as exc:

                print()
                print(
                    "ERROR:",
                    repr(exc),
                )

                print(
                    "MT5 last error:",
                    mt5.last_error(),
                )

                time.sleep(
                    POLL_SECONDS
                )

    except KeyboardInterrupt:

        print()
        print(
            "Bot stopped by user."
        )


# ==========================================================================
# PROGRAM ENTRY
# ==========================================================================

if __name__ == "__main__":

    # --------------------------------------------------------------
    # Validate credentials
    # --------------------------------------------------------------

    if (
        DEMO_LOGIN == 0
        or not DEMO_PASSWORD
        or not DEMO_SERVER
    ):

        print()
        print("=" * 70)
        print("MT5 CREDENTIALS NOT CONFIGURED")
        print("=" * 70)

        print()
        print(
            "Set these environment variables:"
        )

        print()
        print(
            "MT5_LOGIN"
        )

        print(
            "MT5_PASSWORD"
        )

        print(
            "MT5_SERVER"
        )

        print()
        print(
            "Or log into your demo account "
            "inside MT5 and modify the code "
            "to use mt5.initialize()."
        )

        print(
            "=" * 70
        )

    else:

        if connect(
            login=DEMO_LOGIN,
            password=DEMO_PASSWORD,
            server=DEMO_SERVER,
        ):

            try:

                run()

            finally:

                shutdown()