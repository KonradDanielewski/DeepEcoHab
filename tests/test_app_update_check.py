import io
import json

import pytest

from deepecohab.app import services


@pytest.mark.parametrize(
	("installed", "on_pypi", "offered"),
	[
		("0.6.0rc2", "0.5.3", None),  # an rc above the last stable release
		("0.6.0rc2", "0.6.0", "0.6.0"),
		("0.5.3", "0.5.3", None),
		("0.5.2", "0.5.3", "0.5.3"),
	],
)
def test_newer_release(monkeypatch, installed, on_pypi, offered):
	body = json.dumps({"info": {"version": on_pypi}}).encode()
	monkeypatch.setattr(services.urllib.request, "urlopen", lambda *a, **k: io.BytesIO(body))
	monkeypatch.setattr(services, "version", lambda _: installed)
	services.newer_release.cache_clear()
	assert services.newer_release() == offered


def test_newer_release_offline(monkeypatch):
	def unreachable(*_a, **_k):
		raise OSError("no network")

	monkeypatch.setattr(services.urllib.request, "urlopen", unreachable)
	services.newer_release.cache_clear()
	assert services.newer_release() is None
	services.newer_release.cache_clear()
