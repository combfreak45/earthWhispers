import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))

from datetime import datetime, timezone
import streamlit as st
import pandas as pd
import pydeck as pdk
from bq_client import get_enriched_predictions, load_impact_context

st.set_page_config(
    page_title="EarthWhispers",
    page_icon="🌍",
    layout="wide",
)

# ── Custom CSS for scroll flow ─────────────────────────────────────────────────
st.markdown("""
<style>
section.main > div { padding-top: 1rem; }
[data-testid="stSidebar"] { display: none; }
[data-testid="stToolbar"] { display: none; }
h2 { margin-top: 2.5rem; border-bottom: 1px solid #333; padding-bottom: 0.4rem; }
</style>
""", unsafe_allow_html=True)

predictions = get_enriched_predictions()
latest = {}
for p in predictions:
    aid = p.get("area_id")
    if aid not in latest or p.get("predicted_at", "") > latest[aid].get("predicted_at", ""):
        latest[aid] = p
latest_predictions = list(latest.values())

# ══════════════════════════════════════════════════════════════════════════════
# HERO
# ══════════════════════════════════════════════════════════════════════════════
st.title("🌍 EarthWhispers — Flood Risk Intelligence")
st.caption("AI-powered flood risk monitoring for vulnerable catchment areas · **Prototype — not an official emergency warning system**")

# ══════════════════════════════════════════════════════════════════════════════
# DATA FRESHNESS BANNER
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("## ✅ Data Freshness")

for p in latest_predictions:
    event_time   = p.get("event_time", "")
    ingestion_time = p.get("ingestion_time", "")
    data_quality = p.get("data_quality", "unknown")

    try:
        obs_dt    = datetime.fromisoformat(event_time.replace("Z", "+00:00"))
        ingest_dt = datetime.fromisoformat(ingestion_time.replace("Z", "+00:00"))
        age_h     = (datetime.now(timezone.utc) - obs_dt).total_seconds() / 3600
        latency_m = (ingest_dt - obs_dt).total_seconds() / 60
        freshness = f"Observed **{age_h:.0f}h ago** · Ingestion latency **{latency_m:.0f} min**"
    except Exception:
        freshness = f"Observed at {event_time}"

    if data_quality == "good":
        st.success(f"✅ **{p.get('area_name')}** — Data quality: **{data_quality}** · {freshness} · Source: `{p.get('source','N/A')}`")
    elif data_quality == "stale":
        st.warning(f"⚠️ **{p.get('area_name')}** — Data quality: **stale** · {freshness}")
    else:
        st.error(f"❌ **{p.get('area_name')}** — Data quality: **{data_quality}** · Results unreliable")

# ══════════════════════════════════════════════════════════════════════════════
# RISK MAP
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("## 🗺️ Risk Map")
st.caption("Color: 🔴 High · 🟠 Medium · 🟢 Low — hover for details")

map_data = []
for p in latest_predictions:
    geo    = p.get("geometry", {})
    coords = geo.get("coordinates", [0, 0])
    rc     = p.get("risk_class", "low")
    color  = {"high": [220,38,38,200], "medium": [251,146,60,200], "low": [34,197,94,200]}.get(rc, [100,100,100,200])
    map_data.append({
        "lon": coords[0], "lat": coords[1],
        "risk_score": p.get("risk_score", 0),
        "risk_class": rc.upper(),
        "area_name": p.get("area_name", ""),
        "rainfall_24h": p.get("rainfall_24h", 0),
        "anomaly": p.get("anomaly_score", 0),
        "model": p.get("model_version", ""),
        "color": color,
    })

st.pydeck_chart(pdk.Deck(
    layers=[pdk.Layer(
        "ScatterplotLayer", data=pd.DataFrame(map_data),
        get_position=["lon","lat"], get_fill_color="color",
        get_radius=60000, pickable=True,
    )],
    initial_view_state=pdk.ViewState(latitude=26.1, longitude=94.2, zoom=6),
    tooltip={"text": "{area_name}\nRisk: {risk_class} ({risk_score})\n24h Rainfall: {rainfall_24h} mm\nAnomaly: {anomaly}x\nModel: {model}"},
))

c1, c2, c3 = st.columns(3)
c1.metric("🔴 High Risk",   sum(1 for p in latest_predictions if p["risk_class"] == "high"))
c2.metric("🟠 Medium Risk", sum(1 for p in latest_predictions if p["risk_class"] == "medium"))
c3.metric("🟢 Low Risk",    sum(1 for p in latest_predictions if p["risk_class"] == "low"))

# ══════════════════════════════════════════════════════════════════════════════
# EVIDENCE & AFFECTED COMMUNITIES
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("## 📋 Evidence & Affected Communities")

