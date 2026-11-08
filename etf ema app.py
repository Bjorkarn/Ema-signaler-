"""
Streamlit-app för EMA-signaler (veckodata).

Starta:
    pip install streamlit yfinance pandas
    streamlit run etf_ema_app.py

Lägg den här filen i samma mapp som etf_ema_signaler.py.
"""

import pandas as pd
import streamlit as st

import etf_ema_signaler as core

st.set_page_config(page_title="EMA-signaler", page_icon="📈", layout="wide")
st.title("📈 EMA 25/50 – veckosignaler")

COLORS = {
    "STARK KÖP": "#1a7f37",
    "KÖP": "#66c077",
    "NEUTRAL": "#9aa0a6",
    "SÄLJ": "#e8896b",
    "STARK SÄLJ": "#c62828",
}

# ------------------------------ Sidopanel ------------------------------
default_text = "\n".join(f"{t},{n}" for t, n in core.TICKERS.items())
with st.sidebar:
    st.header("Inställningar")
    text = st.text_area("Tickers (en per rad: TICKER,Namn)", default_text, height=260)
    lookback = st.slider("Cross inom senaste veckostaplar", 1, 8, core.LOOKBACK_BARS)
    st.caption("5 handelsdagar ≈ 1 veckostapel.")
    if st.button("Uppdatera data"):
        st.cache_data.clear()


@st.cache_data(ttl=3600, show_spinner=False)
def load(ticker: str) -> pd.DataFrame:
    df = core.fetch_weekly(ticker)
    if df.empty:
        raise ValueError("Yahoo returnerade ingen data (rate limit eller fel ticker)")
    return core.add_emas(df)


tickers = []
for line in text.splitlines():
    line = line.strip()
    if not line:
        continue
    t, _, n = line.partition(",")
    tickers.append((t.strip(), n.strip()))

rows, data, failed, errors = [], {}, [], {}
with st.spinner("Hämtar data..."):
    for t, n in tickers:
        res = None
        try:
            df = load(t)
            res = core.analyze_df(t, n, df, lookback)
            if res is None:
                errors[t] = "För lite historik (behöver minst 51 veckor)"
        except Exception as exc:
            errors[t] = f"{type(exc).__name__}: {exc}"
        if res is None:
            failed.append(t)
        else:
            rows.append(res)
            data[t] = df

if not rows:
    st.error("Ingen data kunde hämtas. Felen nedan visar varför:")
    for t, msg in errors.items():
        st.code(f"{t}\n{msg}")
    st.stop()

table = pd.DataFrame(rows)

# ------------------------------ Översikt ------------------------------
st.subheader("Översikt")
shown = table.drop(columns=["Varningar"])
styled = shown.style.map(
    lambda v: f"background-color: {COLORS.get(v, '')}; color: white; font-weight: 600"
    if v in COLORS else "",
    subset=["Signal"],
)
st.dataframe(styled, use_container_width=True, hide_index=True)
if failed:
    st.warning("Kunde inte hämta/analysera: " + ", ".join(failed))
    with st.expander("Visa felorsaker"):
        for t in failed:
            st.code(f"{t}\n{errors.get(t, '')}")

# ------------------------------ Detalj ------------------------------
st.subheader("Detalj")
choice = st.selectbox(
    "Välj index/ETF",
    [r["Ticker"] for r in rows],
    format_func=lambda t: f"{t} – {table.loc[table.Ticker == t, 'Namn'].iloc[0]}",
)
r = table[table.Ticker == choice].iloc[0]
c1, c2, c3 = st.columns(3)
c1.metric("Signal", r["Signal"])
c2.metric("Poäng (−5…+5)", int(r["Poäng"]))
c3.metric("Pris", r["Pris"])

for w in r["Varningar"]:
    if "GOLDEN" in w:
        st.success(w)
    elif "DEATH" in w:
        st.error(w)
    else:
        st.info(w)

weeks = st.select_slider("Visa antal veckor", [26, 52, 104, 156, 260], value=104)
st.line_chart(data[choice][["Close", "EMA25", "EMA50"]].tail(weeks))

st.caption("Förenklad trendindikator – inte investeringsråd.")
