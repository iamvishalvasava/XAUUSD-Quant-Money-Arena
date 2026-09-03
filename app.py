# ==============================================================================
# 🥇 XAUUSD QUANT MONEY ARENA V5
# 🔐 GOLDAPI CONNECTION ENGINE — CLEAN FINAL VERSION
# ==============================================================================

import os
import time
from datetime import datetime, timezone

import requests
import streamlit as st


# ==============================================================================
# ⚙️ GOLDAPI CONFIGURATION
# ==============================================================================

GOLDAPI_BASE_URL = "https://www.goldapi.io/api/price"

GOLDAPI_METAL = "XAU"
GOLDAPI_CURRENCY = "USD"

REQUEST_TIMEOUT = 15
MAX_RETRIES = 2
RETRY_DELAY = 2.0

# Prevent excessive requests caused by Streamlit reruns
MIN_REQUEST_INTERVAL = 5.0


# ==============================================================================
# 🔐 LOAD GOLDAPI API KEY
# ==============================================================================

def get_goldapi_key():

    api_key = None

    # --------------------------------------------------------------------------
    # STREAMLIT SECRETS
    # --------------------------------------------------------------------------

    try:

        if "GOLDAPI" in st.secrets:
            api_key = st.secrets["GOLDAPI"]

        elif "GOLDAPI_KEY" in st.secrets:
            api_key = st.secrets["GOLDAPI_KEY"]

    except Exception:
        pass

    # --------------------------------------------------------------------------
    # ENVIRONMENT VARIABLES
    # --------------------------------------------------------------------------

    if not api_key:
        api_key = os.getenv("GOLDAPI")

    if not api_key:
        api_key = os.getenv("GOLDAPI_KEY")

    # --------------------------------------------------------------------------
    # CLEAN KEY
    # --------------------------------------------------------------------------

    if api_key:

        api_key = str(api_key).strip()

        api_key = api_key.strip('"')
        api_key = api_key.strip("'")

        if len(api_key) == 0:
            return None

    return api_key


# ==============================================================================
# 🧠 INITIALIZE SESSION STATE
# ==============================================================================

def initialize_goldapi_state():

    defaults = {

        "goldapi_last_quote": None,
        "goldapi_last_success_time": None,
        "goldapi_last_request_time": 0.0,

        "goldapi_last_error": None,

        "goldapi_consecutive_errors": 0,

        "goldapi_total_requests": 0,
        "goldapi_successful_requests": 0,

        "goldapi_last_latency_ms": None,
        "goldapi_last_status_code": None,

    }

    for key, value in defaults.items():

        if key not in st.session_state:

            st.session_state[key] = value


# Initialize immediately
initialize_goldapi_state()


# ==============================================================================
# 🌐 BUILD API URL
# ==============================================================================

def get_goldapi_url():

    return (
        f"{GOLDAPI_BASE_URL}/"
        f"{GOLDAPI_METAL}/"
        f"{GOLDAPI_CURRENCY}"
    )


# ==============================================================================
# 🌐 BUILD REQUEST HEADERS
# ==============================================================================

def build_goldapi_headers(api_key):

    return {

        "x-access-token": api_key,

        "Content-Type": "application/json",

        "Accept": "application/json",

        "User-Agent": "XAUUSD-Quant-Money-Arena-V5/1.0"

    }


# ==============================================================================
# 🔢 SAFE FLOAT
# ==============================================================================

def safe_float(value, default=None):

    try:

        if value is None:
            return default

        return float(value)

    except (ValueError, TypeError):

        return default


# ==============================================================================
# 📊 PARSE GOLDAPI RESPONSE
# ==============================================================================

