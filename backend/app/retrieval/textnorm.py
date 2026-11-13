"""Text normalization shared by the citation repair and the evaluation."""

import re
import unicodedata


def normalize(text: str) -> str:
    """Lowercase, no accents, one kind of dash and space, no Markdown bold:
    "3–5 business days" and "3-5 **business** days" compare equal."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[‐-―−]", "-", text.lower())
    text = text.replace(" ", " ").replace("**", "")
    return re.sub(r"\s+", " ", text)
