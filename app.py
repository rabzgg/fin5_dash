"""
ESG Pay Reality Check  ──  ExComp module
=========================================
ESG-linked executive bonuses are now standard. But are the targets a genuine stretch,
and what is the money actually rewarding?

A screening tool on ESG-linked executive pay (DSW ESG data, 2023 + 2024):
  Punch 1  "Too easy?"       ESG bonus weight vs target achievement (targets are almost always hit)
  Punch 2  "Real teeth?"     emission targets exist but are deferred to LONG-TERM pay; the ANNUAL
                             bonus's ESG leans on softer social / governance criteria

This is a SCREENING signal, not a verdict. It flags packages worth scrutinising; it does not
prove greenwashing. Every flag is interpretable and honest about its limits.

Run:  streamlit run esg_pay_reality_check.py
"""

import os
import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

# ──────────────────────────────────────────────────────────────────────────────
# CONFIG
# ──────────────────────────────────────────────────────────────────────────────
ESG_FILE_CANDIDATES = [
    ["Executive_Compensation_ESG_2023.xlsx", "Executive_Compensation_ESG_2024.xlsx"],
    ["Data/2023/Executive_Compensation_ESG_2023.xlsx", "Data/2024/Executive_Compensation_ESG_2024.xlsx"],
]

WEIGHT_HIGH = 20.0     # ESG weight in STI bonus is "high" at or above this %
ACHIEVE_HIT = 100.0    # target counts as "hit" at or above this %

ACCENT  = "#1D9E75"    # green/teal
WARN    = "#E2A33B"    # amber
DANGER  = "#D1493F"    # red
SOFT    = "#9AA0A6"    # grey
INK     = "#2B2B2B"

st.set_page_config(page_title="ESG Pay Reality Check", layout="wide")


# ──────────────────────────────────────────────────────────────────────────────
# ROBUST PARSING (data is messy: German decimal commas, "3; 3" multi-values)
# ──────────────────────────────────────────────────────────────────────────────
def _clean_scalar(v):
    if v is None:
        return np.nan
    v = str(v).split(";")[0].strip()
    v = "".join(ch for ch in v if ch in "0123456789,.-")
    if v in ("", "-", ".", ","):
        return np.nan
    v = v.replace(",", ".") if ("," in v and "." not in v) else v.replace(",", "")
    try:
        return float(v)
    except ValueError:
        return np.nan


def to_num(series):
    return series.map(_clean_scalar)


def to_flag(series):
    n = to_num(series)
    return pd.Series(np.where(n.notna(), (n > 0).astype(float), np.nan), index=series.index)


# ──────────────────────────────────────────────────────────────────────────────
# LOAD
# ──────────────────────────────────────────────────────────────────────────────
@st.cache_data
def load_data():
    files = next((fs for fs in ESG_FILE_CANDIDATES if all(os.path.exists(f) for f in fs)), None)
    if files is None:
        st.error("Could not find the ESG xlsx files. Edit ESG_FILE_CANDIDATES at the top of the script.")
        st.stop()

    frames = []
    for f in files:
        d = pd.read_excel(f, header=2)
        d.columns = [str(c).strip() for c in d.columns]   # FIX: strip trailing-space headers
        frames.append(d)
    df = pd.concat(frames, ignore_index=True)

    out = pd.DataFrame()
    out["company"] = df.get("cnameshort")
    out["index"]   = df.get("cindex")
    out["year"]    = pd.to_numeric(df.get("year"), errors="coerce")

    # ESG weight in the STI bonus. BUG FIX: cap to 0..100 so the 16,663,333 error can't pollute the mean.
    weight = to_num(df.get("STI_total_ESG_Share"))
    out["esg_weight"] = weight.where((weight >= 0) & (weight <= 100))

    # ESG target achievement (already %, 118 = 118%).
    ach = to_num(df.get("STI_Zielerreichung"))
    out["achievement"] = ach.where((ach >= 0) & (ach <= 300))

    # Emission KPIs: measure in STI, in LTI, and in EITHER (the honest, defensible version).
    em_sti = to_flag(df.get("STI_E_KPI_Emission reduction"))
    em_lti = to_flag(df["LTI_E_KPI_Emission reduction"]) if "LTI_E_KPI_Emission reduction" in df.columns else pd.Series(np.nan, index=df.index)
    out["emission_sti"] = em_sti
    out["emission_lti"] = em_lti
    out["emission_any"] = pd.concat([em_sti, em_lti], axis=1).max(axis=1)   # 1 if either, NaN only if both NaN

    # What kind of ESG is in the ANNUAL (STI) bonus?
    out["has_E"] = to_flag(df.get("STI_E_KPI"))
    out["has_S"] = to_flag(df.get("STI_S_KPI"))
    out["has_G"] = to_flag(df.get("STI_G_KPI"))
    out["n_kpi"] = to_num(df.get("STI_count_of_total_ESG_KPI"))

    return out.dropna(subset=["company"])


