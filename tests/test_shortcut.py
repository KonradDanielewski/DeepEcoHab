"""Cross-platform behavior of the deepecohab-shortcut entry point.

pyshortcuts.make_shortcut itself talks to OS-native APIs (win32com on Windows,
Automator/codesign on macOS) and is out of scope here; it is monkeypatched out
so these tests stay hermetic. What we do own and must verify per-OS is the
logic in shortcut.main(): resolving the target executable, picking a
platform-appropriate install directory, and extracting the bundled icon.
"""

from pathlib import Path

import pytest

from deepecohab.app import shortcut


@pytest.fixture
def fake_make_shortcut(monkeypatch):
	calls = []
	monkeypatch.setattr(shortcut, "make_shortcut", lambda *a, **k: calls.append((a, k)))
	return calls


@pytest.fixture
def fake_target(monkeypatch, tmp_path):
	target = str(tmp_path / "deepecohab-bin")
	monkeypatch.setattr(shortcut.shutil, "which", lambda name: target)
	return target


def test_main_exits_when_executable_not_on_path(monkeypatch):
	monkeypatch.setattr(shortcut.shutil, "which", lambda name: None)
	with pytest.raises(SystemExit, match="not found on PATH"):
		shortcut.main()


@pytest.mark.parametrize(
	"platform, localappdata_set",
	[("win32", True), ("win32", False), ("linux", None), ("darwin", None)],
)
def test_main_picks_platform_appropriate_dest_dir(
	monkeypatch, tmp_path, fake_make_shortcut, fake_target, platform, localappdata_set
):
	monkeypatch.setattr(shortcut.sys, "platform", platform)
	fake_home = tmp_path / "home"
	monkeypatch.setattr(shortcut.Path, "home", lambda: fake_home)

	if platform == "win32" and localappdata_set:
		localappdata = tmp_path / "localappdata"
		monkeypatch.setenv("LOCALAPPDATA", str(localappdata))
		expected_dir = localappdata / "DeepEcoHab"
	else:
		monkeypatch.delenv("LOCALAPPDATA", raising=False)
		expected_dir = (
			fake_home / "DeepEcoHab"
			if platform == "win32"
			else fake_home / ".local" / "share" / "deepecohab"
		)

	shortcut.main()

	assert len(fake_make_shortcut) == 1
	args, kwargs = fake_make_shortcut[0]
	assert args[0] == fake_target
	assert kwargs["name"] == "DeepEcoHab"

	icon_path = Path(kwargs["icon"])
	assert icon_path.parent == expected_dir
	assert icon_path.name == ("deepecohab.icns" if platform == "darwin" else "deepecohab.ico")
	assert icon_path.exists()
	assert icon_path.stat().st_size > 0


@pytest.mark.parametrize(
	"platform, icon_name", [("linux", "deepecohab.ico"), ("darwin", "deepecohab.icns")]
)
def test_main_copies_bundled_icon_contents(
	monkeypatch, tmp_path, fake_make_shortcut, fake_target, platform, icon_name
):
	monkeypatch.setattr(shortcut.sys, "platform", platform)
	monkeypatch.setattr(shortcut.Path, "home", lambda: tmp_path / "home")
	monkeypatch.delenv("LOCALAPPDATA", raising=False)

	shortcut.main()

	_, kwargs = fake_make_shortcut[0]
	copied = Path(kwargs["icon"]).read_bytes()

	import importlib.resources as resources

	source = resources.files("deepecohab.app.assets") / icon_name
	with resources.as_file(source) as src_path:
		assert copied == src_path.read_bytes()
