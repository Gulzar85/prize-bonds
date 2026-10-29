"""The fixtures are byte-exact copies of files published by National Savings; the manifest pins their hashes.

If this fails after a checkout, a tool rewrote line endings (see .gitattributes) and every golden test is suspect.
"""

import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MANIFEST = json.loads((ROOT / "fixtures" / "draws" / "manifest.json").read_text(encoding="utf-8"))["fixtures"]


@pytest.mark.parametrize("entry", MANIFEST, ids=[e["file"].rsplit("/", 1)[-1] for e in MANIFEST])
def test_fixture_bytes_match_the_manifest(entry):
    data = (ROOT.parent / entry["file"]).read_bytes()
    assert len(data) == entry["size_bytes"]
    assert hashlib.sha256(data).hexdigest() == entry["sha256"]


def test_manifest_has_every_fixture_and_nothing_else():
    on_disk = {
        f"tests/fixtures/draws/{p.relative_to(ROOT / 'fixtures' / 'draws').as_posix()}"
        for p in (ROOT / "fixtures" / "draws").rglob("*")
        if p.is_file() and p.name != "manifest.json"
    }
    assert on_disk == {e["file"] for e in MANIFEST}


def test_every_manifest_entry_records_its_source():
    for entry in MANIFEST:
        assert entry["source_url"].startswith("https://savings.gov.pk/wp-content/uploads/")
        assert entry["verification"] in {"hand-read", "pending-hand-read"}