df = load_data()


MASTER_DB_CANDIDATES = ["2008-2024_longitudinal.csv", "Data/2008-2024_longitudinal.csv",
                        "fin5/csv_data/2008-2024_longitudinal.csv"]


@st.cache_data
def load_master():
    """Master longitudinal DB: per-company TSR lookup + market-context (Test A) + general pattern (Test B)."""
    path = next((p for p in MASTER_DB_CANDIDATES if os.path.exists(p)), None)
    if path is None:
        return None
    m = pd.read_csv(path, sep="|", low_memory=False)
    m["year"] = pd.to_numeric(m["year"], errors="coerce")
    m["tsr"] = pd.to_numeric(m.get("tsr"), errors="coerce")
    m["one_year_bonus"] = pd.to_numeric(m.get("one_year_bonus"), errors="coerce")
    m["name"] = m["new_cnameshort"].astype(str).str.strip()
    m.loc[m["new_cnameshort"].isna(), "name"] = m["company_shortname"].astype(str).str.strip()

    tsr_lookup = m.dropna(subset=["tsr"]).groupby(["name", "year"])["tsr"].first().reset_index()

    co = m.dropna(subset=["tsr"]).drop_duplicates(["name", "year"])   # TSR is per company, repeated per exec
    test_a = (co.groupby("year")
                .agg(median_tsr=("tsr", "median"),
                     pct_neg=("tsr", lambda s: (s < 0).mean() * 100),
                     n=("tsr", "size")).reset_index())

    d = m.dropna(subset=["tsr", "one_year_bonus"]).copy()
    d["neg"] = d["tsr"] < 0
    test_b = (d.groupby("neg")
                .agg(pct_bonus=("one_year_bonus", lambda s: (s > 0).mean() * 100),
                     median_bonus=("one_year_bonus", "median"),
                     n=("one_year_bonus", "size")).reset_index())
    return {"tsr_lookup": tsr_lookup, "test_a": test_a, "test_b": test_b}


master = load_master()

# ──────────────────────────────────────────────────────────────────────────────
# HEADER
# ──────────────────────────────────────────────────────────────────────────────
st.title("ESG Pay Reality Check")
st.caption("ESG-linked executive pay — DSW data, 2023–2024. A screening tool, not a verdict.")

# ──────────────────────────────────────────────────────────────────────────────
# SIDEBAR
# ──────────────────────────────────────────────────────────────────────────────
st.sidebar.header("Filters")
years = sorted(df["year"].dropna().unique().tolist())
idxs  = sorted([x for x in df["index"].dropna().unique().tolist()])
sel_year = st.sidebar.multiselect("Year", years, default=years)
sel_idx  = st.sidebar.multiselect("Index", idxs, default=idxs)

f = df[df["year"].isin(sel_year) & df["index"].isin(sel_idx)].copy()
if f.empty:
    st.warning("No rows for the current filters.")
    st.stop()

# ──────────────────────────────────────────────────────────────────────────────
# SHARED COMPUTATIONS (used by hero + tabs)
# ──────────────────────────────────────────────────────────────────────────────
a = f["achievement"].dropna()
w = f["esg_weight"].dropna()
e_any = f["emission_any"].dropna()
median_ach = a.median() if len(a) else float("nan")
hit_rate = (a >= ACHIEVE_HIT).mean() * 100 if len(a) else float("nan")

bad = pd.DataFrame()
if master is not None:
    j = f.merge(master["tsr_lookup"], left_on=["company", "year"], right_on=["name", "year"], how="left")
    bad = j[(j["achievement"] >= ACHIEVE_HIT) & (j["tsr"] < 0)].copy()

