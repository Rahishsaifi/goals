from __future__ import annotations

import re

_EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.I)
_PHONE_RE = re.compile(
    r"(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}"
)
_LOCATION_RE = re.compile(
    r"\b([A-Z][a-zA-Z]+(?:\s[A-Z][a-zA-Z]+)*),\s*([A-Z]{2})\b"
)


def extract_contact_fields(text: str) -> dict[str, str | None]:
    """Best-effort contact fields from resume header text."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    email_match = _EMAIL_RE.search(text)
    phone_match = _PHONE_RE.search(text)
    location_match = _LOCATION_RE.search(text)

    full_name: str | None = None
    for line in lines[:6]:
        if _EMAIL_RE.search(line) or _PHONE_RE.search(line):
            continue
        if "@" in line or "|" in line:
            continue
        words = line.split()
        if 2 <= len(words) <= 4 and all(part[:1].isalpha() for part in words):
            # Prefer title-cased / uppercase name lines over job titles.
            if line.isupper() or all(part[:1].isupper() for part in words):
                if not any(
                    token.lower()
                    in {
                        "software",
                        "developer",
                        "engineer",
                        "resume",
                        "curriculum",
                        "vitae",
                    }
                    for token in words
                ):
                    full_name = " ".join(word.capitalize() for word in words)
                    break

    return {
        "full_name": full_name,
        "email": email_match.group(0) if email_match else None,
        "phone": phone_match.group(0).strip() if phone_match else None,
        "location": (
            f"{location_match.group(1)}, {location_match.group(2)}"
            if location_match
            else None
        ),
    }
