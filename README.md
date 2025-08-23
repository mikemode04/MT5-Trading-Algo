# 🤖 MT5 Trading Algorithms

A collection of **algorithmic trading scripts** for MetaTrader 5 (MT5), focused on quantitative strategies and market microstructure.  
Each script is written in Python and connects to MT5 or external data feeds (e.g. CCXT for crypto exchanges).

---

## 📂 Strategies in this repo
- **FVG Screener (live)** – `FVG_screener_all_live.py`  
  Screens fair value gaps (FVG) in real-time across multiple symbols.  
  Useful for intraday trading and liquidity analysis.

- **Bollinger Band Midline Closer** – `mt5_bb_midline_closer.py`  
  Executes trades when price reverts to the Bollinger Band midline.  
  Simple mean-reversion strategy for FX/indices.

- **Mini HFT with CCXT** – `HFT-mini-MT5_tr_CCXT`  
  Prototype for a high-frequency trading loop using CCXT for crypto exchanges.  
  Focus on order book data and ultra-fast execution logic.

---

## 🛠️ Requirements
- Python 3.9+  
- MetaTrader 5 Python API (`pip install MetaTrader5`)  
- CCXT (`pip install ccxt`)  
- Pandas, Numpy, TA-Lib (for indicators)

---

## ▶️ Usage
Clone repo and run any strategy script:

```bash
git clone https://github.com/mikemode04/MT5-Trading-Algo.git
cd MT5-Trading-Algo

# Example: run FVG screener
python FVG_screener_all_live.py
