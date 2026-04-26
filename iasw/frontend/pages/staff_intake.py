import requests
import streamlit as st

_API_BASE = "http://localhost:8000"

st.title("📋 Account Change Request — Staff Intake")

change_type = st.selectbox("Change Type", ["Name Change", "Address Change", "Contact Change (Phone/Email)"])

# ---------------------------------------------------------------------------
# Name Change form
# ---------------------------------------------------------------------------
if change_type == "Name Change":
    customer_id = st.text_input("Customer ID", placeholder="e.g. C001")
    old_name = st.text_input("Current Name on Record")
    new_name = st.text_input("Requested New Name")
    uploaded_file = st.file_uploader(
        "Upload Supporting Document", type=["pdf", "png", "jpg", "jpeg"]
    )

    if st.button("Submit Request"):
        if not all([customer_id, old_name, new_name, uploaded_file]):
            st.warning("Please fill in all fields and upload a document.")
        else:
            with st.spinner("AI pipeline is processing the document..."):
                try:
                    resp = requests.post(
                        f"{_API_BASE}/requests/name-change",
                        data={
                            "customer_id": customer_id,
                            "old_name": old_name,
                            "new_name": new_name,
                        },
                        files={
                            "document": (
                                uploaded_file.name,
                                uploaded_file.getvalue(),
                                uploaded_file.type,
                            )
                        },
                        timeout=120,
                    )
                except requests.exceptions.ConnectionError:
                    st.error("Cannot reach the backend. Make sure the API server is running on port 8000.")
                    st.stop()
                except Exception as e:
                    st.error(f"Unexpected error: {e}")
                    st.stop()

            if resp.ok:
                data = resp.json()
                st.success(
                    f"Request submitted successfully!\n\n"
                    f"**Request ID:** `{data['request_id']}`\n\n"
                    f"**Confidence Score:** {data.get('overall_confidence', 'N/A')}%\n\n"
                    f"**Recommended Action:** {data.get('recommended_action', 'N/A')}\n\n"
                    f"**Summary:** {data.get('summary', '')}"
                )
            else:
                try:
                    detail = resp.json().get("detail", resp.text)
                except Exception:
                    detail = resp.text
                st.error(f"Submission failed ({resp.status_code}): {detail}")

# ---------------------------------------------------------------------------
# Address Change form
# ---------------------------------------------------------------------------
elif change_type == "Address Change":
    customer_id = st.text_input("Customer ID", placeholder="e.g. C001")
    new_address = st.text_input("New Street Address", placeholder="e.g. 15 Park Street")
    new_city = st.text_input("New City", placeholder="e.g. Mumbai")
    new_state = st.text_input("New State", placeholder="e.g. Maharashtra")
    new_pincode = st.text_input("New Pincode", placeholder="e.g. 400001")
    uploaded_file = st.file_uploader(
        "Upload Address Proof Document", type=["pdf", "png", "jpg", "jpeg"]
    )

    if st.button("Submit Request"):
        if not all([customer_id, new_address, new_city, new_state, new_pincode, uploaded_file]):
            st.warning("Please fill in all fields and upload a document.")
        else:
            with st.spinner("AI pipeline is processing the document..."):
                try:
                    resp = requests.post(
                        f"{_API_BASE}/requests/address-change",
                        data={
                            "customer_id": customer_id,
                            "new_address": new_address,
                            "new_city": new_city,
                            "new_state": new_state,
                            "new_pincode": new_pincode,
                        },
                        files={
                            "document": (
                                uploaded_file.name,
                                uploaded_file.getvalue(),
                                uploaded_file.type,
                            )
                        },
                        timeout=120,
                    )
                except requests.exceptions.ConnectionError:
                    st.error("Cannot reach the backend. Make sure the API server is running on port 8000.")
                    st.stop()
                except Exception as e:
                    st.error(f"Unexpected error: {e}")
                    st.stop()

            if resp.ok:
                data = resp.json()
                st.success(
                    f"Request submitted successfully!\n\n"
                    f"**Request ID:** `{data['request_id']}`\n\n"
                    f"**Confidence Score:** {data.get('overall_confidence', 'N/A')}%\n\n"
                    f"**Recommended Action:** {data.get('recommended_action', 'N/A')}\n\n"
                    f"**Summary:** {data.get('summary', '')}"
                )
            else:
                try:
                    detail = resp.json().get("detail", resp.text)
                except Exception:
                    detail = resp.text
                st.error(f"Submission failed ({resp.status_code}): {detail}")

# ---------------------------------------------------------------------------
# Contact Change form (Phone / Email)
# ---------------------------------------------------------------------------
elif change_type == "Contact Change (Phone/Email)":
    customer_id = st.text_input("Customer ID", placeholder="e.g. C001", key="contact_cid")
    contact_type = st.radio("What do you want to change?", ["PHONE", "EMAIL"], horizontal=True)

    if contact_type == "PHONE":
        new_value = st.text_input("New Phone Number", placeholder="e.g. 9999999999")
    else:
        new_value = st.text_input("New Email Address", placeholder="e.g. new@email.com")

    # --- Step 1: Send OTP ---
    if st.button("📩 Send OTP"):
        if not all([customer_id, new_value]):
            st.warning("Please fill in Customer ID and new contact value.")
        else:
            try:
                resp = requests.post(
                    f"{_API_BASE}/otp/send",
                    json={"contact_value": new_value, "contact_type": contact_type},
                    timeout=10,
                )
                if resp.ok:
                    st.session_state["otp_sent"] = True
                    st.session_state["otp_contact"] = new_value
                    st.success(f"OTP sent to {new_value}. (Demo hint: enter 123456)")
                else:
                    st.error("Failed to send OTP.")
            except requests.exceptions.ConnectionError:
                st.error("Cannot reach the backend.")
            except Exception as e:
                st.error(f"Unexpected error: {e}")

    # --- Step 2: Verify & Submit (only shown after OTP sent for this contact value) ---
    if st.session_state.get("otp_sent") and st.session_state.get("otp_contact") == new_value:
        otp_code = st.text_input("Enter OTP", max_chars=6, key="otp_input")

        if st.button("✅ Verify & Submit"):
            if not otp_code:
                st.warning("Please enter the OTP.")
            else:
                with st.spinner("Verifying OTP and processing request..."):
                    try:
                        resp = requests.post(
                            f"{_API_BASE}/requests/contact-change",
                            json={
                                "customer_id": customer_id,
                                "contact_type": contact_type,
                                "new_value": new_value,
                                "otp_code": otp_code,
                            },
                            timeout=30,
                        )
                    except requests.exceptions.ConnectionError:
                        st.error("Cannot reach the backend.")
                        st.stop()
                    except Exception as e:
                        st.error(f"Unexpected error: {e}")
                        st.stop()

                if resp.ok:
                    data = resp.json()
                    st.session_state["otp_sent"] = False  # reset
                    st.success(
                        f"Request submitted!\n\n"
                        f"**Request ID:** `{data['request_id']}`\n\n"
                        f"**Confidence:** {data.get('overall_confidence', 'N/A')}%\n\n"
                        f"**Recommended:** {data.get('recommended_action', 'N/A')}\n\n"
                        f"**Summary:** {data.get('summary', '')}"
                    )
                else:
                    try:
                        detail = resp.json().get("detail", resp.text)
                    except Exception:
                        detail = resp.text
                    st.error(f"Submission failed ({resp.status_code}): {detail}")
