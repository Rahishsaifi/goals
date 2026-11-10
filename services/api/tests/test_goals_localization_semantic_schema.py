from app.services.goals_localization.semantic_qa_service import CorrectionResult, SemanticQAResult


def test_semantic_qa_schema_accepts_valid_payload() -> None:
    result = SemanticQAResult.model_validate(
        {
            "record_id": "GOAL-001",
            "overall_status": "FAIL",
            "fields": {
                "goal": {"status": "PASS", "issues": []},
                "description": {
                    "status": "FAIL",
                    "issues": [
                        {
                            "type": "SEMANTIC_MISMATCH",
                            "severity": "HIGH",
                            "explanation": "Year-end target changed.",
                        }
                    ],
                },
                "kra": {"status": "PASS", "issues": []},
            },
            "recommendation": "CORRECT",
        }
    )
    assert result.overall_status == "FAIL"
    assert result.fields["description"].issues[0].severity == "HIGH"


def test_correction_schema() -> None:
    result = CorrectionResult.model_validate(
        {"field": "goal", "corrected_text": "Améliorer le revenu", "notes": "fixed"}
    )
    assert result.field == "goal"