# ──────────────────────────────────────────────────────────────────────────────
# HERO — the one punch (always visible)
# ──────────────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown('## German boards almost never miss their "green" pay targets')

h1, h2, h3 = st.columns(3)
h1.metric("Median ESG-target achievement", f"{median_ach:.0f}%" if len(a) else "n/a",
          help="100% = exactly on target. Above 100% = beat the target.")
h2.metric("Hit or beat their ESG target", f"{hit_rate:.0f}%" if len(a) else "n/a")
if not bad.empty:
    h3.metric("Cashed in full while shareholders LOST money", f"{len(bad)} firms")
else:
    h3.metric("Have an emission target somewhere", f"{e_any.mean()*100:.0f}%" if len(e_any) else "n/a")

if not bad.empty:
    worst = bad.sort_values("tsr").head(3)
    names = ", ".join(f"{r['company']} ({r['tsr']*100:.0f}%)" for _, r in worst.iterrows())
    st.markdown(
        f"A genuine stretch goal would not be hit this reliably. And the green bonus pays out even when "
        f"shareholders suffer — **{len(bad)} companies hit their ESG target in a year their shareholders "
        f"lost money** (worst: {names}).")
else:
    st.markdown(
        "A genuine stretch goal would not be hit this reliably. The tabs below show where the climate teeth "
        "sit and which companies warrant a closer look.")

st.caption("Screening signal, not a verdict — we flag packages worth scrutinising, we do not prove greenwashing. "
           "'Pays out when shareholders lose' means decoupled from shareholder value, not that the target was fake.")

# ──────────────────────────────────────────────────────────────────────────────
# TABS — depth on demand
# ──────────────────────────────────────────────────────────────────────────────
tab_break, tab_who, tab_fluke = st.tabs(
    ["📊 The breakdown", "🔍 Which companies", "🧪 Is it a fluke?"])

# ---- TAB 1: THE BREAKDOWN (Punch 1 + Punch 2) ----
with tab_break:
    st.markdown("#### Are the targets too easy?")
    st.markdown(
        "*If a big slice of the bonus rides on ESG but the target is hit almost every time, the ESG "
        "component looks less like a stretch goal and more like a reliable payout.*")

    scat = f.dropna(subset=["esg_weight", "achievement"])
    if not scat.empty:
        fig = px.scatter(
            scat, x="esg_weight", y="achievement",
            color="index", hover_name="company",
            hover_data={"year": True, "esg_weight": ":.1f", "achievement": ":.1f"},
            opacity=0.75, template="plotly_white",
            labels={"esg_weight": "ESG share of bonus (%)", "achievement": "Target achievement (%)"},
        )
        fig.update_traces(marker=dict(size=10, line=dict(width=0.5, color="white")))
        fig.add_hline(y=ACHIEVE_HIT, line_dash="dash", line_color=DANGER,
                      annotation_text="100% — target hit", annotation_position="top left")
        fig.add_vrect(x0=WEIGHT_HIGH, x1=105, fillcolor=WARN, opacity=0.06, line_width=0)
        fig.update_layout(xaxis_range=[-3, 105], yaxis_range=[-10, 250],
                          legend_title_text="Index", margin=dict(l=40, r=20, t=20, b=40), height=460)
        st.plotly_chart(fig, use_container_width=True)
        st.markdown(
            f"**Takeaway:** {hit_rate:.0f}% of company-years met or beat their ESG target "
            f"(median {median_ach:.0f}%). *(Caveat: bonuses overshoot in general; the strongest test compares "
            f"ESG achievement against the same firm's financial-target achievement, which needs a second source.)*")
    else:
        st.info("Not enough weight/achievement data under current filters.")

    st.markdown("---")
    st.markdown("#### Where are the climate teeth?")
    st.markdown(
        "*Emission targets exist, but mostly in LONG-TERM pay. The ANNUAL bonus's 'ESG' leans on softer "
        "social and governance criteria.*")

    sti = f["emission_sti"].dropna().mean() * 100 if f["emission_sti"].notna().any() else 0
    lti = f["emission_lti"].dropna().mean() * 100 if f["emission_lti"].notna().any() else 0
    place = pd.DataFrame({"Plan": ["Annual bonus (STI)", "Long-term plan (LTI)"], "Share": [round(sti), round(lti)]})
    b1 = px.bar(place, x="Share", y="Plan", orientation="h", template="plotly_white", text="Share",
                labels={"Share": "% with an emission-reduction KPI"})
    b1.update_traces(marker_color=[SOFT, ACCENT], texttemplate="%{text}%", textposition="outside", cliponaxis=False)
    b1.update_layout(yaxis=dict(autorange="reversed"), xaxis_range=[0, 100],
                     margin=dict(l=10, r=30, t=10, b=30), height=170, showlegend=False)
    st.markdown("**Emission targets sit in long-term pay, not the annual bonus**")
    st.plotly_chart(b1, use_container_width=True)

    comp = pd.DataFrame({
        "Annual-bonus ESG type": ["Environmental", "Social", "Governance"],
        "Share": [round(f["has_E"].mean()*100), round(f["has_S"].mean()*100), round(f["has_G"].mean()*100)],
    })
    b2 = px.bar(comp, x="Share", y="Annual-bonus ESG type", orientation="h", template="plotly_white", text="Share",
                labels={"Share": "% of companies (STI KPIs)"})
    b2.update_traces(marker_color=[ACCENT, WARN, SOFT], texttemplate="%{text}%", textposition="outside", cliponaxis=False)
    b2.update_layout(yaxis=dict(autorange="reversed"), xaxis_range=[0, 100],
                     margin=dict(l=10, r=30, t=10, b=30), height=200, showlegend=False)
    st.markdown("**Inside the annual bonus, 'ESG' is mostly social, not environmental**")
    st.plotly_chart(b2, use_container_width=True)
    st.caption(
        f"Only {sti:.0f}% put an emission target in the annual bonus, while {lti:.0f}% keep it in the "
        f"long-term plan. Climate goals are real but deferred.")

