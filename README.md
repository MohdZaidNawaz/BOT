# BOT — MT5 Algorithmic Trading Bot

![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)

An automated trading bot for **MetaTrader 5**, combining a **UT Bot** trend-following signal, a **Hull Moving Average (HMA)** trend filter, and an **Opening Range Breakout (ORB)** window, with **ATR-based stop-loss / take-profit** sizing. The strategy is implemented in both **MQL5** (Expert Advisor) and **Python** (via the official `MetaTrader5` package), so it can run natively inside MT5 or as a standalone Python script.

## Features

- 📈 **Multi-signal strategy** — UT Bot (ATR trailing stop) + HMA trend direction + ORB time filter
- 🎯 **Dynamic risk management** — Stop-loss and take-profit distances scaled from live ATR (`SL = ATR × 10`, `TP = ATR × 200`)
- 🔁 **Position management by Magic Number** — the bot only manages its own trades, and flips positions automatically when the signal reverses
- ⏱️ **Configurable polling loop** — checks for a newly closed candle every `POLL_SECONDS`
- 🧪 **Custom backtest window** — restrict signal generation to a specific date range for testing
- 🔐 **Environment-variable credentials** — no plaintext passwords in code

## Repository structure

```
BOT/
├── MT5/              # MQL5 Expert Advisor / MetaTrader 5 project files
├── mt5_bot.py         # Main Python trading loop (connects to MT5, executes trades)
├── new.py             # Signal generation logic (UT Bot, HMA, ORB, ATR)
└── .vscode/           # Editor configuration
```

## How it works

1. **Connect** — `mt5_bot.py` connects to a running MT5 terminal, either using the terminal you're already logged into, or via `MT5_LOGIN` / `MT5_PASSWORD` / `MT5_SERVER` environment variables.
2. **Fetch data** — Pulls the last `BARS_TO_FETCH` **closed** M1 candles for the configured symbol.
3. **Generate signals** — `new.py` computes the UT Bot buy/sell state, HMA direction, and the ORB high/low, and produces `long_signal` / `short_signal` flags.
4. **Manage positions** — On a long signal, any open short is closed and a long is opened (and vice versa), sized with an ATR-based SL/TP.
5. **Loop** — Repeats every `POLL_SECONDS`, only acting on the most recently closed candle.

## Configuration

Key parameters live at the top of `mt5_bot.py`:

| Parameter | Default | Description |
|---|---|---|
| `SYMBOL` | `XAUUSD` | Instrument to trade |
| `TIMEFRAME` | `M1` | Candle timeframe |
| `LOT_SIZE` | `0.10` | Trade volume |
| `SL_ATR_MULTIPLIER` | `10.0` | Stop-loss = ATR × this |
| `TP_ATR_MULTIPLIER` | `200.0` | Take-profit = ATR × this |
| `UT_KEY_VALUE` / `UT_ATR_PERIOD` | `2.0` / `1` | UT Bot sensitivity |
| `HMA_PERIOD` | `31` | Hull Moving Average length |
| `ORB_START` / `ORB_END` | `10:10` / `10:15` | Opening range window |
| `POLL_SECONDS` | `30` | How often the loop checks for a new candle |

## Setup

### Requirements

- Windows with a running **MetaTrader 5** terminal (the Python `MetaTrader5` package requires it)
- Python 3.9+
- A demo or live MT5 trading account

### Installation

```bash
git clone https://github.com/MohdZaidNawaz/BOT.git
cd BOT
pip install MetaTrader5 pandas
```

### Credentials

Never commit your MT5 password. Set these as environment variables instead:

```bash
set MT5_LOGIN=12345678
set MT5_PASSWORD=your_password
set MT5_SERVER=YourBroker-Server
```

If these are left unset, the bot will instead attach to whatever MT5 terminal you already have open and logged in.

### Run

```bash
python mt5_bot.py
```

## MQL5 version

The `MT5/` folder contains the original **MetaTrader 5 Expert Advisor (EA)** source, which implements the same UT Bot + HMA + ORB + ATR logic natively in MQL5 for use directly inside the MetaTrader 5 platform (no Python required).

## ⚠️ Disclaimer

This project is for **educational purposes only**. Trading leveraged instruments like XAUUSD carries a high risk of loss. Nothing here is financial advice. Always test extensively on a **demo account** before considering live use, and trade only with capital you can afford to lose.

## License

This project is licensed under the [Apache License 2.0](LICENSE) — you're free to use, modify, and distribute this code (including commercially), provided you retain the copyright notice and include a copy of the license. See the `LICENSE` file for full terms.
