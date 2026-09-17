"""Invariants HACS and hassfest rely on, checked locally so CI is not the first to notice."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMP = ROOT / "custom_components" / "ios2ha_camera"


def test_manifest_matches_the_domain_and_is_hacs_ready():
    m = json.loads((COMP / "manifest.json").read_text())
    assert m["domain"] == "ios2ha_camera"
    assert m["config_flow"] is True
    assert m["iot_class"] == "local_push"
    assert m["integration_type"] == "device"
    assert m["version"].count(".") == 2
    for key in ("documentation", "issue_tracker", "codeowners", "requirements"):
        assert key in m


def test_hacs_json_pins_the_minimum_home_assistant():
    h = json.loads((ROOT / "hacs.json").read_text())
    assert h["homeassistant"] == "2026.9.1"
    assert h["render_readme"] is True
    assert h["zip_release"] is True
    assert h["filename"] == "ios2ha_camera.zip"


def test_translations_match_strings():
    strings = json.loads((COMP / "strings.json").read_text())
    en = json.loads((COMP / "translations" / "en.json").read_text())
    assert strings == en


def test_fixtures_carry_no_household_details():
    for f in (ROOT / "tests" / "fixtures").glob("*.json"):
        text = f.read_text()
        for needle in ("192.168.", "arcturus", "willroscoe"):
            assert needle not in text, (f.name, needle)


def test_strings_contain_no_urls():
    """Hassfest rejects a URL in a translated string; use a placeholder instead."""
    for name in ("strings.json", "translations/en.json"):
        text = (COMP / name).read_text()
        for scheme in ("http://", "https://"):
            assert scheme not in text, (name, scheme)