# ---- TAB 2: WHICH COMPANIES (screening + reality table) ----
with tab_who:
    st.markdown("#### Heavy ESG marketing, soft ESG substance?")
    st.markdown(
        "*One point each for: high ESG weight, target hit, and no emission target anywhere. "
        "A higher score is a signal worth a closer look, not proof of greenwashing.*")

    s = f.copy()
    s["f_high_weight"] = (s["esg_weight"] >= WEIGHT_HIGH).astype("Int64")
    s["f_target_hit"]  = (s["achievement"] >= ACHIEVE_HIT).astype("Int64")
    s["f_no_emission"] = (s["emission_any"] == 0).astype("Int64")
    s["Screening score (0–3)"] = s[["f_high_weight", "f_target_hit", "f_no_emission"]].sum(axis=1, min_count=1)
    table = (s.sort_values(["Screening score (0–3)", "esg_weight"], ascending=[False, False])
               .assign(**{
                   "ESG weight %": s["esg_weight"].round(1),
                   "Achievement %": s["achievement"].round(0),
                   "Emission KPI (any)": s["emission_any"].map({1: "Yes", 0: "No"}),
               })
               [["company", "year", "index", "ESG weight %", "Achievement %", "Emission KPI (any)", "Screening score (0–3)"]]
               .rename(columns={"company": "Company", "year": "Year", "index": "Index"}))
    st.dataframe(table, use_container_width=True, hide_index=True)

    if not bad.empty:
        bt = bad.copy()
        bt["Achievement %"] = bt["achievement"].round(0)
        bt["Shareholder return %"] = (bt["tsr"] * 100).round(0)
        bt = (bt.sort_values("tsr")[["company", "year", "Achievement %", "Shareholder return %"]]
                .rename(columns={"company": "Company", "year": "Year"}))
        st.markdown("---")
        st.markdown(f"**{len(bt)} companies hit their ESG bonus target in a year their shareholders lost money:**")
        st.dataframe(bt, use_container_width=True, hide_index=True)
        st.caption("Decoupling from shareholder value — NOT proof the ESG target was easy (ESG outcomes and "
                   "stock returns differ). Matched to the master DB for the ~57% of firms whose names align.")

