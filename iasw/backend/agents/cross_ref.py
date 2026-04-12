from rapidfuzz import fuzz


def run(extracted: dict, old_name: str, new_name: str) -> dict:
    """Fuzzy-match extracted document names against the requested name change.

    Input:  extracted (dict) — output from doc_processor.run();
            old_name (str) — customer's current name;
            new_name (str) — requested new name.
    Output: dict with old_name_match (bool), old_name_score (int),
            new_name_match (bool), new_name_score (int).
    """
    old_name_score = fuzz.ratio(
        (extracted.get("bride_name") or "").lower(),
        old_name.lower(),
    )
    new_name_score = fuzz.ratio(
        (extracted.get("married_name") or "").lower(),
        new_name.lower(),
    )
    return {
        "old_name_match": old_name_score >= 85,
        "old_name_score": old_name_score,
        "new_name_match": new_name_score >= 85,
        "new_name_score": new_name_score,
    }
