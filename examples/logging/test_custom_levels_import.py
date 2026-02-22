"""Simple test to verify custom log level imports work."""

import os
import sys

# Add parent directory to path for testing without installation
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

# Test imports
print("Testing imports...")

try:
    from jvspatial.logging import (
        CUSTOM_LEVEL_NUMBER,
        add_custom_log_level,
        get_custom_levels,
        is_custom_level,
    )

    print("✓ Custom level utilities imported successfully")
except Exception as e:
    print(f"✗ Failed to import custom level utilities: {e}")
    sys.exit(1)

try:
    from jvspatial.logging import get_logger

    print("✓ get_logger imported successfully")
except Exception as e:
    print(f"✗ Failed to import get_logger: {e}")
    sys.exit(1)

# Test basic functionality
print("\nTesting functionality...")

try:
    print(f"Pre-registered CUSTOM level: {CUSTOM_LEVEL_NUMBER}")
    print(f"Custom levels: {get_custom_levels()}")
    print(f"Is CUSTOM a custom level? {is_custom_level('CUSTOM')}")
    print(f"Is ERROR a custom level? {is_custom_level('ERROR')}")
    print("✓ Basic functionality works")
except Exception as e:
    print(f"✗ Basic functionality failed: {e}")
    sys.exit(1)

# Test adding a custom level
print("\nTesting add_custom_log_level...")

try:
    AUDIT = add_custom_log_level("AUDIT", 35, "audit")
    print(f"Added AUDIT level: {AUDIT}")
    print(f"Custom levels now: {get_custom_levels()}")
    print("✓ add_custom_log_level works")
except Exception as e:
    print(f"✗ add_custom_log_level failed: {e}")
    sys.exit(1)

# Test JVSpatialLogger has custom() method
print("\nTesting JVSpatialLogger.custom() method...")

try:
    logger = get_logger(__name__)
    if hasattr(logger, "custom"):
        print("✓ JVSpatialLogger has custom() method")
    else:
        print("✗ JVSpatialLogger missing custom() method")
        sys.exit(1)
except Exception as e:
    print(f"✗ JVSpatialLogger test failed: {e}")
    sys.exit(1)

print("\n" + "=" * 60)
print("All import tests passed!")
print("=" * 60)
