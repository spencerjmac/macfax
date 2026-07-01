import re
import unicodedata


def normalize_name(s: str) -> str:
    """
    Unicode-normalize, strip diacritics, lowercase, remove apostrophes and
    common suffixes (Jr., Sr., II, III, IV).  Used for fuzzy player-name
    matching across data sources with inconsistent formatting.
    """
    nfkd = unicodedata.normalize("NFD", s)
    ascii_ = "".join(c for c in nfkd if not unicodedata.combining(c))
    lower = ascii_.lower()
    lower = re.sub(r"[''`]", "", lower)
    # lookahead instead of \b — handles "Jr." at end of string
    lower = re.sub(r"(?<!\w)(jr\.?|sr\.?|ii|iii|iv)(?=\s|$)", "", lower)
    return re.sub(r"\s+", " ", lower).strip()
