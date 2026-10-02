"""The card's script, run as a browser would run it, with just enough browser to load."""

import json
from pathlib import Path
import shutil
import subprocess

import pytest

CARD = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "ios2ha_camera"
    / "www"
    / "ios2ha-camera-card.js"
)

# A registry that refuses a second definition, as the browser's does; then the
# script loaded twice under two versions, as during an update, or when a resource
# added by hand sits beside the one the integration adds.
HARNESS = """
const defined = new Map();
globalThis.HTMLElement = class {};
globalThis.window = globalThis;
globalThis.customElements = {
  get: (name) => defined.get(name),
  define: (name, cls) => {
    if (defined.has(name)) throw new Error(`"${name}" has already been used with this registry`);
    defined.set(name, cls);
  },
};
const banners = [];
console.info = (...args) => banners.push(args.join(" "));
const errors = [];
for (const v of ["0.5.0", "0.5.1"]) {
  try { await import(`${process.argv[1]}?v=${v}`); } catch (e) { errors.push(String(e)); }
}
console.log(JSON.stringify({
  errors,
  defined: [...defined.keys()],
  cards: window.customCards,
  banners,
}));
"""

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="needs node")


@pytest.fixture(scope="module")
def loaded(tmp_path_factory):
    # As .mjs, node loads it as the browser does, a module per URL; as .js it
    # would take it for CommonJS, cached by path, and the second load never runs.
    script = tmp_path_factory.mktemp("card") / "ios2ha-camera-card.mjs"
    shutil.copy(CARD, script)
    out = subprocess.run(
        ["node", "--input-type=module", "-e", HARNESS, script.as_uri()],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    return json.loads(out.stdout)


def test_loading_the_card_twice_raises_nothing(loaded):
    assert loaded["errors"] == []
    assert sorted(loaded["defined"]) == ["ios2ha-camera-card", "ios2ha-camera-card-editor"]


def test_the_card_is_offered_once_with_its_documentation(loaded):
    assert [c["type"] for c in loaded["cards"]] == ["ios2ha-camera-card"]
    assert loaded["cards"][0]["documentationURL"].startswith("https://github.com/")


def test_the_console_names_the_version_the_browser_loaded(loaded):
    # Read from the script's own URL, which carries the integration's version, so
    # it cannot drift from the release the way a constant in the file would.
    assert any("0.5.0" in b for b in loaded["banners"])
