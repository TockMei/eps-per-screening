"""
PEGスクリーニング — EPS成長率 × PER 乖離分析
screening_data.json（EDINET DB由来）を使用
"""

import streamlit as st
import json
import pandas as pd
import math

st.set_page_config(page_title="PEGスクリーニング", layout="wide")

# ─── データ読み込み ───
@st.cache_data
def load_data():
    with open("screening_data.json", "r") as f:
        return json.load(f)

data = load_data()
master = data["master"]
financials = data["financials"]
ratios = data["ratios"]

# ─── EPS CAGR計算（動的起点） ───
def calc_eps_cagr(eps_series: dict, min_years: int = 3):
    """
    EPS時系列からCAGRを算出。
    起点EPSが0以下の場合、正になる最初の年まで前進（最低min_years要件）。
    Returns: (cagr_pct, start_year, end_year, start_eps, end_eps, span) or None
    """
    years = sorted(eps_series.keys())
    if len(years) < 2:
        return None

    end_year = years[-1]
    end_val = eps_series[end_year]
    if not isinstance(end_val, dict):
        return None
    end_eps = end_val.get("eps")
    if end_eps is None or end_eps <= 0:
        return None

    # 起点を探索：正のEPSかつmin_years以上のスパン
    for sy in years:
        sv = eps_series[sy]
        if not isinstance(sv, dict):
            continue
        start_eps = sv.get("eps")
        if start_eps is None or start_eps <= 0:
            continue
        span = int(end_year) - int(sy)
        if span >= min_years:
            cagr = (end_eps / start_eps) ** (1.0 / span) - 1.0
            return (cagr * 100, sy, end_year, start_eps, end_eps, span)

    return None


# ─── 全社計算 ───
@st.cache_data
def build_table(min_years: int):
    rows = []
    for code, info in master.items():
        per = ratios.get(code, {}).get("per")
        mkt = ratios.get(code, {}).get("market_cap")
        if per is None or per <= 0:
            continue

        eps_ts = financials.get(code, {})
        result = calc_eps_cagr(eps_ts, min_years)
        if result is None:
            continue

        cagr_pct, sy, ey, s_eps, e_eps, span = result
        if cagr_pct <= 0:
            continue

        peg = per / cagr_pct

        rows.append({
            "edinet_code": code,
            "証券コード": str(info.get("sec_code", ""))[:4],
            "企業名": info.get("name", ""),
            "業種": info.get("industry", ""),
            "起点年": int(sy),
            "起点EPS": round(s_eps, 2),
            "終点EPS": round(e_eps, 2),
            "年数": span,
            "EPS CAGR(%)": round(cagr_pct, 2),
            "PER": round(per, 2),
            "PEG": round(peg, 3),
            "時価総額(億円)": round(mkt / 1e8, 1) if mkt else None,
        })

    return pd.DataFrame(rows)


# ─── UI ───
st.title("📊 PEGスクリーニング")
st.caption("PEG = PER ÷ EPS CAGR(%)　｜　PEG < 1.0 = 成長に対して割安")

# --- プリセット ---
PRESETS = {
    "テンバガー候補（高成長×超割安）": {"peg_max": 0.5, "cagr_min": 20.0, "mkt_min": 0, "mkt_max": 1e18, "min_years": 5},
    "成長割安（Growth at Reasonable Price）": {"peg_max": 1.0, "cagr_min": 10.0, "mkt_min": 0, "mkt_max": 1e18, "min_years": 5},
    "大型成長割安": {"peg_max": 1.0, "cagr_min": 8.0, "mkt_min": 5000, "mkt_max": 1e18, "min_years": 5},
    "バリュー発掘（低PEG×中小型）": {"peg_max": 0.7, "cagr_min": 5.0, "mkt_min": 0, "mkt_max": 5000, "min_years": 3},
    "カスタム": None,
}

col_preset, col_help = st.columns([3, 1])
with col_preset:
    preset_name = st.selectbox("プリセット", list(PRESETS.keys()))

