def production_audit(*, commit: str = "0" * 40) -> dict[str, object]:
    return {
        "source": {
            "repository": "https://example.com/source",
            "commit": commit,
            "license": "Apache-2.0",
            "production_use_verified": True,
            "license_evidence_url": "https://example.com/source-license",
        },
        "training_data": {
            "summary": "Licensed evaluation corpus",
            "license": "CC-BY-4.0",
            "production_use_verified": True,
            "license_evidence_url": "https://example.com/data-license",
        },
    }
