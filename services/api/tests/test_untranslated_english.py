from __future__ import annotations

from app.goals_localization.glossary import ENGLISH_ALLOWLIST
from app.services.goals_localization.untranslated_english import detect_residual_english

_EHSMS = "Environmental Health and Safety Management System"


def _tokens(
    source: str, translated: str, allow: set[str] | frozenset[str] = ENGLISH_ALLOWLIST
) -> list[str]:
    return [
        hit.token.lower()
        for hit in detect_residual_english(
            field="kra",
            source=source,
            translated=translated,
            target_language="nl",
            allowlist=allow,
        )
    ]


def test_system_name_is_english_only_when_it_is_a_terminology_entry() -> None:
    source = f"Lead delivery of sustainability objectives of BCD's {_EHSMS}"
    translated = f"Leid de uitvoering van de duurzaamheidsdoelstellingen van BCD's {_EHSMS}"
    # Not in the terminology list: it is ordinary English and must be flagged.
    assert _tokens(source, translated)
    # Added as an Allow English term: accepted.
    assert _tokens(source, translated, set(ENGLISH_ALLOWLIST) | {_EHSMS}) == []


def test_ordinary_english_phrase_still_flagged() -> None:
    source = "Improve: customer service delivery process is required."
    translated = "Verbeter: customer service delivery process is vereist."
    assert any("customer service delivery" in token for token in _tokens(source, translated))


def test_substring_of_allowlisted_term_is_not_flagged() -> None:
    source = "Support the Safety Management System rollout."
    translated = "Ondersteun de Safety Management System uitrol."
    assert _tokens(source, translated, set(ENGLISH_ALLOWLIST) | {_EHSMS}) == []


def test_two_word_english_phrases_are_flagged() -> None:
    """These passed the hard gate in job 109fce9f because only 3-word runs were checked."""
    cases = [
        (
            "By Q3, delivery owners and business owners confirm the handover.",
            "Uiterlijk in Q3 bevestigen delivery owners en business owners de overdracht.",
            {"delivery owners", "business owners"},
        ),
        (
            "Reduce post-launch service issues by 10%.",
            "Verminder post-launch service problemen met 10%.",
            {"post-launch service"},
        ),
        (
            "Use quarterly business reviews to track progress.",
            "Gebruik driemaandelijkse business reviews om de voortgang te volgen.",
            {"business reviews"},
        ),
        (
            "Improve one in-scope service measure.",
            "Verbeter één in-scope service maatstaf.",
            {"in-scope service"},
        ),
    ]
    for source, translated, expected in cases:
        assert set(_tokens(source, translated)) == expected, translated


def test_translated_text_and_single_shared_words_are_not_flagged() -> None:
    assert _tokens(
        "By Q3, delivery owners and business owners confirm the handover.",
        "Uiterlijk in Q3 bevestigen leveringsverantwoordelijken en "
        "bedrijfseigenaren de overdracht.",
    ) == []
    # One shared word (team, service, platform) is not judged: it may be valid Dutch.
    assert _tokens(
        "Train the service team on the new platform.",
        "Train het serviceteam op het nieuwe platform.",
    ) == []
    # A glossary term next to one ordinary word is not a two-word English phrase.
    assert _tokens(
        "Increase TripSource adoption by 10%.", "Verhoog de TripSource adoption met 10%."
    ) == []


def test_longest_phrase_is_reported_once() -> None:
    tokens = _tokens(
        "Improve the customer service delivery process.",
        "Verbeter het customer service delivery process.",
    )
    assert tokens == ["customer service delivery process"]


def test_english_written_by_the_model_is_flagged() -> None:
    """Job 53ab89a5 passed the gate with "EHSMS" expanded into an English name."""
    source = "During the performance year, monitor and review EHSMS gaps and data needs"
    translated = (
        "Monitor en beoordeel tijdens het prestatiejaar de hiaten in het "
        "Environmental Health and Safety Management System en de databehoeften."
    )
    assert _tokens(source, translated) == ["environmental health and safety management system"]
    # Listed in Terminology: accepted.
    assert _tokens(source, translated, set(ENGLISH_ALLOWLIST) | {_EHSMS}) == []
    # Dutch wording has no English function words.
    assert _tokens(
        source,
        "Monitor en beoordeel tijdens het prestatiejaar de EHSMS-hiaten en de databehoeften.",
    ) == []
