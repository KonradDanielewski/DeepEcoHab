import importlib.resources as resources
import os
import shutil
import sys
from pathlib import Path

from pyshortcuts import make_shortcut


def main():
	"""Create a desktop shortcut that launches the installed deepecohab executable."""
	target = shutil.which("deepecohab")
	if not target:
		sys.exit("Error: 'deepecohab' executable not found on PATH.")

	if sys.platform == "win32":
		dest_dir = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "DeepEcoHab"
	else:
		dest_dir = Path.home() / ".local" / "share" / "deepecohab"

	dest_dir.mkdir(parents=True, exist_ok=True)

	icon_name = "deepecohab.icns" if sys.platform == "darwin" else "deepecohab.ico"
	icon_dest = dest_dir / icon_name

	source = resources.files("deepecohab.app.assets") / icon_name
	with resources.as_file(source) as src_path:
		shutil.copyfile(src_path, icon_dest)

	make_shortcut(
		target,
		name="DeepEcoHab",
		icon=str(icon_dest),
		description="Launch the DeepEcoHab dashboard",
	)
	print("Desktop shortcut created successfully!")


if __name__ == "__main__":
	main()
