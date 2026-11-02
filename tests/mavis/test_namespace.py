"""Mavis composes the upstream core without borrowing its credentials or optional agents."""
import json
import os
from pathlib import Path
import subprocess
import sys


def test_isolated_namespace_and_optional_features_off(tmp_path):
    env = os.environ.copy()
    env.update(DAFEIYU_MAVIS="1", MAVIS_DATA_HOME=str(tmp_path))
    code = """
import json
from pet.config import Config
from pet.feature_activation import is_active
c = Config()
print(json.dumps({'directory':str(c.dir),'gates':[is_active(x) for x in ['agent_link','chat','voice','system_tools','proactive']]}))
"""
    result = subprocess.run([sys.executable, "-c", code], env=env, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert Path(data["directory"]) == tmp_path / "DaFeiYuMavis"
    assert data["gates"] == [False] * 5
    assert not (tmp_path / "dsh-pet-standalone").exists()


def test_mavis_never_imports_legacy_pet_config_or_sessions(tmp_path):
    legacy = tmp_path / "dsh-pet-standalone"
    legacy.mkdir()
    original = '{"opacity":0.42}'
    (legacy / "config.json").write_text(original)
    (legacy / "sessions").mkdir()
    (legacy / "sessions" / "private.txt").write_text("fixture, not user data")
    env = os.environ.copy()
    env.update(DAFEIYU_MAVIS="1", MAVIS_DATA_HOME=str(tmp_path))
    result = subprocess.run([sys.executable, "-c", "from pet.config import Config; Config()"], env=env, capture_output=True, timeout=15)
    assert result.returncode == 0
    assert not (tmp_path / "DaFeiYuMavis" / "config.json").exists()
    assert not (tmp_path / "DaFeiYuMavis" / "sessions").exists()
    assert (legacy / "config.json").read_text() == original
