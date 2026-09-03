# ==============================================================================
# 🥇 XAUUSD QUANT MONEY ARENA V5
# LIVE MARKET DATA ENGINE
# GoldAPI -> Yahoo Finance fallback -> Cached quote
# ==============================================================================

import os
import time
from datetime import datetime, timezone

import requests
import streamlit as st


# ==============================================================================
# APP CONFIG
# ==============================================================================

st.set_page_config(
    page_title="XAUUSD Quant Money Arena V5",
    page_icon="🥇",
    layout="wide",
)

GOLDAPI_BASE_URL = "https://www.goldapi.io/api/price"
YAHOO_XAUUSD_URL = "https://query1.finance.yahoo.com/v8/finance/chart/XAUUSD=X"

REQUEST_TIMEOUT = 15
CACHE_SECONDS = 30.0

# If GoldAPI returns quota/auth errors, do not keep wasting requests on every rerun.
GOLDAPI_COOLDOWN_SECONDS = 6 * 60 * 60


# ==============================================================================
# SECRETS
# ==============================================================================

def get_secret(*names):
    for name in names:
        try:
            value = st.secrets.get(name)
            if value:
                return str(value).strip().strip('"').strip("'")
        except Exception:
            pass

        value = os.getenv(name)
        if value:
            return str(value).strip().strip('"').strip("'")

    return None


# ==============================================================================
# SESSION STATE
# ==============================================================================

