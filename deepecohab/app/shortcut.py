"""Create a clickable desktop shortcut for the DeepEcoHab dashboard.

Installed as the ``deepecohab-shortcut`` console script. Double-clicking the
resulting shortcut launches the ``deepecohab`` entry point, which starts the
Dash server and opens the browser automatically.
"""

import argparse
import importlib.resources as resources
import os
import shutil
import subprocess
import sys
from pathlib import Path

_ICON_NAME = "deepecohab.ico"
_SHORTCUT_NAME = "DeepEcoHab.lnk"


def _persist_icon() -> Path:
	"""Copy the bundled icon to a stable per-user location and return its path.

	The wheel's package data may live inside a zip, and a shortcut needs an icon
	path that outlives this process, so the icon is materialised under
	``%LOCALAPPDATA%`` rather than referenced in place.
	"""
	dest_dir = Path(os.environ["LOCALAPPDATA"]) / "DeepEcoHab"
	dest_dir.mkdir(parents=True, exist_ok=True)
	dest = dest_dir / _ICON_NAME

	source = resources.files("deepecohab.app.assets") / _ICON_NAME
	with resources.as_file(source) as src_path:
		shutil.copyfile(src_path, dest)
	return dest


def _create_shortcut(target: Path, icon: Path, destination: Path) -> None:
	"""Write a Windows ``.lnk`` shortcut via the WScript.Shell COM object."""
	# PowerShell ships with every supported Windows version, so driving
	# WScript.Shell here avoids a pywin32 dependency for a one-shot operation.
	script = (
		"$s = (New-Object -ComObject WScript.Shell)."
		f"CreateShortcut('{destination}');"
		f"$s.TargetPath = '{target}';"
		f"$s.IconLocation = '{icon}';"
		f"$s.WorkingDirectory = '{Path.home()}';"
		"$s.Description = 'Launch the DeepEcoHab dashboard';"
		"$s.Save()"
	)
	subprocess.run(
		["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
		check=True,
	)


def main() -> int:
	"""Create the desktop shortcut, returning a process exit code."""
	parser = argparse.ArgumentParser(
		description="Create a desktop shortcut for the DeepEcoHab dashboard."
	)
	parser.parse_args()

	if sys.platform != "win32":
		print("deepecohab-shortcut only supports Windows desktops.", file=sys.stderr)
		return 1

	target = shutil.which("deepecohab")
	if target is None:
		print(
			"Could not find the 'deepecohab' executable on PATH. "
			"Install it first with 'uv tool install deepecohab'.",
			file=sys.stderr,
		)
		return 1

	icon = _persist_icon()
	destination = Path.home() / "Desktop" / _SHORTCUT_NAME
	_create_shortcut(Path(target), icon, destination)

	print(f"Created shortcut: {destination}")
	return 0


if __name__ == "__main__":
	raise SystemExit(main())
