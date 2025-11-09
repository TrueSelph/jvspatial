# conftest.py - Test configuration for pytest

import pytest


def pytest_collection_modifyitems(config, items):
    """
    Automatically skip tests that use obsolete/removed API.

    This marks tests as skipped if they test functionality that was
    intentionally removed in the composition refactor.
    """
    skip_obsolete = pytest.mark.skip(
        reason="Tests obsolete API - needs rewrite for new architecture"
    )

    # Test files/classes that use removed API
    obsolete_patterns = [
        # MongoDB tests have been updated to use Database interface
        # No longer need to skip them
    ]

    for item in items:
        # Get the test's node ID (path::class::method)
        test_id = item.nodeid

        # Check if this test matches any obsolete patterns
        for pattern in obsolete_patterns:
            if pattern in test_id:
                item.add_marker(skip_obsolete)
                break
