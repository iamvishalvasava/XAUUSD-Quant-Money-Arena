# XAUUSD QUANT MONEY ARENA V5
import os, time, csv, io
from datetime import datetime, timezone
import requests
import streamlit as st

st.set_page_config(page_title="XAUUSD Quant Money Arena V5", page_icon="🥇", layout="wide")

GOLDAPI_BASE_URL = "https://www.goldapi.io/api/price"
STOOQ_URL = "https://stooq.com/q/l/?s=xauusd&i=1"
REQUEST_TIMEOUT = 15
CACHE_SECONDS = 60.0

def secret(*names):
    for name in names:
        try:
            v = st.secrets.get(name)
            if v:
                return str(v).strip().strip('"').strip("'")
        except Exception:
            pass
        v = os.getenv(name)
        if v:
            return str(v).strip().strip('"').strip("'")
    return None

def init_state():
    defaults = {
        "last_quote": None, "last_request": 0.0, "last_error": None,
        "last_provider": None, "total_requests": 0, "successful_requests": 0,
        "last_status": None
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

def num(v):
    try:
        if v is None: return None
        s = str(v).strip()
        return None if not s or s.upper() in {"N/A","NA","-"} else float(s)
    except (TypeError, ValueError):
        return None

def quote(provider, price, bid=None, ask=None, latency=None, raw=None):
    return {
        "provider": provider, "symbol": "XAU/USD", "price": float(price),
        "mid": float(price), "bid": bid, "ask": ask,
        "spread": ask-bid if bid is not None and ask is not None else None,
        "received_at": datetime.now(timezone.utc).isoformat(),
        "received_epoch": time.time(), "latency_ms": latency,
        "cached": False, "raw": raw or {}
    }

def goldapi():
    key = secret("GOLDAPI", "GOLDAPI_KEY")
    if not key:
        return None, "GoldAPI key not configured"
    start = time.perf_counter()
    try:
        r = requests.get(
            f"{GOLDAPI_BASE_URL}/XAU/USD",
            headers={"x-access-token": key, "Accept": "application/json",
                     "User-Agent": "XAUUSD-Quant-Money-Arena-V5"},
            timeout=REQUEST_TIMEOUT
        )
        latency = round((time.perf_counter()-start)*1000, 2)
        st.session_state.last_status = r.status_code
        if r.status_code != 200:
            try: body = r.json()
            except Exception: body = r.text[:500]
            return None, f"GoldAPI HTTP {r.status_code}: {body}"
        data = r.json()
        price = num(data.get("price"))
        if price is None:
            return None, f"GoldAPI returned no price: {data}"
        return quote("GoldAPI", price, num(data.get("bid")), num(data.get("ask")), latency, data), None
    except requests.RequestException as e:
        return None, f"GoldAPI request error: {e}"

def stooq():
    start = time.perf_counter()
    try:
        r = requests.get(STOOQ_URL, timeout=REQUEST_TIMEOUT,
                         headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code != 200:
            return None, f"Stooq HTTP {r.status_code}"
        rows = list(csv.DictReader(io.StringIO(r.text.strip())))
        if not rows:
            return None, f"Stooq returned no data: {r.text[:200]}"
        row = rows[0]
        price = num(row.get("Close")) or num(row.get("CLOSE")) or num(row.get("close"))
        if price is None:
            return None, f"Stooq returned no valid price: {row}"
        latency = round((time.perf_counter()-start)*1000, 2)
        return quote("Stooq Fallback", price, latency=latency,
                     raw={"source":"Stooq","row":row}), None
    except requests.RequestException as e:
        return None, f"Stooq request error: {e}"

def fetch(force=False):
    init_state()
    now = time.time()
    cached = st.session_state.last_quote
    if not force and cached and now-cached["received_epoch"] < CACHE_SECONDS:
        q = dict(cached); q["cached"] = True
        q["cache_age_seconds"] = round(now-q["received_epoch"],1)
        return {"success":True,"quote":q,"error":None,"cached":True}

    st.session_state.total_requests += 1
    q, gold_error = goldapi()
    if q is None:
        q, fallback_error = stooq()
        if q is None:
            error = " | ".join(x for x in [gold_error, fallback_error] if x)
            st.session_state.last_error = error
            if cached:
                q = dict(cached); q["cached"] = True
                q["cache_age_seconds"] = round(now-q["received_epoch"],1)
                return {"success":False,"quote":q,"error":error,"cached":True}
            return {"success":False,"quote":None,"error":error,"cached":False}
        warning = f"GoldAPI unavailable: {gold_error}"
    else:
        warning = None

    st.session_state.last_quote = q
    st.session_state.last_error = None
    st.session_state.last_provider = q["provider"]
    st.session_state.successful_requests += 1
    return {"success":True,"quote":q,"error":None,"cached":False,"warning":warning}

def get_live_xauusd_quote():
    return fetch()

def money(v):
    return f"${v:,.3f}" if v is not None else "—"

def main():
    st.title("🥇 XAUUSD QUANT MONEY ARENA V5")
    st.caption("GoldAPI → Stooq fallback → cached quote")

    refresh = st.button("🔄 Refresh Price", use_container_width=False)
    with st.spinner("Loading XAU/USD market data..."):
        result = fetch(force=refresh)

    q = result["quote"]
    if q:
        if q.get("cached"):
            st.warning(f"📦 Cached {q['provider']} data ({q.get('cache_age_seconds',0)} sec old)")
        elif q["provider"] == "GoldAPI":
            st.success("🟢 Live GoldAPI data connected")
        else:
            st.warning("🟡 GoldAPI quota unavailable — using Stooq fallback")

        if result.get("warning"):
            st.caption(result["warning"])

        a,b,c,d = st.columns(4)
        a.metric("XAU/USD", money(q["price"]))
        b.metric("Provider", q["provider"])
        c.metric("Bid", money(q.get("bid")))
        d.metric("Ask", money(q.get("ask")))

        with st.expander("📊 Debug / Raw Data"):
            st.json(q)
    else:
        st.error("🔴 No market data available")
        st.code(result.get("error") or "Unknown error")

    st.divider()
    st.subheader("🔐 Provider Status")
    key = secret("GOLDAPI","GOLDAPI_KEY")
    a,b,c,d = st.columns(4)
    a.metric("GoldAPI Key", "Detected" if key else "Not configured")
    b.metric("Last Provider", st.session_state.last_provider or "—")
    c.metric("HTTP Status", st.session_state.last_status or "—")
    total = st.session_state.total_requests
    rate = st.session_state.successful_requests/total*100 if total else 0
    d.metric("Success Rate", f"{rate:.1f}%")

    st.caption("Fallback data can differ from spot XAU/USD and may be delayed. For trading execution use a broker feed.")

if __name__ == "__main__":
    main()
