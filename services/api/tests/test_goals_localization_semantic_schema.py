from app.services.goals_localization.semantic_qa_service import (
    CorrectionResult,
    SemanticQAResult,
    normalize_revision,
)


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


def test_revision_keeps_original_when_foundry_returns_a_blank() -> None:
    revision = normalize_revision(
        {
            "goal": {"text": "", "changed": True, "reason": "blank"},
            "description": {
                "text": "设定优先级并明确责任归属。",
                "changed": True,
                "reason": "ownership meant responsibility, not property rights",
            },
        },
        {
            "goal": "Strengthen delivery",
            "description": "设定优先级并明确所有权。",
            "kra": "1. By Q2, select a workflow.",
        },
    )
    assert revision.goal.text == "Strengthen delivery"
    assert revision.goal.changed is False
    assert revision.description.changed is True
    assert "责任归属" in revision.description.text
    assert revision.kra.text == "1. By Q2, select a workflow."
    assert revision.kra.changed is False


def test_correction_schema() -> None:
    result = CorrectionResult.model_validate(
        {"field": "goal", "corrected_text": "Améliorer le revenu", "notes": "fixed"}
    )
    assert result.field == "goal"
