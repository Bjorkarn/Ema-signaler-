#!/usr/bin/env python3
"""
EMA-signaler på veckodata för ETF:er (yfinance + pandas).

- Laddar ner veckodata per ticker
- Beräknar EMA 25, 50 och 200
- Flaggar korsningar (upp = "Golden Cross", ned = "Death Cross") för
  EMA 25/50 och EMA 50/200 inom de senaste LOOKBACK_BARS veckostaplarna
- Flaggar om priset ligger över/under EMA 25 och EMA 50
- Ger en 5-gradig signal: Stark köp / Köp / Neutral / Sälj / Stark sälj

Installera:  pip install yfinance pandas
Kör:         python etf_ema_signaler.py
"""

import pandas as pd
import yfinance as yf

# ----------------------------- INSTÄLLNINGAR -----------------------------
# Ticker -> beskrivning. Kontrollera alltid att tickern finns på Yahoo Finance
# och att motsvarande ETF går att handla på Avanza (sök på ISIN där).
# Tickers med .DE = Xetra (EUR). Byt gärna mot .L, .AS, .ST m.fl. vid behov.
TICKERS = {
    "DBX8.DE": "(din ticker)",
    "IS3R.DE": "(din ticker)",
    "EUNL.DE": "iShares Core MSCI World",
    "VWCE.DE": "Vanguard FTSE All-World",
    "SXR8.DE": "iShares Core S&P 500",
    "SXRV.DE": "iShares Nasdaq 100",
    "EXS1.DE": "iShares Core DAX",
    "EXSA.DE": "iShares STOXX Europe 600",
    "IS3N.DE": "iShares Core MSCI EM IMI",
}

PERIOD = "8y"          # 200 veckor ≈ 3,9 år, så 8 år ger gott om marginal
LOOKBACK_BARS = 1      # 5 handelsdagar ≈ 1 veckostapel. Höj till 2-4 för längre fönster
EMA_FAST, EMA_MID, EMA_SLOW = 25, 50, 200

LABELS = {
    2: "STARK KÖP",
    1: "KÖP",
    0: "NEUTRAL",
    -1: "SÄLJ",
    -2: "STARK SÄLJ",
}
# -------------------------------------------------------------------------


def fetch_weekly(ticker: str) -> pd.DataFrame:
    df = yf.Ticker(ticker).history(period=PERIOD, interval="1wk", auto_adjust=True)
    if df.empty:
        return df
    return df[["Close"]].dropna()


def add_emas(df: pd.DataFrame) -> pd.DataFrame:
    for n in (EMA_FAST, EMA_MID, EMA_SLOW):
        df[f"EMA{n}"] = df["Close"].ewm(span=n, adjust=False).mean()
    return df


def recent_cross(a: pd.Series, b: pd.Series, lookback: int) -> tuple[bool, bool]:
    """Returnerar (cross_upp, cross_ned) för a mot b inom senaste `lookback` staplarna."""
    valid = a.notna() & b.notna()
    a, b = a[valid], b[valid]
    if len(a) < lookback + 1:
        return False, False
    above = (a > b).astype(int)
    change = above.diff().iloc[-lookback:]
    return bool((change == 1).any()), bool((change == -1).any())


def score_to_label(score: int) -> str:
    """Poäng (-6..+6) -> 5-gradig skala."""
    if score >= 4:
        return LABELS[2]
    if score >= 2:
        return LABELS[1]
    if score <= -4:
        return LABELS[-2]
    if score <= -2:
        return LABELS[-1]
    return LABELS[0]


def analyze(ticker: str) -> dict | None:
    df = fetch_weekly(ticker)
    if df.empty or len(df) < EMA_MID + 1:
        return None
    df = add_emas(df)

    last = df.iloc[-1]
    price = last["Close"]
    e25, e50, e200 = last[f"EMA{EMA_FAST}"], last[f"EMA{EMA_MID}"], last[f"EMA{EMA_SLOW}"]
    has_200 = len(df) >= EMA_SLOW  # EMA 200 är först rimlig med minst 200 staplar

    gc_25_50, dc_25_50 = recent_cross(df[f"EMA{EMA_FAST}"], df[f"EMA{EMA_MID}"], LOOKBACK_BARS)
    if has_200:
        gc_50_200, dc_50_200 = recent_cross(df[f"EMA{EMA_MID}"], df[f"EMA{EMA_SLOW}"], LOOKBACK_BARS)
    else:
        gc_50_200 = dc_50_200 = False

    # ---- Poängsättning: +1 för varje bullish faktor, -1 för bearish ----
    score = 0
    score += 1 if price > e25 else -1
    score += 1 if price > e50 else -1
    score += 1 if e25 > e50 else -1
    if has_200:
        score += 1 if e50 > e200 else -1
    score += 1 if gc_25_50 else 0
    score -= 1 if dc_25_50 else 0
    score += 1 if gc_50_200 else 0
    score -= 1 if dc_50_200 else 0

    warnings = []
    if gc_25_50:
        warnings.append("GOLDEN CROSS 25/50 (EMA25 över EMA50)")
    if dc_25_50:
        warnings.append("DEATH CROSS 25/50 (EMA25 under EMA50)")
    if gc_50_200:
        warnings.append("GOLDEN CROSS 50/200")
    if dc_50_200:
        warnings.append("DEATH CROSS 50/200")
    if price > e25 and price > e50:
        warnings.append("Pris över både EMA25 och EMA50")
    elif price < e25 and price < e50:
        warnings.append("Pris under både EMA25 och EMA50")
    if not has_200:
        warnings.append(f"För lite historik för EMA{EMA_SLOW} (<{EMA_SLOW} veckor)")

    return {
        "Ticker": ticker,
        "Namn": TICKERS.get(ticker, ""),
        "Datum": df.index[-1].strftime("%Y-%m-%d"),
        "Pris": round(price, 2),
        "EMA25": round(e25, 2),
        "EMA50": round(e50, 2),
        "EMA200": round(e200, 2) if has_200 else None,
        "Poäng": score,
        "Signal": score_to_label(score),
        "Varningar": warnings,
    }


def main() -> None:
    rows, failed = [], []
    for t in TICKERS:
        try:
            res = analyze(t)
        except Exception as exc:  # nätverksfel, okänd ticker m.m.
            print(f"[fel] {t}: {exc}")
            res = None
        if res is None:
            failed.append(t)
        else:
            rows.append(res)

    if not rows:
        print("Ingen data kunde hämtas.")
        return

    result = pd.DataFrame(rows)

    pd.set_option("display.width", 200)
    pd.set_option("display.max_columns", None)
    print("\n=== SAMMANFATTNING (veckodata) ===")
    print(result.drop(columns=["Varningar"]).to_string(index=False))

    print("\n=== VARNINGAR ===")
    for r in rows:
        print(f"\n{r['Ticker']} {r['Namn']} -> {r['Signal']} (poäng {r['Poäng']})")
        for w in r["Varningar"]:
            print(f"  - {w}")

    if failed:
        print("\nKunde inte analysera (fel ticker eller för lite data):", ", ".join(failed))

    result.drop(columns=["Varningar"]).to_csv("etf_signaler.csv", index=False)
    print("\nSparade etf_signaler.csv")


if __name__ == "__main__":
    main()
