# ==============================================================================
# 🥇⚡ XAUUSD QUANT MONEY ARENA V5 - FIXED
# ==============================================================================
#
# FEATURES
# ------------------------------------------------------------------------------
# ✓ GoldAPI.io LIVE XAU/USD
# ✓ 5-second automatic refresh
# ✓ Real returned quote history
# ✓ Bid / Ask / Mid / Spread
# ✓ 180-second BUY / SELL forecast
# ✓ 300-second BUY / SELL forecast
# ✓ Momentum Engine
# ✓ Mean Reversion Engine
# ✓ Trend Engine
# ✓ Microstructure Engine (quote-based only)
# ✓ Statistical Engine
# ✓ Random Forest ML when sufficient history exists
# ✓ Paper trade tracking using later observed prices
# ✓ Last 10 completed 5-minute trades
# ✓ Live charts
# ✓ Streamlit Cloud compatible
#
# IMPORTANT
# ------------------------------------------------------------------------------
# PAPER / RESEARCH ONLY
# BUY / SELL is a MODEL DIRECTION.
# MODEL PROBABILITIES ARE ESTIMATES.
# NO GUARANTEED PROFIT.
#
# DATA INTEGRITY
# ------------------------------------------------------------------------------
# ✓ No fabricated tick data
# ✓ No fake volume
# ✓ No fabricated order book
# ✓ No fake latency
# ✓ Polling is NOT WebSocket streaming
# ✓ Spot/futures are not silently mixed
# ==============================================================================


import os
import time
import math
import warnings
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import requests
import streamlit as st
import plotly.graph_objects as go

from sklearn.ensemble import RandomForestClassifier

warnings.filterwarnings("ignore")


# ==============================================================================
# PAGE CONFIG
# ==============================================================================