def init_state():
    defaults = {
        "last_quote": None,
        "last_error": None,
        "last_provider": None,
        "last_goldapi_status": None,
        "goldapi_blocked_until": 0.0,
        "goldapi_block_reason": None,
        "total_requests": 0,
        "successful_requests": 0,
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


init_state()


# ==============================================================================
# HELPERS
# ==============================================================================

def safe_float(value, default=None):
    try:
        if value is None:
            return default
        return float(value)
    except (ValueError, TypeError):
        return default


def make_quote(provider, price, bid=None, ask=None, latency_ms=None, raw=None):
    now = datetime.now(timezone.utc)

    return {
        "provider": provider,
        "symbol": "XAU/USD",
        "price": float(price),
        "mid": float(price),
        "bid": bid,
        "ask": ask,
        "spread": (
            float(ask) - float(bid)
            if bid is not None and ask is not None
            else None
        ),
        "received_at": now.isoformat(),
        "received_epoch": time.time(),
        "latency_ms": latency_ms,
        "cached": False,
        "raw": raw or {},
    }


# ==============================================================================
# GOLDAPI
# ==============================================================================

def fetch_goldapi():
    api_key = get_secret("GOLDAPI", "GOLDAPI_KEY")

    if not api_key:
        return None, "GoldAPI key not configured"

    now = time.time()

    blocked_until = st.session_state.get("goldapi_blocked_until", 0.0)

    if now < blocked_until:
        remaining = int(blocked_until - now)
        reason = st.session_state.get(
            "goldapi_block_reason",
            "GoldAPI temporarily disabled",
        )

        return None, (
            f"{reason}. GoldAPI retry paused for "
            f"{remaining // 60}m {remaining % 60}s"
        )

    start = time.perf_counter()

    try:
        response = requests.get(
            f"{GOLDAPI_BASE_URL}/XAU/USD",
            headers={
                "x-access-token": api_key,
                "Accept": "application/json",
                "User-Agent": "XAUUSD-Quant-Money-Arena-V5",
            },
            timeout=REQUEST_TIMEOUT,
        )

        latency = round((time.perf_counter() - start) * 1000, 2)

        st.session_state["last_goldapi_status"] = response.status_code

        if response.status_code != 200:
            try:
                body = response.json()
            except Exception:
                body = response.text[:500]

            error = f"GoldAPI HTTP {response.status_code}: {body}"

            # These errors should not be retried continuously.
            if response.status_code in (401, 403, 429):
                st.session_state["goldapi_blocked_until"] = (
                    time.time() + GOLDAPI_COOLDOWN_SECONDS
                )
                st.session_state["goldapi_block_reason"] = (
                    f"GoldAPI HTTP {response.status_code}"
                )

            return None, error

        data = response.json()

        price = safe_float(data.get("price"))
        bid = safe_float(data.get("bid"))
        ask = safe_float(data.get("ask"))

        if price is None:
            return None, f"GoldAPI returned no valid price: {data}"

        # Successful response removes cooldown.
        st.session_state["goldapi_blocked_until"] = 0.0
        st.session_state["goldapi_block_reason"] = None

        return (
            make_quote(
                "GoldAPI",
                price,
                bid,
                ask,
                latency,
                data,
            ),
            None,
        )

    except requests.RequestException as error:
        return None, f"GoldAPI request error: {error}"


# ==============================================================================
# YAHOO FINANCE FALLBACK
# ==============================================================================

def fetch_yahoo_xauusd():
    start = time.perf_counter()

    try:
        response = requests.get(
            YAHOO_XAUUSD_URL,
            params={
                "range": "1d",
                "interval": "1m",
                "includePrePost": "false",
            },
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/120 Safari/537.36"
                ),
                "Accept": "application/json",
            },
            timeout=REQUEST_TIMEOUT,
        )

        latency = round((time.perf_counter() - start) * 1000, 2)

        if response.status_code != 200:
            return None, f"Yahoo Finance HTTP {response.status_code}"

        payload = response.json()

        chart = payload.get("chart", {})

        if chart.get("error"):
            return None, f"Yahoo Finance error: {chart['error']}"

        results = chart.get("result") or []

        if not results:
            return None, "Yahoo Finance returned no chart result"

        result = results[0]

        meta = result.get("meta") or {}

        # Yahoo's regularMarketPrice is the newest quote.
        price = safe_float(meta.get("regularMarketPrice"))

        if price is None:
            quote_data = (result.get("indicators") or {}).get("quote") or []

            if quote_data:
                closes = quote_data[0].get("close") or []
                valid_prices = [
                    safe_float(value)
                    for value in closes
                    if safe_float(value) is not None
                ]

                if valid_prices:
                    price = valid_prices[-1]

        if price is None:
            return None, "Yahoo Finance returned no valid XAU/USD price"

        return (
            make_quote(
                "Yahoo Finance Fallback",
                price,
                latency_ms=latency,
                raw={
                    "symbol": meta.get("symbol"),
                    "currency": meta.get("currency"),
                    "exchangeName": meta.get("exchangeName"),
                    "marketState": meta.get("marketState"),
                    "regularMarketTime": meta.get("regularMarketTime"),
                },
            ),
            None,
        )

    except requests.RequestException as error:
        return None, f"Yahoo Finance request error: {error}"

    except Exception as error:
        return None, f"Yahoo Finance parse error: {type(error).__name__}: {error}"


# ==============================================================================
# MASTER FETCH
# ==============================================================================

def fetch_live_xauusd(force=False):
    init_state()

    now = time.time()
    cached = st.session_state.get("last_quote")

    # Use short cache to avoid excessive provider requests.
    if (
        not force
        and cached is not None
        and now - cached.get("received_epoch", 0) < CACHE_SECONDS
    ):
        cached_quote = dict(cached)
        cached_quote["cached"] = True
        cached_quote["cache_age_seconds"] = round(
            now - cached_quote["received_epoch"],
            1,
        )

        return {
            "success": True,
            "quote": cached_quote,
            "error": None,
            "warning": None,
            "cached": True,
        }

    st.session_state["total_requests"] += 1

    # --------------------------------------------------------------------------
    # PRIMARY: GOLDAPI
    # --------------------------------------------------------------------------

    quote, goldapi_error = fetch_goldapi()

    if quote is not None:
        st.session_state["last_quote"] = quote
        st.session_state["last_provider"] = quote["provider"]
        st.session_state["last_error"] = None
        st.session_state["successful_requests"] += 1

        return {
            "success": True,
            "quote": quote,
            "error": None,
            "warning": None,
            "cached": False,
        }

    # --------------------------------------------------------------------------
    # FALLBACK: YAHOO FINANCE
    # --------------------------------------------------------------------------

    quote, yahoo_error = fetch_yahoo_xauusd()

    if quote is not None:
        st.session_state["last_quote"] = quote
        st.session_state["last_provider"] = quote["provider"]
        st.session_state["last_error"] = None
        st.session_state["successful_requests"] += 1

        return {
            "success": True,
            "quote": quote,
            "error": None,
            "warning": (
                "GoldAPI is unavailable. "
                "Yahoo Finance fallback is currently being used."
            ),
            "cached": False,
        }

    # --------------------------------------------------------------------------
    # LAST RESORT: CACHE
    # --------------------------------------------------------------------------

    combined_error = " | ".join(
        error
        for error in (goldapi_error, yahoo_error)
        if error
    )

    st.session_state["last_error"] = combined_error

    if cached is not None:
        cached_quote = dict(cached)
        cached_quote["cached"] = True
        cached_quote["cache_age_seconds"] = round(
            now - cached_quote.get("received_epoch", now),
            1,
        )

        return {
            "success": False,
            "quote": cached_quote,
            "error": combined_error,
            "warning": "Both live providers failed. Using cached data.",
            "cached": True,
        }

    return {
        "success": False,
        "quote": None,
        "error": combined_error or "No market data provider available",
        "warning": None,
        "cached": False,
    }


