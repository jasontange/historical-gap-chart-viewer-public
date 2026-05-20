# Historical Gap Chart Viewer

## Cost And API Usage Disclaimer

This project has not been fully tested for daily production usage, so the ongoing API cost is not yet known.

Caching has not been added yet. If you use this app regularly, add caching before relying on it so you do not waste AskEdgar API calls on data you have already fetched.

Local Flask app for reviewing AskEdgar gap days and loading an interactive historical intraday chart for each date.

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

- AskEdgar provides gap-day stats and related company data.
- Polygon/Massive provides intraday OHLCV candles.
- TradingView Lightweight Charts renders the interactive browser chart.
