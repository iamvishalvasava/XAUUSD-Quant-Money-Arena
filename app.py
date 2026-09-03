# ======================================================================================
# 💰⚡ XAUUSD QUANT MONEY ARENA V5
# STREAMLIT WEB APP
#
# FEATURES
# ✓ GOLDAPI LIVE XAUUSD
# ✓ 3 MINUTE BUY / SELL
# ✓ 5 MINUTE BUY / SELL
# ✓ QUANT FEATURE ENGINE
# ✓ RANDOM FOREST ML
# ✓ PAPER TRADE TRACKING
# ✓ LAST 10 COMPLETED TRADES
# ✓ SQLITE HISTORY
# ✓ AUTO REFRESH
#
# PAPER / RESEARCH ONLY
# BUY / SELL IS A MODEL DIRECTION
# NOT A GUARANTEE OF PROFIT
# ======================================================================================

import os
import time
import math
import sqlite3
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import requests
import streamlit as st
import plotly.graph_objects as go

from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler

try:
    from streamlit_autorefresh import st_autorefresh
    AUTOREFRESH_AVAILABLE = True
except Exception:
    AUTOREFRESH_AVAILABLE = False


# ======================================================================================
# PAGE CONFIG
# ======================================================================================

st.set_page_config(
    page_title="XAUUSD Quant Money Arena V5",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded"
)


# ======================================================================================
# CUSTOM CSS — GAMING STYLE
# ======================================================================================

st.markdown("""
<style>

.stApp {
    background:
        radial-gradient(circle at 10% 20%, rgba(0,255,150,0.08), transparent 25%),
        radial-gradient(circle at 90% 10%, rgba(255,215,0,0.08), transparent 25%),
        linear-gradient(135deg, #05070d 0%, #090d18 50%, #05070d 100%);
}

.block-container {
    padding-top: 1.5rem;
}

.arena-title {
    text-align: center;
    font-size: 44px;
    font-weight: 900;
    color: #ffd700;
    text-shadow:
        0 0 10px rgba(255,215,0,0.6),
        0 0 30px rgba(255,215,0,0.25);
    margin-bottom: 5px;
}

.arena-subtitle {
    text-align: center;
    color: #8a9bb5;
    font-size: 16px;
    margin-bottom: 25px;
}

.metric-card {
    background: linear-gradient(145deg, #111827, #080c14);
    border: 1px solid #26334a;
    border-radius: 16px;
    padding: 18px;
    box-shadow: 0 0 20px rgba(0,0,0,0.4);
}

.buy-card {
    background: linear-gradient(145deg, rgba(0,180,100,0.20), rgba(5,25,20,0.95));
    border: 2px solid #00e676;
    border-radius: 18px;
    padding: 22px;
    text-align: center;
    box-shadow: 0 0 25px rgba(0,230,118,0.18);
}

.sell-card {
    background: linear-gradient(145deg, rgba(255,60,70,0.18), rgba(30,5,8,0.95));
    border: 2px solid #ff4050;
    border-radius: 18px;
    padding: 22px;
    text-align: center;
    box-shadow: 0 0 25px rgba(255,64,80,0.18);
}

.signal-big {
    font-size: 36px;
    font-weight: 900;
}

.small-label {
    color: #94a3b8;
    font-size: 13px;
}

.money-number {
    font-size: 30px;
    font-weight: 800;
    color: #ffd700;
}

</style>
""", unsafe_allow_html=True)


# ======================================================================================
# CONFIG
# ======================================================================================

APP_NAME = "XAUUSD QUANT MONEY ARENA V5"

SYMBOL = "XAU"
CURRENCY = "USD"

POLL_SECONDS = 5

HORIZONS = {
    "3 MIN": 180,
    "5 MIN": 300
}

DB_FILE = "xauusd_quant_v5.db"

MIN_HISTORY_FOR_MODEL = 40

REQUEST_TIMEOUT = 10


# ======================================================================================
# API KEY
# ======================================================================================