def parse_goldapi_quote(data, latency_ms):

    if not isinstance(data, dict):

        raise ValueError(
            "GoldAPI returned invalid JSON data"
        )

    price = safe_float(data.get("price"))

    bid = safe_float(data.get("bid"))

    ask = safe_float(data.get("ask"))

    if price is None:

        raise ValueError(

            "GoldAPI response does not contain a valid price. "
            f"Available fields: {list(data.keys())}"

        )

    spread = None

    if bid is not None and ask is not None:

        spread = ask - bid

    now_utc = datetime.now(timezone.utc)

    quote = {

        "provider": "GoldAPI",

        "instrument": "XAUUSD",

        "symbol": "XAU/USD",

        "price": price,

        "mid": price,

        "bid": bid,

        "ask": ask,

        "spread": spread,

        "provider_timestamp": data.get("timestamp"),

        "provider_datetime": data.get("datetime"),

        "received_at": now_utc.isoformat(),

        "received_epoch": time.time(),

        "latency_ms": round(latency_ms, 2),

        "cached": False,

        "raw": data

    }

    return quote


# ==============================================================================
# ❌ FORMAT PROVIDER ERROR
# ==============================================================================

def get_goldapi_error_message(response):

    status = response.status_code

    try:

        body = response.json()

    except Exception:

        body = response.text

    body_text = str(body)

    # Limit huge HTML error pages
    if len(body_text) > 1000:
        body_text = body_text[:1000] + "..."

    if status == 400:

        return (
            f"❌ GoldAPI HTTP 400 — BAD REQUEST\n\n"
            f"Endpoint:\n{get_goldapi_url()}\n\n"
            f"Provider response:\n{body_text}"
        )

    if status == 401:

        return (
            "❌ GoldAPI HTTP 401 — UNAUTHORIZED\n\n"
            "The API key was rejected.\n\n"
            "Check your Streamlit Secret name and GoldAPI key.\n\n"
            f"Provider response:\n{body_text}"
        )

    if status == 403:

        return (
            "❌ GoldAPI HTTP 403 — ACCESS FORBIDDEN\n\n"
            "The request reached GoldAPI, but access was denied.\n\n"
            "Possible reasons:\n"
            "• Invalid API key\n"
            "• Expired or revoked API key\n"
            "• Account/plan restriction\n"
            "• API quota exhausted\n\n"
            f"Provider response:\n{body_text}"
        )

    if status == 429:

        return (
            "⚠️ GoldAPI HTTP 429 — RATE LIMIT REACHED\n\n"
            "Too many requests were sent.\n\n"
            f"Provider response:\n{body_text}"
        )

    if status >= 500:

        return (
            f"⚠️ GoldAPI HTTP {status} — PROVIDER SERVER ERROR\n\n"
            f"Provider response:\n{body_text}"
        )

    return (

        f"❌ GoldAPI HTTP {status}\n\n"

        f"Provider response:\n{body_text}"

    )


# ==============================================================================
# 🥇 FETCH LIVE XAU/USD
# ==============================================================================

