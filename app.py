#!/usr/bin/env python3
"""EPS成長×PER乖離スクリーニング v3.1 — Streamlit Cloud版
screening_data.json（bundle）から読み込み。J-Quants APIは使用しない。"""
import json, re
from pathlib import Path
import streamlit as st
import pandas as pd

st.set_page_config(page_title="EPS×PER乖離スクリーニング", layout="wide")

DATA_FILE = Path(__file__).parent / "screening_data.json"

PRESETS = {
    "📈 成長割安（長期10年）": {
        "start_year": 2014, "end_year": 2024, "min_ni_cagr": 10,
        "max_per": 20, "min_market_cap_bn": 100, "w_cagr": 1.2, "w_per": 0.8,
        "use_fcf": False, "min_years": 5,
        "desc": "2014→2024年の10年間で純利益CAGR10%以上、PER20倍以下の割安成長株（起点データなしは最低5年で動的補完）"
    },
    "🚀 急成長（直近3年）": {
        "start_year": 2021, "end_year": 2024, "min_ni_cagr": 20,
        "max_per": 30, "min_market_cap_bn": 50, "w_cagr": 1.5, "w_per": 0.5,
        "use_fcf": False, "min_years": 3,
        "desc": "2021→2024年の3年間で純利益CAGR20%以上、PER30倍以下の銘柄"
    },
    "🏢 大型割安（5年）": {
        "start_year": 2019, "end_year": 2024, "min_ni_cagr": 8,
        "max_per": 15, "min_market_cap_bn": 1000, "w_cagr": 1.0, "w_per": 1.2,
        "use_fcf": False, "min_years": 5,
        "desc": "時価総額1,000億円超・5年CAGR8%以上・PER15倍以下の大型割安株"
    },
    "💎 超長期複利（12年）": {
        "start_year": 2012, "end_year": 2024, "min_ni_cagr": 8,
        "max_per": 25, "min_market_cap_bn": 200, "w_cagr": 1.0, "w_per": 1.0,
        "use_fcf": False, "min_years": 7,
        "desc": "2012→2024年の12年間で純利益CAGR8%以上を維持している長期複利銘柄（起点データなしは最低7年で動的補完）"
    },
    "🔬 テンバガー候補（FCF重視）": {
        "start_year": 2019, "end_year": 2024, "min_ni_cagr": 8,
        "max_per": 25, "min_market_cap_bn": 50, "w_cagr": 1.0, "w_per": 1.0,
        "use_fcf": True, "min_years": 5,
        "desc": "Birmingham City Univ.論文(2025)準拠：小型×高FCF利回り×高収益×投資の質チェック"
    },
    "💰 ネットキャッシュ割安": {
        "start_year": 2019, "end_year": 2024, "min_ni_cagr": 5,
        "max_per": 20, "min_market_cap_bn": 50, "w_cagr": 0.8, "w_per": 1.2,
        "use_fcf": False, "min_years": 5,
        "desc": "ネット有利子負債がマイナス（実質ネットキャッシュ）かつ割安な銘柄（清原式）"
    },
    "⚙️ カスタム": {
        "start_year": 2014, "end_year": 2024, "min_ni_cagr": 10,
        "max_per": 25, "min_market_cap_bn": 100, "w_cagr": 1.0, "w_per": 1.0,
        "use_fcf": False, "min_years": 5,
        "desc": "パラメータを自由に設定"
    },
}

@st.cache_data
def load_bundle():
    bundle = json.loads(DATA_FILE.read_text("utf-8"))
    return bundle["master"], bundle["financials"], bundle["ratios"], bundle.get("price_cache", {})

def calc_cagr(v_end, v_start, years):
    if not all([v_end, v_start]) or v_start <= 0 or v_end <= 0 or years <= 0:
        return None
    return (v_end / v_start) ** (1.0 / years) - 1