st.set_page_config(
    page_title="XAUUSD Quant Money Arena V5",
    page_icon="🥇",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ==============================================================================
# OPTIONAL AUTO REFRESH
# ==============================================================================

try:
    from streamlit_autorefresh import st_autorefresh
    AUTOREFRESH_AVAILABLE = True
except Exception:
    AUTOREFRESH_AVAILABLE = False


# ==============================================================================
# CONSTANTS
# ==============================================================================

APP_VERSION = "V5 FIXED"
SYMBOL = "XAUUSD"
INSTRUMENT = "SPOT_XAUUSD"

POLL_SECONDS = 5

FORECAST_HORIZONS = [180, 300]

MAX_QUOTES = 10000
MAX_FORECASTS = 5000
MAX_COMPLETED_TRADES = 1000

MIN_HISTORY_FOR_SIGNALS = 8
MIN_HISTORY_FOR_ML = 80

REQUEST_TIMEOUT = 10


# ==============================================================================
# CUSTOM CSS
# ==============================================================================

st.markdown("""
<style>

.block-container {
    padding-top: 1.2rem;
    padding-bottom: 2rem;
}

[data-testid="stMetric"] {
    background-color: rgba(20, 25, 35, 0.75);
    border: 1px solid rgba(100, 200, 180, 0.25);
    padding: 12px;
    border-radius: 10px;
}

div[data-testid="stMetricLabel"] {
    font-size: 0.80rem;
}

.quant-title {
    text-align: center;
    font-size: 28px;
    font-weight: 800;
    margin-bottom: 2px;
}

.quant-subtitle {
    text-align: center;
    font-size: 11px;
    opacity: 0.65;
    margin-bottom: 25px;
}

.signal-buy {
    color: #00d084;
    font-size: 32px;
    font-weight: 800;
}

.signal-sell {
    color: #ff4b4b;
    font-size: 32px;
    font-weight: 800;
}

.signal-warmup {
    color: #ffcc00;
}

</style>
""", unsafe_allow_html=True)


# ==============================================================================
# SESSION STATE
# ==============================================================================

def initialize_state():

    defaults = {

        "quotes": [],

        "forecasts": [],

        "completed_trades": [],

        "paper_pnl": 0.0,

        "wins": 0,

        "losses": 0,

        "last_quote_time": None,

        "last_forecast": {},

        "ml_model": None,

        "ml_last_train_count": 0,

        "ml_status": "INSUFFICIENT_HISTORY",

        "request_count": 0,

        "provider_errors": 0,

        "app_started": datetime.now(timezone.utc),

    }

    for key, value in defaults.items():

        if key not in st.session_state:

            st.session_state[key] = value


initialize_state()


# ==============================================================================
# API KEY
# ==============================================================================

def get_goldapi_key():

    # Streamlit Secrets

    try:

        if "GOLDAPI" in st.secrets:

            return str(st.secrets["GOLDAPI"])

    except Exception:

        pass

    # Environment variable fallback

    key = os.getenv("GOLDAPI")

    if key:
        return key

    return None


GOLDAPI_KEY = get_goldapi_key()


# ==============================================================================
# GOLDAPI FETCH
# ==============================================================================

def fetch_live_xauusd():

    """
    Fetch real XAU/USD spot quote from GoldAPI.

    No synthetic prices are created.
    If the provider does not return bid/ask, they remain unavailable.
    """

    url = "https://www.goldapi.io/api/XAU/USD"

    headers = {
        "x-access-token": GOLDAPI_KEY,
        "Content-Type": "application/json",
        "User-Agent": "XAUUSD-Quant-Money-Arena-V5"
    }

    start = time.perf_counter()

    try:

        response = requests.get(
            url,
            headers=headers,
            timeout=REQUEST_TIMEOUT
        )

        latency_ms = (time.perf_counter() - start) * 1000

        if response.status_code != 200:

            return {
                "success": False,
                "error": f"GoldAPI HTTP {response.status_code}",
                "latency_ms": latency_ms
            }

        data = response.json()

        # --------------------------------------------------------------
        # PRICE
        # --------------------------------------------------------------

        price = data.get("price")

        if price is None:
            price = data.get("ask")

        if price is None:
            price = data.get("bid")

        if price is None:

            return {
                "success": False,
                "error": "Provider returned no usable price",
                "latency_ms": latency_ms
            }

        price = float(price)

        # --------------------------------------------------------------
        # BID / ASK
        # --------------------------------------------------------------

        bid = data.get("bid")
        ask = data.get("ask")

        bid = float(bid) if bid is not None else None
        ask = float(ask) if ask is not None else None

        # --------------------------------------------------------------
        # MID
        # --------------------------------------------------------------

        if bid is not None and ask is not None:

            mid = (bid + ask) / 2.0
            spread = ask - bid

        else:

            # IMPORTANT:
            # No fabricated bid/ask.
            # Use provider price as reference price only.

            mid = price
            spread = None

        return {
            "success": True,
            "provider": "GOLDAPI",
            "symbol": SYMBOL,
            "instrument": INSTRUMENT,
            "price": price,
            "bid": bid,
            "ask": ask,
            "mid": mid,
            "spread": spread,
            "latency_ms": latency_ms,
            "raw": data
        }

    except Exception as e:

        latency_ms = (time.perf_counter() - start) * 1000

        return {
            "success": False,
            "error": str(e),
            "latency_ms": latency_ms
        }


# ==============================================================================
# DATA MANAGER
# ==============================================================================

class DataManager:


    @staticmethod
    def add_quote(quote):

        now = datetime.now(timezone.utc)

        record = {
            "timestamp": now,
            "timestamp_unix": time.time(),
            "price": float(quote["price"]),
            "mid": float(quote["mid"]),
            "bid": quote["bid"],
            "ask": quote["ask"],
            "spread": quote["spread"],
            "latency_ms": float(quote["latency_ms"]),
            "provider": quote["provider"]
        }

        st.session_state.quotes.append(record)

        if len(st.session_state.quotes) > MAX_QUOTES:

            st.session_state.quotes = (
                st.session_state.quotes[-MAX_QUOTES:]
            )

        st.session_state.last_quote_time = now

        return record


    @staticmethod
    def dataframe():

        if not st.session_state.quotes:

            return pd.DataFrame()

        df = pd.DataFrame(st.session_state.quotes)

        df["timestamp"] = pd.to_datetime(
            df["timestamp"],
            utc=True
        )

        return df


# ==============================================================================
# FEATURE ENGINEERING
# ==============================================================================

def safe_std(values):

    values = np.asarray(values, dtype=float)

    if len(values) < 2:
        return 0.0

    value = float(np.std(values))

    if math.isnan(value):
        return 0.0

    return value


def calculate_features(df):

    """
    Features are calculated only from actually collected quotes.
    """

    result = {}

    if df.empty or len(df) < 2:

        return {
            "returns": np.array([]),
            "last_return": 0.0,
            "momentum_short": 0.0,
            "momentum_medium": 0.0,
            "volatility": 0.0,
            "trend_slope": 0.0,
            "zscore": 0.0,
            "mean_deviation": 0.0,
            "spread": 0.0,
            "spread_change": 0.0,
            "quote_imbalance": 0.0,
        }

    prices = df["mid"].astype(float).values

    returns = np.diff(prices) / prices[:-1]

    last_return = float(returns[-1]) if len(returns) else 0.0


    # ------------------------------------------------------------------
    # MOMENTUM
    # ------------------------------------------------------------------

    short_n = min(6, len(prices) - 1)
    medium_n = min(20, len(prices) - 1)

    momentum_short = 0.0
    momentum_medium = 0.0

    if short_n > 0:

        momentum_short = (
            prices[-1] / prices[-1 - short_n]
        ) - 1.0

    if medium_n > 0:

        momentum_medium = (
            prices[-1] / prices[-1 - medium_n]
        ) - 1.0


    # ------------------------------------------------------------------
    # VOLATILITY
    # ------------------------------------------------------------------

    volatility = safe_std(returns)


    # ------------------------------------------------------------------
    # TREND SLOPE
    # ------------------------------------------------------------------

    slope_n = min(30, len(prices))

    trend_slope = 0.0

    if slope_n >= 3:

        y = prices[-slope_n:]

        x = np.arange(slope_n)

        slope = np.polyfit(x, y, 1)[0]

        trend_slope = slope / max(prices[-1], 1e-9)


    # ------------------------------------------------------------------
    # MEAN REVERSION
    # ------------------------------------------------------------------

    mean_n = min(30, len(prices))

    rolling_prices = prices[-mean_n:]

    rolling_mean = float(np.mean(rolling_prices))

    rolling_std = safe_std(rolling_prices)

    mean_deviation = (
        prices[-1] - rolling_mean
    ) / max(prices[-1], 1e-9)

    zscore = (
        (prices[-1] - rolling_mean)
        / max(rolling_std, 1e-9)
    )


    # ------------------------------------------------------------------
    # SPREAD FEATURES
    # ------------------------------------------------------------------

    spread_values = df["spread"].dropna().values

    spread = 0.0

    spread_change = 0.0

    if len(spread_values) > 0:

        spread = float(spread_values[-1])

    if len(spread_values) >= 2:

        spread_change = (
            float(spread_values[-1])
            - float(spread_values[-2])
        )


    # ------------------------------------------------------------------
    # QUOTE IMBALANCE PROXY
    # ------------------------------------------------------------------
    #
    # This is NOT order-book imbalance.
    #
    # It is only based on observed quote movement:
    # upward quote changes vs downward quote changes.
    # ------------------------------------------------------------------

    quote_imbalance = 0.0

    if len(returns) >= 5:

        recent = returns[-min(10, len(returns)):]

        up = np.sum(recent > 0)

        down = np.sum(recent < 0)

        total = up + down

        if total > 0:

            quote_imbalance = (up - down) / total


    result = {

        "returns": returns,

        "last_return": last_return,

        "momentum_short": momentum_short,

        "momentum_medium": momentum_medium,

        "volatility": volatility,

        "trend_slope": trend_slope,

        "zscore": zscore,

        "mean_deviation": mean_deviation,

        "spread": spread,

        "spread_change": spread_change,

        "quote_imbalance": quote_imbalance,

    }

    return result


# ==============================================================================
# MODEL ENGINES
# ==============================================================================

def clip_score(value):

    return float(np.clip(value, -1.0, 1.0))


def momentum_engine(features):

    score = (
        features["momentum_short"] * 4000
        + features["momentum_medium"] * 2500
        + features["last_return"] * 2500
    )

    return clip_score(score)


def mean_reversion_engine(features):

    z = features["zscore"]

    # Negative z-score = below mean = upward reversion tendency
    score = -z / 3.0

    return clip_score(score)


def trend_engine(features):

    score = (
        features["trend_slope"] * 6000
        + features["momentum_medium"] * 2000
    )

    return clip_score(score)


def microstructure_engine(features):

    """
    Quote-based only.

    NOT real order-book microstructure.
    """

    quote_component = features["quote_imbalance"]

    spread_penalty = 0.0

    if features["spread"] > 0:

        spread_penalty = min(
            abs(features["spread_change"])
            / max(features["spread"], 1e-9),
            1.0
        )

    score = quote_component * (1.0 - 0.25 * spread_penalty)

    return clip_score(score)


def statistical_engine(features):

    returns = features["returns"]

    if len(returns) < 5:
        return 0.0

    recent = returns[-min(20, len(returns)):]

    mean_return = float(np.mean(recent))

    std_return = safe_std(recent)

    score = mean_return / max(std_return, 1e-9)

    return clip_score(score / 2.0)


# ==============================================================================
# ML FEATURES
# ==============================================================================

def feature_vector_from_dataframe(df):

    f = calculate_features(df)

    return np.array([
        f["last_return"],
        f["momentum_short"],
        f["momentum_medium"],
        f["volatility"],
        f["trend_slope"],
        f["zscore"],
        f["mean_deviation"],
        f["spread"],
        f["spread_change"],
        f["quote_imbalance"],
    ], dtype=float)


# ==============================================================================
# ML TRAINING
# ==============================================================================

def train_ml_model_if_needed():

    completed = st.session_state.completed_trades

    if len(completed) < MIN_HISTORY_FOR_ML:

        st.session_state.ml_status = (
            f"INSUFFICIENT_HISTORY "
            f"({len(completed)}/{MIN_HISTORY_FOR_ML})"
        )

        return


    # Retrain periodically

    if (
        st.session_state.ml_model is not None
        and len(completed)
        - st.session_state.ml_last_train_count
        < 10
    ):
        return


    X = []
    y = []


    for trade in completed:

        vector = trade.get("feature_vector")

        outcome = trade.get("outcome")

        if vector is None:
            continue

        if outcome not in [0, 1]:
            continue

        X.append(vector)

        y.append(outcome)


    if len(X) < MIN_HISTORY_FOR_ML:

        st.session_state.ml_status = "INSUFFICIENT_VALID_TRAINING_DATA"

        return


    # Need both classes

    if len(set(y)) < 2:

        st.session_state.ml_status = "WAITING_FOR_BOTH_OUTCOME_CLASSES"

        return


    try:

        model = RandomForestClassifier(
            n_estimators=200,
            max_depth=6,
            min_samples_leaf=3,
            random_state=42,
            n_jobs=-1
        )

        model.fit(
            np.asarray(X, dtype=float),
            np.asarray(y, dtype=int)
        )

        st.session_state.ml_model = model

        st.session_state.ml_last_train_count = len(completed)

        st.session_state.ml_status = (
            f"ACTIVE | TRAINED ON {len(X)} COMPLETED TRADES"
        )

    except Exception as e:

        st.session_state.ml_status = f"ML ERROR: {str(e)[:100]}"


# ==============================================================================
# ML PREDICTION
# ==============================================================================

def get_ml_probability(df):

    model = st.session_state.ml_model

    if model is None:

        return None

    try:

        x = feature_vector_from_dataframe(df).reshape(1, -1)

        probability = model.predict_proba(x)[0]

        classes = list(model.classes_)

        if 1 in classes:

            idx = classes.index(1)

            return float(probability[idx])

    except Exception:

        return None

    return None


# ==============================================================================
# FORECAST ENGINE
# ==============================================================================

def run_forecast(df, horizon_seconds):

    start = time.perf_counter()

    features = calculate_features(df)

    # --------------------------------------------------------------------------
    # MODEL SCORES
    # --------------------------------------------------------------------------

    momentum = momentum_engine(features)

    mean_reversion = mean_reversion_engine(features)

    microstructure = microstructure_engine(features)

    statistical = statistical_engine(features)

    trend = trend_engine(features)


    scores = {

        "Momentum": momentum,

        "Mean Reversion": mean_reversion,

        "Microstructure": microstructure,

        "Statistical": statistical,

        "Trend": trend,

    }


    # --------------------------------------------------------------------------
    # HORIZON WEIGHTS
    # --------------------------------------------------------------------------

    if horizon_seconds == 180:

        weights = {
            "Momentum": 0.28,
            "Mean Reversion": 0.18,
            "Microstructure": 0.22,
            "Statistical": 0.14,
            "Trend": 0.18,
        }

    else:

        weights = {
            "Momentum": 0.20,
            "Mean Reversion": 0.18,
            "Microstructure": 0.12,
            "Statistical": 0.15,
            "Trend": 0.35,
        }


    # --------------------------------------------------------------------------
    # ENSEMBLE
    # --------------------------------------------------------------------------

    weighted_score = sum(
        scores[name] * weights[name]
        for name in scores
    )


    # --------------------------------------------------------------------------
    # ML
    # --------------------------------------------------------------------------

    ml_probability = get_ml_probability(df)

    if ml_probability is not None:

        ml_score = (ml_probability - 0.5) * 2.0

        ensemble_score = (
            weighted_score * 0.75
            + ml_score * 0.25
        )

    else:

        ensemble_score = weighted_score


    ensemble_score = clip_score(ensemble_score)


    # --------------------------------------------------------------------------
    # AGREEMENT
    # --------------------------------------------------------------------------

    if ensemble_score >= 0:

        agreement = sum(
            1 for value in scores.values()
            if value > 0
        )

    else:

        agreement = sum(
            1 for value in scores.values()
            if value < 0
        )


    # --------------------------------------------------------------------------
    # PROBABILITIES
    # --------------------------------------------------------------------------

    strength = abs(ensemble_score)

    flat_probability = max(
        0.12,
        0.28 - strength * 0.18
    )

    directional_probability = 1.0 - flat_probability


    if ensemble_score >= 0:

        up_probability = (
            directional_probability
            * (0.50 + strength * 0.50)
        )

        down_probability = (
            directional_probability - up_probability
        )

    else:

        down_probability = (
            directional_probability
            * (0.50 + strength * 0.50)
        )

        up_probability = (
            directional_probability - down_probability
        )


    # Normalize

    total_probability = (
        up_probability
        + down_probability
        + flat_probability
    )

    up_probability /= total_probability

    down_probability /= total_probability

    flat_probability /= total_probability


    # --------------------------------------------------------------------------
    # FINAL SIGNAL
    # ALWAYS BUY OR SELL
    # --------------------------------------------------------------------------

    signal = (
        "BUY"
        if up_probability >= down_probability
        else "SELL"
    )


    # --------------------------------------------------------------------------
    # EXPECTED MOVE
    #
    # Derived from observed quote volatility.
    # --------------------------------------------------------------------------

    current_price = float(df["mid"].iloc[-1])

    observed_volatility = features["volatility"]

    # Approximate number of 5-second polling intervals

    intervals = max(
        horizon_seconds / POLL_SECONDS,
        1
    )

    volatility_move = (
        current_price
        * observed_volatility
        * math.sqrt(intervals)
    )

    direction = (
        1
        if signal == "BUY"
        else -1
    )

    confidence = max(
        abs(up_probability - down_probability),
        0.01
    )

    expected_move = (
        direction
        * volatility_move
        * confidence
    )


    # If history is still warming up, expected move remains conservative

    if len(df) < MIN_HISTORY_FOR_SIGNALS:

        expected_move = 0.0


    expected_return_pct = (
        expected_move
        / max(current_price, 1e-9)
        * 100
    )


    # --------------------------------------------------------------------------
    # FORECAST RANGE
    # --------------------------------------------------------------------------

    range_width = max(
        volatility_move * 2.0,
        current_price * 0.00005
    )

    forecast_low = current_price - range_width

    forecast_high = current_price + range_width


    # --------------------------------------------------------------------------
    # MARKET REGIME
    # --------------------------------------------------------------------------

    if len(df) < MIN_HISTORY_FOR_SIGNALS:

        regime = "WARMUP"

        volatility_label = "WARMUP"

    else:

        if observed_volatility < 0.00005:
            volatility_label = "LOW"

        elif observed_volatility < 0.00015:
            volatility_label = "NORMAL"

        else:
            volatility_label = "HIGH"


        trend_strength = abs(features["trend_slope"])

        if trend_strength > 0.00010:

            regime = "TRENDING"

        elif abs(features["zscore"]) > 1.5:

            regime = "MEAN_REVERSION"

        else:

            regime = "RANGING"


    # --------------------------------------------------------------------------
    # DATA QUALITY
    # --------------------------------------------------------------------------

    quality = 0.0

    if len(df) >= 2:
        quality += 35

    if len(df) >= 10:
        quality += 20

    if len(df) >= 30:
        quality += 20

    if df["bid"].notna().iloc[-1]:
        quality += 12.5

    if df["ask"].notna().iloc[-1]:
        quality += 12.5


    processing_ms = (
        time.perf_counter() - start
    ) * 1000


    forecast = {

        "timestamp": datetime.now(timezone.utc),

        "horizon": horizon_seconds,

        "entry_price": current_price,

        "signal": signal,

        "up_probability": up_probability * 100,

        "down_probability": down_probability * 100,

        "flat_probability": flat_probability * 100,

        "signal_power": ensemble_score,

        "agreement": agreement,

        "model_scores": scores,

        "expected_move": expected_move,

        "expected_return_pct": expected_return_pct,

        "forecast_low": forecast_low,

        "forecast_high": forecast_high,

        "market_regime": regime,

        "volatility_label": volatility_label,

        "data_quality": quality,

        "ml_probability": (
            ml_probability * 100
            if ml_probability is not None
            else None
        ),

        "feature_vector": feature_vector_from_dataframe(df).tolist(),

        "processing_ms": processing_ms,

        "completed": False,

        "exit_price": None,

        "pnl": None,

        "outcome": None,

    }

    return forecast


# ==============================================================================
# PAPER TRADE COMPLETION
# ==============================================================================

def update_completed_trades(current_price):

    now = datetime.now(timezone.utc)

    newly_completed = 0

    remaining_forecasts = []


    for forecast in st.session_state.forecasts:

        if forecast.get("completed", False):

            continue


        age_seconds = (
            now - forecast["timestamp"]
        ).total_seconds()


        # ----------------------------------------------------------------------
        # Complete when later observed quote exists
        # ----------------------------------------------------------------------

        if age_seconds >= forecast["horizon"]:

            forecast["completed"] = True

            forecast["exit_price"] = float(current_price)


            if forecast["signal"] == "BUY":

                pnl = (
                    current_price
                    - forecast["entry_price"]
                )

            else:

                pnl = (
                    forecast["entry_price"]
                    - current_price
                )


            forecast["pnl"] = float(pnl)

            # Binary outcome for ML

            outcome = 1 if pnl > 0 else 0

            forecast["outcome"] = outcome


            trade = forecast.copy()

            st.session_state.completed_trades.append(trade)

            st.session_state.paper_pnl += pnl


            if pnl > 0:

                st.session_state.wins += 1

            elif pnl < 0:

                st.session_state.losses += 1


            newly_completed += 1


        else:

            remaining_forecasts.append(forecast)


    st.session_state.forecasts = remaining_forecasts


    if len(st.session_state.completed_trades) > MAX_COMPLETED_TRADES:

        st.session_state.completed_trades = (
            st.session_state.completed_trades[-MAX_COMPLETED_TRADES:]
        )


    return newly_completed


# ==============================================================================
# FORECAST STORAGE
# ==============================================================================

def create_new_forecasts(df):

    created = []

    for horizon in FORECAST_HORIZONS:

        forecast = run_forecast(
            df,
            horizon
        )

        st.session_state.forecasts.append(forecast)

        created.append(forecast)


    if len(st.session_state.forecasts) > MAX_FORECASTS:

        st.session_state.forecasts = (
            st.session_state.forecasts[-MAX_FORECASTS:]
        )


    st.session_state.last_forecast = {

        f["horizon"]: f
        for f in created
    }

    return created


# ==============================================================================
# CHART FUNCTIONS
# ==============================================================================

def make_price_chart(df):

    fig = go.Figure()

    if not df.empty:

        fig.add_trace(
            go.Scatter(
                x=df["timestamp"],
                y=df["mid"],
                mode="lines",
                name="XAUUSD MID"
            )
        )


    fig.update_layout(

        height=350,

        margin=dict(
            l=10,
            r=10,
            t=35,
            b=10
        ),

        title="📈 LIVE XAUUSD PRICE",

        xaxis_title="Time",

        yaxis_title="Price ($)",

        template="plotly_dark",

        showlegend=False,

    )

    return fig


def make_probability_chart(forecasts):

    labels = []

    up = []

    down = []

    flat = []


    for f in forecasts:

        labels.append(
            f"{f['horizon']} SEC"
        )

        up.append(f["up_probability"])

        down.append(f["down_probability"])

        flat.append(f["flat_probability"])


    fig = go.Figure()


    fig.add_trace(
        go.Bar(
            name="UP",
            x=labels,
            y=up
        )
    )

    fig.add_trace(
        go.Bar(
            name="DOWN",
            x=labels,
            y=down
        )
    )

    fig.add_trace(
        go.Bar(
            name="FLAT",
            x=labels,
            y=flat
        )
    )


    fig.update_layout(

        barmode="group",

        height=320,

        title="🎯 MODEL PROBABILITY ARENA",

        yaxis_title="Probability %",

        template="plotly_dark",

        legend=dict(
            orientation="h"
        )

    )

    return fig


def make_model_chart(forecasts):

    if not forecasts:

        return go.Figure()


    # Use 300-second model scores if available

    forecast = forecasts[-1]

    scores = forecast["model_scores"]

    names = list(scores.keys())

    values = list(scores.values())


    fig = go.Figure(

        data=[
            go.Bar(
                x=names,
                y=values
            )
        ]

    )


    fig.update_layout(

        title="🧠 MODEL POWER MATRIX",

        yaxis_title="BUY ←→ SELL POWER",

        height=350,

        template="plotly_dark",

        yaxis=dict(
            range=[-1, 1]
        )

    )

    return fig


# ==============================================================================
# FORECAST CARD
# ==============================================================================

def render_forecast_card(f):

    signal = f["signal"]

    if signal == "BUY":

        signal_class = "signal-buy"
        signal_emoji = "🟢"

    else:

        signal_class = "signal-sell"
        signal_emoji = "🔴"


    st.subheader(
        f"🎯 {f['horizon']} SECOND FORECAST"
    )


    c1, c2, c3 = st.columns(3)

    c1.metric(
        "UP Probability",
        f"{f['up_probability']:.2f}%"
    )

    c2.metric(
        "DOWN Probability",
        f"{f['down_probability']:.2f}%"
    )

    c3.metric(
        "FLAT Probability",
        f"{f['flat_probability']:.2f}%"
    )


    st.markdown(
        f'<div class="{signal_class}">'
        f'{signal_emoji} {signal}'
        f'</div>',
        unsafe_allow_html=True
    )


    a, b, c = st.columns(3)

    a.metric(
        "Signal Power",
        f"{f['signal_power']:+.4f}"
    )

    b.metric(
        "Model Agreement",
        f"{f['agreement']}/5"
    )

    c.metric(
        "Expected Move",
        f"${f['expected_move']:+.4f}"
    )


    d, e, g = st.columns(3)

    d.metric(
        "Expected Return",
        f"{f['expected_return_pct']:+.4f}%"
    )

    e.metric(
        "Forecast Low",
        f"${f['forecast_low']:,.3f}"
    )

    g.metric(
        "Forecast High",
        f"${f['forecast_high']:,.3f}"
    )


    st.caption(
        f"Market Regime: {f['market_regime']} | "
        f"Volatility: {f['volatility_label']} | "
        f"Data Quality: {f['data_quality']:.1f}%"
    )


    if f["ml_probability"] is not None:

        st.caption(
            f"🤖 ML UP Probability: "
            f"{f['ml_probability']:.2f}%"
        )

    else:

        st.caption(
            "🤖 ML: Waiting for sufficient completed trade history"
        )


# ==============================================================================
# SIDEBAR
# ==============================================================================

with st.sidebar:

    st.title("🎮 CONTROL PANEL")

    auto_refresh = st.toggle(
        "Auto Refresh",
        value=True
    )

    refresh_seconds = st.slider(
        "Refresh Interval (seconds)",
        min_value=5,
        max_value=60,
        value=5,
        step=5
    )

    st.divider()

    st.write("### ⚡ SYSTEM")

    st.write(f"**Mode:** PAPER")

    st.write(f"**Symbol:** {SYMBOL}")

    st.write(f"**Provider:** GOLDAPI")

    st.write(f"**Polling:** {refresh_seconds} sec")


    st.divider()


    if st.button(
        "🔄 REFRESH NOW",
        use_container_width=True
    ):
        st.rerun()


    if st.button(
        "🗑️ CLEAR SESSION DATA",
        use_container_width=True
    ):

        for key in [
            "quotes",
            "forecasts",
            "completed_trades",
            "paper_pnl",
            "wins",
            "losses",
            "ml_model",
            "ml_last_train_count",
            "ml_status",
        ]:

            if key in st.session_state:

                del st.session_state[key]

        st.rerun()


    st.divider()

    st.info(
        "⚠️ The app collects a quote when Streamlit runs. "
        "Polling is not WebSocket streaming."
    )


# ==============================================================================
# AUTO REFRESH
# ==============================================================================

if auto_refresh and AUTOREFRESH_AVAILABLE:

    st_autorefresh(
        interval=refresh_seconds * 1000,
        key="xauusd_live_refresh"
    )


# ==============================================================================
# HEADER
# ==============================================================================

st.markdown(
    '<div class="quant-title">'
    '🥇⚡ XAUUSD QUANT MONEY ARENA V5 🎮'
    '</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="quant-subtitle">'
    'LIVE QUANT SIGNALS • 3 MINUTE • 5 MINUTE • PAPER MONEY GAME'
    '</div>',
    unsafe_allow_html=True
)


# ==============================================================================
# API CHECK
# ==============================================================================

if not GOLDAPI_KEY:

    st.error(
        "❌ GOLDAPI API KEY NOT FOUND"
    )

    st.info(
        """
Add your API key in Streamlit Secrets:

GOLDAPI = "YOUR_API_KEY"
        """
    )

    st.stop()


# ==============================================================================
# FETCH LIVE QUOTE
# ==============================================================================

with st.spinner("⚡ Fetching live XAUUSD quote..."):

    quote = fetch_live_xauusd()


if not quote["success"]:

    st.session_state.provider_errors += 1

    st.error(
        f"❌ LIVE DATA ERROR: {quote['error']}"
    )

    st.caption(
        f"Provider latency: "
        f"{quote.get('latency_ms', 0):.1f} ms"
    )


    # Display previously collected data if available

    df = DataManager.dataframe()

    if df.empty:

        st.stop()

else:

    st.session_state.request_count += 1

    DataManager.add_quote(quote)

    df = DataManager.dataframe()


# ==============================================================================
# COMPLETE OLD PAPER TRADES
# ==============================================================================

current_mid = float(df["mid"].iloc[-1])

new_completed = update_completed_trades(
    current_mid
)


# ==============================================================================
# TRAIN ML
# ==============================================================================

train_ml_model_if_needed()


# ==============================================================================
# CREATE CURRENT FORECASTS
# ==============================================================================

forecasts = create_new_forecasts(df)


# ==============================================================================
# LIVE MARKET METRICS
# ==============================================================================

st.subheader("⚡ LIVE MARKET")


m1, m2, m3, m4, m5 = st.columns(5)


latest = df.iloc[-1]


m1.metric(
    "XAUUSD MID",
    f"${latest['mid']:,.3f}"
)


bid_text = (
    f"${latest['bid']:,.3f}"
    if pd.notna(latest["bid"])
    else "N/A"
)

m2.metric(
    "BID",
    bid_text
)


ask_text = (
    f"${latest['ask']:,.3f}"
    if pd.notna(latest["ask"])
    else "N/A"
)

m3.metric(
    "ASK",
    ask_text
)


spread_text = (
    f"${latest['spread']:,.5f}"
    if pd.notna(latest["spread"])
    else "N/A"
)

m4.metric(
    "SPREAD",
    spread_text
)


m5.metric(
    "LATENCY",
    f"{latest['latency_ms']:.1f} ms"
)


st.divider()


# ==============================================================================
# SIGNAL ARENA
# ==============================================================================

st.subheader("🎯 QUANT SIGNAL ARENA")


left, right = st.columns(2)


with left:

    render_forecast_card(
        forecasts[0]
    )


with right:

    render_forecast_card(
        forecasts[1]
    )


st.divider()


# ==============================================================================
# MODEL POWER MATRIX
# ==============================================================================

st.plotly_chart(
    make_model_chart(forecasts),
    use_container_width=True
)


# ==============================================================================
# LIVE PRICE
# ==============================================================================

st.plotly_chart(
    make_price_chart(df),
    use_container_width=True
)


# ==============================================================================
# PROBABILITY CHART
# ==============================================================================

st.plotly_chart(
    make_probability_chart(forecasts),
    use_container_width=True
)


# ==============================================================================
# PAPER MONEY SCOREBOARD
# ==============================================================================

st.subheader("💰🏆 PAPER MONEY SCOREBOARD")


completed_count = len(
    st.session_state.completed_trades
)


total_decisions = (
    st.session_state.wins
    + st.session_state.losses
)


win_rate = (
    st.session_state.wins
    / total_decisions
    * 100
    if total_decisions > 0
    else 0.0
)


s1, s2, s3, s4 = st.columns(4)


s1.metric(
    "🏆 Completed Trades",
    completed_count
)


s2.metric(
    "🟢 Wins",
    st.session_state.wins
)


s3.metric(
    "🎯 Win Rate",
    f"{win_rate:.2f}%"
)


s4.metric(
    "💰 Paper P&L",
    f"${st.session_state.paper_pnl:+.3f}"
)


# ==============================================================================
# LAST 10 COMPLETED TRADES
# ==============================================================================

st.subheader(
    "🏆 LAST 10 COMPLETED 5-MINUTE PAPER TRADES"
)


if not st.session_state.completed_trades:

    st.info(
        "🎮 No completed 5-minute paper trades yet. "
        "A 300-second forecast completes after approximately 300 seconds "
        "when a later quote is observed."
    )

else:

    # Only 300-second trades

    five_minute_trades = [

        t
        for t in st.session_state.completed_trades

        if t["horizon"] == 300

    ]


    if not five_minute_trades:

        st.info(
            "No completed 300-second trades yet."
        )

    else:

        rows = []

        for trade in five_minute_trades[-10:][::-1]:

            rows.append({

                "Time": (
                    pd.Timestamp(
                        trade["timestamp"]
                    ).strftime("%H:%M:%S")
                ),

                "Signal": trade["signal"],

                "Entry": round(
                    trade["entry_price"],
                    3
                ),

                "Exit": round(
                    trade["exit_price"],
                    3
                ),

                "P&L": round(
                    trade["pnl"],
                    4
                ),

                "Result": (
                    "WIN"
                    if trade["pnl"] > 0
                    else (
                        "LOSS"
                        if trade["pnl"] < 0
                        else "FLAT"
                    )
                ),

            })


        history_df = pd.DataFrame(rows)

        st.dataframe(
            history_df,
            use_container_width=True,
            hide_index=True
        )


# ==============================================================================
# LIVE DATA HISTORY
# ==============================================================================

with st.expander(
    "📊 VIEW LIVE QUOTE HISTORY",
    expanded=False
):

    if not df.empty:

        display_df = df.copy()

        display_df["timestamp"] = (
            display_df["timestamp"]
            .dt.strftime("%Y-%m-%d %H:%M:%S UTC")
        )

        st.dataframe(
            display_df.tail(100),
            use_container_width=True,
            hide_index=True
        )


# ==============================================================================
# MODEL DETAILS
# ==============================================================================

with st.expander(
    "🧠 MODEL POWER DETAILS",
    expanded=False
):

    score_rows = []

    for name, value in forecasts[-1]["model_scores"].items():

        score_rows.append({

            "Model": name,

            "Score": round(value, 6),

            "Direction": (
                "BUY"
                if value > 0
                else (
                    "SELL"
                    if value < 0
                    else "NEUTRAL"
                )
            )

        })


    st.dataframe(
        pd.DataFrame(score_rows),
        use_container_width=True,
        hide_index=True
    )


# ==============================================================================
# SYSTEM STATUS
# ==============================================================================

st.subheader("⚙️ SYSTEM STATUS")


status_text = f"""
🟢 **QUANT MONEY ENGINE ONLINE**

**Version:** {APP_VERSION}

**Provider:** GOLDAPI

**Instrument:** {INSTRUMENT}

**Quotes Collected:** {len(df)}

**Active Paper Forecasts:** {len(st.session_state.forecasts)}

**Completed Trades:** {len(st.session_state.completed_trades)}

**ML Status:** {st.session_state.ml_status}

**Provider Requests:** {st.session_state.request_count}

**Provider Errors:** {st.session_state.provider_errors}

⚠️ **PAPER / RESEARCH ONLY**

BUY and SELL are model directions.

Probabilities are model probability estimates.

No guaranteed profit claims.
"""

st.success(status_text)


# ==============================================================================
# FOOTER
# ==============================================================================

st.caption(
    f"🥇 XAUUSD Quant Money Arena V5 FIXED | "
    f"Last Update: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')} "
    f"| Polling Interval: {refresh_seconds} sec"
)
