"""
PEGスクリーニング v3 — EPS成長率 × PER 乖離分析
screening_data.json（EDINET DB由来）を使用
"""

import streamlit as st
import json
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np

import japanize_matplotlib

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
def calc_eps_cagr(eps_series: dict, min_years: int = 3, min_start_eps: float = 10.0):
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
    for sy in years:
        sv = eps_series[sy]
        if not isinstance(sv, dict):
            continue
        start_eps = sv.get("eps")
        if start_eps is None or start_eps < min_start_eps:
            continue
        span = int(end_year) - int(sy)
        if span >= min_years:
            cagr = (end_eps / start_eps) ** (1.0 / span) - 1.0
            return (cagr * 100, sy, end_year, start_eps, end_eps, span)
    return None


# ─── 全社計算 ───
@st.cache_data
def build_table(min_years: int, min_start_eps: float):
    rows = []
    for code, info in master.items():
        per = ratios.get(code, {}).get("per")
        mkt = ratios.get(code, {}).get("market_cap")
        if per is None or per <= 0:
            continue
        eps_ts = financials.get(code, {})
        result = calc_eps_cagr(eps_ts, min_years, min_start_eps)
        if result is None:
            continue
        cagr_pct, sy, ey, s_eps, e_eps, span = result
        if cagr_pct <= 0:
            continue
        peg = per / cagr_pct
        mkt_oku = round(mkt / 1e8, 1) if mkt and mkt > 0 else None
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
            "時価総額(億円)": mkt_oku,
        })
    return pd.DataFrame(rows)


def peg_label(peg):
    if peg < 0.5:
        return "🟢 大幅割安"
    elif peg < 1.0:
        return "🔵 割安"
    elif peg < 2.0:
        return "🟡 適正"
    else:
        return "🔴 割高"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# UI
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

st.title("PEGスクリーニング")
st.caption("PEG = PER ÷ EPS CAGR(%)　｜　PEG < 1.0 → 成長速度に対して株価が割安")

# --- プリセット ---
PRESETS = {
    "📊 EPS×PER乖離（成長未反映）": {"peg_max": 1.0, "cagr_min": 5.0, "mkt_min": 0, "min_years": 5, "min_start_eps": 10.0},
    "📈 成長割安（GARP）": {"peg_max": 1.0, "cagr_min": 10.0, "mkt_min": 0, "min_years": 5, "min_start_eps": 10.0},
    "🏢 大型成長割安（時価総額1000億円超）": {"peg_max": 1.0, "cagr_min": 8.0, "mkt_min": 1000, "min_years": 5, "min_start_eps": 10.0},
    "💎 バリュー発掘（低PEG×安定成長）": {"peg_max": 0.7, "cagr_min": 5.0, "mkt_min": 0, "min_years": 3, "min_start_eps": 20.0},
    "⚙️ カスタム": None,
}

col_left, col_right = st.columns([4, 1])
with col_left:
    preset_name = st.selectbox("プリセット", list(PRESETS.keys()))
with col_right:
    with st.expander("PEGとは？"):
        st.markdown(
            "**PEG**（Price/Earnings to Growth）\n\n"
            "ピーター・リンチ提唱。\n\n"
            "🟢 < 0.5　大幅割安\n\n"
            "🔵 0.5–1.0　割安\n\n"
            "🟡 1.0–2.0　適正\n\n"
            "🔴 ≧ 2.0　割高"
        )

preset = PRESETS[preset_name]

if preset is not None:
    peg_max = preset["peg_max"]
    cagr_min = preset["cagr_min"]
    mkt_min = preset["mkt_min"]
    min_years = preset["min_years"]
    min_start_eps = preset["min_start_eps"]
else:
    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        peg_max = st.number_input("PEG上限", min_value=0.1, max_value=10.0, value=1.0, step=0.1)
    with c2:
        cagr_min = st.number_input("EPS CAGR下限(%)", min_value=0.0, max_value=100.0, value=10.0, step=1.0)
    with c3:
        mkt_min = st.number_input("時価総額下限(億円)", min_value=0, value=0, step=100,
                                   help="0=フィルタなし。時価総額データは全体の約12%のみ。")
    with c4:
        min_years = st.number_input("最低年数", min_value=2, max_value=12, value=5, step=1)
    with c5:
        min_start_eps = st.number_input("起点EPS下限(円)", min_value=0.0, max_value=500.0, value=10.0, step=5.0,
                                         help="低すぎる起点からの見かけ上の高CAGRを排除")

# --- テーブル構築 ---
df = build_table(min_years if preset is None else preset["min_years"],
                 min_start_eps if preset is None else preset["min_start_eps"])

if df.empty:
    st.warning("条件に合致する企業がありません。")
    st.stop()

# --- フィルタ適用 ---
mask = (df["PEG"] <= peg_max) & (df["EPS CAGR(%)"] >= cagr_min)
if mkt_min > 0:
    mask &= df["時価総額(億円)"].fillna(0) >= mkt_min

filtered = df[mask].sort_values("PEG").reset_index(drop=True)

if len(filtered) == 0:
    st.warning("条件に合致する企業がありません。フィルタを緩めてください。")
    st.stop()

