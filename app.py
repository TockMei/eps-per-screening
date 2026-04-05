"""
EPS成長とPER水準の乖離がある上場企業の抽出（＝PEGスクリーニング） v7
純利益CAGRベース（株式分割の影響を受けない）
screening_data.json（EDINET DB由来）を使用
"""

import streamlit as st
import json
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from pathlib import Path
import matplotlib.ticker as mticker
import numpy as np

_font_path = Path(__file__).parent / "ipaexg.ttf"
if _font_path.exists():
    fm.fontManager.addfont(str(_font_path))
    plt.rcParams["font.family"] = "IPAexGothic"

st.set_page_config(page_title="EPS成長×PER乖離スクリーニング", layout="wide")

# ─── データ読み込み ───
@st.cache_data
def load_data():
    with open("screening_data.json", "r") as f:
        return json.load(f)

data = load_data()
master = data["master"]
ratios = data["ratios"]

# CAGR上限キャップ（赤字→黒字転換による見かけ上の異常値を排除）
CAGR_CAP_PCT = 100.0

def peg_label(peg):
    if peg < 0.5:
        return "🟢 大幅割安"
    elif peg < 1.0:
        return "🔵 割安"
    elif peg < 2.0:
        return "🟡 適正"
    else:
        return "🔴 割高"

@st.cache_data
def build_table(cagr_period: str):
    cagr_key = f"ni_cagr_{cagr_period}"
    rows = []
    for code, info in master.items():
        r = ratios.get(code, {})
        per = r.get("per")
        cagr = r.get(cagr_key)
        if per is None or per <= 2 or per > 200:
            continue
        if cagr is None or cagr <= 0:
            continue
        cagr_pct = cagr * 100
        if cagr_pct > CAGR_CAP_PCT:
            continue
        peg = per / cagr_pct
        mkt = r.get("market_cap")
        mkt_oku = round(mkt / 1e8, 1) if mkt and mkt > 0 else None
        roe = r.get("roe")
        roe_pct = round(roe * 100, 1) if roe is not None else None
        ni_growth = r.get("ni_growth")
        ni_growth_pct = round(ni_growth * 100, 1) if ni_growth is not None else None
        rows.append({
            "edinet_code": code,
            "証券コード": str(info.get("sec_code", ""))[:4],
            "企業名": info.get("name", ""),
            "業種": info.get("industry", ""),
            "純利益CAGR(%)": round(cagr_pct, 1),
            "PER": round(per, 1),
            "PEG": round(peg, 3),
            "ROE(%)": roe_pct,
            "直近NI成長(%)": ni_growth_pct,
            "時価総額(億円)": mkt_oku,
        })
    return pd.DataFrame(rows)

# ━━━ ヘッダー ━━━
st.title("EPS成長とPER水準の乖離がある上場企業の抽出（＝PEGスクリーニング）")
st.caption("PEG = PER ÷ 純利益CAGR(%)　｜　PEG < 1.0 → 利益の成長速度に対してPERが低い＝株価に成長が未反映")

with st.expander("PEGとは？"):
    st.markdown(
        "**PEG比率**（Price/Earnings to Growth）= PER ÷ 利益成長率(%)。"
        "ピーター・リンチが提唱した指標。PERだけでは見えない"
        "「成長速度に対する株価の割安度」を測る。\n\n"
        "| PEG | 判定 |\n|---|---|\n"
        "| < 0.5 | 🟢 大幅割安 |\n"
        "| 0.5 – 1.0 | 🔵 割安 |\n"
        "| 1.0 – 2.0 | 🟡 適正 |\n"
        "| ≧ 2.0 | 🔴 割高 |"
    )

# ━━━ プリセット ━━━
PRESETS = {
    "📊 利益成長×PER乖離": {"peg_max": 1.0, "cagr_min": 5.0, "mkt_min": 0, "period": "5y",
                            "desc": "5年純利益CAGR 5%以上 / PEG 1.0以下"},
    "🚀 高成長×超割安": {"peg_max": 0.5, "cagr_min": 15.0, "mkt_min": 0, "period": "5y",
                          "desc": "5年CAGR 15%以上 / PEG 0.5以下"},
    "🏢 大型成長割安": {"peg_max": 1.0, "cagr_min": 8.0, "mkt_min": 1000, "period": "5y",
                         "desc": "時価総額1000億超 / 5年CAGR 8%以上"},
    "⚡ 直近3年の勢い": {"peg_max": 1.0, "cagr_min": 10.0, "mkt_min": 0, "period": "3y",
                          "desc": "3年CAGR 10%以上 / PEG 1.0以下"},
    "⚙️ カスタム": None,
}

if "active_preset" not in st.session_state:
    st.session_state.active_preset = list(PRESETS.keys())[0]

cols = st.columns(len(PRESETS))
for i, key in enumerate(PRESETS.keys()):
    with cols[i]:
        btn_type = "primary" if st.session_state.active_preset == key else "secondary"
        if st.button(key, use_container_width=True, type=btn_type):
            st.session_state.active_preset = key
            st.rerun()

active = st.session_state.active_preset
preset = PRESETS[active]

if preset is not None:
    st.info(f"**{active}** — {preset['desc']}")
    peg_max = preset["peg_max"]
    cagr_min = preset["cagr_min"]
    mkt_min = preset["mkt_min"]
    period = preset["period"]
