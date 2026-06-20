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

# ──────────────────────────────────────────────────────────────────────────────
# HEADER
# ──────────────────────────────────────────────────────────────────────────────
st.title("ESG Pay Reality Check")
st.subheader("ESG-linked bonuses are now standard. But are the targets a genuine stretch?")
st.caption(
    "A screening tool on ESG-linked executive pay (DSW data, 2023–2024). It flags packages worth "
    "scrutinising and is honest about what it can and cannot show. Read every flag as a question, not a verdict."
)

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
# SECTION 1 — THE CLAIM
# ──────────────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("### The claim: boards tie pay to ESG")

w  = f["esg_weight"].dropna()
a  = f["achievement"].dropna()
e_any = f["emission_any"].dropna()

c1, c2, c3, c4 = st.columns(4)
c1.metric("Avg ESG weight in bonus",
          f"{w.mean():.1f}%" if len(w) else "n/a",
          help="Average share of the short-term bonus (STI) tied to ESG. Capped 0–100% to ignore data-entry errors.")
c2.metric("Hit their ESG target (≥100%)",
          f"{(a >= ACHIEVE_HIT).mean()*100:.0f}%" if len(a) else "n/a",
          help="Share of company-years that met or exceeded their ESG bonus target.")
c3.metric("Have an emission target somewhere",
          f"{e_any.mean()*100:.0f}%" if len(e_any) else "n/a",
          help="Share with an emission-reduction KPI in the short-term OR long-term plan.")
c4.metric("Company-years analysed", f"{len(f)}")

st.markdown(
    f"<span style='color:{INK}'>ESG pay is real and emission targets are common. The next two questions "
    f"ask whether the targets are a stretch, and where the climate teeth actually sit.</span>",
    unsafe_allow_html=True)

# ──────────────────────────────────────────────────────────────────────────────
# SECTION 2 — PUNCH 1: ARE THE TARGETS TOO EASY?
# ──────────────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("### Punch 1 — Are the targets too easy?")
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

    hit = (a >= ACHIEVE_HIT).mean() * 100 if len(a) else 0
    st.markdown(
        f"**Takeaway:** {hit:.0f}% of company-years met or beat their ESG target "
        f"(median {a.median():.0f}%). A genuine stretch goal would not be hit this reliably. "
        f"*(Caveat: bonuses overshoot in general; the strongest test compares ESG achievement against "
        f"the same firm's financial-target achievement, which needs a second data source.)*")
else:
    st.info("Not enough weight/achievement data under current filters.")

# ──────────────────────────────────────────────────────────────────────────────
# SECTION 3 — PUNCH 2: WHERE ARE THE CLIMATE TEETH?
# ──────────────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("### Punch 2 — Where are the climate teeth?")
st.markdown(
    "*Emission targets exist, but mostly in LONG-TERM pay. The ANNUAL bonus's 'ESG' leans on softer "
    "social and governance criteria. So the money paid out each year is largely not about emissions.*")

colA, colB = st.columns([3, 2])

with colA:
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

with colB:
    st.markdown(f"#### {sti:.0f}% vs {lti:.0f}%")
    st.markdown(
        f"Only **{sti:.0f}%** put an emission target in the **annual** bonus, while **{lti:.0f}%** keep it "
        f"in the **long-term** plan. \n\nClimate goals are real but deferred. The cash rewarded each year "
        f"is mostly tied to softer criteria.")

# ──────────────────────────────────────────────────────────────────────────────
# SECTION 4 — SCREENING SCORE
# ──────────────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown("### The screening score: heavy ESG marketing, soft ESG substance?")
st.markdown(
    "*One point each for: high ESG weight, target hit, and no emission target anywhere (STI or LTI). "
    "A higher score is not proof of greenwashing — it is a signal worth a closer look.*")

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

# ──────────────────────────────────────────────────────────────────────────────
# METHODOLOGY + CAVEATS
# ──────────────────────────────────────────────────────────────────────────────
with st.expander("Methodology & caveats (read before quoting a number)"):
    st.markdown(
        f"""
- **Data:** DSW ESG remuneration data, reporting years 2023–2024. N = {len(df)} company-years.
- **Bug fixed:** `STI_total_ESG_Share` held a 16,663,333 data-entry error; it is now capped 0–100%,
  so the average ESG weight is no longer distorted.
- **Emission measured honestly across STI and LTI.** Quoting only the short-term bonus would undercount,
  because most emission targets sit in long-term plans. The headline emission figure uses STI-or-LTI.
- **Flags are descriptive, not causal.** A high screening score means a firm pairs heavy, reliably-hit
  ESG pay with no emission target anywhere. That raises a question; it does not prove greenwashing.
- **Strongest open follow-up:** compare ESG-target achievement against the firm's own FINANCIAL-target
  achievement. This file has no financial Zielerreichung, so that needs a second source.
- **STI vs LTI scope:** composition charts describe the annual (STI) bonus; emission presence uses STI or LTI.
"""
    )