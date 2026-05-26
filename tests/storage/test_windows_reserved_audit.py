"""Windows-reserved-name rejection (audit §4.18 / SPEC §15.1)."""

import pytest

from jvspatial.storage.exceptions import InvalidPathError
from jvspatial.storage.security.path_sanitizer import PathSanitizer


@pytest.mark.parametrize(
    "filename",
    [
        "CON",
        "con.txt",
        "PRN.json",
        "AUX",
        "NUL.bin",
        "COM1",
        "com9.dat",
        "LPT1",
        "lpt9.log",
    ],
)
def test_sanitize_path_rejects_windows_reserved(filename):
    with pytest.raises(InvalidPathError, match="Reserved Windows filename"):
        PathSanitizer.sanitize_path(filename)


@pytest.mark.parametrize(
    "filename",
    ["CONFIG.json", "context.txt", "PRNT.log", "COMRADE.bin"],
)
def test_sanitize_path_allows_non_reserved(filename):
    """Names that *start* with a reserved stem but are longer must pass."""
    out = PathSanitizer.sanitize_path(filename)
    assert out == filename


def test_sanitize_filename_rejects_reserved():
    with pytest.raises(InvalidPathError, match="Reserved Windows filename"):
        PathSanitizer.sanitize_filename("CON.txt")


def test_sanitize_path_blocks_reserved_in_subdir():
    with pytest.raises(InvalidPathError):
        PathSanitizer.sanitize_path("uploads/CON.txt")
