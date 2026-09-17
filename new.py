import numpy as np
import pandas as pd


# --------------------------------------------------------------------------
# 1. ATR - Wilder / RMA
# --------------------------------------------------------------------------

def atr(df: pd.DataFrame, period: int = 1) -> pd.Series:
    """
    Wilder-style ATR.

    Equivalent to the ATR used by the MQL5 EA:
        iATR(_Symbol, PERIOD_CURRENT, period)
    """

    high = df["high"]
    low = df["low"]
    close = df["close"]

    prev_close = close.shift(1)

    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    # Wilder RMA
    return tr.ewm(
        alpha=1 / period,
        adjust=False
    ).mean()


# --------------------------------------------------------------------------
# 2. UT BOT
# --------------------------------------------------------------------------

def ut_bot(
    df: pd.DataFrame,
    key_value: float = 2.0,
    atr_period: int = 1,
) -> pd.DataFrame:
    """
    Python equivalent of the UT Bot section in the MQL5 EA.

    MQL5:
        nLoss = InpUTKeyValue * ATR

        trailing stop:
            if src > prevStop && prevSrc > prevStop
                max(prevStop, src - nLoss)

            else if src < prevStop && prevSrc < prevStop
                min(prevStop, src + nLoss)

            else if src > prevStop
                src - nLoss

            else
                src + nLoss
    """

    src = df["close"].astype(float)

    atr_values = atr(df, atr_period)

    n_loss = key_value * atr_values

    src_values = src.to_numpy()
    n_loss_values = n_loss.to_numpy()

    trailing_stop = np.zeros(len(df), dtype=float)
    pos = np.zeros(len(df), dtype=int)

    if len(df) == 0:
        return pd.DataFrame(
            columns=[
                "xATRTrailingStop",
                "pos",
                "buy",
                "sell",
            ],
            index=df.index,
        )

    trailing_stop[0] = 0.0
    pos[0] = 0

    for i in range(1, len(df)):

        current_src = src_values[i]
        previous_src = src_values[i - 1]

        previous_stop = trailing_stop[i - 1]
        current_loss = n_loss_values[i]

        # Same recursive trailing stop logic as MQL5
        if (
            current_src > previous_stop
            and previous_src > previous_stop
        ):
            trailing_stop[i] = max(
                previous_stop,
                current_src - current_loss,
            )

        elif (
            current_src < previous_stop
            and previous_src < previous_stop
        ):
            trailing_stop[i] = min(
                previous_stop,
                current_src + current_loss,
            )

        elif current_src > previous_stop:
            trailing_stop[i] = current_src - current_loss

        else:
            trailing_stop[i] = current_src + current_loss

        # Same pos logic as MQL5
        if (
            previous_src < previous_stop
            and current_src > trailing_stop[i]
        ):
            pos[i] = 1

        elif (
            previous_src > previous_stop
            and current_src < trailing_stop[i]
        ):
            pos[i] = -1

        else:
            pos[i] = pos[i - 1]

    trailing_stop_series = pd.Series(
        trailing_stop,
        index=df.index,
    )

    pos_series = pd.Series(
        pos,
        index=df.index,
    )

    # MQL5:
    #
    # above =
    # close[last] > stop[last]
    # &&
    # close[prev] <= stop[prev]
    #
    # below =
    # stop[last] > close[last]
    # &&
    # stop[prev] <= close[prev]

    above = (
        (src > trailing_stop_series)
        &
        (
            src.shift(1)
            <= trailing_stop_series.shift(1)
        )
    )

    below = (
        (trailing_stop_series > src)
        &
        (
            trailing_stop_series.shift(1)
            <= src.shift(1)
        )
    )

    buy = (
        (src > trailing_stop_series)
        & above
    )

    sell = (
        (src < trailing_stop_series)
        & below
    )

    return pd.DataFrame(
        {
            "xATRTrailingStop": trailing_stop_series,
            "pos": pos_series,
            "buy": buy,
            "sell": sell,
        },
        index=df.index,
    )


# --------------------------------------------------------------------------
# 3. WMA
# --------------------------------------------------------------------------

def wma(series: pd.Series, period: int) -> pd.Series:
    """
    Weighted Moving Average.

    Same weighting used by the MQL5 WMA function:
        weight = i + 1
    """

    if period <= 0:
        raise ValueError("WMA period must be greater than zero")

    weights = np.arange(
        1,
        period + 1,
        dtype=float,
    )

    weight_sum = weights.sum()

    return series.rolling(period).apply(
        lambda values: np.dot(values, weights) / weight_sum,
        raw=True,
    )


# --------------------------------------------------------------------------
# 4. HULL MOVING AVERAGE
# --------------------------------------------------------------------------

def hull_ma(
    df: pd.DataFrame,
    period: int = 31,
) -> pd.Series:
    """
    HMA equivalent to the MQL5 HullMA() function.

    HMA =
        WMA(
            2 * WMA(close, halfPeriod)
            - WMA(close, period),
            sqrtPeriod
        )
    """

    close = df["close"].astype(float)

    half_period = int(
        round(period / 2.0)
    )

    sqrt_period = int(
        round(np.sqrt(period))
    )

    wma_half = wma(
        close,
        half_period,
    )

    wma_full = wma(
        close,
        period,
    )

    diff = (
        2.0 * wma_half
        - wma_full
    )

    return wma(
        diff,
        sqrt_period,
    )


