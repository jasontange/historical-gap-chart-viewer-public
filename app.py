import os
from datetime import datetime, time

import matplotlib.dates as mdates
import numpy as np
import pandas as pd
import requests
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template, request

from historical_charts import prepare_chart_data


load_dotenv()

ASKEDGAR_API_KEY = os.environ.get("ASKEDGAR_API_KEY", "")
ASKEDGAR_BASE = "https://eapi.askedgar.io"

app = Flask(__name__)


def normalize_ticker(value):
    return (value or "").strip().upper()


def extract_row_date(row):
    date_fields = [
        "date",
        "gap_date",
        "trading_date",
        "day",
        "market_date",
        "session_date",
    ]
    for field in date_fields:
        value = row.get(field)
        if value:
            return str(value)[:10]

    for key, value in row.items():
        if "date" in key.lower() and value:
            return str(value)[:10]

    return None


def fetch_all_gap_stats(ticker, limit=100):
    if not ASKEDGAR_API_KEY:
        raise ValueError("Missing ASKEDGAR_API_KEY environment variable.")

    results = []
    page = 1
    while True:
        response = requests.get(
            f"{ASKEDGAR_BASE}/v1/gap-stats",
            params={"ticker": ticker, "page": page, "limit": limit},
            headers={"API-KEY": ASKEDGAR_API_KEY},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        page_results = payload.get("results", [])
        if not isinstance(page_results, list):
            raise ValueError("AskEdgar returned an unexpected response shape.")

        results.extend(page_results)
        if not payload.get("has_more"):
            return results, payload
        page += 1


def build_chart_payload(ticker, chart_date, candle_minutes=3):
    data, previous_date = prepare_chart_data(
        ticker,
        chart_date,
        candle_minutes,
        previous_start=time(9, 30),
    )
    if data.empty:
        return None

    synthetic_start = pd.Timestamp("2000-01-01 09:30", tz="UTC")
    synthetic_times = [
        int((synthetic_start + pd.Timedelta(minutes=candle_minutes * i)).timestamp())
        for i in range(len(data))
    ]

    candles = []
    volume = []
    vwap = []
    labels = {}
    for i, (_, row) in enumerate(data.iterrows()):
        synthetic_time = synthetic_times[i]
        candles.append(
            {
                "time": synthetic_time,
                "open": round(float(row["open"]), 4),
                "high": round(float(row["high"]), 4),
                "low": round(float(row["low"]), 4),
                "close": round(float(row["close"]), 4),
            }
        )
        volume.append(
            {
                "time": synthetic_time,
                "value": int(row["volume"]),
                "color": "#00e676" if row["close"] >= row["open"] else "#ff5252",
            }
        )
        vwap.append({"time": synthetic_time, "value": round(float(row["vwap"]), 4)})
        labels[str(synthetic_time)] = data.index[i].strftime("%m-%d %H:%M")

    timestamp_nums = mdates.date2num(data.index.to_pydatetime())

    def nearest_synthetic_time(session_time):
        session_num = mdates.date2num(session_time.to_pydatetime())
        nearest_index = int(np.argmin(np.abs(timestamp_nums - session_num)))
        return synthetic_times[nearest_index]

    event_specs = [
        ("Prev Open", pd.Timestamp(f"{previous_date} 09:30", tz="America/New_York"), "#1f77b4"),
        ("Prev Close", pd.Timestamp(f"{previous_date} 16:00", tz="America/New_York"), "#777777"),
        ("AH End", pd.Timestamp(f"{previous_date} 20:00", tz="America/New_York"), "#777777"),
        ("Premarket", pd.Timestamp(f"{chart_date} 04:00", tz="America/New_York"), "#777777"),
        ("Open", pd.Timestamp(f"{chart_date} 09:30", tz="America/New_York"), "#1f77b4"),
        ("Noon", pd.Timestamp(f"{chart_date} 12:00", tz="America/New_York"), "#9467bd"),
        ("Close", pd.Timestamp(f"{chart_date} 16:00", tz="America/New_York"), "#d62728"),
    ]
    event_lines = [
        {
            "time": nearest_synthetic_time(event_time),
            "label": label,
            "color": color,
        }
        for label, event_time, color in event_specs
    ]

    extended_ranges = [
        {
            "start": nearest_synthetic_time(pd.Timestamp(f"{previous_date} 16:00", tz="America/New_York")),
            "end": nearest_synthetic_time(pd.Timestamp(f"{previous_date} 20:00", tz="America/New_York")),
            "label": "Previous After Hours",
        },
        {
            "start": nearest_synthetic_time(pd.Timestamp(f"{chart_date} 04:00", tz="America/New_York")),
            "end": nearest_synthetic_time(pd.Timestamp(f"{chart_date} 09:30", tz="America/New_York")),
            "label": "Premarket",
        },
        {
            "start": nearest_synthetic_time(pd.Timestamp(f"{chart_date} 16:00", tz="America/New_York")),
            "end": nearest_synthetic_time(pd.Timestamp(f"{chart_date} 20:00", tz="America/New_York")),
            "label": "After Hours",
        },
    ]

    return {
        "title": f"{ticker} {previous_date} 09:30 to {chart_date} 20:00 ET - {candle_minutes} min",
        "candles": candles,
        "volume": volume,
        "vwap": vwap,
        "labels": labels,
        "eventLines": event_lines,
        "extendedRanges": extended_ranges,
    }


@app.get("/")
def index():
    return render_template("index.html")


@app.route("/api/gaps", methods=["GET", "POST"])
def gap_stats():
    payload = request.get_json(silent=True) or {}
    ticker = normalize_ticker(payload.get("ticker") or request.args.get("ticker"))
    if not ticker:
        return jsonify({"error": "Ticker is required."}), 400

    try:
        rows, raw_payload = fetch_all_gap_stats(ticker)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 502

    for row in rows:
        if isinstance(row, dict):
            row["_chart_date"] = extract_row_date(row)

    return jsonify(
        {
            "ticker": ticker,
            "rows": rows,
            "raw": {
                "status": raw_payload.get("status"),
                "count": len(rows),
                "has_more": raw_payload.get("has_more"),
            },
        }
    )


@app.get("/api/chart")
def chart():
    ticker = normalize_ticker(request.args.get("ticker"))
    date_value = request.args.get("date")
    candle_minutes = int(request.args.get("candleMinutes", 3))
    if not ticker or not date_value:
        return jsonify({"error": "Ticker and date are required."}), 400

    try:
        chart_date = datetime.strptime(date_value[:10], "%Y-%m-%d").date()
        payload = build_chart_payload(ticker, chart_date, candle_minutes)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 502

    if not payload:
        return jsonify({"error": f"No chart data found for {ticker} on {date_value}."}), 404

    return jsonify(payload)


@app.get("/api/news")
def news():
    ticker = normalize_ticker(request.args.get("ticker"))
    date_from = request.args.get("date_from")
    date_to = request.args.get("date_to")
    if not ticker:
        return jsonify({"error": "Ticker is required."}), 400
    if not ASKEDGAR_API_KEY:
        return jsonify({"error": "Missing ASKEDGAR_API_KEY environment variable."}), 500

    params = {
        "ticker": ticker,
        "limit": 50,
        "include_body": "false",
        "include_summary": "false",
    }
    if date_from:
        params["date_from"] = date_from
    if date_to:
        params["date_to"] = date_to

    try:
        response = requests.get(
            f"{ASKEDGAR_BASE}/v1/news-basic",
            params=params,
            headers={"API-KEY": ASKEDGAR_API_KEY},
            timeout=30,
        )
        response.raise_for_status()
        return jsonify(response.json())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 502


@app.get("/api/dilution")
def dilution():
    ticker = normalize_ticker(request.args.get("ticker"))
    date_val = request.args.get("date")
    if not ticker:
        return jsonify({"error": "Ticker is required."}), 400
    if not ASKEDGAR_API_KEY:
        return jsonify({"error": "Missing ASKEDGAR_API_KEY environment variable."}), 500

    params = {"ticker": ticker, "limit": 1}
    if date_val:
        params["date_to"] = date_val

    try:
        response = requests.get(
            f"{ASKEDGAR_BASE}/v1/historical-dilution",
            params=params,
            headers={"API-KEY": ASKEDGAR_API_KEY},
            timeout=30,
        )
        response.raise_for_status()
        return jsonify(response.json())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 502


@app.get("/api/offerings")
def offerings():
    ticker = normalize_ticker(request.args.get("ticker"))
    date_from = request.args.get("date_from")
    date_to = request.args.get("date_to")
    if not ticker:
        return jsonify({"error": "Ticker is required."}), 400
    if not ASKEDGAR_API_KEY:
        return jsonify({"error": "Missing ASKEDGAR_API_KEY environment variable."}), 500

    params = {"ticker": ticker, "limit": 50}
    if date_from:
        params["date_from"] = date_from
    if date_to:
        params["date_to"] = date_to

    try:
        response = requests.get(
            f"{ASKEDGAR_BASE}/v1/offerings",
            params=params,
            headers={"API-KEY": ASKEDGAR_API_KEY},
            timeout=30,
        )
        response.raise_for_status()
        return jsonify(response.json())
    except Exception as exc:
        return jsonify({"error": str(exc)}), 502


if __name__ == "__main__":
    app.run(debug=False, port=5000, use_reloader=False)
