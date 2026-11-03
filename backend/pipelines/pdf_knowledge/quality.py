"""Lightweight readability checks, not scientific verification."""
import re
import unicodedata

VERSION = "readable-source-v1"


class QualityError(ValueError):
    pass


def words(text):
    return re.findall(r"[^\W_]+", unicodedata.normalize("NFKC", text).casefold())


def readable(text):
    text = text.strip()
    tokens = words(text)
    cjk = sum("\u3400" <= c <= "\u9fff" for c in text)
    return (len(text) >= 20 and sum(c.isalpha() for c in text) >= 12
            and (cjk >= 12 or len(tokens) >= 3 and len(set(tokens)) >= 3)
            and text.count("\ufffd") / max(1, len(text)) < .03)


def substantive(text):
    return readable(text) and len(words(text)) >= 20 and len(text.strip()) >= 100


def validate_answer(parsed, source_text="", *, check_quote=True):
    for index, item in enumerate(parsed.knowledge):
        if not readable(item.claim) or not readable(item.support_quote):
            raise QualityError(f"Item {index + 1} needs a complete readable claim and supporting excerpt; single letters, fragments and placeholders are invalid")
        # A broad overlap check tolerates layout/spacing changes, without claiming
        # exact quote anchoring or independent scientific verification.
        if check_quote and substantive(source_text):
            quote = set(words(item.support_quote))
            if len(quote) >= 5 and len(quote & set(words(source_text))) / len(quote) < .5:
                raise QualityError(f"Item {index + 1} supporting text does not match the supplied source")
    if not parsed.knowledge and substantive(source_text) and parsed.page_kind.casefold() not in {"references", "bibliography"}:
        raise QualityError("Readable source content was returned as an empty extraction")
    return parsed
