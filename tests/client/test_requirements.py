"""The client installs on machines that have no server, so it stays light."""

from pathlib import Path


def test_client_requirements_stay_small() -> None:
    requirements = (Path(__file__).resolve().parents[2] / "client" / "requirements.txt").read_text(encoding="utf-8")
    names = {
        line.split(">=")[0].split("==")[0].split("<")[0].strip().lower()
        for line in requirements.splitlines()
        if line.strip() and not line.startswith("#")
    }
    assert names == {"httpx", "pydantic"}