# Compatibility with your previous code.
def get_live_xauusd_quote():
    return fetch_live_xauusd()


# ==============================================================================
# UI
# ==============================================================================

def money(value):
    if value is None:
        return "—"
    return f"${float(value):,.3f}"


def main():
    st.title("🥇 XAUUSD QUANT MONEY ARENA V5")
    st.caption("GoldAPI → Yahoo Finance fallback → cached quote")

    refresh = st.button("🔄 Refresh Price")

    with st.spinner("Loading XAU/USD market data..."):
        result = fetch_live_xauusd(force=refresh)

    quote = result.get("quote")

    if quote is not None:

        if quote.get("cached"):
            st.warning(
                f"📦 Cached data • {quote.get('cache_age_seconds', 0)} sec old"
            )

        elif quote["provider"] == "GoldAPI":
            st.success("🟢 Live GoldAPI XAU/USD connected")

        else:
            st.warning("🟡 Live Yahoo Finance fallback is active")

        if result.get("warning"):
            st.caption(result["warning"])

        col1, col2, col3, col4 = st.columns(4)

        col1.metric("XAU/USD", money(quote.get("price")))
        col2.metric("Provider", quote.get("provider"))
        col3.metric("Bid", money(quote.get("bid")))
        col4.metric("Ask", money(quote.get("ask")))

        latency = quote.get("latency_ms")

        if latency is not None:
            st.caption(f"Provider latency: {latency:.0f} ms")

        with st.expander("📊 Debug / Raw Data"):
            st.json(quote)

    else:
        st.error("🔴 No market data available")
        st.code(result.get("error") or "Unknown provider error")

    st.divider()
    st.subheader("🔐 Provider Status")

    api_key = get_secret("GOLDAPI", "GOLDAPI_KEY")

    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        "GoldAPI Key",
        "Detected" if api_key else "Not configured",
    )

    col2.metric(
        "Last Provider",
        st.session_state.get("last_provider") or "—",
    )

    col3.metric(
        "GoldAPI HTTP Status",
        st.session_state.get("last_goldapi_status") or "—",
    )

    total = st.session_state.get("total_requests", 0)
    successful = st.session_state.get("successful_requests", 0)

    success_rate = (successful / total * 100) if total else 0.0

    col4.metric("Success Rate", f"{success_rate:.1f}%")

    blocked_until = st.session_state.get("goldapi_blocked_until", 0.0)

    if blocked_until > time.time():
        remaining = int(blocked_until - time.time())

        st.info(
            "GoldAPI cooldown active because the provider returned "
            "an access/quota error. "
            f"Next GoldAPI retry in approximately "
            f"{remaining // 60} minutes."
        )

    st.caption(
        "Yahoo Finance is a fallback feed and may differ from broker "
        "execution prices. For automated trading, use your broker's official feed."
    )


if __name__ == "__main__":
    main()
