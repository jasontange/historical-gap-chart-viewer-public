# Project Summary

## Overview

This project is a local Flask web app for reviewing stock gap days and opening an interactive historical intraday chart for each selected date.

The app combines:

- AskEdgar gap-day and company-related API data.
- Polygon/Massive intraday OHLCV aggregate candles.
- TradingView Lightweight Charts for browser-based chart rendering.

## Main Workflow

1. A user enters a ticker in the web app.
2. The Flask backend calls AskEdgar's `gap-stats` endpoint for that ticker.
3. The frontend displays the returned gap days and stats in a table.
4. When a user clicks a table row, the frontend requests chart data for that ticker/date.
5. The backend fetches 3-minute intraday aggregate candles from Polygon/Massive.
6. The backend prepares the chart payload: candles, volume, VWAP, time labels, session lines, and extended-hours shading ranges.
7. The frontend renders the chart using TradingView Lightweight Charts.

## Data Sources

AskEdgar is used for:

- Gap-day rows and gap statistics.
- News.
- Historical dilution.
- Offerings.

Polygon/Massive is used for:

- Intraday aggregate OHLCV candles.
- Previous-day context.
- Premarket, regular-session, and after-hours chart data.

TradingView Lightweight Charts is used only as a rendering library. It does not provide market data.

## Chart Behavior

The chart uses 3-minute candles by default. For the web app chart, the backend includes:

- Previous market day from 9:30 AM ET through 8:00 PM ET.
- Selected gap day from 4:00 AM ET through 8:00 PM ET.
- VWAP calculated from the returned intraday candles.
- Volume histogram.
- Vertical reference lines for session events.
- Shaded extended-hours regions.

The chart uses a synthetic/compressed time axis so inactive overnight gaps do not consume visual space.

## Important Files

- `app.py`: Flask backend, AskEdgar API routes, and chart payload generation.
- `historical_charts.py`: Polygon/Massive candle fetching, chart data preparation, PDF generation, and standalone TradingView HTML export.
- `templates/index.html`: Main web app UI, table rendering, and TradingView Lightweight Charts frontend logic.
- `requirements.txt`: Python dependencies.
- `.env.example`: Environment variable template.
- `.gitignore`: Keeps secrets, generated charts, logs, and cache files out of Git.

## Environment Variables

The app expects API keys to be provided through environment variables or a local `.env` file:

```text
ASKEDGAR_API_KEY=your_askedgar_api_key_here
POLYGON_API_KEY=your_polygon_or_massive_api_key_here
```

Then run:

```powershell
python app.py
```

`MASSIVE_API_KEY` can be used instead of `POLYGON_API_KEY`. The real `.env` file is ignored by git.

## Local App URL

When running locally, open:

```text
http://127.0.0.1:5000/
```

## Notes

Generated PDFs, standalone generated TradingView HTML files, logs, and `.env` files are intentionally ignored by Git.