def fetch_goldapi_xauusd():

    initialize_goldapi_state()

    # --------------------------------------------------------------------------
    # GET API KEY
    # --------------------------------------------------------------------------

    api_key = get_goldapi_key()

    if not api_key:

        error = (

            "❌ GOLDAPI API KEY NOT FOUND\n\n"

            "Add this in Streamlit Secrets:\n\n"

            'GOLDAPI = "YOUR_REAL_API_KEY"'

        )

        st.session_state["goldapi_last_error"] = error

        return {

            "success": False,

            "quote": None,

            "error": error,

            "using_cached_quote": False

        }

    # --------------------------------------------------------------------------
    # CACHE / RATE PROTECTION
    # --------------------------------------------------------------------------

    now = time.time()

    last_request = st.session_state.get(
        "goldapi_last_request_time",
        0.0
    )

    elapsed = now - last_request

    if elapsed < MIN_REQUEST_INTERVAL:

        cached = st.session_state.get(
            "goldapi_last_quote"
        )

        if cached is not None:

            cached_quote = dict(cached)

            cached_quote["cached"] = True

            cached_quote["cache_age_seconds"] = round(

                time.time()
                - cached_quote.get(
                    "received_epoch",
                    time.time()
                ),

                1

            )

            return {

                "success": True,

                "quote": cached_quote,

                "error": None,

                "using_cached_quote": True

            }

    # --------------------------------------------------------------------------
    # BUILD REQUEST
    # --------------------------------------------------------------------------

    url = get_goldapi_url()

    headers = build_goldapi_headers(api_key)

    # --------------------------------------------------------------------------
    # RECORD REQUEST
    # --------------------------------------------------------------------------

    st.session_state[
        "goldapi_last_request_time"
    ] = time.time()

    st.session_state[
        "goldapi_total_requests"
    ] += 1

    last_error = None

    # ==========================================================================
    # 🔄 REQUEST LOOP
    # ==========================================================================

    for attempt in range(1, MAX_RETRIES + 1):

        try:

            request_start = time.perf_counter()

            response = requests.get(

                url,

                headers=headers,

                timeout=REQUEST_TIMEOUT

            )

            latency_ms = (

                time.perf_counter()
                - request_start

            ) * 1000

            # ------------------------------------------------------------------
            # SAVE DEBUG INFO
            # ------------------------------------------------------------------

            st.session_state[
                "goldapi_last_latency_ms"
            ] = round(latency_ms, 2)

            st.session_state[
                "goldapi_last_status_code"
            ] = response.status_code

            # ==================================================================
            # SUCCESS
            # ==================================================================

            if response.status_code == 200:

                data = response.json()

                quote = parse_goldapi_quote(

                    data,

                    latency_ms

                )

                # --------------------------------------------------------------
                # SAVE SUCCESS
                # --------------------------------------------------------------

                st.session_state[
                    "goldapi_last_quote"
                ] = quote

                st.session_state[
                    "goldapi_last_success_time"
                ] = time.time()

                st.session_state[
                    "goldapi_last_error"
                ] = None

                st.session_state[
                    "goldapi_consecutive_errors"
                ] = 0

                st.session_state[
                    "goldapi_successful_requests"
                ] += 1

                return {

                    "success": True,

                    "quote": quote,

                    "error": None,

                    "using_cached_quote": False

                }

            # ==================================================================
            # HTTP ERROR
            # ==================================================================

            last_error = get_goldapi_error_message(
                response
            )

            # Never retry authentication/access errors
            if response.status_code in (
                400,
                401,
                403
            ):

                break

            # Rate limit
            if response.status_code == 429:

                if attempt < MAX_RETRIES:

                    retry_after = response.headers.get(
                        "Retry-After"
                    )

                    try:

                        wait_time = float(retry_after)

                    except Exception:

                        wait_time = RETRY_DELAY * attempt

                    time.sleep(wait_time)

                    continue

                break

            # Server errors
            if response.status_code >= 500:

                if attempt < MAX_RETRIES:

                    time.sleep(
                        RETRY_DELAY * attempt
                    )

                    continue

                break

            break

        except requests.exceptions.Timeout:

            last_error = (

                f"❌ GoldAPI request timed out after "
                f"{REQUEST_TIMEOUT} seconds."

            )

        except requests.exceptions.ConnectionError as e:

            last_error = (

                f"❌ GoldAPI connection error:\n{e}"

            )

        except requests.exceptions.RequestException as e:

            last_error = (

                f"❌ GoldAPI request error:\n{e}"

            )

        except Exception as e:

            last_error = (

                f"❌ Unexpected GoldAPI error:\n"
                f"{type(e).__name__}: {e}"

            )

        if attempt < MAX_RETRIES:

            time.sleep(
                RETRY_DELAY * attempt
            )

    # ==========================================================================
    # ALL REQUESTS FAILED
    # ==========================================================================

    st.session_state[
        "goldapi_last_error"
    ] = last_error

    st.session_state[
        "goldapi_consecutive_errors"
    ] += 1

    # --------------------------------------------------------------------------
    # USE CACHED DATA
    # --------------------------------------------------------------------------

    cached = st.session_state.get(
        "goldapi_last_quote"
    )

    if cached is not None:

        cached_quote = dict(cached)

        cached_quote["cached"] = True

        cached_quote["cache_age_seconds"] = round(

            time.time()
            - cached_quote.get(
                "received_epoch",
                time.time()
            ),

            1

        )

        return {

            "success": False,

            "quote": cached_quote,

            "error": last_error,

            "using_cached_quote": True

        }

    # --------------------------------------------------------------------------
    # NO DATA
    # --------------------------------------------------------------------------

    return {

        "success": False,

        "quote": None,

        "error": last_error,

        "using_cached_quote": False

    }


