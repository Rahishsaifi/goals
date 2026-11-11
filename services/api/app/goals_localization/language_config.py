"""Central language configuration for Goals Library Localization.

Single source of truth for frontend and backend. Do not duplicate elsewhere.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class TargetLanguage:
    code: str
    name: str
    azure_translator_code: str
    sheet_code: str
    rtl: bool = False
    translate: bool = True


# Client language list. `code` is the unique selector. `sheet_code` is written
# to the workbook Code column. Variants that share a sheet code stay separate
# choices (European vs Latam Spanish, European vs Canadian French).
# English is the source language and is not a target.
SUPPORTED_LANGUAGES: tuple[TargetLanguage, ...] = (
    TargetLanguage("zh", "Simplified Chinese", "zh-Hans", "zh"),
    TargetLanguage("ja", "Japanese", "ja", "ja"),
    TargetLanguage("nl", "Dutch", "nl", "nl"),
    TargetLanguage("de", "German", "de", "de"),
    TargetLanguage("fr", "European French", "fr", "fr"),
    TargetLanguage("es", "European Spanish", "es", "es"),
    TargetLanguage("es-latam", "Latam Spanish", "es", "es"),
    TargetLanguage("pt", "Brazilian Portuguese", "pt", "pt"),
    TargetLanguage("cs", "Czech", "cs", "cs"),
    TargetLanguage("pl", "Polish", "pl", "pl"),
    TargetLanguage("it", "Italian", "it", "it"),
    TargetLanguage("en-gb", "English UK", "en", "en", translate=False),
    TargetLanguage("fr-ca", "Canadian French", "fr-ca", "fr"),
)

_BY_CODE = {lang.code.lower(): lang for lang in SUPPORTED_LANGUAGES}


def list_languages() -> list[dict[str, object]]:
    return [
        {
            "code": lang.code,
            "name": lang.name,
            "sheet_code": lang.sheet_code,
            "azure_translator_code": lang.azure_translator_code,
            "rtl": lang.rtl,
            "translate": lang.translate,
        }
        for lang in SUPPORTED_LANGUAGES
    ]


def resolve_language(code: str) -> TargetLanguage:
    key = code.strip()
    lang = _BY_CODE.get(key.lower()) or _BY_CODE.get(key)
    if lang is None:
        # zh-Hans is mixed case
        for item in SUPPORTED_LANGUAGES:
            if item.code.lower() == key.lower():
                return item
        raise ValueError(f"Unsupported target language: {code}")
    return lang


# Always-on structural/translation options (semantic QA is controlled by qa_mode).
MANDATORY_OPTIONS: tuple[str, ...] = (
    "translate_goal",
    "translate_description",
    "translate_kra",
    "preserve_technical_fields",
    "preserve_formatting",
    "run_numerical_validation",
    "run_structural_reconciliation",
    "run_category_specific_qa",
)

# foundry = Azure Translator + Foundry semantic QA/correction
# classic = Azure Translator + protected terminology + Python validation (no Foundry)
QA_MODES: tuple[dict[str, str], ...] = (
    {
        "id": "classic",
        "label": "Classic (Translator + Python)",
        "description": (
            "Protected terminology, Azure Translator, numeric/date QA, Excel rebuild. "
            "No Foundry."
        ),
    },
    {
        "id": "foundry",
        "label": "Foundry semantic QA",
        "description": (
            "Same translation path, plus Azure OpenAI meaning checks and auto-correction."
        ),
    },
)

DEFAULT_QA_MODE = "classic"


def resolve_qa_mode(value: str | None) -> str:
    key = (value or DEFAULT_QA_MODE).strip().lower()
    if key not in {"classic", "foundry"}:
        raise ValueError(f"Unsupported qa_mode: {value}. Use classic or foundry.")
    return key

TECHNICAL_FIELDS: tuple[str, ...] = (
    "JobLevelCode",
    "LeaderOrNonLeader",
    "FunctionalArea",
    "JobFunctionCode",
    "Category",
)

TRANSLATABLE_FIELDS: tuple[str, ...] = ("Goal", "Description", "KRA")

STAGE_ORDER: tuple[str, ...] = (
    "file_validation",
    "english_extraction",
    "record_reconciliation",
    "translation",
    "semantic_qa",
    "automatic_correction",
    "technical_validation",
    "special_category_validation",
    "excel_reconstruction",
    "final_hard_gate",
)