else:
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        peg_max = st.number_input("PEG上限", min_value=0.1, max_value=10.0, value=1.0, step=0.1)
    with c2:
        cagr_min = st.number_input("純利益CAGR下限(%)", min_value=0.0, max_value=100.0, value=5.0, step=1.0)
    with c3:
        mkt_min = st.number_input("時価総額下限(億円)", min_value=0, value=0, step=100,
                                   help="0=フィルタなし。時価総額データは全体の約12%のみ。")
    with c4:
        period = st.selectbox("CAGR期間", ["5y", "3y"],
                               format_func=lambda x: "5年" if x == "5y" else "3年")

# ━━━ テーブル構築・フィルタ ━━━
df = build_table(period)

if df.empty:
    st.warning("条件に合致する企業がありません。")
    st.stop()

mask = (df["PEG"] <= peg_max) & (df["純利益CAGR(%)"] >= cagr_min)
if mkt_min > 0:
    mask &= df["時価総額(億円)"].fillna(0) >= mkt_min

filtered = df[mask].sort_values("PEG").reset_index(drop=True)

if len(filtered) == 0:
    st.warning("条件に合致する企業がありません。フィルタを緩めてください。")
    st.stop()

# ━━━ サマリー ━━━
st.markdown("---")
period_label = "5年" if period == "5y" else "3年"

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
    st.metric(f"中央値CAGR({period_label})", f"{filtered['純利益CAGR(%)'].median():.1f}%")

# ━━━ ランキングテーブル ━━━
st.markdown("---")
st.subheader("ランキング（PEG昇順）")

filtered = filtered.copy()
filtered["判定"] = filtered["PEG"].apply(peg_label)
filtered["有報"] = filtered["edinet_code"].apply(
    lambda c: f"https://edinetdb.jp/company/{c}"
)

display_cols = ["判定", "証券コード", "企業名", "業種",
                "純利益CAGR(%)", "PER", "PEG", "ROE(%)", "直近NI成長(%)",
                "時価総額(億円)", "有報"]


# 銘柄検索
search_q = st.text_input("🔍 銘柄検索（社名・証券コード）", placeholder="例: トヨタ、7203")
if search_q:
    search_mask = filtered["企業名"].str.contains(search_q, case=False, na=False) | filtered["証券コード"].str.contains(search_q, na=False)
    filtered = filtered[search_mask].reset_index(drop=True)
    if len(filtered) == 0:
        st.warning(f"「{search_q}」に該当する企業がありません。")
        st.stop()
show_all = st.toggle(f"全{len(filtered)}社を表示", value=False)
show_df = filtered[display_cols] if show_all else filtered[display_cols].head(50)
if not show_all:
    st.caption(f"上位50社を表示中　全{len(filtered)}社")

st.dataframe(
    show_df,
    column_config={
        "有報": st.column_config.LinkColumn("📄有報", display_text="開く"),
        "PEG": st.column_config.NumberColumn(format="%.3f"),
        "純利益CAGR(%)": st.column_config.NumberColumn(format="%.1f"),
        "PER": st.column_config.NumberColumn(format="%.1f"),
        "ROE(%)": st.column_config.NumberColumn(format="%.1f"),
        "直近NI成長(%)": st.column_config.NumberColumn(format="%.1f"),
        "時価総額(億円)": st.column_config.NumberColumn(format="%.1f"),
    },
    width="stretch",
    height=400 if not show_all else 800,
    hide_index=True,
)

csv_cols = [c for c in display_cols if c != "有報"]
csv = filtered[csv_cols].to_csv(index=False, encoding="utf-8-sig")
st.download_button("📥 CSV出力", csv, "peg_screening.csv", "text/csv")

# ━━━ チャート ━━━
st.markdown("---")
st.subheader("分布")

chart_col1, chart_col2 = st.columns([3, 2])

with chart_col1:
    fig, ax = plt.subplots(figsize=(8, 5))
    x = filtered["純利益CAGR(%)"].values
    y = filtered["PER"].values

    cagr_line = np.linspace(1, max(x.max() * 1.1, 50), 200)
    for peg_val, color, ls, label in [
        (0.5, "#2ca02c", "--", "PEG=0.5"),
        (1.0, "#1f77b4", "-",  "PEG=1.0"),
        (2.0, "#d62728", ":",  "PEG=2.0"),
    ]:
        per_line = peg_val * cagr_line
        ax.plot(cagr_line, per_line, color=color, ls=ls, lw=1.5, alpha=0.7, label=label)

    colors = ["#2ca02c" if p < 0.5 else "#1f77b4" if p < 1.0 else "#ff7f0e" if p < 2.0 else "#d62728"
              for p in filtered["PEG"].values]
    ax.scatter(x, y, c=colors, alpha=0.6, s=30, edgecolors="white", linewidth=0.3)

    ax.set_xlabel(f"純利益CAGR {period_label} (%)", fontsize=11)
    ax.set_ylabel("PER (倍)", fontsize=11)
    ax.set_title("純利益成長率 × PER（線の下が割安）", fontsize=12)
    ax.legend(loc="upper left", fontsize=9)
    ax.set_xlim(left=0)
    ax.set_ylim(bottom=0, top=min(y.max() * 1.2, 150))
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    st.pyplot(fig, use_container_width=True)

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

# ━━━ 注記 ━━━
st.markdown("---")
st.caption(
    "データ: EDINET DB（有価証券報告書・XBRL由来）｜"
    "PER: 有報期末株価ベース（株式分割調整済み）｜"
    "CAGR: 純利益ベース（株式分割の影響を受けない・上限100%キャップ）｜PER: 2〜200倍の範囲外は除外｜"
    "EDINET DB公式算出値を使用｜"
    "時価総額: J-Quants（取得済み企業のみ）｜"
    "※EPSベースのCAGRは株式分割時に遡及調整されないため（EDINET XBRL仕様）、分割の影響を受けない純利益CAGRを採用"
)
