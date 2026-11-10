from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from pydantic import BaseModel, Field


class ExtractedProfile(BaseModel):
    full_name: str | None = None
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    skills: list[str] = Field(default_factory=list)
    job_titles: list[str] = Field(default_factory=list)
    employers: list[str] = Field(default_factory=list)
    qualifications: list[str] = Field(default_factory=list)
    summary: str = ""
    evidence_passages: list[str] = Field(default_factory=list)


class CriterionAssessment(BaseModel):
    criterion_key: str
    score: float = Field(ge=0, le=100)
    status: Literal["satisfied", "not_satisfied", "unknown"]
    passage: str | None = None
    page_number: int | None = None


class UsageTelemetry(BaseModel):
    input_tokens: int | None = None
    output_tokens: int | None = None
    embedding_tokens: int | None = None
    usage_available: bool = False
    model_deployment: str | None = None
    provider_request_id: str | None = None


@dataclass(frozen=True)
class ProviderResult[T]:
    value: T
    usage: UsageTelemetry


class ModelProvider(Protocol):
    name: str

    def extract_resume_profile(self, text: str) -> ProviderResult[ExtractedProfile]: ...

    def extract_jd_requirements(self, text: str) -> ProviderResult[list[dict[str, object]]]: ...

    def assess_criteria_from_profile(
        self, *, criteria: list[dict[str, object]], profile: dict[str, object]
    ) -> ProviderResult[list[CriterionAssessment]]: ...


class MockModelProvider:
    """Explicit local mock. Never used as a silent fallback for a live provider."""

    name = "mock"

    def extract_resume_profile(self, text: str) -> ProviderResult[ExtractedProfile]:
        from app.parsers.contact import extract_contact_fields

        lowered = text.lower()
        skills = [s for s in ("python", "fastapi", "postgres", "azure", "react") if s in lowered]
        titles = [t for t in ("engineer", "developer", "recruiter") if t in lowered]
        contact = extract_contact_fields(text)
        profile = ExtractedProfile(
            full_name=contact.get("full_name"),
            email=contact.get("email"),
            phone=contact.get("phone"),
            location=contact.get("location"),
            skills=skills or ["unspecified"],
            job_titles=titles,
            employers=[],
            qualifications=[],
            summary=text[:240],
            evidence_passages=[text[:160]] if text else [],
        )
        return ProviderResult(
            value=profile,
            usage=UsageTelemetry(
                input_tokens=len(text.split()),
                output_tokens=40,
                usage_available=True,
                model_deployment="mock-extract-v1",
            ),
        )

    def extract_jd_requirements(self, text: str) -> ProviderResult[list[dict[str, object]]]:
        defaults: list[dict[str, object]] = [
            {
                "key": "technical_skills",
                "display_name": "Technical skills",
                "weight": 30,
                "mandatory": True,
                "severity": "mandatory",
                "description": "Core technical skills from the JD",
            },
            {
                "key": "relevant_experience",
                "display_name": "Relevant experience",
                "weight": 20,
                "mandatory": False,
                "severity": "preferred",
                "description": "Years and relevance of experience",
            },
            {
                "key": "project_domain",
                "display_name": "Project/domain experience",
                "weight": 15,
                "mandatory": False,
                "severity": "preferred",
                "description": "Domain projects",
            },
            {
                "key": "qualifications",
                "display_name": "Qualifications",
                "weight": 10,
                "mandatory": False,
                "severity": "informational",
                "description": "Degrees and certifications",
            },
            {
                "key": "responsibilities",
                "display_name": "Role responsibilities",
                "weight": 15,
                "mandatory": False,
                "severity": "preferred",
                "description": "Overlap with stated responsibilities",
            },
            {
                "key": "preferred_skills",
                "display_name": "Preferred skills",
                "weight": 10,
                "mandatory": False,
                "severity": "preferred",
                "description": "Nice-to-have skills",
            },
        ]
        if "python" in text.lower():
            defaults[0]["description"] = "Python and related stack"
        return ProviderResult(
            value=defaults,
            usage=UsageTelemetry(
                input_tokens=len(text.split()),
                output_tokens=80,
                usage_available=True,
                model_deployment="mock-jd-v1",
            ),
        )

    def assess_criteria_from_profile(
        self, *, criteria: list[dict[str, object]], profile: dict[str, object]
    ) -> ProviderResult[list[CriterionAssessment]]:
        haystack = " ".join(
            [
                str(profile.get("summary") or ""),
                " ".join(str(item) for item in profile.get("skills") or []),
                " ".join(str(item) for item in profile.get("job_titles") or []),
                " ".join(str(item) for item in profile.get("employers") or []),
                " ".join(str(item) for item in profile.get("qualifications") or []),
                " ".join(str(item) for item in profile.get("evidence_passages") or []),
            ]
        ).lower()
        keywords = {
            "technical_skills": ("python", "fastapi", "postgres", "sql", "react"),
            "relevant_experience": ("year", "experience", "engineer", "developer"),
            "project_domain": ("project", "platform", "recruit"),
            "qualifications": ("bachelor", "master", "certified", "degree"),
            "responsibilities": ("owned", "led", "built", "designed"),
            "preferred_skills": ("azure", "docker", "kubernetes"),
        }
        assessments: list[CriterionAssessment] = []
        for criterion in criteria:
            key = str(criterion.get("key", "unknown"))
            hits = [k for k in keywords.get(key, ()) if k in haystack]
            if not haystack.strip():
                status: Literal["satisfied", "not_satisfied", "unknown"] = "unknown"
                score = 0.0
                passage = None
            elif hits:
                status = "satisfied"
                score = min(100.0, 40.0 + 15.0 * len(hits))
                passage = hits[0]
            else:
                status = "unknown"
                score = 0.0
                passage = None
            assessments.append(
                CriterionAssessment(
                    criterion_key=key,
                    score=score,
                    status=status,
                    passage=passage,
                    page_number=1,
                )
            )
        return ProviderResult(
            value=assessments,
            usage=UsageTelemetry(
                input_tokens=max(20, len(haystack.split()) + 20 * len(criteria)),
                output_tokens=25 * max(len(criteria), 1),
                usage_available=True,
                model_deployment="mock-assess-v1",
            ),
        )


def get_model_provider(name: str = "mock") -> ModelProvider:
    if name == "mock":
        return MockModelProvider()
    if name == "foundry":
        from app.integrations.foundry_provider import FoundryModelProvider

        # Explicit live provider. Failures must surface; never fall back to mock.
        return FoundryModelProvider()
    raise RuntimeError(
        f"Unknown MODEL_PROVIDER={name!r}. Supported values: mock, foundry."
    )