def get_goldapi_key():

    try:
        if "GOLDAPI" in st.secrets:
            return str(st.secrets["GOLDAPI"]).strip()
    except Exception:
        pass

    try:
        if "GOLDAPI_KEY" in st.secrets:
            return str(st.secrets["GOLDAPI_KEY"]).strip()
    except Exception:
        pass

    return os.environ.get("GOLDAPI_KEY", "").strip()


# ======================================================================================
# DATABASE
# ======================================================================================

def get_connection():

    conn = sqlite3.connect(
        DB_FILE,
        check_same_thread=False
    )

    return conn


def init_database():

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS quotes (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        timestamp REAL,

        datetime TEXT,

        price REAL,

        bid REAL,

        ask REAL,

        spread REAL

    )
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS forecasts (

        id INTEGER PRIMARY KEY AUTOINCREMENT,

        created_at REAL,

        created_datetime TEXT,

        horizon INTEGER,

        direction TEXT,

        entry_price REAL,

        probability_up REAL,

        probability_down REAL,

        probability_flat REAL,

        signal_score REAL,

        expected_move REAL,

        status TEXT,

        exit_price REAL,

        exit_time REAL,

        pnl REAL,

        outcome TEXT

    )
    """)

    conn.commit()

    conn.close()


# ======================================================================================
# QUOTE DATABASE
# ======================================================================================

def save_quote(timestamp, price, bid, ask):

    spread = ask - bid

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("""

        INSERT INTO quotes
        (
            timestamp,
            datetime,
            price,
            bid,
            ask,
            spread
        )

        VALUES (?, ?, ?, ?, ?, ?)

    """, (

        timestamp,

        datetime.fromtimestamp(
            timestamp,
            tz=timezone.utc
        ).strftime("%Y-%m-%d %H:%M:%S UTC"),

        price,

        bid,

        ask,

        spread

    ))

    conn.commit()

    conn.close()


def load_quotes(limit=1000):

    conn = get_connection()

    query = f"""

        SELECT
            timestamp,
            datetime,
            price,
            bid,
            ask,
            spread

        FROM quotes

        ORDER BY timestamp DESC

        LIMIT {int(limit)}

    """

    df = pd.read_sql_query(
        query,
        conn
    )

    conn.close()

    if len(df) == 0:
        return df

    return df.sort_values("timestamp").reset_index(drop=True)


# ======================================================================================
# GOLDAPI LIVE DATA
# ======================================================================================

@st.cache_data(
    ttl=2,
    show_spinner=False
)
def fetch_goldapi_quote(api_key):

    url = "https://www.goldapi.io/api/XAU/USD"

    headers = {

        "x-access-token": api_key,

        "Content-Type": "application/json",

        "User-Agent": "XAUUSD-Quant-Money-Arena-V5"

    }

    start = time.perf_counter()

    response = requests.get(

        url,

        headers=headers,

        timeout=REQUEST_TIMEOUT

    )

    latency_ms = (
        time.perf_counter() - start
    ) * 1000

    response.raise_for_status()

    data = response.json()

    price = float(data.get("price"))

    bid = data.get("bid")

    ask = data.get("ask")

    if bid is None:
        bid = price

    if ask is None:
        ask = price

    bid = float(bid)

    ask = float(ask)

    return {

        "ok": True,

        "timestamp": time.time(),

        "price": price,

        "bid": bid,

        "ask": ask,

        "spread": ask - bid,

        "provider": "GOLDAPI",

        "latency_ms": latency_ms

    }


# ======================================================================================
# FEATURE ENGINE
# ======================================================================================

def safe_tanh(value):

    try:
        return float(np.tanh(value))
    except Exception:
        return 0.0


def build_features(df):

    if len(df) < 5:

        return {

            "momentum": 0.0,

            "mean_reversion": 0.0,

            "trend": 0.0,

            "microstructure": 0.0,

            "statistical": 0.0,

            "volatility": 0.0,

            "vol_percentile": 50.0,

            "regime": "WARMUP"

        }

    prices = df["price"].astype(float)

    returns = prices.pct_change().fillna(0)

    # ------------------------------------------------------------------
    # MOMENTUM
    # ------------------------------------------------------------------

    lookback = min(10, len(prices) - 1)

    momentum_return = (

        prices.iloc[-1]
        /
        prices.iloc[-lookback]

        - 1

    )

    momentum = safe_tanh(
        momentum_return * 1000
    )

    # ------------------------------------------------------------------
    # MEAN REVERSION
    # ------------------------------------------------------------------

    window = min(20, len(prices))

    rolling_mean = prices.iloc[-window:].mean()

    rolling_std = prices.iloc[-window:].std()

    if rolling_std > 0:

        zscore = (

            prices.iloc[-1]
            -
            rolling_mean

        ) / rolling_std

    else:

        zscore = 0

    mean_reversion = safe_tanh(
        -zscore / 2
    )

    # ------------------------------------------------------------------
    # TREND
    # ------------------------------------------------------------------

    fast_window = min(5, len(prices))

    slow_window = min(20, len(prices))

    fast_ma = prices.iloc[-fast_window:].mean()

    slow_ma = prices.iloc[-slow_window:].mean()

    trend_diff = (

        fast_ma
        -
        slow_ma

    ) / max(
        slow_ma,
        1e-9
    )

    trend = safe_tanh(
        trend_diff * 1000
    )

    # ------------------------------------------------------------------
    # MICROSTRUCTURE
    # ------------------------------------------------------------------

    if "bid" in df.columns and "ask" in df.columns:

        spread = (

            df["ask"].iloc[-1]
            -
            df["bid"].iloc[-1]

        )

        avg_spread = df["spread"].tail(

            min(20, len(df))

        ).mean()

        spread_score = safe_tanh(

            (avg_spread - spread)
            /
            max(avg_spread, 0.000001)

        )

    else:

        spread_score = 0.0

    recent_returns = returns.tail(

        min(8, len(returns))

    )

    directional_pressure = safe_tanh(

        recent_returns.sum() * 1500

    )

    microstructure = (

        0.60 * directional_pressure
        +
        0.40 * spread_score

    )

    # ------------------------------------------------------------------
    # STATISTICAL
    # ------------------------------------------------------------------

    short_mean = returns.tail(

        min(5, len(returns))

    ).mean()

    long_mean = returns.tail(

        min(20, len(returns))

    ).mean()

    statistical = safe_tanh(

        (short_mean - long_mean) * 2000

    )

    # ------------------------------------------------------------------
    # VOLATILITY
    # ------------------------------------------------------------------

    volatility = float(

        returns.tail(

            min(30, len(returns))

        ).std()

    )

    historical_vol = (

        returns.rolling(
            min(20, max(5, len(returns)))
        ).std().dropna()

    )

    if len(historical_vol) > 5:

        vol_percentile = float(

            (
                historical_vol
                <=
                volatility
            ).mean() * 100

        )

    else:

        vol_percentile = 50.0

    # ------------------------------------------------------------------
    # REGIME
    # ------------------------------------------------------------------

    if volatility == 0:

        regime = "WARMUP"

    elif abs(trend) > 0.35:

        regime = "TREND"

    elif vol_percentile > 75:

        regime = "HIGH VOL"

    else:

        regime = "RANGE"

    return {

        "momentum": float(momentum),

        "mean_reversion": float(mean_reversion),

        "trend": float(trend),

        "microstructure": float(microstructure),

        "statistical": float(statistical),

        "volatility": volatility,

        "vol_percentile": vol_percentile,

        "regime": regime

    }


# ======================================================================================
# ML ENGINE
# ======================================================================================

def run_ml_model(df):

    if len(df) < MIN_HISTORY_FOR_MODEL:

        return {

            "score": 0.0,

            "status": "INSUFFICIENT_HISTORY"

        }

    try:

        work = df.copy()

        prices = work["price"].astype(float)

        work["r1"] = prices.pct_change(1)

        work["r3"] = prices.pct_change(3)

        work["r5"] = prices.pct_change(5)

        work["ma_fast"] = (

            prices.rolling(5).mean()
            /
            prices

            - 1

        )

        work["ma_slow"] = (

            prices.rolling(15).mean()
            /
            prices

            - 1

        )

        work["vol"] = (

            prices.pct_change()
            .rolling(10)
            .std()

        )

        work["spread_feature"] = (

            work["spread"]
            /
            prices

        )

        # Future target
        work["future_price"] = prices.shift(-3)

        work["target"] = (

            work["future_price"]
            >
            prices

        ).astype(int)

        feature_columns = [

            "r1",

            "r3",

            "r5",

            "ma_fast",

            "ma_slow",

            "vol",

            "spread_feature"

        ]

        train = work.dropna().copy()

        if len(train) < 20:

            return {

                "score": 0.0,

                "status": "INSUFFICIENT_TRAINING"

            }

        X = train[feature_columns]

        y = train["target"]

        if y.nunique() < 2:

            return {

                "score": 0.0,

                "status": "ONE_CLASS_DATA"

            }

        scaler = StandardScaler()

        X_scaled = scaler.fit_transform(X)

        model = RandomForestClassifier(

            n_estimators=120,

            max_depth=5,

            min_samples_leaf=3,

            random_state=42,

            n_jobs=-1,

            class_weight="balanced"

        )

        model.fit(

            X_scaled,

            y

        )

        latest = work[feature_columns].iloc[-1:]

        if latest.isna().any(axis=None):

            return {

                "score": 0.0,

                "status": "FEATURE_WARMUP"

            }

        latest_scaled = scaler.transform(latest)

        probability_up = float(

            model.predict_proba(
                latest_scaled
            )[0][1]

        )

        score = (

            probability_up - 0.5

        ) * 2

        return {

            "score": float(score),

            "status": "ACTIVE"

        }

    except Exception as e:

        return {

            "score": 0.0,

            "status": f"ML_ERROR: {str(e)[:50]}"

        }


# ======================================================================================
# QUANT FORECAST
# ======================================================================================

def generate_forecast(df, horizon):

    features = build_features(df)

    ml = run_ml_model(df)

    weights = {

        "momentum": 0.18,

        "mean_reversion": 0.12,

        "trend": 0.22,

        "microstructure": 0.18,

        "statistical": 0.15,

        "ml": 0.15

    }

    scores = {

        "Momentum": features["momentum"],

        "Mean Reversion": features["mean_reversion"],

        "Trend": features["trend"],

        "Microstructure": features["microstructure"],

        "Statistical": features["statistical"],

        "ML": ml["score"]

    }

    ensemble = (

        features["momentum"]
        * weights["momentum"]

        +

        features["mean_reversion"]
        * weights["mean_reversion"]

        +

        features["trend"]
        * weights["trend"]

        +

        features["microstructure"]
        * weights["microstructure"]

        +

        features["statistical"]
        * weights["statistical"]

        +

        ml["score"]
        * weights["ml"]

    )

    ensemble = float(

        np.clip(

            ensemble,

            -1,

            1

        )

    )

    # ALWAYS BUY OR SELL
    direction = (

        "BUY"

        if ensemble >= 0

        else

        "SELL"

    )

    # Probability estimate
    directional_confidence = abs(ensemble)

    p_direction = (

        0.50
        +
        0.30 * directional_confidence

    )

    flat_probability = max(

        0.10,

        0.30
        -
        0.15 * directional_confidence

    )

    remaining = 1 - flat_probability

    if direction == "BUY":

        probability_up = remaining * p_direction

        probability_down = remaining - probability_up

    else:

        probability_down = remaining * p_direction

        probability_up = remaining - probability_down

    probability_flat = flat_probability

    total = (

        probability_up
        +
        probability_down
        +
        probability_flat

    )

    probability_up /= total

    probability_down /= total

    probability_flat /= total

    current_price = float(

        df["price"].iloc[-1]

    )

    volatility = features["volatility"]

    horizon_factor = math.sqrt(

        horizon / 180

    )

    expected_return = (

        ensemble
        *
        max(volatility * 5, 0.00002)
        *
        horizon_factor

    )

    expected_move = (

        current_price
        *
        expected_return

    )

    forecast_range = (

        max(

            current_price
            *
            volatility
            *
            4
            *
            horizon_factor,

            current_price * 0.00005

        )

    )

    agreement = sum(

        1

        for value in scores.values()

        if (

            value >= 0
            and direction == "BUY"

        )

        or (

            value < 0
            and direction == "SELL"

        )

    )

    return {

        "timestamp": time.time(),

        "horizon": horizon,

        "price": current_price,

        "direction": direction,

        "signal_score": ensemble,

        "probability_up": probability_up,

        "probability_down": probability_down,

        "probability_flat": probability_flat,

        "expected_move": expected_move,

        "expected_return": expected_return,

        "range_low": current_price - forecast_range,

        "range_high": current_price + forecast_range,

        "agreement": agreement,

        "model_count": len(scores),

        "scores": scores,

        "regime": features["regime"],

        "volatility": volatility,

        "vol_percentile": features["vol_percentile"],

        "ml_status": ml["status"]

    }


# ======================================================================================
# FORECAST DATABASE
# ======================================================================================

def save_forecast(forecast):

    conn = get_connection()

    cursor = conn.cursor()

    timestamp = forecast["timestamp"]

    cursor.execute("""

        INSERT INTO forecasts
        (

            created_at,

            created_datetime,

            horizon,

            direction,

            entry_price,

            probability_up,

            probability_down,

            probability_flat,

            signal_score,

            expected_move,

            status

        )

        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

    """, (

        timestamp,

        datetime.fromtimestamp(
            timestamp,
            tz=timezone.utc
        ).strftime("%Y-%m-%d %H:%M:%S UTC"),

        forecast["horizon"],

        forecast["direction"],

        forecast["price"],

        forecast["probability_up"],

        forecast["probability_down"],

        forecast["probability_flat"],

        forecast["signal_score"],

        forecast["expected_move"],

        "OPEN"

    ))

    conn.commit()

    conn.close()


# ======================================================================================
# COMPLETE EXPIRED PAPER TRADES
# ======================================================================================

def complete_expired_trades(current_price):

    now = time.time()

    conn = get_connection()

    cursor = conn.cursor()

    cursor.execute("""

        SELECT

            id,

            created_at,

            horizon,

            direction,

            entry_price

        FROM forecasts

        WHERE status = 'OPEN'

    """)

    open_trades = cursor.fetchall()

    completed = 0

    for trade in open_trades:

        trade_id = trade[0]

        created_at = trade[1]

        horizon = trade[2]

        direction = trade[3]

        entry_price = trade[4]

        if now >= created_at + horizon:

            if direction == "BUY":

                pnl = (

                    current_price
                    -
                    entry_price

                )

            else:

                pnl = (

                    entry_price
                    -
                    current_price

                )

            outcome = (

                "WIN"

                if pnl > 0

                else

                "LOSS"

            )

            cursor.execute("""

                UPDATE forecasts

                SET

                    status = 'COMPLETED',

                    exit_price = ?,

                    exit_time = ?,

                    pnl = ?,

                    outcome = ?

                WHERE id = ?

            """, (

                current_price,

                now,

                pnl,

                outcome,

                trade_id

            ))

            completed += 1

    conn.commit()

    conn.close()

    return completed


# ======================================================================================
# TRADE HISTORY
# ======================================================================================

def get_completed_trades(limit=10):

    conn = get_connection()

    query = f"""

        SELECT

            id,

            created_datetime,

            horizon,

            direction,

            entry_price,

            exit_price,

            pnl,

            outcome

        FROM forecasts

        WHERE

            status = 'COMPLETED'

            AND

            horizon = 300

        ORDER BY id DESC

        LIMIT {int(limit)}

    """

    df = pd.read_sql_query(

        query,

        conn

    )

    conn.close()

    return df


def get_trade_statistics():

    conn = get_connection()

    query = """

        SELECT

            COUNT(*) AS trades,

            SUM(
                CASE
                    WHEN outcome = 'WIN'
                    THEN 1
                    ELSE 0
                END
            ) AS wins,

            COALESCE(
                SUM(pnl),
                0
            ) AS total_pnl

        FROM forecasts

        WHERE

            status = 'COMPLETED'

            AND

            horizon = 300

    """

    stats = pd.read_sql_query(

        query,

        conn

    )

    conn.close()

    trades = int(stats["trades"].iloc[0])

    wins = int(

        stats["wins"].iloc[0]

        if pd.notna(stats["wins"].iloc[0])

        else 0

    )

    total_pnl = float(

        stats["total_pnl"].iloc[0]

    )

    win_rate = (

        wins / trades * 100

        if trades > 0

        else 0.0

    )

    return {

        "trades": trades,

        "wins": wins,

        "win_rate": win_rate,

        "total_pnl": total_pnl

    }


# ======================================================================================
# DISPLAY SIGNAL CARD
# ======================================================================================

def display_signal_card(label, forecast):

    direction = forecast["direction"]

    if direction == "BUY":

        css_class = "buy-card"

        emoji = "🟢"

    else:

        css_class = "sell-card"

        emoji = "🔴"

    st.markdown(

        f"""

        <div class="{css_class}">

            <div class="small-label">
                🎯 XAUUSD NEXT {label}
            </div>

            <div class="signal-big">
                {emoji} {direction}
            </div>

            <br>

            <div>
                Signal Power:
                <b>{forecast["signal_score"]:+.4f}</b>
            </div>

            <div>
                🟢 UP:
                <b>{forecast["probability_up"]*100:.1f}%</b>
            </div>

            <div>
                🔴 DOWN:
                <b>{forecast["probability_down"]*100:.1f}%</b>
            </div>

            <div>
                🟡 FLAT:
                <b>{forecast["probability_flat"]*100:.1f}%</b>
            </div>

        </div>

        """,

        unsafe_allow_html=True

    )


# ======================================================================================
# MAIN APP
# ======================================================================================

def main():

    init_database()

    # ------------------------------------------------------------------
    # TITLE
    # ------------------------------------------------------------------

    st.markdown(

        '<div class="arena-title">💰⚡ XAUUSD QUANT MONEY ARENA V5 🎮</div>',

        unsafe_allow_html=True

    )

    st.markdown(

        '<div class="arena-subtitle">'
        'LIVE QUANT SIGNALS • 3 MINUTE + 5 MINUTE • PAPER MONEY GAME'
        '</div>',

        unsafe_allow_html=True

    )

    # ------------------------------------------------------------------
    # SIDEBAR
    # ------------------------------------------------------------------

    st.sidebar.title("🎮 CONTROL PANEL")

    refresh_seconds = st.sidebar.slider(

        "🔄 Auto Refresh (seconds)",

        min_value=5,

        max_value=60,

        value=5,

        step=5

    )

    history_limit = st.sidebar.slider(

        "📊 Quote History",

        min_value=50,

        max_value=2000,

        value=500,

        step=50

    )

    manual_refresh = st.sidebar.button(

        "⚡ REFRESH NOW"

    )

    st.sidebar.markdown("---")

    st.sidebar.info(

        """
        💡 The app collects a quote whenever
        the Streamlit app refreshes.

        For guaranteed 24/7 background collection,
        a separate always-on worker is required.
        """

    )

    # ------------------------------------------------------------------
    # AUTO REFRESH
    # ------------------------------------------------------------------

    if AUTOREFRESH_AVAILABLE:

        st_autorefresh(

            interval=refresh_seconds * 1000,

            key="xauusd_v5_refresh"

        )

    # ------------------------------------------------------------------
    # API KEY
    # ------------------------------------------------------------------

    api_key = get_goldapi_key()

    if not api_key:

        st.error(
            "❌ GOLDAPI API KEY NOT FOUND"
        )

        st.code("""

