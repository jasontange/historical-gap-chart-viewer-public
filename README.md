# Historical Chart Viewer

Local Flask app for reviewing AskEdgar gap days, premarket movers, and afterhours movers with interactive historical intraday charts.

## Cost And API Usage Disclaimer

API responses are cached locally in a SQLite database (`cache.db`). Gap/premarket/afterhours stats are cached for 24 hours; news, dilution, offerings, and chart data are cached permanently (historical data does not change). Delete `cache.db` to force a full refresh.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

For local API keys, copy `.env.example` to `.env` and fill in your real values:

```text
ASKEDGAR_API_KEY=your_askedgar_api_key_here
POLYGON_API_KEY=your_polygon_or_massive_api_key_here
```

The `.env` file is ignored by git and should not be committed.

Then open:

```text
http://127.0.0.1:5000/
```

## Notes

- AskEdgar provides gap-day stats, premarket/afterhours movers, dilution ratings, news, and offerings data.
- Polygon/Massive provides intraday OHLCV candles.
- TradingView Lightweight Charts renders the interactive browser chart.
- Three tabs: Gaps, Premarket Movers, Afterhours Movers — each with date-based historical chart lookup.
