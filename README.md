---

# 📈 AlgoTrader – Crypto Signal Scanner & Auto-Trading Engine

`AlgoTrader` is a **real-time crypto signal and trading engine** combining **multi-timeframe technical analysis**, **machine learning-based signal filtering**, and **Bybit USDT futures trading** into one automated loop.

It scans top-volume USDT pairs on Bybit, generates high-quality signals using technical indicators (EMA, RSI, MACD, ATR, Bollinger Bands), ranks them by score and confidence, filters them using ML, then executes real or simulated trades. It logs every action to PostgreSQL and JSON, and exports reports as PDF + social alerts via Discord and Telegram.

---

## 🚀 Features

* 📊 **Multi-Timeframe Technical Signal Scanner**
  Analyzes 15m, 1h, and 4h candles using:

  * EMA (9, 21), SMA (20)
  * RSI, MACD, ATR
  * Bollinger Bands
  * Trend detection & breakout classification

* 🧠 **ML-Based Signal Filtering**
  Uses `MLFilter` for score boosting and filtering based on:

  * Z-score thresholds
  * Confidence level
  * Historical win rate

* 💹 **Hybrid Trading Engine**

  * **REAL mode**: Executes trades via Bybit API
  * **VIRTUAL mode**: Simulated trades in-memory

* 🧾 **Logging: PostgreSQL + JSON**

  * All trades/signals logged to PostgreSQL (via SQLAlchemy)
  * JSON backups for redundancy

* 📤 **Signal Reporting + Alerts**

  * Top 20 signals exported to `/reports/*.pdf`
  * Top 5 signals auto-posted to **Discord** and **Telegram**

* 🧩 **Smart Trade Structuring**

  * Signals include TP, SL, trailing stop
  * Classified by trend type (Scalp / Swing / Trend)
  * Tagged by market regime (Mean vs. Breakout)

---

## 🧱 Project Structure

```
├── hybrid_engine.py       # Main engine logic
├── database.py            # SQLAlchemy ORM + DB manager
├── bybit_client.py        # Real/virtual Bybit interface
├── data_provider.py       # OHLCV feed from Bybit
├── exports.py             # PDF exports + social hooks
├── ml.py                  # ML filter logic
├── utils.py               # Helpers: JSON, math, etc.
├── reports/               # Generated PDFs
├── signals/               # Signal logs (JSON)
├── trades/                # Trade logs (JSON)
```

---

## ⚙️ Configuration

| Parameter               | Description                   | Default      |
| ----------------------- | ----------------------------- | ------------ |
| `REAL_MODE`             | Enables live Bybit trading    | `false`      |
| `ML_ENABLED`            | Enables ML signal enhancement | `true`       |
| `TOP_SYMBOL_LIMIT`      | # of Bybit USDT pairs to scan | `100`        |
| `TOP_TERMINAL_LIMIT`    | Signals printed to terminal   | `5`          |
| `TOP_PDF_LIMIT`         | Signals exported to PDF       | `20`         |
| `SCAN_INTERVAL_MINUTES` | Scan interval in minutes      | `15`         |
| `UTC_OFFSET`            | Timezone for logs             | `+3 (UTC+3)` |

Set in your `.env`:

```env
REAL_MODE=false
ML_ENABLED=true
```

---

## 📈 Signal Logic

A signal is **valid** if:

* Trend aligns on 15m, 1h, and 4h
* ML filter approves it
* Score ≥ 60 **and** Confidence ≥ 70

Each signal contains:

* `symbol`, `side` (LONG/SHORT)
* `entry`, `tp`, `sl`, `trail`
* `score`, `confidence`, `margin`, `liq_price`
* `trend`, `regime`, `type`
* Timestamp (UTC+3)

---

## 🛒 Trade Execution

Trade logic:

* Position size = `(wallet_balance * 0.75) / entry_price`
* Orders contain: TP, SL, trailing stop
* Execution:

  * If `REAL_MODE=true`: Uses Bybit API
  * If `REAL_MODE=false`: Simulated trade
* Saved to DB and `/trades/*.json`

---

## 📤 Output & Alerts

After each scan:

* ✅ Top 5 signals:

  * Printed in terminal
  * Sent to **Discord** and **Telegram**

* 📝 Top 20 signals:

  * Exported to PDF at `/reports/signals_<timestamp>.pdf`

* 🧠 All valid signals:

  * Saved in `/signals/*.json`
  * Logged to PostgreSQL (`DatabaseManager`)

---

## 🔁 Execution Loop

Run with:

```bash
python app.py
```

Loop every 15 minutes:

1. Get top symbols by USDT volume
2. Fetch multi-timeframe OHLCV
3. Run indicators & generate signals
4. Filter + score with ML
5. Export / alert / log
6. Auto-trade if valid
7. Wait `SCAN_INTERVAL_MINUTES`

---

## ✅ Requirements

* Python 3.9+
* Bybit API keys in `.env`
* PostgreSQL (configured in `database.py`)

Install dependencies:

```bash
pip install ta numpy pandas sqlalchemy pybit praw reportlab python-dotenv
```

---

## 📌 Notes

* Compatible with both paper and real trading
* Modular design for easy extension
* `.env` switches between modes
* Optimized for short- and swing-term futures strategies

---

## 🧠 Future Enhancements

* Historical backtest mode
* Telegram Bot with commands
* Portfolio rebalancing + optimizer
* Strategy presets: Scalp / Trend / Mean Reversion
* Streamlit Web Dashboard (UI + Analytics)

---

## 📫 Contact

**Developer**: OL'PHEMIE JEGEDE
**Project**: `AlgoTrader – Crypto Engine Suite`
**Exchange**: Bybit (USDT Perpetual Futures)

For collaboration, support, or custom strategy dev — feel free to reach out!

---
