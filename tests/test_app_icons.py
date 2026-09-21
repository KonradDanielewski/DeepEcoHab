"""Every icon name the app asks for must have a file in ``assets/icons``.

``components.icon`` masks a span with the SVG, so a name with no file renders as an empty
box rather than raising: ``_SCOPE`` shipped "template" and "bookmark" that way.
"""

import re
from pathlib import Path

from dash import Dash

Dash(__name__, use_pages=True, pages_folder="")

from deepecohab.app.pages import builder  # noqa: E402

APP = Path(__file__).parent.parent / "deepecohab" / "app"
ICON_REF = re.compile(r'icon\(\s*["\']([a-z0-9-]+)["\']|icons/([a-z0-9-]+)\.svg')


def test_every_icon_name_has_a_file():
	have = {p.stem for p in (APP / "assets" / "icons").glob("*.svg")}
	names = {name for name, _ in builder._SCOPE.values()}
	for attr, table in vars(builder).items():
		if "ICON" in attr and isinstance(table, dict):
			names |= set(table.values())
	for path in (*APP.rglob("*.py"), *APP.rglob("*.css"), *APP.rglob("*.js")):
		for match in ICON_REF.finditer(path.read_text(encoding="utf-8")):
			names.add(match.group(1) or match.group(2))
	assert not names - have
