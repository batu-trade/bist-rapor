import json
import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
FIX = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def fixture_text():
    def read(name):
        return (FIX / name).read_text(encoding="utf-8")
    return read


@pytest.fixture
def fixture_json(fixture_text):
    def read(name):
        return json.loads(fixture_text(name))
    return read


@pytest.fixture
def tmp_root(tmp_path):
    """Gerçek config dosyalarının kopyasıyla geçici proje kökü (ağ işçisi = 1)."""
    shutil.copytree(ROOT / "config", tmp_path / "config")
    shutil.copytree(ROOT / "web", tmp_path / "web")
    s = json.loads((tmp_path / "config" / "settings.json").read_text(encoding="utf-8"))
    s["network"]["workers"] = 1
    (tmp_path / "config" / "settings.json").write_text(json.dumps(s, ensure_ascii=False), encoding="utf-8")
    return tmp_path
