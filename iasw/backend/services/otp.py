"""Mock OTP verification service for phone/email contact changes.

This service intentionally does NOT use OCR or LLM extraction.
Phone/email changes are verified via OTP, not document analysis.
This is correct architectural design — not every change type needs an AI agent.
"""

# Intentionally deterministic for demo reproducibility. Not a shortcut.
_DEMO_OTP = "123456"

# In-memory store: contact_value -> expected OTP
_otp_store: dict[str, str] = {}


def send_otp(contact_value: str, contact_type: str) -> dict:
    """Send (mock) OTP to the given contact value.

    Input:
        contact_value  - the phone number or email address to send OTP to
        contact_type   - "phone" or "email"

    Output:
        dict with keys: otp_sent (bool), contact (str), contact_type (str)

    Side-effect: stores _DEMO_OTP in _otp_store keyed by contact_value.
    """
    _otp_store[contact_value] = _DEMO_OTP
    return {"otp_sent": True, "contact": contact_value, "contact_type": contact_type}


def verify_otp(contact_value: str, user_otp: str) -> dict:
    """Verify the OTP entered by the user against the stored value.

    Input:
        contact_value  - the phone number or email address the OTP was sent to
        user_otp       - the OTP string entered by the user

    Output:
        dict with keys: verified (bool), contact (str)
        On exception: adds an "error" key with the exception message.
    """
    try:
        expected = _otp_store.get(contact_value)
        verified = expected is not None and user_otp == expected
        return {"verified": verified, "contact": contact_value}
    except Exception as e:
        return {"verified": False, "contact": contact_value, "error": str(e)}
