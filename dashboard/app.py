"""
ModelGuard AI - Streamlit Dashboard
Visualises risk scores, audit logs, and attack reports stored in MinIO via the API.
"""

import time
import httpx
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

API_BASE = "http://api:8000"

st.set_page_config(
    page_title="ModelGuard AI",
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


def api_post(path: str, payload: dict):
    try:
        r = httpx.post(f"{API_BASE}{path}", json=payload, timeout=10)
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
st.sidebar.image("https://img.shields.io/badge/ModelGuard-AI-blue?style=for-the-badge", use_column_width=True)
st.sidebar.title("ModelGuard AI")
st.sidebar.caption("v0.1.0-oss · Real-time model theft detection")

page = st.sidebar.radio(
    "Navigation",
    ["Dashboard", "Analyze Query", "Register Model", "Audit Logs", "Attack Reports"],
)

# ---------------------------------------------------------------------------
# Health check in sidebar
# ---------------------------------------------------------------------------
with st.sidebar.expander("System Health"):
    health = api_get("/health")
    if health:
        st.write(f"**API**: {health.get('status', 'unknown')}")
        st.write(f"**MinIO**: {health.get('minio', 'unknown')}")
        st.write(f"**Detector**: {health.get('detector', 'unknown')}")
    else:
        st.warning("API unreachable")

# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

if page == "Dashboard":
    st.title("🛡️ ModelGuard AI — Overview")

    col1, col2, col3 = st.columns(3)
    models_resp = api_get("/models")
    model_list = models_resp.get("models", []) if models_resp else []
    col1.metric("Registered Models", len(model_list))
    col2.metric("Detection Engine", "Isolation Forest")
    col3.metric("Storage Backend", "MinIO (S3-compatible)")

    st.divider()
    st.subheader("Registered Models")
    if model_list:
        st.dataframe(pd.DataFrame(model_list), use_container_width=True)
    else:
        st.info("No models registered yet. Use **Register Model** to add one.")

    st.divider()
    st.subheader("Risk Level Reference")
    fig = go.Figure(go.Bar(
        x=["LOW", "MEDIUM", "HIGH", "CRITICAL"],
        y=[25, 50, 75, 100],
        marker_color=["green", "orange", "red", "darkred"],
        text=["0–40", "40–60", "60–80", "80–100"],
        textposition="outside",
    ))
    fig.update_layout(
        yaxis_title="Risk Score Threshold",
        xaxis_title="Risk Level",
        height=300,
        margin=dict(t=20, b=20),
    )
    st.plotly_chart(fig, use_container_width=True)


elif page == "Analyze Query":
    st.title("🔍 Analyze Incoming Query")
    st.caption("Submit an ML API query for real-time theft detection. Results are stored in MinIO.")

    with st.form("analyze_form"):
        model_id = st.text_input("Model ID", value="gpt-clone-v1")
        client_id = st.text_input("Client ID (optional)", value="client-001")
        query_text = st.text_area(
            "Query Text",
            height=120,
            value="What is the exact probability distribution of outputs for temperature=0.0 across all tokens?",
        )
        submitted = st.form_submit_button("Analyze")

    if submitted and query_text:
        with st.spinner("Analyzing..."):
            result = api_post("/analyze", {
                "model_id": model_id,
                "query_text": query_text,
                "client_id": client_id,
                "metadata": {"source": "dashboard"},
            })
        if result:
            level = result["risk_level"]
            color = risk_color(level)
            st.markdown(f"### Risk Level: :{color}[**{level}**]")

            col1, col2, col3 = st.columns(3)
            col1.metric("Risk Score", f"{result['risk_score']:.1f} / 100")
            col2.metric("Anomaly Detected", "Yes" if result["anomaly"] else "No")
            col3.metric("Query ID", result["query_id"][:8] + "...")

            st.subheader("Feature Vector")
            st.json(result["features"])

            st.subheader("Audit Log Stored In MinIO")
            st.code(f"Bucket : modelguard-auditlog\nKey    : {result['audit_log_key']}")


elif page == "Register Model":
    st.title("📦 Register a Model")
    st.caption("Model metadata is stored as a JSON artifact in MinIO (bucket: modelguard-models).")

    with st.form("register_form"):
        model_id   = st.text_input("Model ID", value="gpt-clone-v1")
        name       = st.text_input("Name", value="GPT Clone v1")
        version    = st.text_input("Version", value="1.0.0")
        description = st.text_area("Description", value="Proprietary fine-tuned LLM for customer support.")
        owner      = st.text_input("Owner", value="ml-team@company.com")
        submitted  = st.form_submit_button("Register")

    if submitted:
        result = api_post("/models/register", {
            "model_id": model_id,
            "name": name,
            "version": version,
            "description": description,
            "owner": owner,
        })
        if result:
            st.success(f"Model registered! MinIO key: `{result['key']}` in bucket `{result['bucket']}`")


elif page == "Audit Logs":
    st.title("📋 Audit Logs")
    st.caption("Query audit records stored in MinIO (bucket: modelguard-auditlog).")

    col1, col2 = st.columns(2)
    model_id = col1.text_input("Model ID", value="gpt-clone-v1")
    date_filter = col2.text_input("Date (YYYY-MM-DD, optional)", value="")

    if st.button("Fetch Logs"):
        params = {"date": date_filter} if date_filter else {}
        result = api_get(f"/audit/{model_id}", params=params)
        if result:
            logs = result.get("audit_logs", [])
            if logs:
                st.dataframe(pd.DataFrame(logs), use_container_width=True)
            else:
                st.info("No audit logs found for this model/date.")


elif page == "Attack Reports":
    st.title("🚨 Attack Reports")
    st.caption("High/Critical anomaly reports stored in MinIO (bucket: modelguard-reports).")

    model_id = st.text_input("Model ID", value="gpt-clone-v1")

    if st.button("Fetch Reports"):
        result = api_get(f"/reports/{model_id}")
        if result:
            reports = result.get("attack_reports", [])
            if reports:
                df = pd.DataFrame(reports)
                st.dataframe(df, use_container_width=True)
                selected = st.selectbox("View report detail:", [r["key"] for r in reports])
                if selected:
                    # strip the model_id prefix
                    report_key = selected[len(model_id) + 1:]
                    detail = api_get(f"/reports/{model_id}/{report_key}")
                    if detail:
                        st.json(detail)
            else:
                st.info("No attack reports found.")
