"""Test suite for text normalization utilities.

Tests Unicode to ASCII text normalization functionality including:
- Character replacement (quotes, dashes, spaces)
- NFKD normalization
- Combining character removal
- Nested data structure normalization
- Configuration and environment variable handling
"""

import os
from unittest.mock import patch

import pytest

from jvspatial.utils.normalization import (
    is_text_normalization_enabled,
    normalize_data,
    normalize_text_to_ascii,
)


class TestNormalizeTextToAscii:
    """Test normalize_text_to_ascii function."""

    def test_simple_ascii_text(self):
        """Test that simple ASCII text is unchanged."""
        text = "Hello, world!"
        result = normalize_text_to_ascii(text)
        assert result == "Hello, world!"

    def test_right_single_quotation_mark(self):
        """Test conversion of right single quotation mark (apostrophe)."""
        text = "Here\u2019s a story"
        result = normalize_text_to_ascii(text)
        assert result == "Here's a story"
        assert "\u2019" not in result

    def test_left_single_quotation_mark(self):
        """Test conversion of left single quotation mark."""
        text = "\u2018Hello\u2019"
        result = normalize_text_to_ascii(text)
        assert result == "'Hello'"
        assert "\u2018" not in result
        assert "\u2019" not in result

    def test_double_quotation_marks(self):
        """Test conversion of smart double quotation marks."""
        text = "\u201CHello\u201D world"
        result = normalize_text_to_ascii(text)
        assert result == '"Hello" world'
        assert "\u201C" not in result
        assert "\u201D" not in result

    def test_em_dash(self):
        """Test conversion of em dash."""
        text = "Hello\u2014world"
        result = normalize_text_to_ascii(text)
        assert result == "Hello-world"
        assert "\u2014" not in result

    def test_en_dash(self):
        """Test conversion of en dash."""
        text = "Hello\u2013world"
        result = normalize_text_to_ascii(text)
        assert result == "Hello-world"
        assert "\u2013" not in result

    def test_ellipsis(self):
        """Test conversion of horizontal ellipsis."""
        text = "Hello\u2026world"
        result = normalize_text_to_ascii(text)
        assert result == "Hello...world"
        assert "\u2026" not in result

    def test_non_breaking_space(self):
        """Test conversion of non-breaking space."""
        text = "Hello\u00A0world"
        result = normalize_text_to_ascii(text)
        assert result == "Hello world"
        assert "\u00A0" not in result

    def test_various_unicode_spaces(self):
        """Test conversion of various Unicode space characters."""
        spaces = [
            "\u2000",  # En quad
            "\u2001",  # Em quad
            "\u2002",  # En space
            "\u2003",  # Em space
            "\u2009",  # Thin space
            "\u200A",  # Hair space
            "\u202F",  # Narrow no-break space
            "\u3000",  # Ideographic space
        ]
        for space in spaces:
            text = f"Hello{space}world"
            result = normalize_text_to_ascii(text)
            assert result == "Hello world", f"Failed for {space}"
            assert space not in result

    def test_zero_width_characters_removed(self):
        """Test that zero-width characters are removed."""
        text = "Hello\u200Bworld\u200C\u200D"
        result = normalize_text_to_ascii(text)
        assert result == "Helloworld"
        assert "\u200B" not in result
        assert "\u200C" not in result
        assert "\u200D" not in result

    def test_diacritics_removed(self):
        """Test that diacritics are removed from characters."""
        text = "café naïve résumé"
        result = normalize_text_to_ascii(text)
        assert result == "cafe naive resume"
        assert "é" not in result
        assert "ï" not in result

    def test_mixed_unicode_characters(self):
        """Test normalization of text with multiple Unicode characters."""
        text = "Here\u2019s a \u201Cquote\u201D with\u2014dashes and\u2026ellipsis"
        result = normalize_text_to_ascii(text)
        assert result == 'Here\'s a "quote" with-dashes and...ellipsis'
        assert "\u2019" not in result
        assert "\u201C" not in result
        assert "\u201D" not in result
        assert "\u2014" not in result
        assert "\u2026" not in result

    def test_empty_string(self):
        """Test that empty string is handled correctly."""
        result = normalize_text_to_ascii("")
        assert result == ""

    def test_non_string_input(self):
        """Test that non-string input is returned as-is."""
        result = normalize_text_to_ascii(123)
        assert result == 123
        result = normalize_text_to_ascii(None)
        assert result is None
        result = normalize_text_to_ascii(["not", "a", "string"])
        assert result == ["not", "a", "string"]


