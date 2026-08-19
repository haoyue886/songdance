APPROVED_REVIEW_RATINGS = {"minor_edits", "direct_use"}
COMPLETED_REVIEW_RATINGS = APPROVED_REVIEW_RATINGS | {"needs_redo"}
MAXIMUM_PUBLIC_REST_COUNT = 80
MAXIMUM_PUBLIC_VOICES_PER_STAFF_MEASURE = 2


def completed_review(current_review: dict[str, object]) -> dict[str, str]:
    if current_review["rating"] in COMPLETED_REVIEW_RATINGS:
        return {
            "rating": str(current_review["rating"]),
            "reviewed_at": str(current_review["reviewed_at"]),
            "model_version": str(current_review["model_version"]),
        }
    latest = current_review.get("latest_completed_review")
    if isinstance(latest, dict) and latest.get("rating") in COMPLETED_REVIEW_RATINGS:
        if not latest.get("reviewed_at") or not latest.get("model_version"):
            raise ValueError("latest completed public example review is incomplete")
        return {
            "rating": str(latest["rating"]),
            "reviewed_at": str(latest["reviewed_at"]),
            "model_version": str(latest["model_version"]),
        }
    raise ValueError("pending public example review is missing completed review history")


def validate_notation_density(structure: dict[str, object]) -> None:
    if int(structure.get("rest_count", 0)) > MAXIMUM_PUBLIC_REST_COUNT:
        raise ValueError("public example source has excessive notation rests")
    voice_counts = structure.get("maximum_voices_by_staff_measure", {})
    if not isinstance(voice_counts, dict) or set(voice_counts) != {"1", "2"} or any(
        not isinstance(count, int) or count > MAXIMUM_PUBLIC_VOICES_PER_STAFF_MEASURE
        for count in voice_counts.values()
    ):
        raise ValueError("public example source has excessive notation voices")
