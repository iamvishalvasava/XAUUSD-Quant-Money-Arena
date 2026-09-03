# ==============================================================================
# 🥇 XAUUSD QUANT MONEY ARENA V5
# 🔐 GOLDAPI CONNECTION ENGINE — FIXED VERSION
# ==============================================================================

import os
import time
import requests
import streamlit as st
from datetime import datetime, timezone


# ==============================================================================
# ⚙️ GOLDAPI CONFIGURATION
# ==============================================================================

GOLDAPI_BASE_URL = "https://www.goldapi.io/api"
GOLDAPI_SYMBOL = "XAU/USD"

REQUEST_TIMEOUT = 12
MAX_RETRIES = 3
RETRY_DELAY = 2.0

# 5-second polling is fine, but avoid accidentally hammering the API
MIN_REQUEST_INTERVAL = 4.0


# ==============================================================================
# 🔐 LOAD GOLDAPI API KEY
# ==============================================================================

def get_goldapi_key():
    """
    Load GoldAPI key safely.

    Priority:
        1. Streamlit Cloud Secrets
        2. Environment Variable

    Expected Streamlit secret:

        GOLDAPI = "YOUR_API_KEY"
    """

    api_key = None

    # --------------------------------------------------------------------------
    # 1️⃣ STREAMLIT SECRETS
    # --------------------------------------------------------------------------

    try:

        if "GOLDAPI" in st.secrets:
            api_key = st.secrets["GOLDAPI"]

        # Optional alternative name
        elif "GOLDAPI_KEY" in st.secrets:
            api_key = st.secrets["GOLDAPI_KEY"]

    except Exception:
        pass


    # --------------------------------------------------------------------------
    # 2️⃣ ENVIRONMENT VARIABLE FALLBACK
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

        # Remove accidental surrounding quotes
        api_key = api_key.strip('"')
        api_key = api_key.strip("'")

    return api_key


# ==============================================================================
# 🔑 GLOBAL API KEY
# ==============================================================================

GOLDAPI_KEY = get_goldapi_key()


# ==============================================================================
# 🧠 SESSION STATE INITIALIZATION
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

    }

    for key, value in defaults.items():

        if key not in st.session_state:

            st.session_state[key] = value


initialize_goldapi_state()


# ==============================================================================
# 🌐 BUILD REQUEST HEADERS
# ==============================================================================

def build_goldapi_headers():

    return {

        # GoldAPI authentication header
        "x-access-token": GOLDAPI_KEY,

        # Request JSON
        "Accept": "application/json",

        # Helpful user agent
        "User-Agent": "XAUUSD-Quant-Money-Arena-V5/1.0"

    }


# ==============================================================================
# 🔎 SAFE NUMBER CONVERTER
# ==============================================================================

def safe_float(value, default=None):

    try:

        if value is None:
            return default

        return float(value)

    except Exception:

        return default


# ==============================================================================
# 🧾 PARSE GOLDAPI RESPONSE
# ==============================================================================

def parse_goldapi_quote(data, latency_ms):

    """
    Converts GoldAPI response into a standard XAUUSD quote format.
    """

    if not isinstance(data, dict):

        raise ValueError("GoldAPI returned invalid JSON data")


    # --------------------------------------------------------------------------
    # GOLDAPI PRICE FIELDS
    # --------------------------------------------------------------------------

    price = safe_float(data.get("price"))

    bid = safe_float(data.get("bid"))

    ask = safe_float(data.get("ask"))


    # --------------------------------------------------------------------------
    # VALIDATE PRICE
    # --------------------------------------------------------------------------

    if price is None:

        raise ValueError(
            f"GoldAPI response does not contain a valid price. "
            f"Received keys: {list(data.keys())}"
        )


    # --------------------------------------------------------------------------
    # BID / ASK FALLBACK LOGIC
    #
    # IMPORTANT:
    # We do NOT invent fake Bid/Ask prices.
    #
    # If provider does not return them:
    # bid = None
    # ask = None
    # spread = None
    # --------------------------------------------------------------------------

    spread = None

    if bid is not None and ask is not None:

        spread = ask - bid


    # --------------------------------------------------------------------------
    # TIMESTAMP
    # --------------------------------------------------------------------------

    provider_timestamp = data.get("timestamp")

    now_utc = datetime.now(timezone.utc)


    # --------------------------------------------------------------------------
    # STANDARDIZED QUOTE
    # --------------------------------------------------------------------------

    quote = {

        "provider": "GOLDAPI",

        "instrument": "SPOT_XAUUSD",

        "symbol": "XAU/USD",

        "price": price,

        "mid": price,

        "bid": bid,

        "ask": ask,

        "spread": spread,

        "provider_timestamp": provider_timestamp,

        "received_at": now_utc.isoformat(),

        "received_epoch": time.time(),

        "latency_ms": round(latency_ms, 2),

        "raw": data

    }


    return quote


# ==============================================================================
# 🛡️ GOLDAPI ERROR MESSAGE
# ==============================================================================