with col_help:
    st.markdown("")
    st.markdown("")
    with st.expander("PEGとは？"):
        st.markdown(
            "**PEG比率**（Price/Earnings to Growth）= PER ÷ EPS年平均成長率(%)。"
            "ピーター・リンチが提唱した指標で、PERだけでは見えない「成長速度に対する株価の割安度」を測る。\n\n"
            "- **PEG < 0.5** → 大幅割安\n"
            "- **0.5 ≦ PEG < 1.0** → 割安\n"
            "- **1.0 ≦ PEG < 2.0** → 適正\n"
            "- **PEG ≧ 2.0** → 割高"
        )

preset = PRESETS[preset_name]

if preset is not None:
    peg_max = preset["peg_max"]
    cagr_min = preset["cagr_min"]
    mkt_min = preset["mkt_min"]
    mkt_max = preset["mkt_max"]
    min_years = preset["min_years"]
else:
    st.markdown("---")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        peg_max = st.number_input("PEG上限", min_value=0.1, max_value=10.0, value=1.0, step=0.1)
    with c2:
        cagr_min = st.number_input("EPS CAGR下限(%)", min_value=0.0, max_value=100.0, value=10.0, step=1.0)
    with c3:
        mkt_min = st.number_input("時価総額下限(億円)", min_value=0, value=0, step=100)
    with c4:
        min_years = st.number_input("最低年数", min_value=2, max_value=12, value=5, step=1)
    mkt_max = 1e18

# --- テーブル構築 ---
df = build_table(min_years if preset is None else preset.get("min_years", 5))

if df.empty:
    st.warning("条件に合致する企業がありません。")
    st.stop()

# --- フィルタ適用 ---
mask = (
    (df["PEG"] <= peg_max)
    & (df["EPS CAGR(%)"] >= cagr_min)
)
if mkt_min > 0:
    mask &= df["時価総額(億円)"].fillna(0) >= mkt_min
if mkt_max < 1e18:
    mask &= df["時価総額(億円)"].fillna(0) <= mkt_max

filtered = df[mask].sort_values("PEG").reset_index(drop=True)

# --- サマリー ---
st.markdown(f"**{len(filtered)}社** ／ PEG計算可能 {len(df)}社 ／ 全{len(master)}社")

# --- PEG分布 ---
if len(filtered) > 0:
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        n_super = len(filtered[filtered["PEG"] < 0.5])
        st.metric("大幅割安 (PEG<0.5)", f"{n_super}社")
    with col_b:
        n_cheap = len(filtered[(filtered["PEG"] >= 0.5) & (filtered["PEG"] < 1.0)])
        st.metric("割安 (0.5≦PEG<1.0)", f"{n_cheap}社")
    with col_c:
        st.metric("中央値PEG", f"{filtered['PEG'].median():.3f}")

# --- 結果テーブル ---
st.markdown("---")

display_cols = ["証券コード", "企業名", "業種", "起点年", "起点EPS", "終点EPS",
                "年数", "EPS CAGR(%)", "PER", "PEG", "時価総額(億円)", "edinet_code"]

show_df = filtered[display_cols].copy()

# EDINET有報リンク列
show_df["有報"] = show_df["edinet_code"].apply(
    lambda c: f"https://edinetdb.jp/company/{c}"
)

st.dataframe(
    show_df.drop(columns=["edinet_code"]),
    column_config={
        "有報": st.column_config.LinkColumn("📄", display_text="開く"),
        "PEG": st.column_config.NumberColumn(format="%.3f"),
        "EPS CAGR(%)": st.column_config.NumberColumn(format="%.2f"),
        "PER": st.column_config.NumberColumn(format="%.2f"),
        "時価総額(億円)": st.column_config.NumberColumn(format="%.1f"),
    },
    use_container_width=True,
    height=700,
    hide_index=True,
)

# --- CSV出力 ---
csv = filtered[display_cols[:-1]].to_csv(index=False)
st.download_button("CSV出力", csv, "peg_screening.csv", "text/csv")

# --- 注記 ---
st.markdown("---")
st.caption(
    "データ: EDINET DB（有価証券報告書・XBRL由来）｜"
    "PER: 有報期末株価ベース（株式分割調整済み）｜"
    "EPS: EDINET XBRL記載値｜"
    "EPS起点が0以下の場合は正になる最初の年を動的起点として使用"
)