Create Streamlit Secret:

GOLDAPI = "YOUR_GOLDAPI_KEY"

        """)

        st.stop()

    # ------------------------------------------------------------------
    # FETCH LIVE QUOTE
    # ------------------------------------------------------------------

    try:

        fetch_goldapi_quote.clear()

        quote = fetch_goldapi_quote(api_key)

    except Exception as e:

        st.error(

            f"❌ GOLDAPI ERROR: {str(e)}"

        )

        existing = load_quotes(1)

        if len(existing) == 0:

            st.stop()

        quote = {

            "timestamp": time.time(),

            "price": float(existing["price"].iloc[-1]),

            "bid": float(existing["bid"].iloc[-1]),

            "ask": float(existing["ask"].iloc[-1]),

            "spread": float(existing["spread"].iloc[-1]),

            "provider": "LAST_SAVED_QUOTE",

            "latency_ms": 0

        }

        st.warning(
            "⚠️ Using last saved quote."
        )

    # ------------------------------------------------------------------
    # SAVE QUOTE
    # ------------------------------------------------------------------

    save_quote(

        quote["timestamp"],

        quote["price"],

        quote["bid"],

        quote["ask"]

    )

    # ------------------------------------------------------------------
    # COMPLETE TRADES
    # ------------------------------------------------------------------

    completed_now = complete_expired_trades(

        quote["price"]

    )

    # ------------------------------------------------------------------
    # LOAD HISTORY
    # ------------------------------------------------------------------

    quotes = load_quotes(

        history_limit

    )

    # ------------------------------------------------------------------
    # FORECASTS
    # ------------------------------------------------------------------

    forecast_3m = generate_forecast(

        quotes,

        180

    )

    forecast_5m = generate_forecast(

        quotes,

        300

    )

    # ------------------------------------------------------------------
    # SAVE FORECASTS
    #
    # Avoid creating duplicates every rerun within a short interval
    # ------------------------------------------------------------------

    now = time.time()

    if "last_forecast_save" not in st.session_state:

        st.session_state.last_forecast_save = 0.0

    if now - st.session_state.last_forecast_save >= refresh_seconds - 1:

        save_forecast(forecast_3m)

        save_forecast(forecast_5m)

        st.session_state.last_forecast_save = now

    # ------------------------------------------------------------------
    # LIVE METRICS
    # ------------------------------------------------------------------

    st.markdown("## ⚡ LIVE MARKET")

    c1, c2, c3, c4, c5 = st.columns(5)

    c1.metric(

        "💰 XAUUSD MID",

        f"${quote['price']:,.3f}"

    )

    c2.metric(

        "🔵 BID",

        f"${quote['bid']:,.3f}"

    )

    c3.metric(

        "🟠 ASK",

        f"${quote['ask']:,.3f}"

    )

    c4.metric(

        "↔ SPREAD",

        f"${quote['spread']:.5f}"

    )

    c5.metric(

        "⚡ LATENCY",

        f"{quote['latency_ms']:.0f} ms"

    )

    # ------------------------------------------------------------------
    # SIGNAL ARENA
    # ------------------------------------------------------------------

    st.markdown("## 🎯 QUANT SIGNAL ARENA")

    col1, col2 = st.columns(2)

    with col1:

        display_signal_card(

            "180 SECONDS (3 MIN)",

            forecast_3m

        )

    with col2:

        display_signal_card(

            "300 SECONDS (5 MIN)",

            forecast_5m

        )

    # ------------------------------------------------------------------
    # MODEL MATRIX
    # ------------------------------------------------------------------

    st.markdown("## 🧠 MODEL POWER MATRIX")

    score_names = list(

        forecast_5m["scores"].keys()

    )

    score_values = list(

        forecast_5m["scores"].values()

    )

    fig_scores = go.Figure(

        data=[

            go.Bar(

                x=score_names,

                y=score_values,

                marker_color=[

                    "#00e676"

                    if x >= 0

                    else

                    "#ff4050"

                    for x in score_values

                ]

            )

        ]

    )

    fig_scores.update_layout(

        height=350,

        paper_bgcolor="rgba(0,0,0,0)",

        plot_bgcolor="rgba(0,0,0,0)",

        font=dict(color="white"),

        yaxis=dict(

            range=[-1, 1],

            gridcolor="rgba(255,255,255,0.1)"

        )

    )

    st.plotly_chart(

        fig_scores,

        use_container_width=True

    )

    # ------------------------------------------------------------------
    # PRICE CHART
    # ------------------------------------------------------------------

    st.markdown("## 📈 LIVE XAUUSD PRICE")

    if len(quotes) > 1:

        chart_quotes = quotes.tail(200)

        fig_price = go.Figure()

        fig_price.add_trace(

            go.Scatter(

                x=pd.to_datetime(

                    chart_quotes["timestamp"],

                    unit="s"

                ),

                y=chart_quotes["price"],

                mode="lines",

                name="XAUUSD MID"

            )

        )

        fig_price.update_layout(

            height=400,

            paper_bgcolor="rgba(0,0,0,0)",

            plot_bgcolor="rgba(0,0,0,0)",

            font=dict(color="white"),

            xaxis=dict(

                gridcolor="rgba(255,255,255,0.08)"

            ),

            yaxis=dict(

                gridcolor="rgba(255,255,255,0.08)"

            )

        )

        st.plotly_chart(

            fig_price,

            use_container_width=True

        )

    else:

        st.info(

            "⏳ Collecting quote history..."

        )

    # ------------------------------------------------------------------
    # PAPER MONEY SCOREBOARD
    # ------------------------------------------------------------------

    st.markdown("## 💰🏆 PAPER MONEY SCOREBOARD")

    stats = get_trade_statistics()

    s1, s2, s3, s4 = st.columns(4)

    s1.metric(

        "🏆 Completed 5M Trades",

        stats["trades"]

    )

    s2.metric(

        "🟢 Wins",

        stats["wins"]

    )

    s3.metric(

        "🎯 Win Rate",

        f"{stats['win_rate']:.1f}%"

    )

    s4.metric(

        "💰 Paper P&L",

        f"${stats['total_pnl']:+.3f}"

    )

    # ------------------------------------------------------------------
    # LAST 10 COMPLETED TRADES
    # ------------------------------------------------------------------

    st.markdown("## 🏆 LAST 10 COMPLETED 5-MINUTE PAPER TRADES")

    trades = get_completed_trades(10)

    if len(trades) == 0:

        st.info(

            "🎮 No completed 5-minute trades yet. "
            "The first trade completes after approximately 300 seconds."

        )

    else:

        display_df = trades.copy()

        display_df["entry_price"] = display_df["entry_price"].map(

            lambda x: f"${x:,.3f}"

        )

        display_df["exit_price"] = display_df["exit_price"].map(

            lambda x: f"${x:,.3f}"

        )

        display_df["pnl"] = display_df["pnl"].map(

            lambda x: f"${x:+.3f}"

        )

        display_df.columns = [

            "ID",

            "ENTRY TIME",

            "HORIZON",

            "SIGNAL",

            "ENTRY",

            "EXIT",

            "P&L",

            "RESULT"

        ]

        st.dataframe(

            display_df,

            use_container_width=True,

            hide_index=True

        )

    # ------------------------------------------------------------------
    # SYSTEM STATUS
    # ------------------------------------------------------------------

    st.markdown("## ⚙️ SYSTEM STATUS")

    st.success(

        f"""

💰 QUANT MONEY ENGINE ONLINE 🎮

Provider: {quote['provider']}

Quotes stored: {len(quotes)}

3-Min Signal: {forecast_3m['direction']}

5-Min Signal: {forecast_5m['direction']}

5-Min Model Agreement:
{forecast_5m['agreement']}/{forecast_5m['model_count']}

Market Regime:
{forecast_5m['regime']}

ML Status:
{forecast_5m['ml_status']}

Newly completed trades:
{completed_now}

⚠️ PAPER / RESEARCH ONLY

BUY and SELL are model directions.
They are not guaranteed profitable predictions.

        """

    )


# ======================================================================================
# RUN
# ======================================================================================

if __name__ == "__main__":

    main()