# ==============================================================================
# 🎯 COMPATIBILITY FUNCTION
# ==============================================================================

def get_live_xauusd_quote():

    return fetch_goldapi_xauusd()


# ==============================================================================
# 📊 GOLDAPI STATUS
# ==============================================================================

def get_goldapi_status():

    initialize_goldapi_state()

    api_key = get_goldapi_key()

    total = st.session_state.get(
        "goldapi_total_requests",
        0
    )

    successful = st.session_state.get(
        "goldapi_successful_requests",
        0
    )

    success_rate = 0.0

    if total > 0:

        success_rate = round(

            (successful / total) * 100,

            2

        )

    return {

        "provider": "GoldAPI",

        "api_key_configured": bool(api_key),

        "api_key_length":
            len(api_key) if api_key else 0,

        "endpoint": get_goldapi_url(),

        "total_requests": total,

        "successful_requests": successful,

        "success_rate": success_rate,

        "consecutive_errors":
            st.session_state.get(
                "goldapi_consecutive_errors",
                0
            ),

        "last_error":
            st.session_state.get(
                "goldapi_last_error"
            ),

        "last_latency_ms":
            st.session_state.get(
                "goldapi_last_latency_ms"
            ),

        "last_status_code":
            st.session_state.get(
                "goldapi_last_status_code"
            )

    }


# ==============================================================================
# 🖥️ DISPLAY GOLDAPI STATUS
# ==============================================================================

def show_goldapi_connection_status():

    status = get_goldapi_status()

    st.subheader("🔐 GoldAPI Connection Status")

    if status["api_key_configured"]:

        st.success(
            "🟢 GoldAPI API Key Detected"
        )

    else:

        st.error(
            "🔴 GoldAPI API Key Not Found"
        )

    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        "Provider",
        status["provider"]
    )

    col2.metric(
        "HTTP Status",
        status["last_status_code"]
        if status["last_status_code"] is not None
        else "—"
    )

    col3.metric(
        "Latency",
        f"{status['last_latency_ms']} ms"
        if status["last_latency_ms"] is not None
        else "—"
    )

    col4.metric(
        "Success Rate",
        f"{status['success_rate']}%"
    )

    with st.expander("🔍 GoldAPI Debug Information"):

        st.code(
            status["endpoint"]
        )

        st.write(
            "API Key Detected:",
            status["api_key_configured"]
        )

        st.write(
            "API Key Length:",
            status["api_key_length"]
        )

        st.write(
            "Total Requests:",
            status["total_requests"]
        )

        st.write(
            "Successful Requests:",
            status["successful_requests"]
        )

    if status["last_error"]:

        st.warning(
            status["last_error"]
        )


# ==============================================================================
# 🧪 TEST CONNECTION
# ==============================================================================

def test_goldapi_connection():

    result = fetch_goldapi_xauusd()

    if result["success"]:

        quote = result["quote"]

        return {

            "connected": True,

            "message": (
                f"🟢 GoldAPI Connected | "
                f"XAU/USD: ${quote['price']:,.3f}"
            ),

            "quote": quote

        }

    return {

        "connected": False,

        "message": (
            result.get("error")
            or "Unknown GoldAPI error"
        ),

        "quote": result.get("quote")

    }


# ==============================================================================
# 🚀 END GOLDAPI CONNECTION ENGINE
# ==============================================================================