def get_goldapi_error_message(response):

    status = response.status_code

    try:

        body = response.json()

    except Exception:

        body = response.text


    # --------------------------------------------------------------------------
    # HTTP 403
    # --------------------------------------------------------------------------

    if status == 403:

        return (
            "GoldAPI HTTP 403 — ACCESS FORBIDDEN.\n\n"
            "Possible causes:\n"
            "• API key is invalid\n"
            "• API key has expired or was revoked\n"
            "• API key is not correctly saved in Streamlit Secrets\n"
            "• Your GoldAPI plan does not allow this request\n"
            "• Provider blocked the request\n\n"
            f"Provider response: {body}"
        )


    # --------------------------------------------------------------------------
    # HTTP 401
    # --------------------------------------------------------------------------

    if status == 401:

        return (
            "GoldAPI HTTP 401 — UNAUTHORIZED.\n\n"
            "Check your GOLDAPI secret and make sure the API key is valid.\n\n"
            f"Provider response: {body}"
        )


    # --------------------------------------------------------------------------
    # HTTP 429
    # --------------------------------------------------------------------------

    if status == 429:

        return (
            "GoldAPI HTTP 429 — TOO MANY REQUESTS.\n\n"
            "The API rate limit has been reached.\n"
            "Wait before making the next request.\n\n"
            f"Provider response: {body}"
        )


    # --------------------------------------------------------------------------
    # HTTP 5XX
    # --------------------------------------------------------------------------

    if status >= 500:

        return (
            f"GoldAPI HTTP {status} — PROVIDER SERVER ERROR.\n\n"
            "GoldAPI server may be temporarily unavailable.\n\n"
            f"Provider response: {body}"
        )


    # --------------------------------------------------------------------------
    # OTHER ERROR
    # --------------------------------------------------------------------------

    return (

        f"GoldAPI HTTP {status}\n\n"
        f"Provider response: {body}"

    )


# ==============================================================================
# 🥇 FETCH LIVE XAUUSD QUOTE
# ==============================================================================

