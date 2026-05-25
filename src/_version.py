from pathlib import Path

_VERSION_FILE = Path(__file__).resolve().parent.parent / "VERSION"
_version_string: str | None = None


def get_version() -> str:
    global _version_string
    if _version_string is None:
        _version_string = _VERSION_FILE.read_text().strip()
    return _version_string