def run_screening(params, fins, master, ratios, price_cache):
    sy, ey    = params["start_year"], params["end_year"]
    min_years = params.get("min_years", 5)
    use_fcf   = params.get("use_fcf", False)
    preset    = params.get("preset_name", "")
    results   = []
    codes     = list(fins.keys())
    prog      = st.progress(0)
    txt       = st.empty()

    for i, ec in enumerate(codes):
        prog.progress((i+1)/len(codes))
        if i % 500 == 0:
            txt.text(f"{i}/{len(codes)}社処理中")
        by = fins[ec]
        m  = master.get(ec, {})
        sc = m.get("sec_code", "")
        if not sc or not re.match(r'^\d+$', str(sc)):
            continue

        ni1  = by.get(str(ey), {}).get("net_income")
        eps1 = by.get(str(ey), {}).get("eps")
        if not ni1 or ni1 <= 0 or not eps1 or eps1 <= 0:
            continue

        ni0 = by.get(str(sy), {}).get("net_income")
        actual_sy = sy
        if ni0 is None or ni0 <= 0:
            actual_sy = None
            for yr in range(sy, ey - min_years + 1):
                candidate = by.get(str(yr), {}).get("net_income")
                if candidate and candidate > 0:
                    actual_sy = yr
                    ni0 = candidate
                    break
            if actual_sy is None:
                continue

        yspan = ey - actual_sy
        if yspan < min_years:
            continue

        g = calc_cagr(ni1, ni0, yspan)
        if g is None or g*100 < params["min_ni_cagr"]:
            continue

        rat      = ratios.get(ec, {})
        per      = rat.get("per")
        fcf      = rat.get("fcf")
        ebitda   = rat.get("ebitda")
        net_debt = rat.get("net_debt")
        oi_cagr3 = rat.get("oi_cagr_3y")
        gross_m  = rat.get("gross_margin")
        net_m    = rat.get("net_margin")
        equity_r = rat.get("equity_ratio")

        if not per or per <= 0 or per > params["max_per"]:
            continue

        mc = ni1 * per / 1e8
        if mc < params["min_market_cap_bn"]:
            continue

        price = price_cache.get(f"{sc}_2024-03-31")

        if preset == "💰 ネットキャッシュ割安":
            if net_debt is None or net_debt >= 0:
                continue

        mc_yen = mc * 1e8
        fcf_yield = None
        if fcf is not None and mc_yen > 0:
            fcf_yield = fcf / mc_yen

        if use_fcf:
            if fcf_yield is None or fcf_yield <= 0:
                continue

        score = g*100*params["w_cagr"] - per*params["w_per"]
        if use_fcf and fcf_yield:
            score += fcf_yield * 100 * 0.5

        row = {
            "企業名":           m.get("name","")[:20],
            "業種":             m.get("industry","不明")[:10],
            "証券コード":       sc,
            "有報全文":         f"https://edinetdb.jp/company/{ec}/text",
            "起点年":           actual_sy,
            "純利益起点(百万)": round(ni0/1e6, 0),
            f"純利益{ey}(億)":  round(ni1/1e8, 1),
            "データ期間":       f"{actual_sy}→{ey}({yspan}年)",
            "CAGR(%)":          round(g*100, 1),
            "PER(倍)":          round(per, 1),
            "時価総額(億)":     round(mc, 0),
            "乖離スコア":       round(score, 2),
        }
        if price:
            row["株価参考"] = round(price, 0)
        if fcf is not None:
            row["FCF(億)"] = round(fcf/1e8, 1)
        if fcf_yield is not None:
            row["FCF利回り(%)"] = round(fcf_yield*100, 1)
        if net_debt is not None:
            row["ネット有利負債(億)"] = round(net_debt/1e8, 0)
        if oi_cagr3 is not None:
            row["OI_CAGR3y(%)"] = round(oi_cagr3*100, 1)
        if gross_m is not None:
            row["粗利率(%)"] = round(gross_m*100, 1)
        if net_m is not None:
            row["純利益率(%)"] = round(net_m*100, 1)
        if equity_r is not None:
            row["自己資本比率(%)"] = round(equity_r*100, 1)

        results.append(row)

    prog.empty(); txt.empty()
    if not results:
        return pd.DataFrame()
    df = pd.DataFrame(results).sort_values("乖離スコア", ascending=False).reset_index(drop=True)
    df.index += 1
    return df

# ---- UI ----
st.title("📊 EPS成長 × PER乖離スクリーニング v3.1")
st.caption("純利益CAGR・FCF利回り・テンバガー論文指標を統合したスクリーニング ｜ ⚠️ J-Quantsデータは個人利用限定")

master, fins, ratios, price_cache = load_bundle()

preset_name = st.radio("スクリーニングパターン", list(PRESETS.keys()), horizontal=True, index=0)
preset = PRESETS[preset_name]
st.info(f"💡 {preset['desc']}")

if preset_name == "⚙️ カスタム":
    c1, c2 = st.columns(2)
    with c1:
        sy  = st.selectbox("起点年", list(range(2012, 2024)), index=2)
        ey  = st.selectbox("終点年", list(range(2013, 2025)), index=11)
        mnc = st.slider("最低CAGR(%)", 0, 50, 10)
        use_fcf = st.checkbox("FCF利回りフィルタ（FCF>0のみ）", value=False)
    with c2:
        mp  = st.slider("最大PER(倍)", 5, 100, 25)
        mmc = st.slider("最低時価総額(億)", 0, 5000, 100, 50)
        wc  = st.slider("CAGR重み", 0.0, 2.0, 1.0, 0.1)
        wp  = st.slider("低PER重み", 0.0, 2.0, 1.0, 0.1)
        myr = st.slider("最低データ期間（年）", 3, 10, 5)
    params = {"start_year":sy,"end_year":ey,"min_ni_cagr":mnc,"max_per":mp,
              "min_market_cap_bn":mmc,"w_cagr":wc,"w_per":wp,"use_fcf":use_fcf,
              "preset_name":preset_name,"min_years":myr}