# --------------------------------------------------------------------------
# 5. OPENING RANGE BREAKOUT
# --------------------------------------------------------------------------

def opening_range_breakout(
    df: pd.DataFrame,
    session_start: str = "10:10",
    session_end: str = "10:15",
) -> pd.DataFrame:
    """
    Equivalent to the ORB section of the MQL5 EA.

    The MQL5 EA calculates today's:
        highest high
        lowest low

    between:
        session_start
        session_end

    inclusive.
    """

    if not isinstance(df.index, pd.DatetimeIndex):
        raise TypeError(
            "DataFrame index must be a DatetimeIndex"
        )

    start_time = pd.to_datetime(
        session_start
    ).time()

    end_time = pd.to_datetime(
        session_end
    ).time()

    timestamps = df.index

    in_session = pd.Series(
        [
            start_time <= timestamp.time() <= end_time
            for timestamp in timestamps
        ],
        index=df.index,
    )

    orb_high = np.full(
        len(df),
        np.nan,
        dtype=float,
    )

    orb_low = np.full(
        len(df),
        np.nan,
        dtype=float,
    )

    current_date = None
    current_high = np.nan
    current_low = np.nan

    for i in range(len(df)):

        current_day = timestamps[i].date()

        # New day
        if current_day != current_date:
            current_date = current_day

            current_high = np.nan
            current_low = np.nan

        # Update ORB only during the session
        if in_session.iloc[i]:

            bar_high = float(
                df["high"].iloc[i]
            )

            bar_low = float(
                df["low"].iloc[i]
            )

            if np.isnan(current_high):
                current_high = bar_high
            else:
                current_high = max(
                    current_high,
                    bar_high,
                )

            if np.isnan(current_low):
                current_low = bar_low
            else:
                current_low = min(
                    current_low,
                    bar_low,
                )

        orb_high[i] = current_high
        orb_low[i] = current_low

    return pd.DataFrame(
        {
            "orb_high": orb_high,
            "orb_low": orb_low,
            "in_session": in_session,
        },
        index=df.index,
    )


# --------------------------------------------------------------------------
# 6. COMBINED SIGNAL GENERATOR
# --------------------------------------------------------------------------

def generate_signals(
    df: pd.DataFrame,
    ut_key_value: float = 2.0,
    ut_atr_period: int = 1,
    hma_period: int = 31,
    orb_start: str = "10:10",
    orb_end: str = "10:15",
) -> pd.DataFrame:
    """
    Combines:

        UT Bot
        HMA
        ORB

    Exact signal conditions from MQL5:

        LONG:
            utBuy
            AND hmaRising
            AND haveORB
            AND close > orbHigh

        SHORT:
            utSell
            AND NOT hmaRising
            AND haveORB
            AND close < orbLow
    """

    if df.empty:
        return df.copy()

    # UT Bot
    ut = ut_bot(
        df,
        key_value=ut_key_value,
        atr_period=ut_atr_period,
    )

    # HMA
    hma = hull_ma(
        df,
        period=hma_period,
    )

    # ORB
    orb = opening_range_breakout(
        df,
        session_start=orb_start,
        session_end=orb_end,
    )

    # ATR required for MQL5-style SL/TP
    atr_values = atr(
        df,
        ut_atr_period,
    )

    out = df.copy()

    out["atr"] = atr_values

    out["xATRTrailingStop"] = (
        ut["xATRTrailingStop"]
    )

    out["pos"] = ut["pos"]

    out["ut_buy"] = ut["buy"]

    out["ut_sell"] = ut["sell"]

    out["hma"] = hma

    out["hma_rising"] = (
        hma > hma.shift(1)
    )

    out["orb_high"] = (
        orb["orb_high"]
    )

    out["orb_low"] = (
        orb["orb_low"]
    )

    out["have_orb"] = (
        out["orb_high"].notna()
        &
        out["orb_low"].notna()
    )

    # --------------------------------------------------------------
    # Exact MQL5 long condition
    # --------------------------------------------------------------

    out["long_signal"] = (
        out["ut_buy"]
        &
        out["hma_rising"]
        &
        out["have_orb"]
        &
        (
            out["close"]
            > out["orb_high"]
        )
    )

    # --------------------------------------------------------------
    # Exact MQL5 short condition
    # --------------------------------------------------------------

    out["short_signal"] = (
        out["ut_sell"]
        &
        (~out["hma_rising"])
        &
        out["have_orb"]
        &
        (
            out["close"]
            < out["orb_low"]
        )
    )

    return out


# --------------------------------------------------------------------------
# TEST
# --------------------------------------------------------------------------

if __name__ == "__main__":

    print(
        "Strategy module loaded successfully."
    )

    print(
        "Use generate_signals(df) "
        "to calculate UT Bot + HMA + ORB signals."
    )