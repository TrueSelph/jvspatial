"""Text normalization utilities for Unicode to ASCII conversion.

This module provides functions for normalizing Unicode text to ASCII equivalents,
preventing encoding issues when persisting data to databases.
"""

from __future__ import annotations

import os
import unicodedata
from typing import Any


def is_text_normalization_enabled() -> bool:
    """Check if text normalization is enabled for database persistence.

    Reads from JVSPATIAL_TEXT_NORMALIZATION_ENABLED environment variable.
    Defaults to True if not set.

    Returns:
        True if text normalization should be applied, False otherwise
    """
    return os.getenv("JVSPATIAL_TEXT_NORMALIZATION_ENABLED", "true").lower() == "true"


def normalize_text_to_ascii(text: str) -> str:
    r"""Normalize Unicode text to ASCII equivalents.

    Uses a comprehensive mapping of Unicode characters to ASCII equivalents,
    then applies NFKD normalization and ASCII encoding to handle any remaining
    edge cases.

    Args:
        text: Input string that may contain Unicode characters

    Returns:
        Normalized ASCII string

    Examples:
        >>> normalize_text_to_ascii("Here's a story")
        "Here's a story"
        >>> normalize_text_to_ascii("smart quotes: "hello" and 'world'")
        'smart quotes: "hello" and \'world\''
        >>> normalize_text_to_ascii("em dash — and en dash –")
        'em dash - and en dash -'
    """
    if not isinstance(text, str):
        return text

    # Comprehensive mapping of Unicode characters to ASCII equivalents
    # Apply this FIRST before encoding to prevent '?' replacements
    replacements = {
        # Quotation marks
        "\u2018": "'",  # Left single quotation mark
        "\u2019": "'",  # Right single quotation mark (apostrophe)
        "\u201A": "'",  # Single low-9 quotation mark
        "\u201B": "'",  # Single high-reversed-9 quotation mark
        "\u2032": "'",  # Prime (minutes, feet)
        "\u2035": "'",  # Reversed prime
        "\u201C": '"',  # Left double quotation mark
        "\u201D": '"',  # Right double quotation mark
        "\u201E": '"',  # Double low-9 quotation mark
        "\u201F": '"',  # Double high-reversed-9 quotation mark
        "\u2033": '"',  # Double prime (seconds, inches)
        "\u2036": '"',  # Reversed double prime
        # Dashes and hyphens
        "\u2013": "-",  # En dash
        "\u2014": "-",  # Em dash
        "\u2015": "-",  # Horizontal bar
        "\u2212": "-",  # Minus sign
        "\uFE58": "-",  # Small em dash
        "\uFE63": "-",  # Small hyphen-minus
        # Ellipsis
        "\u2026": "...",  # Horizontal ellipsis
        # Spaces (various Unicode spaces to regular space)
        "\u00A0": " ",  # Non-breaking space
        "\u2000": " ",  # En quad
        "\u2001": " ",  # Em quad
        "\u2002": " ",  # En space
        "\u2003": " ",  # Em space
        "\u2004": " ",  # Three-per-em space
        "\u2005": " ",  # Four-per-em space
        "\u2006": " ",  # Six-per-em space
        "\u2007": " ",  # Figure space
        "\u2008": " ",  # Punctuation space
        "\u2009": " ",  # Thin space
        "\u200A": " ",  # Hair space
        "\u202F": " ",  # Narrow no-break space
        "\u205F": " ",  # Medium mathematical space
        "\u3000": " ",  # Ideographic space
        # Other common punctuation
        "\u2022": "*",  # Bullet
        "\u2020": "+",  # Dagger
        "\u2021": "++",  # Double dagger
        "\u2039": "<",  # Single left-pointing angle quotation mark
        "\u203A": ">",  # Single right-pointing angle quotation mark
        "\u00AD": "",  # Soft hyphen (remove)
        "\u200B": "",  # Zero-width space (remove)
        "\u200C": "",  # Zero-width non-joiner (remove)
        "\u200D": "",  # Zero-width joiner (remove)
        "\u2060": "",  # Word joiner (remove)
        "\uFEFF": "",  # Zero-width no-break space (remove)
    }

    # Apply replacements first (before encoding)
    result = text
    for unicode_char, ascii_char in replacements.items():
        result = result.replace(unicode_char, ascii_char)

    # Apply NFKD normalization to decompose any remaining composite characters
    result = unicodedata.normalize("NFKD", result)

    # Remove combining characters (diacritics) that NFKD normalization may have exposed
    # This handles cases like é -> e, ñ -> n, etc.
    result = "".join(char for char in result if not unicodedata.combining(char))

    # Final pass: encode to ASCII, replacing any remaining non-ASCII with closest equivalent
    # Use 'replace' to convert any remaining unmappable characters to '?'
    # But we should have handled most cases above
    try:
        result = result.encode("ascii", "replace").decode("ascii")
    except (UnicodeEncodeError, UnicodeDecodeError):
        # Fallback: if encoding fails, try with 'ignore' to remove problematic chars
        result = result.encode("ascii", "ignore").decode("ascii")

    return result


def normalize_data(obj: Any) -> Any:
    """Recursively normalize all string values in a data structure to ASCII.

    Processes nested dictionaries and lists, normalizing all string values
    while preserving the structure and non-string types.

    Args:
        obj: Data structure (dict, list, str, or other type)

    Returns:
        Normalized data structure with all strings converted to ASCII

    Examples:
        >>> normalize_data({"text": "Here's a story", "number": 42})
        {'text': "Here's a story", 'number': 42}
        >>> normalize_data(["item1", "item2", {"nested": "value"}])
        ['item1', 'item2', {'nested': 'value'}]
    """
    if isinstance(obj, str):
        return normalize_text_to_ascii(obj)
    if isinstance(obj, dict):
        return {k: normalize_data(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [normalize_data(item) for item in obj]
    # For other types (int, float, bool, None, etc.), return as-is
    return obj