else:
    params = {k: preset[k] for k in
              ["start_year","end_year","min_ni_cagr","max_per","min_market_cap_bn","w_cagr","w_per","use_fcf","min_years"]}
    params["preset_name"] = preset_name
    yspan = params["end_year"] - params["start_year"]
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("分析期間",    f"{params['start_year']}→{params['end_year']}年（{yspan}年）")
    c2.metric("最低CAGR",   f"{params['min_ni_cagr']}%")
    c3.metric("最大PER",    f"{params['max_per']}倍")
    c4.metric("最低時価総額",f"{params['min_market_cap_bn']}億円")

run_btn = st.button("🔍 実行", type="primary")

for key in ["df_result","last_params","last_preset"]:
    if key not in st.session_state:
        st.session_state[key] = None

if run_btn or st.session_state.df_result is None:
    with st.spinner("スクリーニング実行中..."):
        df = run_screening(params, fins, master, ratios, price_cache)
    st.session_state.df_result   = df
    st.session_state.last_params = params
    st.session_state.last_preset = preset_name

df = st.session_state.df_result
p  = st.session_state.last_params

if df is not None and len(df) > 0 and p:
    cagr_col = "CAGR(%)"
    st.markdown("---")
    c1,c2,c3,c4,c5 = st.columns(5)
    c1.metric("抽出企業数",     f"{len(df)}社")
    c2.metric("CAGR中央値",     f"{df[cagr_col].median():.1f}%")
    c3.metric("PER中央値",      f"{df['PER(倍)'].median():.1f}倍")
    c4.metric("最高乖離スコア", f"{df['乖離スコア'].max():.1f}")
    full_span = df[df["起点年"] == p["start_year"]]
    c5.metric("フルスパン率",   f"{len(full_span)}/{len(df)}社")

    st.subheader(f"📋 結果（{st.session_state.last_preset}）")
    st.caption(f"乖離スコア = CAGR(%) × {p['w_cagr']} − PER × {p['w_per']}" +
               (" + FCF利回り×50" if p.get("use_fcf") else "") +
               f" ｜ 起点年データなしの企業は最古有効年を動的起点（最低{p.get('min_years',5)}年要件）")

    base_cols = ["企業名","業種","証券コード","有報全文","データ期間",
                 "純利益起点(百万)",f"純利益{p['end_year']}(億)",
                 cagr_col,"PER(倍)","時価総額(億)","乖離スコア","株価参考"]
    extra_cols = ["FCF(億)","FCF利回り(%)","ネット有利負債(億)","OI_CAGR3y(%)","粗利率(%)","純利益率(%)","自己資本比率(%)"]
    dcols = [c for c in base_cols + extra_cols if c in df.columns]

    fmt = {}
    for col in dcols:
        if col in ["企業名","業種","証券コード","データ期間","有報全文"]:
            continue
        elif col in [cagr_col,"FCF利回り(%)","OI_CAGR3y(%)","粗利率(%)","純利益率(%)","自己資本比率(%)"]:
            fmt[col] = "{:.1f}"
        elif col in ["PER(倍)","乖離スコア"]:
            fmt[col] = "{:.1f}"
        elif col in ["純利益起点(百万)",f"純利益{p['end_year']}(億)",
                     "時価総額(億)","FCF(億)","ネット有利負債(億)","株価参考"]:
            fmt[col] = "{:.0f}"

    styled = df[dcols].style.format(fmt, na_rep="-")
    if cagr_col in dcols:
        styled = styled.background_gradient(subset=[cagr_col], cmap="Greens")
    if "PER(倍)" in dcols:
        styled = styled.background_gradient(subset=["PER(倍)"], cmap="RdYlGn_r")
    if "乖離スコア" in dcols:
        styled = styled.background_gradient(subset=["乖離スコア"], cmap="Blues")
    if "FCF利回り(%)" in dcols:
        styled = styled.background_gradient(subset=["FCF利回り(%)"], cmap="Oranges")
    st.dataframe(styled, use_container_width=True, height=650,
                   column_config={"有報全文": st.column_config.LinkColumn("有報全文", display_text="📄開く")})

    st.download_button("📥 CSVダウンロード（内部用・非公開）",
                       df.to_csv(index=True, encoding="utf-8-sig"),
                       f"eps_per_{p['start_year']}_{p['end_year']}.csv", "text/csv")

    st.markdown("---")
    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("業種別分布")
        ind = df["業種"].value_counts().reset_index()
        ind.columns = ["業種","社数"]
        st.bar_chart(ind.set_index("業種")["社数"], height=300)
    with col_b:
        if "FCF利回り(%)" in df.columns:
            st.subheader("FCF利回り分布")
            fcf_pos = df[df["FCF利回り(%)"] > 0]["FCF利回り(%)"]
            if len(fcf_pos) > 0:
                st.bar_chart(fcf_pos.value_counts(bins=10).sort_index(), height=300)

elif df is not None and len(df) == 0:
    st.warning("条件に合う企業が見つかりませんでした。フィルタを緩めてください。")
