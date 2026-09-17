import numpy as np
import pandas as pd


# --------------------------------------------------------------------------
# 1. UT BOT
# --------------------------------------------------------------------------

def atr(df: pd.DataFrame, period: int = 1) -> pd.Series:
    """Average True Range (Wilder-style, matches Pine's built-in atr())."""
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)

    tr = pd.concat(
        [
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    # Pine's atr() uses Wilder's RMA smoothing (alpha = 1/period)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def ut_bot(df: pd.DataFrame, key_value: float = 2.0, atr_period: int = 1,
           use_heikin_ashi: bool = False) -> pd.DataFrame:
    """
    Replicates the UT Bot Alerts indicator.

    Returns a DataFrame with columns:
        xATRTrailingStop, pos, buy, sell
    """
    src = df["close"].copy()

    if use_heikin_ashi:
        src = _heikin_ashi_close(df)

    n_loss = key_value * atr(df, atr_period)

    trailing_stop = np.zeros(len(df))
    src_vals = src.values
    n_loss_vals = n_loss.values

    for i in range(len(df)):
        if i == 0:
            trailing_stop[i] = 0.0
            continue

        prev_stop = trailing_stop[i - 1]
        prev_src = src_vals[i - 1]

        if src_vals[i] > prev_stop and prev_src > prev_stop:
            trailing_stop[i] = max(prev_stop, src_vals[i] - n_loss_vals[i])
        elif src_vals[i] < prev_stop and prev_src < prev_stop:
            trailing_stop[i] = min(prev_stop, src_vals[i] + n_loss_vals[i])
        elif src_vals[i] > prev_stop:
            trailing_stop[i] = src_vals[i] - n_loss_vals[i]
        else:
            trailing_stop[i] = src_vals[i] + n_loss_vals[i]

    trailing_stop = pd.Series(trailing_stop, index=df.index)

    # pos: +1 uptrend, -1 downtrend, 0 undefined
    pos = np.zeros(len(df))
    for i in range(1, len(df)):
        if src_vals[i - 1] < trailing_stop.iloc[i - 1] and src_vals[i] > trailing_stop.iloc[i]:
            pos[i] = 1
        elif src_vals[i - 1] > trailing_stop.iloc[i - 1] and src_vals[i] < trailing_stop.iloc[i]:
            pos[i] = -1
        else:
            pos[i] = pos[i - 1]
    pos = pd.Series(pos, index=df.index)

    # ema(src, 1) == src itself, so "above"/"below" are just crossovers of src vs stop
    above = (src > trailing_stop) & (src.shift(1) <= trailing_stop.shift(1))
    below = (trailing_stop > src) & (trailing_stop.shift(1) <= src.shift(1))

    buy = (src > trailing_stop) & above
    sell = (src < trailing_stop) & below

    return pd.DataFrame(
        {
            "xATRTrailingStop": trailing_stop,
            "pos": pos,
            "buy": buy,
            "sell": sell,
        },
        index=df.index,
    )


def _heikin_ashi_close(df: pd.DataFrame) -> pd.Series:
    """Compute Heikin Ashi close values from regular OHLC."""
    ha_close = (df["open"] + df["high"] + df["low"] + df["close"]) / 4
    return ha_close


# --------------------------------------------------------------------------
# 2. HULL MOVING AVERAGE
# --------------------------------------------------------------------------

def wma(series: pd.Series, period: int) -> pd.Series:
    """Weighted Moving Average."""
    weights = np.arange(1, period + 1)
    return series.rolling(period).apply(
        lambda x: np.dot(x, weights) / weights.sum(), raw=True
    )


def hull_ma(df: pd.DataFrame, period: int = 31) -> pd.Series:
    """
    Hull Moving Average.
    HMA = WMA(2*WMA(close, n/2) - WMA(close, n), sqrt(n))
    """
    close = df["close"]
    half_period = int(round(period / 2))
    sqrt_period = int(round(np.sqrt(period)))

    wma_half = wma(close, half_period)
    wma_full = wma(close, period)
    diff = 2 * wma_half - wma_full

    hma = wma(diff, sqrt_period)
    return hma


# --------------------------------------------------------------------------
# 3. OPENING RANGE BREAKOUT (ORB)
# --------------------------------------------------------------------------

def opening_range_breakout(
    df: pd.DataFrame,
    session_start: str = "10:10",
    session_end: str = "10:15",
) -> pd.DataFrame:
    """
    Tracks the high/low made during a daily time window (the "opening range"),
    then holds that high/low flat for the rest of the day so later price
    action can be compared against it for a breakout.

    Requires df.index to be a DatetimeIndex.

    Returns a DataFrame with columns: orb_high, orb_low, in_session
    """
    idx_time = df.index.time
    start_t = pd.to_datetime(session_start).time()
    end_t = pd.to_datetime(session_end).time()

    in_session = pd.Series(
        [start_t <= t <= end_t for t in idx_time], index=df.index
    )

    dates = df.index.date
    orb_high = np.full(len(df), np.nan)
    orb_low = np.full(len(df), np.nan)

    current_date = None
    day_high = np.nan
    day_low = np.nan

    for i in range(len(df)):
        d = dates[i]
        if d != current_date:
            current_date = d
            day_high = np.nan
            day_low = np.nan

        if in_session.iloc[i]:
            h, l = df["high"].iloc[i], df["low"].iloc[i]
            day_high = h if np.isnan(day_high) else max(day_high, h)
            day_low = l if np.isnan(day_low) else min(day_low, l)

        orb_high[i] = day_high
        orb_low[i] = day_low

    return pd.DataFrame(
        {
            "orb_high": orb_high,
            "orb_low": orb_low,
            "in_session": in_session,
        },
        index=df.index,
    )


# --------------------------------------------------------------------------
# 4. COMBINED SIGNAL GENERATOR (example of using all three together)
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
    Combines UT Bot + HMA + ORB into one DataFrame.
    Adds a simple confluence 'long_signal' / 'short_signal' example:
        long  = UT buy AND HMA rising AND close breaks above ORB high
        short = UT sell AND HMA falling AND close breaks below ORB low
    Adjust this confluence logic to match your own strategy.
    """
    ut = ut_bot(df, ut_key_value, ut_atr_period)
    hma = hull_ma(df, hma_period)
    orb = opening_range_breakout(df, orb_start, orb_end)

    out = df.copy()
    out["xATRTrailingStop"] = ut["xATRTrailingStop"]
    out["ut_buy"] = ut["buy"]
    out["ut_sell"] = ut["sell"]
    out["hma"] = hma
    out["hma_rising"] = hma > hma.shift(1)
    out["orb_high"] = orb["orb_high"]
    out["orb_low"] = orb["orb_low"]

    out["long_signal"] = (
        out["ut_buy"]
        & out["hma_rising"]
        & (out["close"] > out["orb_high"])
    )
    out["short_signal"] = (
        out["ut_sell"]
        & (~out["hma_rising"])
        & (out["close"] < out["orb_low"])
    )

    return out


# --------------------------------------------------------------------------
# Example usage
# --------------------------------------------------------------------------
if __name__ == "__main__":
    # Load your own OHLCV data here, e.g. from a CSV or a broker's API.
    # DataFrame must have columns: open, high, low, close
    # and a DatetimeIndex.
    #
    # Example:
    # df = pd.read_csv("data.csv", index_col="datetime", parse_dates=True)
    # signals = generate_signals(df)
    # print(signals[signals["long_signal"] | signals["short_signal"]])

    print("Import this module and call generate_signals(df) with your OHLCV data.")
