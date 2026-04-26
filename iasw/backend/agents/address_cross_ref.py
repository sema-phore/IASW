from datetime import date

from dateutil import parser as dateutil_parser
from rapidfuzz import fuzz


def run(extracted: dict, customer_name: str, new_address: dict) -> dict:
    """Validate extracted address proof fields against customer and requested address data.

    Performs field-level matching rather than a single fuzzy string comparison,
    because each field carries different KYC weight (pincode is exact-match only).

    Input:
        extracted      - output of address_doc_processor.run(); expected keys:
                         full_name, address_line, city, state, pincode, issue_date.
        customer_name  - the account holder's name on record (for name-on-document check).
        new_address    - dict with keys address, city, state, pincode
                         representing the address the customer wants to register.

    Output:
        dict with:
            name_match (bool), name_match_score (int 0-100)
            address_match (bool), address_match_score (int 0-100)
            city_match (bool), city_match_score (int 0-100)
            state_match (bool), state_match_score (int 0-100)
            pincode_match (bool)  — exact match only, per KYC policy
            doc_age_days (int)    — days since document issue_date
            doc_recency_valid (bool) — True if doc is ≤90 days old
    """
    # --- Name match: simple ratio, threshold 85% ---
    extracted_name = (extracted.get("full_name") or "").strip().lower()
    name_match_score = int(fuzz.ratio(extracted_name, customer_name.strip().lower()))
    name_match = name_match_score >= 85

    # --- Address line match: token_sort_ratio handles field-order variation ---
    # e.g. "42 MG Road" vs "MG Road 42" should still score high
    extracted_address = (extracted.get("address_line") or "").strip().lower()
    requested_address = (new_address.get("address") or "").strip().lower()
    address_match_score = int(fuzz.token_sort_ratio(extracted_address, requested_address))
    address_match = address_match_score >= 75

    # --- City match: simple ratio, threshold 80% ---
    extracted_city = (extracted.get("city") or "").strip().lower()
    requested_city = (new_address.get("city") or "").strip().lower()
    city_match_score = int(fuzz.ratio(extracted_city, requested_city))
    city_match = city_match_score >= 80

    # --- State match: simple ratio, threshold 80% ---
    extracted_state = (extracted.get("state") or "").strip().lower()
    requested_state = (new_address.get("state") or "").strip().lower()
    state_match_score = int(fuzz.ratio(extracted_state, requested_state))
    state_match = state_match_score >= 80

    # --- Pincode match: EXACT only — no fuzziness allowed per KYC policy ---
    extracted_pincode = (extracted.get("pincode") or "").strip()
    requested_pincode = (new_address.get("pincode") or "").strip()
    pincode_match = extracted_pincode == requested_pincode

    # --- Document recency: must be ≤90 days old per banking policy ---
    doc_age_days = -1
    doc_recency_valid = False
    issue_date_raw = extracted.get("issue_date")
    if issue_date_raw:
        try:
            issue_date = dateutil_parser.parse(str(issue_date_raw)).date()
            doc_age_days = (date.today() - issue_date).days
            doc_recency_valid = doc_age_days <= 90
        except Exception:
            # If date cannot be parsed, treat document as invalid for recency
            doc_age_days = -1
            doc_recency_valid = False

    return {
        "name_match": name_match,
        "name_match_score": name_match_score,
        "address_match": address_match,
        "address_match_score": address_match_score,
        "city_match": city_match,
        "city_match_score": city_match_score,
        "state_match": state_match,
        "state_match_score": state_match_score,
        "pincode_match": pincode_match,
        "doc_age_days": doc_age_days,
        "doc_recency_valid": doc_recency_valid,
    }