def fetch_goldapi_xauusd():

    """
    Fetch real XAU/USD spot quote from GoldAPI.

    Returns:
        {
            "success": True/False,
            "quote": dict or None,
            "error": str or None,
            "using_cached_quote": bool
        }
    """


    # --------------------------------------------------------------------------
    # INITIALIZE STATE
    # --------------------------------------------------------------------------

    initialize_goldapi_state()


    # --------------------------------------------------------------------------
    # CHECK API KEY
    # --------------------------------------------------------------------------

    if not GOLDAPI_KEY:

        error = (
            "GOLDAPI API KEY NOT FOUND.\n\n"
            "Add this to Streamlit Secrets:\n\n"
            'GOLDAPI = "YOUR_REAL_GOLDAPI_KEY"'
        )

        st.session_state["goldapi_last_error"] = error

        return {

            "success": False,

            "quote": None,

            "error": error,

            "using_cached_quote": False

        }


    # --------------------------------------------------------------------------
    # RATE PROTECTION
    # --------------------------------------------------------------------------

    now = time.time()

    last_request = st.session_state.get(
        "goldapi_last_request_time",
        0.0
    )

    elapsed = now - last_request


    if elapsed < MIN_REQUEST_INTERVAL:

        cached = st.session_state.get("goldapi_last_quote")

        if cached is not None:

            return {

                "success": True,

                "quote": cached,

                "error": None,

                "using_cached_quote": True

            }


    # --------------------------------------------------------------------------
    # MARK REQUEST TIME
    # --------------------------------------------------------------------------

    st.session_state["goldapi_last_request_time"] = time.time()

    st.session_state["goldapi_total_requests"] += 1


    # --------------------------------------------------------------------------
    # URL
    # --------------------------------------------------------------------------

    url = f"{GOLDAPI_BASE_URL}/{GOLDAPI_SYMBOL}"


    # --------------------------------------------------------------------------
    # HEADERS
    # --------------------------------------------------------------------------

    headers = build_goldapi_headers()


    # --------------------------------------------------------------------------
    # RETRY LOOP
    # --------------------------------------------------------------------------

    last_error = None


    for attempt in range(1, MAX_RETRIES + 1):

        try:

            request_start = time.perf_counter()


            response = requests.get(

                url,

                headers=headers,

                timeout=REQUEST_TIMEOUT

            )


            latency_ms = (
                time.perf_counter() - request_start
            ) * 1000


            # ------------------------------------------------------------------
            # SUCCESS
            # ------------------------------------------------------------------

            if response.status_code == 200:

                try:

                    data = response.json()

                except Exception as e:

                    raise ValueError(
                        f"GoldAPI returned invalid JSON: {e}"
                    )


                quote = parse_goldapi_quote(
                    data=data,
                    latency_ms=latency_ms
                )


                # --------------------------------------------------------------
                # STORE SUCCESS
                # --------------------------------------------------------------

                st.session_state["goldapi_last_quote"] = quote

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


            # ------------------------------------------------------------------
            # HTTP ERROR
            # ------------------------------------------------------------------

            error_message = get_goldapi_error_message(response)

            last_error = error_message


            # --------------------------------------------------------------
            # DON'T RETRY AUTHORIZATION ERRORS
            # --------------------------------------------------------------

            if response.status_code in [401, 403]:

                break


            # --------------------------------------------------------------
            # DON'T RETRY RATE LIMIT TOO AGGRESSIVELY
            # --------------------------------------------------------------

            if response.status_code == 429:

                retry_after = response.headers.get(
                    "Retry-After"
                )

                try:

                    wait_time = float(retry_after)

                except Exception:

                    wait_time = RETRY_DELAY * attempt


                if attempt < MAX_RETRIES:

                    time.sleep(wait_time)

                    continue

                break


            # --------------------------------------------------------------
            # RETRY SERVER ERRORS
            # --------------------------------------------------------------

            if attempt < MAX_RETRIES:

                time.sleep(RETRY_DELAY * attempt)

                continue


        except requests.exceptions.Timeout:

            last_error = (
                f"GoldAPI request timed out "
                f"after {REQUEST_TIMEOUT} seconds."
            )


        except requests.exceptions.ConnectionError as e:

            last_error = (
                f"GoldAPI connection error: {e}"
            )


        except Exception as e:

            last_error = (
                f"GoldAPI unexpected error: "
                f"{type(e).__name__}: {e}"
            )


        # ----------------------------------------------------------------------
        # WAIT BEFORE RETRY
        # ----------------------------------------------------------------------

        if attempt < MAX_RETRIES:

            time.sleep(RETRY_DELAY * attempt)


    # ==========================================================================
    # ❌ ALL REQUESTS FAILED
    # ==========================================================================

    st.session_state["goldapi_last_error"] = last_error

    st.session_state[
        "goldapi_consecutive_errors"
    ] += 1


    # --------------------------------------------------------------------------
    # USE LAST SUCCESSFUL QUOTE IF AVAILABLE
    #
    # IMPORTANT:
    # This is clearly marked as cached/stale.
    # --------------------------------------------------------------------------

    cached_quote = st.session_state.get(
        "goldapi_last_quote"
    )


    if cached_quote is not None:

        cached_quote = dict(cached_quote)

        cached_quote["cached"] = True

        cached_quote["cache_age_seconds"] = round(

            time.time()
            -
            cached_quote.get(
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
    # NO DATA AVAILABLE
    # --------------------------------------------------------------------------

    return {

        "success": False,

        "quote": None,

        "error": last_error,

        "using_cached_quote": False

    }


# ==============================================================================
# 🎯 SIMPLE COMPATIBILITY FUNCTION
# ==============================================================================

def get_live_xauusd_quote():

    """
    Compatibility wrapper for the rest of V5.
    """

    result = fetch_goldapi_xauusd()

    return result


# ==============================================================================
# 📊 GOLDAPI STATUS FUNCTION
# ==============================================================================

def get_goldapi_status():

    initialize_goldapi_state()


    total_requests = st.session_state.get(
        "goldapi_total_requests",
        0
    )

    successful_requests = st.session_state.get(
        "goldapi_successful_requests",
        0
    )


    success_rate = 0.0


    if total_requests > 0:

        success_rate = (
            successful_requests / total_requests
        ) * 100


    return {

        "provider": "GOLDAPI",

        "api_key_configured": bool(GOLDAPI_KEY),

        "total_requests": total_requests,

        "successful_requests": successful_requests,

        "success_rate": round(success_rate, 2),

        "consecutive_errors":
            st.session_state.get(
                "goldapi_consecutive_errors",
                0
            ),

        "last_error":
            st.session_state.get(
                "goldapi_last_error"
            ),

        "last_success_time":
            st.session_state.get(
                "goldapi_last_success_time"
            )

    }


# ==============================================================================
# 🖥️ DISPLAY GOLDAPI STATUS
# ==============================================================================

def show_goldapi_connection_status():

    status = get_goldapi_status()


    if status["api_key_configured"]:

        st.success(
            "🟢 GOLDAPI CONNECTION ENGINE READY"
        )

    else:

        st.error(
            "🔴 GOLDAPI API KEY NOT CONFIGURED"
        )


    col1, col2, col3, col4 = st.columns(4)


    col1.metric(
        "Provider",
        status["provider"]
    )


    col2.metric(
        "Requests",
        status["total_requests"]
    )


    col3.metric(
        "Success Rate",
        f'{status["success_rate"]}%'
    )


    col4.metric(
        "Errors",
        status["consecutive_errors"]
    )


    if status["last_error"]:

        st.warning(
            f"⚠️ Last Provider Error:\n\n"
            f"{status['last_error']}"
        )


# ==============================================================================
# 🧪 CONNECTION TEST FUNCTION
# ==============================================================================

def test_goldapi_connection():

    result = fetch_goldapi_xauusd()


    if result["success"]:

        quote = result["quote"]

        return {

            "connected": True,

            "message": (
                f"GoldAPI Connected | "
                f"XAU/USD: ${quote['price']:,.3f}"
            ),

            "quote": quote

        }


    return {

        "connected": False,

        "message": result["error"],

        "quote": result["quote"]

    }


# ==============================================================================
# 🚀 END GOLDAPI CONNECTION ENGINE
# ==============================================================================
