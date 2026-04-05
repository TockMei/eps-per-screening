"""
利益成長力とPER水準の乖離分析（PEGスクリーニング） v8
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

st.set_page_config(page_title="利益成長力×PER乖離分析", layout="wide")

# ─── データ読み込み ───
@st.cache_data
def load_data():
    with open("screening_data.json", "r") as f:
        return json.load(f)

data = load_data()
master = data["master"]
ratios = data["ratios"]
financials = data.get("financials", {})

# CAGR上限キャップ（赤字→黒字転換による見かけ上の異常値を排除）
CAGR_CAP_PCT = 100.0

PERIOD_LABELS = {"3y": "過去3期", "5y": "過去5期", "10y": "過去10期", "full": "全期間（最大14期）"}
PERIOD_SHORT  = {"3y": "3期", "5y": "5期", "10y": "10期", "full": "全期間"}


def peg_label(peg):
    if peg < 0.5:
        return "🟢 PEG<0.5"
    elif peg < 1.0:
        return "🔵 PEG<1.0"
    elif peg < 2.0:
        return "🟡 PEG<2.0"
    else:
        return "🔴 PEG≧2.0"


def compute_ni_cagr(fin_data, n_years):
    """financials時系列から純利益CAGRを計算。
    fin_data: {"2012": {"net_income": ...}, "2013": {...}, ...}
    n_years: 整数（3,5,10）またはNone（全期間）
    戻り値: float（小数表記 0.08=8%）またはNone
    """
    if not fin_data:
        return None
    years = sorted(fin_data.keys(), key=lambda x: int(x))
    if len(years) < 2:
        return None

    latest_year = years[-1]
    ni_end = fin_data[latest_year].get("net_income")

    if n_years is None:
        start_year = years[0]
    else:
        target_start = str(int(latest_year) - n_years)
        available = [y for y in years if int(y) <= int(target_start)]
        if not available:
            return None
        start_year = available[-1]

    ni_start = fin_data[start_year].get("net_income")

    if ni_start is None or ni_end is None or ni_start <= 0 or ni_end <= 0:
        return None

    actual_years = int(latest_year) - int(start_year)
    if actual_years < 1:
        return None

    return (ni_end / ni_start) ** (1 / actual_years) - 1


@st.cache_data
def build_table(period: str):
    """period: '3y', '5y', '10y', 'full'"""
    n_years_map = {"3y": 3, "5y": 5, "10y": 10, "full": None}
    n_years = n_years_map[period]

    # 3y/5yはEDINET DB公式算出値を優先使用、10y/fullは自前計算
    use_precomputed = period in ("3y", "5y")
    cagr_key = f"ni_cagr_{period}" if use_precomputed else None

    rows = []
    for code, info in master.items():
        r = ratios.get(code, {})
        per = r.get("per")

        if per is None or per <= 2 or per > 200:
            continue

        # CAGR取得
        if use_precomputed:
            cagr = r.get(cagr_key)
        else:
            fin = financials.get(code, {})
            cagr = compute_ni_cagr(fin, n_years)

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
            "PER(倍)": round(per, 1),
            "PEG": round(peg, 3),
            "ROE(%)": roe_pct,
            "直近NI成長(%)": ni_growth_pct,
            "時価総額(億円)": mkt_oku,
        })
    return pd.DataFrame(rows)


# ═══════════════════════════════════════════════════
# ヘッダー
# ═══════════════════════════════════════════════════
st.title("利益成長力とPER水準の乖離分析")
st.caption(
    "PEG = PER ÷ 純利益CAGR(%)　｜　"
    "利益の成長速度に対するPER水準の相対的位置を測定する指標"
)

# ─── 解説セクション ───
with st.expander("PEG比率とは"):
    st.markdown(
        "**PEG比率**（Price/Earnings to Growth）= PER ÷ 利益成長率(%)。\n\n"
        "PERだけでは判断できない「利益成長速度に対するPER水準の相対的位置」を測定する。"
        "PEGが低い＝利益成長速度に対してPERが低い＝成長が株価に十分反映されていない可能性がある。\n\n"
        "| PEG | 区分 | 意味 |\n|---|---|---|\n"
        "| < 0.5 | 🟢 成長対比PER低位 | 成長速度に対しPERが顕著に低い |\n"
        "| 0.5 – 1.0 | 🔵 成長対比PERやや低位 | 成長速度に対しPERがやや低い |\n"
        "| 1.0 – 2.0 | 🟡 成長対比PER中位 | 成長速度とPERが概ね均衡 |\n"
        "| ≧ 2.0 | 🔴 成長対比PER高位 | 成長速度に対しPERが高い |"
    )

with st.expander("なぜEPSではなく純利益CAGRを使用するか"):
    st.markdown(
        "PER（株価収益率）はEPS（1株当たり利益）を分母とするため、"
        "本来PEGの分母もEPS成長率を用いるのが理論的に正確です。\n\n"
        "しかし**EDINET XBRLのEPS時系列は株式分割時に遡及調整されません**"
        "（XBRL仕様上の制約）。"
        "分割が入ると見かけ上EPSが急落し、CAGR計算が破綻します。\n\n"
        "**純利益CAGRを代替とする妥当性:**\n"
        "- 純利益は発行済株式数の変動に影響されないため、分割・併合の影響を完全に排除できる\n"
        "- PER（per_official）はEDINET DB側で分割調整済みのため正確\n"
        "- 希薄化（新株発行による持分の減少）がなければ、EPS CAGRと純利益CAGRは一致する\n"
        "- 大規模増資がある場合のみ純利益CAGRがやや楽観的になるが、"
        "上場企業全体では実務上の乖離は限定的\n\n"
        "EDINET DBは分割調整済みEPS時系列を開発予定とされており、"
        "利用可能になり次第EPSベースに切り替える方針です。"
    )

# ═══════════════════════════════════════════════════
# 操作パネル: 期間選択・ソート方法
# ═══════════════════════════════════════════════════
st.markdown("---")

ctrl_col1, ctrl_col2 = st.columns(2)
with ctrl_col1:
    period = st.selectbox(
        "CAGR算出期間",
        ["3y", "5y", "10y", "full"],
        index=1,
        format_func=lambda x: PERIOD_LABELS[x],
        help="純利益CAGRの算出起点を指定。"
             "3期/5期はEDINET DB公式算出値、10期/全期間は純利益時系列から算出。"
             "起点年度の純利益が赤字の場合はCAGR算出不可（除外）。"
    )
with ctrl_col2:
    sort_option = st.selectbox(
        "ランキング順序",
        ["PEG昇順", "純利益CAGR降順", "PER昇順"],
        index=0,
        help="PEG昇順 = 利益成長速度に対してPERが最も低い順"
    )

period_label = PERIOD_SHORT[period]

# ═══════════════════════════════════════════════════
# プリセット
# ═══════════════════════════════════════════════════
PRESETS = {
    "📊 利益成長×PER乖離": {
        "peg_max": 1.0, "cagr_min": 5.0, "mkt_min": 0,
        "desc": f"純利益CAGR({period_label}) 5%以上 / PEG 1.0以下"
    },
    "📈 高成長×PEG低位": {
        "peg_max": 0.5, "cagr_min": 15.0, "mkt_min": 0,
        "desc": f"CAGR({period_label}) 15%以上 / PEG 0.5以下"
    },
    "🏢 大型・成長対比PER低位": {
        "peg_max": 1.0, "cagr_min": 8.0, "mkt_min": 1000,
        "desc": f"時価総額1,000億超 / CAGR({period_label}) 8%以上 / PEG 1.0以下"
    },
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
else:
    c1, c2, c3 = st.columns(3)
    with c1:
        peg_max = st.number_input(
            "PEG上限", min_value=0.1, max_value=10.0, value=1.0, step=0.1
        )
    with c2:
        cagr_min = st.number_input(
            "純利益CAGR下限(%)", min_value=0.0, max_value=100.0, value=5.0, step=1.0
        )
    with c3:
        mkt_min = st.number_input(
            "時価総額下限(億円)", min_value=0, value=0, step=100,
            help="0=フィルタなし。時価総額はPER×純利益による推計値（有報期末時点）。"
        )

# ═══════════════════════════════════════════════════
# テーブル構築・フィルタ
# ═══════════════════════════════════════════════════
df = build_table(period)

if df.empty:
    st.warning("条件に合致する企業がありません。")
    st.stop()

mask = (df["PEG"] <= peg_max) & (df["純利益CAGR(%)"] >= cagr_min)
if mkt_min > 0:
    mask &= df["時価総額(億円)"].fillna(0) >= mkt_min

filtered = df[mask].copy()

if len(filtered) == 0:
    st.warning("条件に合致する企業がありません。フィルタを緩めてください。")
    st.stop()

# ソート適用
sort_map = {
    "PEG昇順":        ("PEG", True),
    "純利益CAGR降順":  ("純利益CAGR(%)", False),
    "PER昇順":        ("PER(倍)", True),
}
sort_key, sort_asc = sort_map[sort_option]
filtered = filtered.sort_values(sort_key, ascending=sort_asc).reset_index(drop=True)

# ═══════════════════════════════════════════════════
# サマリー指標
# ═══════════════════════════════════════════════════
st.markdown("---")

m1, m2, m3, m4, m5 = st.columns(5)
with m1:
    st.metric("抽出", f"{len(filtered)}社")
with m2:
    st.metric("🟢 PEG<0.5", f"{len(filtered[filtered['PEG'] < 0.5])}社")
with m3:
    st.metric("🔵 PEG<1.0",
              f"{len(filtered[(filtered['PEG'] >= 0.5) & (filtered['PEG'] < 1.0)])}社")
with m4:
    st.metric("中央値PEG", f"{filtered['PEG'].median():.3f}")
with m5:
    st.metric(f"中央値CAGR({period_label})", f"{filtered['純利益CAGR(%)'].median():.1f}%")

# ═══════════════════════════════════════════════════
# ランキングテーブル
# ═══════════════════════════════════════════════════
st.markdown("---")

sort_desc = {
    "PEG昇順":
        "PEG（= PER ÷ 純利益CAGR%）が低い順。"
        "利益成長速度に対してPERが最も低い企業から表示。",
    "純利益CAGR降順":
        f"純利益CAGR（{period_label}）が高い順。"
        "利益の複利成長率が最も高い企業から表示。",
    "PER昇順":
        "PER（有報期末株価ベース・株式分割調整済み）が低い順。",
}
st.subheader(f"ランキング — {sort_option}")
st.caption(f"**並び順の定義:** {sort_desc[sort_option]}")

filtered["判定"] = filtered["PEG"].apply(peg_label)
filtered["有報"] = filtered["edinet_code"].apply(
    lambda c: f"https://edinetdb.jp/company/{c}"
)

display_cols = [
    "判定", "証券コード", "企業名", "業種",
    "純利益CAGR(%)", "PER(倍)", "PEG", "ROE(%)", "直近NI成長(%)",
    "時価総額(億円)", "有報",
]

# 銘柄検索
search_q = st.text_input(
    "🔍 銘柄検索（社名・証券コード）", placeholder="例: トヨタ、7203"
)
if search_q:
    search_mask = (
        filtered["企業名"].str.contains(search_q, case=False, na=False)
        | filtered["証券コード"].str.contains(search_q, na=False)
    )
    filtered = filtered[search_mask].reset_index(drop=True)
    if len(filtered) == 0:
        st.warning(f"「{search_q}」に該当する企業がありません。")
        st.stop()

show_all = st.toggle(f"全{len(filtered)}社を表示", value=False)
show_df = filtered[display_cols] if show_all else filtered[display_cols].head(50)
if not show_all:
    st.caption(f"上位50社を表示中（全{len(filtered)}社）")

st.dataframe(
    show_df,
    column_config={
        "有報": st.column_config.LinkColumn("📄有報", display_text="開く"),
        "PEG": st.column_config.NumberColumn(format="%.3f"),
        "純利益CAGR(%)": st.column_config.NumberColumn(format="%.1f"),
        "PER(倍)": st.column_config.NumberColumn(format="%.1f"),
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

# ═══════════════════════════════════════════════════
# チャート
# ═══════════════════════════════════════════════════
st.markdown("---")
st.subheader("分布")

chart_col1, chart_col2 = st.columns([3, 2])

with chart_col1:
    fig, ax = plt.subplots(figsize=(8, 5))

    # 全データ（フィルタ前）をグレーで背景描画
    all_x = df["純利益CAGR(%)"].values
    all_y = df["PER(倍)"].values
    ax.scatter(all_x, all_y, c="#cccccc", alpha=0.25, s=15,
               edgecolors="none", label=f"全対象企業（{len(df)}社）")

    # PEG等値線
    x_max = max(all_x.max() * 1.1, 50)
    cagr_line = np.linspace(1, x_max, 200)
    for peg_val, color, ls, label in [
        (0.5, "#2ca02c", "--", "PEG=0.5"),
        (1.0, "#1f77b4", "-",  "PEG=1.0"),
        (2.0, "#d62728", ":",  "PEG=2.0"),
    ]:
        per_line = peg_val * cagr_line
        ax.plot(cagr_line, per_line, color=color, ls=ls, lw=1.5,
                alpha=0.7, label=label)

    # フィルタ通過企業を色付きで重ねる
    filt_x = filtered["純利益CAGR(%)"].values
    filt_y = filtered["PER(倍)"].values
    dot_colors = [
        "#2ca02c" if p < 0.5
        else "#1f77b4" if p < 1.0
        else "#ff7f0e" if p < 2.0
        else "#d62728"
        for p in filtered["PEG"].values
    ]
    ax.scatter(filt_x, filt_y, c=dot_colors, alpha=0.7, s=30,
               edgecolors="white", linewidth=0.3,
               label=f"条件該当（{len(filtered)}社）")

    ax.set_xlabel(f"純利益CAGR {period_label} (%)", fontsize=11)
    ax.set_ylabel("PER (倍)", fontsize=11)
    ax.set_title("全上場企業の中での条件該当企業の位置", fontsize=12)
    ax.legend(loc="upper left", fontsize=8)
    ax.set_xlim(left=0, right=min(x_max, 110))
    ax.set_ylim(bottom=0, top=min(all_y.max() * 1.1, 210))
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    st.pyplot(fig, use_container_width=True)
    st.caption(
        "グレー = CAGR・PERの算出が可能な全上場企業　｜　"
        "色付き = 現在のフィルタ条件を満たす企業　｜　"
        "線はPEG等値線（線の下ほどPEGが低い）"
    )

with chart_col2:
    # 業種別 該当企業の割合
    ind_total = df["業種"].value_counts()
    ind_hit = filtered["業種"].value_counts()
    # 母集団5社以上の業種のみ
    valid_inds = ind_total[ind_total >= 5].index
    hit_rate = {}
    for ind in valid_inds:
        total = ind_total[ind]
        hit = ind_hit.get(ind, 0)
        if hit > 0:
            hit_rate[ind] = (hit / total * 100, hit, total)
    if hit_rate:
        # 該当率降順でソート、上位15業種
        sorted_inds = sorted(hit_rate.keys(),
                             key=lambda x: -hit_rate[x][0])[:15]
        labels = sorted_inds[::-1]
        rates = [hit_rate[i][0] for i in labels]
        annotations = [f"{hit_rate[i][1]}/{hit_rate[i][2]}"
                       for i in labels]

        fig2, ax2 = plt.subplots(figsize=(6, 5))
        bars = ax2.barh(range(len(labels)), rates, color="#4c78a8", height=0.6)
        ax2.set_yticks(range(len(labels)))
        ax2.set_yticklabels(labels)
        ax2.set_xlabel("該当企業の割合 (%)", fontsize=11)
        ax2.set_title("業種別 該当企業の割合", fontsize=12)
        for j, bar in enumerate(bars):
            w = bar.get_width()
            ax2.text(w + 0.5, bar.get_y() + bar.get_height() / 2,
                     f"{rates[j]:.0f}%（{annotations[j]}社）",
                     va="center", fontsize=8)
        ax2.set_xlim(right=max(rates) * 1.4)
        fig2.tight_layout()
        st.pyplot(fig2, use_container_width=True)
        st.caption(
            "各業種の全対象企業のうち、現在の条件を満たす企業が占める割合"
            "（母集団5社未満の業種は除外）"
        )
    else:
        st.info("該当企業が少なく業種別割合を表示できません。")

# ═══════════════════════════════════════════════════
# 注記
# ═══════════════════════════════════════════════════
st.markdown("---")
st.caption(
    "**データソース:** EDINET DB（有価証券報告書・XBRL由来）　"
    "**PER:** 有報期末株価ベース・株式分割調整済み（EDINET DB per_official）　"
    "**CAGR:** 純利益ベース（株式分割の影響を受けない）、上限100%キャップ　"
    "**フィルタ:** PER 2〜200倍の範囲外は除外 / 起点純利益が赤字の場合はCAGR算出不可（除外）　"
    "**時価総額:** PER×純利益による推計値（有報期末時点・純利益が正の企業のみ）"
)
st.caption(
    "**EPSベースCAGRを使用しない理由:** "
    "EDINET XBRLのEPS時系列は株式分割時に遡及調整されない仕様のため、"
    "分割の影響を受けない純利益CAGRを採用。"
    "PER（per_official）は分割調整済み。"
    "希薄化（大規模増資）がなければEPS CAGRと純利益CAGRは一致する。"
)
st.caption(
    "**注意:** CAGRは起点の利益水準が低い企業ほど高く算出される傾向がある。"
    "赤字から黒字への回復局面と構造的な成長を区別する必要がある。"
    "本分析は特定銘柄の投資推奨を目的としたものではない。"
)
