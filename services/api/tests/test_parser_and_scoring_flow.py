from decimal import Decimal

from recruitment_scoring.engine import CriterionInput, score_candidate

from app.integrations.model_provider import MockModelProvider
from app.parsers.documents import parse_document
from app.services.usage_service import estimate_cost


def test_parse_docx_bytes() -> None:
    # Minimal DOCX zip produced by python-docx
    import io

    from docx import Document

    document = Document()
    document.add_paragraph("Python FastAPI engineer with Postgres experience")
    buffer = io.BytesIO()
    document.save(buffer)
    parsed = parse_document(
        content=buffer.getvalue(),
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename="resume.docx",
    )
    assert "Python" in parsed.text


def test_mock_provider_is_labeled_mock() -> None:
    provider = MockModelProvider()
    assert provider.name == "mock"
    result = provider.extract_resume_profile("Python FastAPI developer")
    assert "python" in result.value.skills
    assert result.usage.usage_available is True


def test_mock_assesses_all_criteria_from_profile() -> None:
    provider = MockModelProvider()
    profile = provider.extract_resume_profile(
        "Python FastAPI developer with Postgres experience who led platform projects"
    ).value.model_dump()
    batch = provider.assess_criteria_from_profile(
        criteria=[
            {"key": "technical_skills", "weight": 50, "mandatory": True},
            {"key": "preferred_skills", "weight": 50, "mandatory": False},
        ],
        profile=profile,
    )
    assert len(batch.value) == 2
    assert batch.value[0].criterion_key == "technical_skills"
    assert batch.value[0].status == "satisfied"
    assert batch.usage.usage_available is True


def test_estimate_cost_distinguishes_unavailable() -> None:
    assert estimate_cost(input_tokens=None, output_tokens=None, embedding_tokens=None) is None
    cost = estimate_cost(
        input_tokens=1_000_000,
        output_tokens=0,
        embedding_tokens=0,
        input_rate=Decimal("1.00"),
    )
    assert cost == Decimal("1.00")


def test_score_does_not_treat_unknown_as_not_satisfied() -> None:
    result = score_candidate(
        [
            CriterionInput(
                key="technical_skills",
                weight=Decimal("100"),
                mandatory=True,
                score=Decimal("0"),
                status="unknown",
            )
        ]
    )
    assert result.mandatory_status == "unknown"
