import requests
import streamlit as st

_API_BASE = "http://localhost:8000"

st.title("🔍 Checker Review Dashboard")

# ---------------------------------------------------------------------------
# Sidebar — pending queue
# ---------------------------------------------------------------------------
st.sidebar.header("Pending Queue")

try:
    pending_resp = requests.get(f"{_API_BASE}/requests/pending", timeout=10)
    pending_list = pending_resp.json() if pending_resp.ok else []
except Exception:
    pending_list = []
    st.sidebar.warning("Could not load pending requests.")

if not pending_list:
    st.sidebar.info("No pending requests.")

for item in pending_list:
    confidence_json = item.get("confidence_json") or {}
    score = confidence_json.get("overall_confidence", "?") if isinstance(confidence_json, dict) else "?"
    label = (
        f"{item['customer_id']} — "
        f"{item['old_value']} → {item['new_value']} "
        f"[{score}%]"
    )
    if st.sidebar.button(label, key=f"select_{item['request_id']}"):
        st.session_state["selected_request_id"] = item["request_id"]
        # Clear any prior decision state for fresh selection
        st.session_state.pop(f"decision_{item['request_id']}", None)

# ---------------------------------------------------------------------------
# Main panel — request detail
# ---------------------------------------------------------------------------
request_id = st.session_state.get("selected_request_id")

if request_id is None:
    st.info("Select a request from the sidebar to begin review.")
    st.stop()

try:
    detail_resp = requests.get(f"{_API_BASE}/requests/{request_id}", timeout=10)
except Exception as e:
    st.error(f"Failed to fetch request: {e}")
    st.stop()

if not detail_resp.ok:
    st.error(f"Request not found ({detail_resp.status_code}).")
    st.stop()

req = detail_resp.json()
confidence = req.get("confidence_json") or {}
extracted = req.get("extracted_json") or {}

# Header
st.subheader(f"Request: {request_id}")

# AI summary
st.info(req.get("ai_summary") or "No AI summary available.")

# Metrics
col1, col2, col3 = st.columns(3)
col1.metric("Name Match", f"{confidence.get('name_match_score', '—')}%")
col2.metric("Authenticity", f"{confidence.get('authenticity_score', '—')}%")
col3.metric("Forgery Check", confidence.get("forgery_verdict", "—"), delta=None)

# FileNet reference
st.caption(f"FileNet Reference: {req.get('filenet_ref', 'N/A')}")

# Expanders
with st.expander("Extracted Document Fields"):
    if extracted:
        st.table({"Field": list(extracted.keys()), "Value": list(extracted.values())})
    else:
        st.write("No extracted fields available.")

with st.expander("Full Confidence Card"):
    if confidence:
        st.json(confidence)
    else:
        st.write("No confidence data available.")

st.divider()

# ---------------------------------------------------------------------------
# Decision controls
# ---------------------------------------------------------------------------
decision_key = f"decision_{request_id}"
decided = decision_key in st.session_state

checker_id = st.text_input("Checker ID", value="CHK001", disabled=decided)
comment = st.text_area("Comments (optional)", disabled=decided)

col_a, col_b = st.columns(2)
approve_btn = col_a.button("✅ Approve", type="primary", disabled=decided, key=f"approve_{request_id}")
reject_btn = col_b.button("❌ Reject", disabled=decided, key=f"reject_{request_id}")

if approve_btn and not decided:
    if not checker_id.strip():
        st.warning("Please enter a Checker ID before approving.")
    else:
        try:
            resp = requests.post(
                f"{_API_BASE}/requests/{request_id}/decision",
                json={"decision": "APPROVE", "checker_id": checker_id, "comment": comment},
                timeout=30,
            )
        except Exception as e:
            st.error(f"Connection error: {e}")
            st.stop()

        if resp.ok:
            st.session_state[decision_key] = "APPROVE"
            st.rerun()
        else:
            try:
                detail = resp.json().get("detail", resp.text)
            except Exception:
                detail = resp.text
            st.error(f"Approval failed ({resp.status_code}): {detail}")

if reject_btn and not decided:
    if not checker_id.strip():
        st.warning("Please enter a Checker ID before rejecting.")
    else:
        try:
            resp = requests.post(
                f"{_API_BASE}/requests/{request_id}/decision",
                json={"decision": "REJECT", "checker_id": checker_id, "comment": comment},
                timeout=30,
            )
        except Exception as e:
            st.error(f"Connection error: {e}")
            st.stop()

        if resp.ok:
            st.session_state[decision_key] = "REJECT"
            st.rerun()
        else:
            try:
                detail = resp.json().get("detail", resp.text)
            except Exception:
                detail = resp.text
            st.error(f"Rejection failed ({resp.status_code}): {detail}")

# Show outcome after decision
if decided:
    if st.session_state[decision_key] == "APPROVE":
        st.success("✅ Approved. RPS updated.")
        st.balloons()
    else:
        st.error("❌ Request rejected.")
