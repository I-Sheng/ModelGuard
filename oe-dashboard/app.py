"""
ModelGuard AI - Operations & Engineering Dashboard
Internal tool for platform operators: health monitoring, audit log review,
and theft report investigation.
"""

import os

import httpx
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

API_BASE = "http://backend:8000"
_OE_USER = os.getenv("OE_ADMIN_USER",     "admin")
_OE_PASS = os.getenv("OE_ADMIN_PASSWORD", "admin_password")

st.set_page_config(
    page_title="ModelGuard OE Dashboard",
    page_icon="🛡️",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_token() -> str:
    if "oe_token" not in st.session_state:
        r = httpx.post(f"{API_BASE}/auth/login",
                       data={"username": _OE_USER, "password": _OE_PASS}, timeout=5)
        r.raise_for_status()
        st.session_state["oe_token"] = r.json()["access_token"]
    return st.session_state["oe_token"]


def api_get(path: str, params: dict | None = None):
    try:
        token = _get_token()
        headers = {"Authorization": f"Bearer {token}"}
        r = httpx.get(f"{API_BASE}{path}", params=params, headers=headers, timeout=5)
        if r.status_code == 401:
            del st.session_state["oe_token"]
            headers["Authorization"] = f"Bearer {_get_token()}"
            r = httpx.get(f"{API_BASE}{path}", params=params, headers=headers, timeout=5)
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
st.sidebar.caption("OE Dashboard · v0.3.0-oss")
st.sidebar.caption("Operations & Engineering Monitoring")

page = st.sidebar.radio(
    "Navigation",
    ["System Health", "Statistics", "Audit Logs", "Theft Reports"],
)

# ---------------------------------------------------------------------------
# Live health indicator in sidebar
# ---------------------------------------------------------------------------
with st.sidebar.expander("Live System Health", expanded=True):
    health = api_get("/health/detail")
    if health:
        api_ok      = health.get("status",   "unknown") == "ok"
        minio_ok    = health.get("minio",    "unknown") == "ok"
        det_ok      = health.get("detector", "unknown") == "loaded"
        frontend_ok = health.get("frontend", "unknown") == "ok"

        st.write(f"**Frontend** {'✅' if frontend_ok else '❌'} {health.get('frontend', '?')}")
        st.write(f"**API**      {'✅' if api_ok      else '❌'} {health.get('status',   '?')}")
        st.write(f"**MinIO**    {'✅' if minio_ok    else '❌'} {health.get('minio',    '?')}")
        st.write(f"**Detector** {'✅' if det_ok      else '❌'} {health.get('detector', '?')}")
    else:
        st.warning("Backend unreachable")

# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

if page == "System Health":
    st.title("System Health")

    health = api_get("/health/detail")
    if not health:
        st.error("Cannot reach the backend. Is `modelguard-backend` running?")
        st.stop()

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Frontend",         health.get("frontend", "—").upper())
    col2.metric("API Status",       health.get("status",   "—").upper())
    col3.metric("MinIO",            health.get("minio",    "—").upper())
    col4.metric("Detection Engine", health.get("detector", "—").upper())

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
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Registered Partners",   stats.get("total_partners",         "—"))
        col2.metric("Batches Analyzed",      stats.get("total_batches_analyzed", "—"))
        col3.metric("Detection Engine",      stats.get("detector", "—").upper())
        col4.metric("MinIO",                 stats.get("minio",    "—").upper())
    else:
        st.warning("Could not fetch stats from backend.")


elif page == "Audit Logs":
    st.title("Audit Logs")
    st.caption("Batch analysis records — bucket: `modelguard-auditlog`")

    col1, col2 = st.columns(2)
    partner_id  = col1.text_input("Partner ID", value="openai-demo")
    date_filter = col2.text_input("Date filter (YYYY-MM-DD, optional)", value="")

    if st.button("Fetch Audit Logs"):
        params = {"date": date_filter} if date_filter else {}
        result = api_get(f"/audit/{partner_id}", params=params)
        if result:
            logs = result.get("audit_logs", [])
            if logs:
                st.success(f"{len(logs)} record(s) found.")
                st.dataframe(pd.DataFrame(logs), use_container_width=True)
            else:
                st.info("No audit logs found for this partner / date combination.")


elif page == "Theft Reports":
    st.title("Theft Reports")
    st.caption("HIGH / CRITICAL batch theft reports — bucket: `modelguard-reports`")

    partner_id = st.text_input("Partner ID", value="openai-demo")

    if st.button("Fetch Theft Reports"):
        result = api_get(f"/reports/{partner_id}")
        if result:
            reports = result.get("theft_reports", [])
            if reports:
                st.warning(f"{len(reports)} theft report(s) found for **{partner_id}**.")
                df = pd.DataFrame(reports)
                st.dataframe(df, use_container_width=True)

                st.divider()
                selected = st.selectbox("Inspect report:", [r["key"] for r in reports])
                if selected:
                    report_key = selected[len(partner_id) + 1:]
                    detail = api_get(f"/reports/{partner_id}/{report_key}")
                    if detail:
                        level = detail.get("batch_risk_level", "")
                        color = risk_color(level)
                        st.markdown(f"**Batch Risk Level**: :{color}[**{level}**]")

                        col1, col2, col3 = st.columns(3)
                        col1.metric("Flagged Users",        detail.get("flagged_users",    "?"))
                        col2.metric("Total Queries",        detail.get("total_queries",    "?"))
                        col3.metric("Batch ID",             str(detail.get("batch_id", ""))[:8] + "...")

                        st.subheader("User Results")
                        user_results = detail.get("user_results", [])
                        if user_results:
                            flagged = [u for u in user_results if u.get("risk_level") in ("HIGH", "CRITICAL")]
                            if flagged:
                                st.error(f"{len(flagged)} flagged user(s):")
                                st.dataframe(pd.DataFrame(flagged), use_container_width=True)

                        st.subheader("Full Report")
                        st.json(detail)
            else:
                st.info(f"No theft reports found for partner **{partner_id}**.")