class TestNormalizeData:
    """Test normalize_data function for nested structures."""

    def test_simple_string(self):
        """Test normalization of a simple string."""
        data = "Here\u2019s text"
        result = normalize_data(data)
        assert result == "Here's text"

    def test_dictionary(self):
        """Test normalization of dictionary values."""
        data = {
            "utterance": "Here\u2019s a story",
            "response": "That\u2019s great!",
            "number": 42,
        }
        result = normalize_data(data)
        assert result["utterance"] == "Here's a story"
        assert result["response"] == "That's great!"
        assert result["number"] == 42  # Non-string preserved

    def test_nested_dictionary(self):
        """Test normalization of nested dictionaries."""
        data = {
            "context": {
                "utterance": "Here\u2019s text",
                "metadata": {
                    "description": "A \u201Cquote\u201D here",
                },
            },
            "number": 123,
        }
        result = normalize_data(data)
        assert result["context"]["utterance"] == "Here's text"
        assert result["context"]["metadata"]["description"] == 'A "quote" here'
        assert result["number"] == 123

    def test_list(self):
        """Test normalization of list items."""
        data = ["Here\u2019s", "some\u2014text", "normal"]
        result = normalize_data(data)
        assert result == ["Here's", "some-text", "normal"]

    def test_nested_list(self):
        """Test normalization of nested lists."""
        data = [
            "Here\u2019s",
            ["nested\u2014text", "more\u2026text"],
            "normal",
        ]
        result = normalize_data(data)
        assert result == ["Here's", ["nested-text", "more...text"], "normal"]

    def test_complex_nested_structure(self):
        """Test normalization of complex nested structures."""
        data = {
            "interaction": {
                "utterance": "Tell me\u2014a story",
                "response": "Here\u2019s a \u201Cstory\u201D",
                "events": [
                    {"action": "Process\u2026", "status": "done"},
                    {"action": "Complete", "status": "ok"},
                ],
            },
            "metadata": {
                "tags": ["tag1", "tag2\u2019s"],
            },
        }
        result = normalize_data(data)
        assert result["interaction"]["utterance"] == "Tell me-a story"
        assert result["interaction"]["response"] == 'Here\'s a "story"'
        assert result["interaction"]["events"][0]["action"] == "Process..."
        assert result["interaction"]["events"][1]["action"] == "Complete"
        assert result["metadata"]["tags"][1] == "tag2's"

    def test_non_string_types_preserved(self):
        """Test that non-string types are preserved."""
        data = {
            "string": "text\u2019s",
            "int": 42,
            "float": 3.14,
            "bool": True,
            "none": None,
            "list": [1, 2, 3],
        }
        result = normalize_data(data)
        assert result["string"] == "text's"
        assert result["int"] == 42
        assert result["float"] == 3.14
        assert result["bool"] is True
        assert result["none"] is None
        assert result["list"] == [1, 2, 3]

    def test_empty_structures(self):
        """Test normalization of empty structures."""
        assert normalize_data({}) == {}
        assert normalize_data([]) == []
        assert normalize_data("") == ""


class TestIsTextNormalizationEnabled:
    """Test is_text_normalization_enabled function."""

    def test_default_enabled(self):
        """Test that normalization is enabled by default."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove the env var if it exists
            if "JVSPATIAL_TEXT_NORMALIZATION_ENABLED" in os.environ:
                del os.environ["JVSPATIAL_TEXT_NORMALIZATION_ENABLED"]
            result = is_text_normalization_enabled()
            assert result is True

    def test_explicitly_enabled(self):
        """Test that normalization can be explicitly enabled."""
        with patch.dict(os.environ, {"JVSPATIAL_TEXT_NORMALIZATION_ENABLED": "true"}):
            result = is_text_normalization_enabled()
            assert result is True

    def test_explicitly_enabled_uppercase(self):
        """Test that uppercase TRUE is accepted."""
        with patch.dict(os.environ, {"JVSPATIAL_TEXT_NORMALIZATION_ENABLED": "TRUE"}):
            result = is_text_normalization_enabled()
            assert result is True

    def test_explicitly_disabled(self):
        """Test that normalization can be disabled."""
        with patch.dict(os.environ, {"JVSPATIAL_TEXT_NORMALIZATION_ENABLED": "false"}):
            result = is_text_normalization_enabled()
            assert result is False

    def test_explicitly_disabled_uppercase(self):
        """Test that uppercase FALSE is accepted."""
        with patch.dict(os.environ, {"JVSPATIAL_TEXT_NORMALIZATION_ENABLED": "FALSE"}):
            result = is_text_normalization_enabled()
            assert result is False

    def test_case_insensitive(self):
        """Test that the check is case-insensitive."""
        with patch.dict(os.environ, {"JVSPATIAL_TEXT_NORMALIZATION_ENABLED": "True"}):
            result = is_text_normalization_enabled()
            assert result is True

        with patch.dict(os.environ, {"JVSPATIAL_TEXT_NORMALIZATION_ENABLED": "False"}):
            result = is_text_normalization_enabled()
            assert result is False


class TestNormalizationIntegration:
    """Integration tests for normalization in real-world scenarios."""

    def test_interaction_log_data(self):
        """Test normalization of typical interaction log data."""
        data = {
            "utterance": "Tell me a story",
            "response": "Here\u2019s a quick story:\n\nOne sunny Saturday, you walked into your kitchen craving the perfect sandwich. You gathered fresh bread, crisp lettuce, juicy tomatoes, and your favorite cheese. As you layered each ingredient, the aroma filled the room. With a final touch of your preferred sauce, you took a bite and smiled\u2014sometimes, the simplest things bring the most joy.",
            "interpretation": "User shares a light-hearted story about making a sandwich, indicating a desire for entertainment rather than seeking information.",
        }
        result = normalize_data(data)
        assert "\u2019" not in result["response"]
        assert "\u2014" not in result["response"]
        assert "Here's" in result["response"]
        assert (
            "smiled-sometimes" in result["response"]
            or "smiled -sometimes" in result["response"]
        )

    def test_preserves_structure(self):
        """Test that data structure is preserved after normalization."""
        original = {
            "nested": {
                "deep": {
                    "value": "text\u2019s",
                    "list": [1, 2, "item\u2014three"],
                },
            },
            "array": ["a", "b", "c"],
        }
        result = normalize_data(original)
        # Structure should be identical
        assert "nested" in result
        assert "deep" in result["nested"]
        assert "value" in result["nested"]["deep"]
        assert "list" in result["nested"]["deep"]
        assert "array" in result
        # Only strings should be normalized
        assert result["nested"]["deep"]["value"] == "text's"
        assert result["nested"]["deep"]["list"][2] == "item-three"
        assert result["nested"]["deep"]["list"][0] == 1
        assert result["array"] == ["a", "b", "c"]