for p in latest_predictions:
    area_id    = p.get("area_id", "")
    rc         = p.get("risk_class", "low")
    rs         = p.get("risk_score", 0)
    icon       = {"high":"🔴","medium":"🟠","low":"🟢"}.get(rc,"⚪")
    impact     = load_impact_context(area_id)
    settlements = impact.get("nearby_settlements", [])
    assets      = impact.get("critical_assets", [])

    with st.expander(f"{icon} {p.get('area_name')} — {rc.upper()} (score: {rs:.2f})", expanded=True):
        if p.get("is_experimental"):
            st.warning("⚠️ **EXPERIMENTAL** — not validated against real flood events.")

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**Rainfall Evidence**")
            m1, m2 = st.columns(2)
            m1.metric("1h",  f"{p.get('rainfall_1h','N/A')} mm")
            m2.metric("6h",  f"{p.get('rainfall_6h','N/A')} mm")
            m1.metric("24h", f"{p.get('rainfall_24h','N/A')} mm")
            m2.metric("72h", f"{p.get('rainfall_72h','N/A')} mm")
            st.metric("Anomaly vs baseline", f"{p.get('anomaly_score','N/A')}x  (baseline {p.get('baseline_24h','N/A')} mm/24h)")
            st.caption(f"Signal rule: `{p.get('triggered_rule','N/A')}` · Feature version: `{p.get('feature_version','N/A')}`")

        with col2:
            st.markdown("**Affected Communities**")
            for s in settlements:
                st.markdown(f"🏘️ **{s['name']}** — pop. {s['population']:,} &nbsp; `{s['distance_km']} km`")

            st.markdown("**Critical Infrastructure**")
            asset_icons = {"hospital":"🏥","bridge":"🌉","road":"🛣️","power_station":"⚡"}
            for a in assets:
                ai = asset_icons.get(a["type"], "📍")
                st.markdown(f"{ai} **{a['name']}** ({a['type']}) &nbsp; `{a['distance_km']} km`")

# ══════════════════════════════════════════════════════════════════════════════
# PREDICTION HISTORY
# ══════════════════════════════════════════════════════════════════════════════
st.markdown("## 📈 Prediction History")

rows = []
for p in predictions:
    rc = p.get("risk_class","low")
    dq = p.get("data_quality","unknown")
    try:
        obs_dt = datetime.fromisoformat(p.get("event_time","").replace("Z","+00:00"))
        age    = f"{(datetime.now(timezone.utc)-obs_dt).total_seconds()/3600:.0f}h ago"
    except Exception:
        age = "unknown"
    rows.append({
        "Predicted At":      p.get("predicted_at",""),
        "Area":              p.get("area_name",""),
        "Risk":              {"high":"🔴 HIGH","medium":"🟠 MEDIUM","low":"🟢 LOW"}.get(rc,rc),
        "Score":             round(p.get("risk_score",0),2),
        "24h Rainfall (mm)": p.get("rainfall_24h",""),
        "Anomaly":           f"{p.get('anomaly_score','')}x",
        "Data Quality":      {"good":"✅ good","stale":"⚠️ stale","missing":"❌ missing"}.get(dq,dq),
        "Obs Age":           age,
        "Model":             p.get("model_version",""),
    })

st.dataframe(
    pd.DataFrame(rows).sort_values("Predicted At", ascending=False),
    use_container_width=True, hide_index=True,
)

# ── Event drill-down ──────────────────────────────────────────────────────────
st.markdown("#### 🔍 Event Evidence Drill-down")
sorted_preds = sorted(predictions, key=lambda x: x.get("predicted_at",""), reverse=True)
selected_eid = st.selectbox(
    "Select event",
    options=[p["event_id"] for p in sorted_preds],
    format_func=lambda eid: next(
        (f"{p['area_name']} — {p.get('event_time','')} ({p.get('risk_class','').upper()})"
         for p in sorted_preds if p["event_id"]==eid), eid
    ),
)

sel = next((p for p in predictions if p["event_id"]==selected_eid), None)
if sel:
    rc   = sel.get("risk_class","low")
    icon = {"high":"🔴","medium":"🟠","low":"🟢"}.get(rc,"⚪")
    st.markdown(f"**{icon} {sel.get('area_name')} — {rc.upper()} (score: {sel.get('risk_score',0):.2f})**")

    d1, d2, d3 = st.columns(3)
    with d1:
        st.markdown("**Rainfall**")
        st.metric("1h",  f"{sel.get('rainfall_1h','N/A')} mm")
        st.metric("3h",  f"{sel.get('rainfall_3h','N/A')} mm")
        st.metric("6h",  f"{sel.get('rainfall_6h','N/A')} mm")
        st.metric("24h", f"{sel.get('rainfall_24h','N/A')} mm")
        st.metric("72h", f"{sel.get('rainfall_72h','N/A')} mm")
    with d2:
        st.markdown("**Baseline & Anomaly**")
        st.metric("Seasonal baseline (24h)", f"{sel.get('baseline_24h','N/A')} mm")
        st.metric("Anomaly score", f"{sel.get('anomaly_score','N/A')}x")
        st.caption(f"Signal rule: `{sel.get('triggered_rule','N/A')}`")
        st.markdown("**Data Lineage**")
        st.caption(f"Source: `{sel.get('source','N/A')}`")
        st.caption(f"Feature version: `{sel.get('feature_version','N/A')}`")
        st.caption(f"Model version: `{sel.get('model_version','N/A')}`")
    with d3:
        st.markdown("**Timestamps**")
        st.caption(f"🕐 Observed: `{sel.get('event_time','N/A')}`")
        st.caption(f"📥 Ingested: `{sel.get('ingestion_time','N/A')}`")
        st.caption(f"🤖 Predicted: `{sel.get('predicted_at','N/A')}`")
        st.markdown("**Data Quality**")
        dq = sel.get("data_quality","unknown")
        if dq == "good":    st.success("✅ good")
        elif dq == "stale": st.warning("⚠️ stale")
        else:               st.error("❌ missing/unknown")

st.divider()
st.caption("🌍 EarthWhispers · AI Builder Cup · Sustainability & Social Impact · **Experimental prototype**")
