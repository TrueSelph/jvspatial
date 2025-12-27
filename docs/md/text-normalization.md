# Text Normalization

jvspatial automatically normalizes Unicode text to ASCII equivalents when persisting data to the database. This prevents encoding issues and ensures consistent data storage across different systems and databases.

## Overview

Text normalization converts Unicode characters (like smart quotes, em dashes, and special spaces) to their ASCII equivalents before saving entities to the database. This feature:

- **Prevents encoding issues**: Avoids problems with Unicode characters like `\u2019` (right single quotation mark)
- **Ensures compatibility**: Guarantees ASCII-only text in database storage
- **Preserves meaning**: Converts characters to their closest ASCII equivalents (e.g., `'` instead of `\u2019`)
- **Works automatically**: Applied transparently during entity save operations
- **Configurable**: Can be enabled or disabled via environment variable

## Configuration

Text normalization is **enabled by default**. Control it with the `JVSPATIAL_TEXT_NORMALIZATION_ENABLED` environment variable:

```bash
# Enable (default)
export JVSPATIAL_TEXT_NORMALIZATION_ENABLED=true

# Disable
export JVSPATIAL_TEXT_NORMALIZATION_ENABLED=false
```

## How It Works

When you save an entity (Node, Edge, Object, or Walker), jvspatial:

1. **Exports the entity** to a dictionary structure
2. **Normalizes all string values** recursively through nested dictionaries and lists
3. **Preserves non-string types** (numbers, booleans, None, etc.)
4. **Saves the normalized data** to the database

The normalization process:

1. **Applies character replacements** for common Unicode characters (quotes, dashes, spaces)
2. **Uses NFKD normalization** to decompose composite characters
3. **Removes combining characters** (diacritics) to get base characters
4. **Encodes to ASCII** as a final step

## Supported Character Conversions

### Quotation Marks

| Unicode | Character | ASCII | Example |
|---------|-----------|-------|---------|
| `\u2018` | Left single quotation mark | `'` | `'Hello'` |
| `\u2019` | Right single quotation mark (apostrophe) | `'` | `Here's` |
| `\u201C` | Left double quotation mark | `"` | `"Hello"` |
| `\u201D` | Right double quotation mark | `"` | `"Hello"` |

### Dashes and Hyphens

| Unicode | Character | ASCII | Example |
|---------|-----------|-------|---------|
| `\u2013` | En dash | `-` | `text-dash` |
| `\u2014` | Em dash | `-` | `text-dash` |
| `\u2015` | Horizontal bar | `-` | `text-dash` |

### Spaces

All Unicode space characters are converted to regular ASCII space (` `):

- Non-breaking space (`\u00A0`)
- En space, Em space (`\u2002`, `\u2003`)
- Thin space, Hair space (`\u2009`, `\u200A`)
- Ideographic space (`\u3000`)
- And many others

### Other Characters

| Unicode | Character | ASCII | Example |
|---------|-----------|-------|---------|
| `\u2026` | Horizontal ellipsis | `...` | `text...` |
| `\u2022` | Bullet | `*` | `* item` |
| `\u00AD` | Soft hyphen | (removed) | - |
| `\u200B` | Zero-width space | (removed) | - |

### Diacritics

Characters with diacritics are converted to base characters:

- `café` → `cafe`
- `naïve` → `naive`
- `résumé` → `resume`
- `ñ` → `n`
- `é` → `e`

## Examples

### Basic Usage

```python
from jvspatial.core.entities import Object

class MyObject(Object):
    text: str = ""

# Unicode text is automatically normalized when saved
obj = MyObject(text="Here\u2019s a story with \u201Cquotes\u201D")
await obj.save()

# The saved data will contain: "Here's a story with \"quotes\""
```

### Nested Structures

Normalization works recursively through nested dictionaries and lists:

```python
data = {
    "utterance": "Tell me\u2014a story",
    "response": "Here\u2019s a \u201Cstory\u201D",
    "events": [
        {"action": "Process\u2026", "status": "done"},
    ],
}

# All string values are normalized automatically
# Result:
# {
#     "utterance": "Tell me-a story",
#     "response": "Here's a \"story\"",
#     "events": [
#         {"action": "Process...", "status": "done"},
#     ],
# }
```

### Non-String Types Preserved

Only strings are normalized; other types remain unchanged:

```python
data = {
    "text": "text\u2019s",      # Normalized
    "number": 42,               # Preserved
    "float": 3.14,              # Preserved
    "bool": True,               # Preserved
    "none": None,               # Preserved
    "list": [1, 2, 3],         # Preserved (numbers)
}
```

## Programmatic Usage

You can also use the normalization functions directly:

```python
from jvspatial.utils.normalization import normalize_text_to_ascii, normalize_data

# Normalize a single string
text = "Here\u2019s text"
normalized = normalize_text_to_ascii(text)
# Result: "Here's text"

# Normalize a data structure
data = {"text": "Here\u2019s", "number": 42}
normalized = normalize_data(data)
# Result: {"text": "Here's", "number": 42}
```

## Checking Normalization Status

```python
from jvspatial.utils.normalization import is_text_normalization_enabled

if is_text_normalization_enabled():
    print("Text normalization is enabled")
else:
    print("Text normalization is disabled")
```

## When to Disable

You may want to disable normalization if:

- You need to preserve exact Unicode characters for display purposes
- You're working with international text that requires specific Unicode characters
- You have a database that fully supports Unicode encoding

**Note**: Most modern databases support Unicode, but normalization ensures consistent ASCII storage and prevents encoding issues across different systems.

## Implementation Details

The normalization process uses:

1. **Character replacement dictionary**: Maps common Unicode characters to ASCII equivalents
2. **NFKD normalization**: Decomposes composite characters using Unicode Normalization Form Compatibility Decomposition
3. **Combining character removal**: Strips diacritics to get base characters
4. **ASCII encoding**: Final encoding step with error handling

This multi-step approach ensures comprehensive coverage of Unicode characters while maintaining performance.

## See Also

- [Environment Configuration](environment-configuration.md) - Full configuration reference
- [Graph Context](graph-context.md) - How entities are saved
- [Entity Reference](entity-reference.md) - Entity save operations

