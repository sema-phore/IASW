from rapidfuzz import fuzz


def run(extracted: dict, old_name: str, new_name: str) -> dict:
    old_name_score = fuzz.ratio(
        extracted.get("bride_name", "").lower(),
        old_name.lower(),
    )
    new_name_score = fuzz.ratio(
        extracted.get("married_name", "").lower(),
        new_name.lower(),
    )
    return {
        "old_name_match": old_name_score >= 85,
        "old_name_score": old_name_score,
        "new_name_match": new_name_score >= 85,
        "new_name_score": new_name_score,
    }