# ---- TAB 3: IS IT A FLUKE? (Test A + Test B) ----
with tab_fluke:
    if master is None:
        st.info("Master database not found — robustness checks need 2008-2024_longitudinal.csv. "
                "Edit MASTER_DB_CANDIDATES at the top of the script.")
    else:
        st.markdown(
            "*Two checks against the master database. Shareholder-return data covers 2022–2024 "
            "(one down market year, two up), so this is a short-window check*")
        r1, r2 = st.columns(2)
        with r1:
            ta = master["test_a"]
            ta = ta[(ta["year"] >= 2008) & (ta["year"] <= 2024)].copy()
            ta["median_tsr_pct"] = (ta["median_tsr"] * 100).round(0)
            figA = px.bar(ta, x="year", y="median_tsr_pct", template="plotly_white",
                          labels={"median_tsr_pct": "Median shareholder return (%)", "year": "Year"})
            figA.update_traces(marker_color=[DANGER if v < 0 else ACCENT for v in ta["median_tsr_pct"]])
            figA.add_hline(y=0, line_color="#888")
            figA.update_layout(margin=dict(l=10, r=10, t=10, b=30), height=260, showlegend=False)
            st.markdown("**Test A — the market was UP in 2023–2024**")
            st.plotly_chart(figA, use_container_width=True)
            st.caption("2023 (+23%) and 2024 (+13%) were good market years — matching the actual DAX total return "
                       "(+20% and +18%) — so firms paying full ESG bonuses while their shareholders lost 20–30% "
                       "were genuine underperformers, not crash victims. ~40 large-cap firms per year.")
        with r2:
            tb = master["test_b"].set_index("neg")
            pct_neg = tb.loc[True, "pct_bonus"] if True in tb.index else float("nan")
            mb_pos = tb.loc[False, "median_bonus"] if False in tb.index else float("nan")
            mb_neg = tb.loc[True, "median_bonus"] if True in tb.index else float("nan")
            drop = (1 - mb_neg / mb_pos) * 100 if mb_pos else float("nan")
            st.markdown("**Test B — in 2022–2024 (one down year + two up years)**")
            m1, m2 = st.columns(2)
            m1.metric("Still got a bonus when shareholders LOST money", f"{pct_neg:.0f}%")
            m2.metric("How much the bonus dropped in those years", f"−{drop:.0f}%")
            st.caption("Most executives kept a substantial bonus even when shareholders lost money; the bonus "
                       "dropped only about a third.")

# ──────────────────────────────────────────────────────────────────────────────
# METHODOLOGY + CAVEATS
# ──────────────────────────────────────────────────────────────────────────────
with st.expander("Methodology & caveats (read before quoting a number)"):
    st.markdown(
        f"""
- **Data:** DSW ESG remuneration data, reporting years 2023–2024. N = {len(df)} company-years.
- **Sample balance:** the data is 2023-weighted (88 company-years vs 40 in 2024; no 2022 in the dashboard). The
  headline finding is robust to this: median ESG-target achievement is 119% in 2023 and 118% in 2024, with hit
  rates of 71% vs 76%. The emission-target rate is the exception, rising from 64% (2023) to 95% (2024), so quote
  that figure by year rather than pooled.
- **Bug fixed:** `STI_total_ESG_Share` held a 16,663,333 data-entry error; it is now capped 0–100%,
  so the average ESG weight is no longer distorted.
- **Emission measured honestly across STI and LTI.** Quoting only the short-term bonus would undercount,
  because most emission targets sit in long-term plans. The headline emission figure uses STI-or-LTI.
- **Flags are descriptive, not causal.** A high screening score means a firm pairs heavy, reliably-hit
  ESG pay with no emission target anywhere. That raises a question; it does not prove greenwashing.
- **Strongest open follow-up:** compare ESG-target achievement against the firm's own FINANCIAL-target
  achievement. This file has no financial Zielerreichung, so that needs a second source.
- **STI vs LTI scope:** composition charts describe the annual (STI) bonus; emission presence uses STI or LTI.
- **Robustness (fluke tab):** the master database's shareholder-return data only covers 2022–2024, so the
  robustness window is three years (one down market year, two up), not 18. Our per-year medians (2022 −8%,
  2023 +23%, 2024 +13%) match the actual DAX total returns (−13%, +20%, +18%), confirming the year labels are
  correct. Performance covers ~40 large-cap firms per year (TSR is per company, deduplicated from per-exec
  rows). In that window most executives kept a bonus even in negative-return years (the bonus fell about a
  third). The shareholder-return join matches roughly 57% of ESG firms by name.
"""
    )
