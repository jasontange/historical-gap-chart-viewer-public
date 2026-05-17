

import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, date, time, timedelta
import numpy as np
from polygon import RESTClient
import matplotlib.dates as mdates
import json
import os

POLYGON_API_KEY = os.environ.get("POLYGON_API_KEY") or os.environ.get("MASSIVE_API_KEY", "")

def previous_market_date(chart_date):
    """
    Return the previous weekday. This handles normal weekends but not market holidays.
    """
    previous_date = chart_date - timedelta(days=1)
    while previous_date.weekday() >= 5:
        previous_date -= timedelta(days=1)
    return previous_date

def get_intraday_data(ticker, start_date, end_date, candle_minutes=3):
    """
    Fetch intraday data for a given ticker between start_date and end_date
    using the Polygon RESTClient. Returns a pandas DataFrame.
    """
    try:
        if not POLYGON_API_KEY:
            raise ValueError("Missing POLYGON_API_KEY or MASSIVE_API_KEY environment variable.")

        client = RESTClient(POLYGON_API_KEY)

        # Convert dates to strings in the required format
        start_str = start_date.strftime('%Y-%m-%d')
        end_str = end_date.strftime('%Y-%m-%d')

        # Minute candles. Default is 3-minute bars for readability.
        aggs = client.get_aggs(
            ticker=ticker,
            multiplier=candle_minutes,
            timespan='minute',
            from_=start_str,
            to=end_str,
            limit=50000
        )
        data = pd.DataFrame(aggs)
        if data.empty:
            print(f"No intraday data returned for {ticker} in {start_str} to {end_str}")
            return pd.DataFrame()
        return data

    except Exception as e:
        print(f"Error fetching data from Polygon API: {e}")
        return pd.DataFrame()

def prepare_chart_data(ticker, chart_date, candle_minutes=3, previous_start=time(16, 0)):
    """
    Fetch and prepare previous-day context plus the requested chart day.
    """
    if isinstance(chart_date, datetime):
        chart_date = chart_date.date()

    previous_date = previous_market_date(chart_date)

    # Fetch enough intraday data for previous after-hours and the requested date.
    data = get_intraday_data(ticker, previous_date, chart_date, candle_minutes)
    if data.empty:
        print("No data to plot. Exiting.")
        return pd.DataFrame(), previous_date

    # Convert Polygon UTC timestamps to New York market time.
    data['timestamp'] = (
        pd.to_datetime(data['timestamp'], unit='ms', utc=True)
        .dt.tz_convert('America/New_York')
    )
    data.dropna(subset=['timestamp', 'open', 'high', 'low', 'close', 'volume'], inplace=True)
    data.set_index('timestamp', inplace=True)
    data.sort_index(inplace=True)

    previous_day_context = (
        (data.index.date == previous_date)
        & (data.index.time >= previous_start)
        & (data.index.time <= time(20, 0))
    )
    chart_day_extended_hours = (
        (data.index.date == chart_date)
        & (data.index.time >= time(4, 0))
        & (data.index.time <= time(20, 0))
    )
    data = data[previous_day_context | chart_day_extended_hours]
    if data.empty:
        print("No data after applying extended-hours filters.")
        return pd.DataFrame(), previous_date

    # Calculate VWAP
    data['typical_price'] = (data['high'] + data['low'] + data['close']) / 3
    data['pv'] = data['typical_price'] * data['volume']
    data['cum_pv'] = data['pv'].cumsum()
    data['cum_vol'] = data['volume'].cumsum()
    data['vwap'] = data['cum_pv'] / data['cum_vol']

    return data, previous_date

