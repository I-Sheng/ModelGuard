"""
ModelGuard AI - Operations & Engineering Dashboard
Internal tool for platform operators: health monitoring, audit log review,
and attack report investigation.
"""

import httpx
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

API_BASE = "http://backend:8000"

st.set_page_config(
    page_title="ModelGuard OE Dashboard",
    page_icon="🛡️",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def api_get(path: str, params: dict | None = None):
    try:
        r = httpx.get(f"{API_BASE}{path}", params=params, timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        st.error(f"API error ({path}): {exc}")
        return None


def risk_color(level: str) -> str:
    return {"LOW": "green", "MEDIUM": "orange", "HIGH": "red", "CRITICAL": "darkred"}.get(level, "gray")


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
st.sidebar.title("🛡️ ModelGuard AI")
st.sidebar.caption("OE Dashboard · v0.2.0-oss")
st.sidebar.caption("Operations & Engineering Monitoring")

page = st.sidebar.radio(
    "Navigation",
    ["System Health", "Statistics", "Audit Logs", "Attack Reports"],
)

# ---------------------------------------------------------------------------
# Live health indicator in sidebar
# ---------------------------------------------------------------------------
with st.sidebar.expander("Live System Health", expanded=True):
    health = api_get("/health")
    if health:
        api_ok      = health.get("status",   "unknown") == "ok"
        minio_ok    = health.get("minio",    "unknown") == "ok"
        det_ok      = health.get("detector", "unknown") == "loaded"
        frontend_ok = health.get("frontend", "unknown") == "ok"

        st.write(f"**API**      {'✅' if api_ok      else '❌'} {health.get('status',   '?')}")
        st.write(f"**MinIO**    {'✅' if minio_ok    else '❌'} {health.get('minio',    '?')}")
        st.write(f"**Detector** {'✅' if det_ok      else '❌'} {health.get('detector', '?')}")
        st.write(f"**Frontend** {'✅' if frontend_ok else '❌'} {health.get('frontend', '?')}")
    else:
        st.warning("Backend unreachable")

# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

if page == "System Health":
    st.title("System Health")

    health = api_get("/health")
    if not health:
        st.error("Cannot reach the backend. Is `modelguard-backend` running?")
        st.stop()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("API Status",      health.get("status",   "—").upper())
    col2.metric("MinIO",           health.get("minio",    "—").upper())
    col3.metric("Detection Engine",health.get("detector", "—").upper())
    col4.metric("Frontend",        health.get("frontend", "—").upper())

    st.divider()
    st.subheader("Raw Health Payload")
    st.json(health)

    st.divider()
    st.subheader("Risk Level Reference")
    fig = go.Figure(go.Bar(
        x=["LOW", "MEDIUM", "HIGH", "CRITICAL"],
        y=[39, 59, 79, 100],
        marker_color=["green", "orange", "red", "darkred"],
        text=["0 – 39", "40 – 59", "60 – 79", "80 – 100"],
        textposition="outside",
    ))
    fig.update_layout(
        yaxis_title="Risk Score Upper Bound",
        xaxis_title="Risk Level",
        height=300,
        margin=dict(t=30, b=20),
    )
    st.plotly_chart(fig, use_container_width=True)


elif page == "Statistics":
    st.title("Statistics")

    stats = api_get("/stats")
    if stats:
        col1, col2, col3 = st.columns(3)
        col1.metric("Registered Models", stats.get("total_models", "—"))
        col2.metric("Detection Engine",  stats.get("detector", "—").upper())
        col3.metric("MinIO",             stats.get("minio",    "—").upper())
    else:
        st.warning("Could not fetch stats from backend.")

    st.divider()
    st.subheader("Registered Models")
    models_resp = api_get("/models")
    model_list  = models_resp.get("models", []) if models_resp else []
    if model_list:
        st.dataframe(pd.DataFrame(model_list), use_container_width=True)
    else:
        st.info("No models registered yet. Use the SwaggerAI frontend to register one.")


elif page == "Audit Logs":
    st.title("Audit Logs")
    st.caption("Query audit records — bucket: `modelguard-auditlog`")

    col1, col2 = st.columns(2)
    model_id    = col1.text_input("Model ID", value="sentiment-v1")
    date_filter = col2.text_input("Date filter (YYYY-MM-DD, optional)", value="")

    if st.button("Fetch Audit Logs"):
        params = {"date": date_filter} if date_filter else {}
        result = api_get(f"/audit/{model_id}", params=params)
        if result:
            logs = result.get("audit_logs", [])
            if logs:
                st.success(f"{len(logs)} record(s) found.")
                st.dataframe(pd.DataFrame(logs), use_container_width=True)
            else:
                st.info("No audit logs found for this model / date combination.")


elif page == "Attack Reports":
    st.title("Attack Reports")
    st.caption("HIGH / CRITICAL anomaly reports — bucket: `modelguard-reports`")

    model_id = st.text_input("Model ID", value="sentiment-v1")

    if st.button("Fetch Attack Reports"):
        result = api_get(f"/reports/{model_id}")
        if result:
            reports = result.get("attack_reports", [])
            if reports:
                st.warning(f"{len(reports)} attack report(s) found for **{model_id}**.")
                df = pd.DataFrame(reports)
                st.dataframe(df, use_container_width=True)

                st.divider()
                selected = st.selectbox("Inspect report:", [r["key"] for r in reports])
                if selected:
                    report_key = selected[len(model_id) + 1:]
                    detail = api_get(f"/reports/{model_id}/{report_key}")
                    if detail:
                        level = detail.get("risk_level", "")
                        color = risk_color(level)
                        st.markdown(f"**Risk Level**: :{color}[**{level}**]")

                        col1, col2, col3 = st.columns(3)
                        col1.metric("Risk Score",       f"{detail.get('risk_score', '?')} / 100")
                        col2.metric("Anomaly",          "Yes" if detail.get("anomaly") else "No")
                        col3.metric("Query ID",         str(detail.get("query_id", ""))[:8] + "...")

                        st.subheader("Feature Vector")
                        st.json(detail.get("features", {}))

                        st.subheader("Full Report")
                        st.json(detail)
            else:
                st.info(f"No attack reports found for model **{model_id}**.")