# ━━━ サマリー ━━━
st.markdown("---")

c1, c2, c3, c4, c5 = st.columns(5)
with c1:
    st.metric("抽出", f"{len(filtered)}社")
with c2:
    st.metric("🟢 大幅割安", f"{len(filtered[filtered['PEG'] < 0.5])}社")
with c3:
    st.metric("🔵 割安", f"{len(filtered[(filtered['PEG'] >= 0.5) & (filtered['PEG'] < 1.0)])}社")
with c4:
    st.metric("中央値PEG", f"{filtered['PEG'].median():.3f}")
with c5:
    st.metric("中央値CAGR", f"{filtered['EPS CAGR(%)'].median():.1f}%")

# ━━━ チャート ━━━
chart_col1, chart_col2 = st.columns([3, 2])

# --- 散布図: EPS CAGR vs PER（PEGアイソライン付き） ---
with chart_col1:
    fig, ax = plt.subplots(figsize=(8, 5))

    x = filtered["EPS CAGR(%)"].values
    y = filtered["PER"].values

    # PEGアイソライン（PEG = PER / CAGR → PER = PEG × CAGR）
    cagr_line = np.linspace(1, max(x.max() * 1.1, 50), 200)
    for peg_val, color, ls, label in [
        (0.5, "#2ca02c", "--", "PEG=0.5"),
        (1.0, "#1f77b4", "-",  "PEG=1.0"),
        (2.0, "#d62728", ":",  "PEG=2.0"),
    ]:
        per_line = peg_val * cagr_line
        ax.plot(cagr_line, per_line, color=color, ls=ls, lw=1.5, alpha=0.7, label=label)

    # 散布
    colors = ["#2ca02c" if p < 0.5 else "#1f77b4" if p < 1.0 else "#ff7f0e" if p < 2.0 else "#d62728"
              for p in filtered["PEG"].values]
    ax.scatter(x, y, c=colors, alpha=0.6, s=30, edgecolors="white", linewidth=0.3)

    ax.set_xlabel("EPS CAGR (%)", fontsize=11)
    ax.set_ylabel("PER (x)", fontsize=11)
    ax.set_title("EPS成長率 × PER（線の下が割安）", fontsize=12)
    ax.legend(loc="upper left", fontsize=9)
    ax.set_xlim(left=0)
    ax.set_ylim(bottom=0, top=min(y.max() * 1.2, 150))
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    st.pyplot(fig, use_container_width=True)

# --- 業種分布 ---
with chart_col2:
    ind_counts = filtered["業種"].value_counts().head(15)
    fig2, ax2 = plt.subplots(figsize=(6, 5))
    bars = ax2.barh(ind_counts.index[::-1], ind_counts.values[::-1], color="#4c78a8", height=0.6)
    ax2.set_xlabel("社数", fontsize=11)
    ax2.set_title("業種別分布（上位15）", fontsize=12)
    ax2.xaxis.set_major_locator(mticker.MaxNLocator(integer=True))
    for bar in bars:
        w = bar.get_width()
        ax2.text(w + 0.3, bar.get_y() + bar.get_height()/2, str(int(w)),
                 va="center", fontsize=9)
    fig2.tight_layout()
    st.pyplot(fig2, use_container_width=True)

# ━━━ 結果テーブル ━━━
st.markdown("---")

filtered = filtered.copy()
filtered["判定"] = filtered["PEG"].apply(peg_label)
filtered["有報"] = filtered["edinet_code"].apply(
    lambda c: f"https://edinetdb.jp/company/{c}"
)

display_cols = ["判定", "証券コード", "企業名", "業種", "起点年", "起点EPS", "終点EPS",
                "年数", "EPS CAGR(%)", "PER", "PEG", "時価総額(億円)", "有報"]

st.dataframe(
    filtered[display_cols],
    column_config={
        "有報": st.column_config.LinkColumn("📄有報", display_text="開く"),
        "PEG": st.column_config.NumberColumn(format="%.3f"),
        "EPS CAGR(%)": st.column_config.NumberColumn(format="%.2f"),
        "PER": st.column_config.NumberColumn(format="%.2f"),
        "時価総額(億円)": st.column_config.NumberColumn(format="%.1f"),
        "起点EPS": st.column_config.NumberColumn(format="%.2f"),
        "終点EPS": st.column_config.NumberColumn(format="%.2f"),
    },
    width="stretch",
    height=600,
    hide_index=True,
)

# --- CSV出力 ---
csv_cols = [c for c in display_cols if c != "有報"]
csv = filtered[csv_cols].to_csv(index=False)
st.download_button("📥 CSV出力", csv, "peg_screening.csv", "text/csv")

# --- 注記 ---
st.markdown("---")
st.caption(
    "データ: EDINET DB（有価証券報告書・XBRL由来）｜"
    "PER: 有報期末株価ベース（株式分割調整済み）｜"
    "EPS: EDINET XBRL記載値｜"
    "時価総額: J-Quants（取得済み企業のみ）｜"
    "起点EPSが下限未満の場合は閾値以上の最初の年を動的起点として使用"
)