def timespan_candle_chart(ticker, chart_date, candle_minutes=3):
    """
    Generates a candlestick chart (with volume) for 'ticker' on 'chart_date'.
    Saves the resulting figure as a PDF in the current directory.
    """
    # Make sure chart_date is a date object
    if isinstance(chart_date, datetime):
        chart_date = chart_date.date()

    data, previous_date = prepare_chart_data(ticker, chart_date, candle_minutes)
    if data.empty:
        print("No data to plot. Exiting.")
        return

    # Create figure
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), sharex=True, gridspec_kw={"height_ratios": [3, 1]})
    fig.subplots_adjust(hspace=0)

    # Use compressed candle positions so overnight gaps do not take up chart space.
    plot_x = np.arange(len(data))
    timestamp_nums = mdates.date2num(data.index.to_pydatetime())

    def x_position_for_time(target_time):
        target_num = mdates.date2num(target_time.to_pydatetime())
        return np.interp(target_num, timestamp_nums, plot_x)

    # Candles
    colors = np.where(data['close'] >= data['open'], 'g', 'r')
    width = 0.8

    for i in range(len(data)):
        color = 'green' if colors[i] == 'g' else 'red'
        ax1.bar(
            plot_x[i],
            data['close'].iloc[i] - data['open'].iloc[i],
            bottom=data['open'].iloc[i],
            width=width,
            color=color
        )
        ax1.vlines(
            x=plot_x[i],
            ymin=data['low'].iloc[i],
            ymax=data['high'].iloc[i],
            color='black',
            linewidth=1
        )

    # Plot VWAP on the same axis
    ax1.plot(plot_x, data['vwap'], linewidth=1.2, label='VWAP')

    market_lines = [
        ('Prev Market Close', f'{previous_date} 16:00', '#9e9e9e', '--'),
        ('Prev After-Hours End', f'{previous_date} 20:00', '#9e9e9e', ':'),
        ('Premarket Open', '04:00', '#7f7f7f', ':'),
        ('Market Open', '09:30', '#1f77b4', '--'),
        ('Noon', '12:00', '#9467bd', ':'),
        ('Market Close', '16:00', '#d62728', '--'),
    ]
    for label, clock_time, color, linestyle in market_lines:
        if clock_time.startswith(str(previous_date)):
            line_time = pd.Timestamp(clock_time, tz='America/New_York')
        else:
            line_time = pd.Timestamp(f'{chart_date} {clock_time}', tz='America/New_York')
        line_x = x_position_for_time(line_time)
        ax1.axvline(line_x, color=color, linestyle=linestyle, linewidth=1.1, label=label)
        ax2.axvline(line_x, color=color, linestyle=linestyle, linewidth=1.0)

    ax1.set_ylabel('Price')
    ax1.set_title(
        f'{ticker} {previous_date} 16:00 to {chart_date} 20:00 '
        f'(Eastern Time) - {candle_minutes} min'
    )
    ax1.legend()
    ax1.grid(True)

    # Volume chart
    ax2.bar(plot_x, data['volume'], color=colors, width=width)
    ax2.set_ylabel('Volume')
    ax2.grid(True)

    # Format x-axis labels
    tick_count = min(10, len(data))
    tick_positions = np.linspace(0, len(data) - 1, tick_count, dtype=int)
    tick_labels = [data.index[i].strftime('%m-%d %H:%M') for i in tick_positions]
    ax2.set_xticks(tick_positions)
    ax2.set_xticklabels(tick_labels)
    fig.autofmt_xdate()

    # Save figure as PDF
    filename = f"{ticker}-{chart_date}-{candle_minutes}min.pdf"
    plt.savefig(filename, format='pdf', bbox_inches='tight')
    plt.close()
    print(f"Chart saved as {filename} in the current directory.")

