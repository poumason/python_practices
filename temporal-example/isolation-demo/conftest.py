"""Makes the demo's top-level packages importable and isolates storage per test."""
import pytest

from common import settings


@pytest.fixture(autouse=True)
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "DATA_DIR", str(tmp_path / "data"))
    return tmp_path / "data"
