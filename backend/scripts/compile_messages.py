"""Compile locale/*/LC_MESSAGES/django.po to .mo without needing GNU gettext."""

from pathlib import Path

import polib

for po_path in Path(__file__).resolve().parent.parent.glob("locale/*/LC_MESSAGES/django.po"):
    polib.pofile(str(po_path)).save_as_mofile(str(po_path.with_suffix(".mo")))
    print(f"compiled {po_path}")