def tradingview_html_chart(ticker, chart_date, candle_minutes=3):
    """
    Generates an interactive HTML chart using TradingView Lightweight Charts.
    This uses the same Polygon data and keeps the matplotlib PDF flow separate.
    """
    if isinstance(chart_date, datetime):
        chart_date = chart_date.date()

    data, previous_date = prepare_chart_data(
        ticker,
        chart_date,
        candle_minutes,
        previous_start=time(9, 30),
    )
    if data.empty:
        print("No data to export. Exiting.")
        return

    synthetic_start = pd.Timestamp('2000-01-01 09:30', tz='UTC')
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
        candles.append({
            'time': synthetic_time,
            'open': round(float(row['open']), 4),
            'high': round(float(row['high']), 4),
            'low': round(float(row['low']), 4),
            'close': round(float(row['close']), 4),
        })
        volume.append({
            'time': synthetic_time,
            'value': int(row['volume']),
            'color': '#159947' if row['close'] >= row['open'] else '#d71920',
        })
        vwap.append({
            'time': synthetic_time,
            'value': round(float(row['vwap']), 4),
        })
        labels[str(synthetic_time)] = data.index[i].strftime('%m-%d %H:%M')

    event_specs = [
        ('Prev Open', pd.Timestamp(f'{previous_date} 09:30', tz='America/New_York'), 'aboveBar', '#1f77b4'),
        ('Prev Close', pd.Timestamp(f'{previous_date} 16:00', tz='America/New_York'), 'aboveBar', '#777777'),
        ('AH End', pd.Timestamp(f'{previous_date} 20:00', tz='America/New_York'), 'aboveBar', '#777777'),
        ('Premarket', pd.Timestamp(f'{chart_date} 04:00', tz='America/New_York'), 'belowBar', '#777777'),
        ('Open', pd.Timestamp(f'{chart_date} 09:30', tz='America/New_York'), 'aboveBar', '#1f77b4'),
        ('Noon', pd.Timestamp(f'{chart_date} 12:00', tz='America/New_York'), 'aboveBar', '#9467bd'),
        ('Close', pd.Timestamp(f'{chart_date} 16:00', tz='America/New_York'), 'aboveBar', '#d62728'),
    ]
    timestamp_nums = mdates.date2num(data.index.to_pydatetime())
    markers = []
    event_lines = []
    for label, event_time, position, color in event_specs:
        event_num = mdates.date2num(event_time.to_pydatetime())
        nearest_index = int(np.argmin(np.abs(timestamp_nums - event_num)))
        event_time_value = synthetic_times[nearest_index]
        markers.append({
            'time': event_time_value,
            'position': position,
            'color': color,
            'shape': 'circle',
            'text': label,
        })
        event_lines.append({
            'time': event_time_value,
            'label': label,
            'color': color,
        })

    def nearest_synthetic_time(session_time):
        session_num = mdates.date2num(session_time.to_pydatetime())
        nearest_index = int(np.argmin(np.abs(timestamp_nums - session_num)))
        return synthetic_times[nearest_index]

    extended_ranges = [
        {
            'start': nearest_synthetic_time(pd.Timestamp(f'{previous_date} 16:00', tz='America/New_York')),
            'end': nearest_synthetic_time(pd.Timestamp(f'{previous_date} 20:00', tz='America/New_York')),
            'label': 'Previous After Hours',
        },
        {
            'start': nearest_synthetic_time(pd.Timestamp(f'{chart_date} 04:00', tz='America/New_York')),
            'end': nearest_synthetic_time(pd.Timestamp(f'{chart_date} 09:30', tz='America/New_York')),
            'label': 'Premarket',
        },
        {
            'start': nearest_synthetic_time(pd.Timestamp(f'{chart_date} 16:00', tz='America/New_York')),
            'end': nearest_synthetic_time(pd.Timestamp(f'{chart_date} 20:00', tz='America/New_York')),
            'label': 'After Hours',
        },
    ]

    page_title = f'{ticker} {previous_date} 09:30 to {chart_date} 20:00 ET - {candle_minutes} min'
    filename = f"{ticker}-{chart_date}-{candle_minutes}min-tradingview.html"
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{page_title}</title>
  <script src="https://unpkg.com/lightweight-charts/dist/lightweight-charts.standalone.production.js"></script>
  <style>
    html, body {{
      height: 100%;
      margin: 0;
      font-family: Arial, sans-serif;
      background: #ffffff;
      color: #111111;
    }}
    .header {{
      height: 44px;
      display: flex;
      align-items: center;
      justify-content: center;
      border-bottom: 1px solid #dddddd;
      font-size: 18px;
      font-weight: 600;
    }}
    #chart {{
      height: calc(100% - 44px);
      width: 100%;
      position: relative;
    }}
    #session-overlay {{
      position: absolute;
      inset: 0;
      pointer-events: none;
      z-index: 2;
    }}
    .credit {{
      position: fixed;
      right: 10px;
      bottom: 6px;
      font-size: 11px;
      color: #666666;
      background: rgba(255, 255, 255, 0.8);
    }}
    .credit a {{
      color: #2962ff;
      text-decoration: none;
    }}
  </style>
</head>
<body>
  <div class="header">{page_title}</div>
  <div id="chart">
    <canvas id="session-overlay"></canvas>
  </div>
  <div class="credit">Created with <a href="https://www.tradingview.com/" target="_blank" rel="noreferrer">TradingView</a> Lightweight Charts</div>

  <script>
    const candleData = {json.dumps(candles)};
    const volumeData = {json.dumps(volume)};
    const vwapData = {json.dumps(vwap)};
    const markers = {json.dumps(markers)};
    const eventLines = {json.dumps(event_lines)};
    const extendedRanges = {json.dumps(extended_ranges)};
    const labels = {json.dumps(labels)};

    const container = document.getElementById('chart');
    const overlay = document.getElementById('session-overlay');
    const overlayContext = overlay.getContext('2d');

    const chart = LightweightCharts.createChart(container, {{
      layout: {{
        background: {{ type: 'solid', color: '#ffffff' }},
        textColor: '#111111'
      }},
      grid: {{
        vertLines: {{ color: '#e5e5e5' }},
        horzLines: {{ color: '#d0d0d0' }}
      }},
      rightPriceScale: {{
        borderColor: '#cccccc'
      }},
      timeScale: {{
        borderColor: '#cccccc',
        timeVisible: true,
        secondsVisible: false,
        tickMarkFormatter: (time) => labels[String(time)] || ''
      }},
      crosshair: {{
        mode: LightweightCharts.CrosshairMode.Normal
      }}
    }});

    function resizeOverlay() {{
      const rect = container.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      overlay.width = Math.floor(rect.width * dpr);
      overlay.height = Math.floor(rect.height * dpr);
      overlay.style.width = `${{rect.width}}px`;
      overlay.style.height = `${{rect.height}}px`;
      overlayContext.setTransform(dpr, 0, 0, dpr, 0, 0);
    }}

    function drawSessions() {{
      resizeOverlay();
      const width = overlay.clientWidth;
      const height = overlay.clientHeight;
      overlayContext.clearRect(0, 0, width, height);

      extendedRanges.forEach((range) => {{
        const startX = chart.timeScale().timeToCoordinate(range.start);
        const endX = chart.timeScale().timeToCoordinate(range.end);
        if (startX === null || endX === null) return;
        const left = Math.max(0, Math.min(startX, endX));
        const right = Math.min(width, Math.max(startX, endX));
        if (right <= 0 || left >= width) return;
        overlayContext.fillStyle = 'rgba(235, 235, 235, 0.48)';
        overlayContext.fillRect(left, 0, right - left, height);
      }});

      eventLines.forEach((eventLine) => {{
        const x = chart.timeScale().timeToCoordinate(eventLine.time);
        if (x === null || x < 0 || x > width) return;
        overlayContext.beginPath();
        overlayContext.setLineDash([5, 5]);
        overlayContext.strokeStyle = eventLine.color;
        overlayContext.lineWidth = 1;
        overlayContext.moveTo(x, 0);
        overlayContext.lineTo(x, height);
        overlayContext.stroke();
        overlayContext.setLineDash([]);
      }});
    }}

    const candles = chart.addSeries(LightweightCharts.CandlestickSeries, {{
      upColor: '#159947',
      downColor: '#d71920',
      borderUpColor: '#159947',
      borderDownColor: '#d71920',
      wickUpColor: '#111111',
      wickDownColor: '#111111'
    }});
    candles.setData(candleData);
    LightweightCharts.createSeriesMarkers(candles, markers);

    const vwap = chart.addSeries(LightweightCharts.LineSeries, {{
      color: '#0b2aa8',
      lineWidth: 2,
      priceLineVisible: false
    }});
    vwap.setData(vwapData);

    const volume = chart.addSeries(LightweightCharts.HistogramSeries, {{
      priceFormat: {{ type: 'volume' }},
      priceScaleId: 'volume',
      priceLineVisible: false
    }});
    volume.setData(volumeData);
    chart.priceScale('volume').applyOptions({{
      scaleMargins: {{ top: 0.78, bottom: 0 }}
    }});

    chart.timeScale().fitContent();
    drawSessions();
    chart.timeScale().subscribeVisibleLogicalRangeChange(drawSessions);
    window.addEventListener('resize', () => {{
      chart.applyOptions({{
        width: container.clientWidth,
        height: container.clientHeight
      }});
      drawSessions();
    }});
  </script>
</body>
</html>
"""
    with open(filename, 'w', encoding='utf-8') as html_file:
        html_file.write(html)
    print(f"TradingView-style chart saved as {filename} in the current directory.")

# --------------------
# Example usage (uncomment to run standalone)
# --------------------
# if __name__ == '__main__':
#     user_ticker = input("Enter a ticker (e.g., AAPL): ")
#     user_date_str = input("Enter a date in YYYY-MM-DD format: ")
#     user_date = datetime.strptime(user_date_str, "%Y-%m-%d").date()
#     timespan_candle_chart(user_ticker, user_date, candle_minutes=3)
#     tradingview_html_chart(user_ticker, user_date, candle_minutes=3)
