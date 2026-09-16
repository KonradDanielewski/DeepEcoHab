"""Tests for the recording dashboard's navigation callbacks."""

import contextlib

import pytest
from dash import Dash
from dash._callback_context import context_value
from dash._utils import AttributeDict
from dash.exceptions import PreventUpdate

from deepecohab.app import services

# The page module calls dash.register_page at import time, which needs an app to register
# against; pages_folder="" keeps this one from re-importing the whole pages package.
Dash(__name__, use_pages=True, pages_folder="")

from deepecohab.app.pages import recording  # noqa: E402

_CONTEXT = {"location": "/project", "recording": "rec_b"}


class _Stub:
	def __init__(self):
		self.recordings = [AttributeDict(name=name) for name in ("rec_a", "rec_b", "rec_c")]


@pytest.fixture(autouse=True)
def _project(monkeypatch):
	monkeypatch.setattr(services, "load_project", lambda _location: _Stub())


@contextlib.contextmanager
def _triggered(*inputs):
	"""Dash's context for a callback fired by ``inputs``; none of them means a fresh mount."""
	context_value.set(AttributeDict(triggered_inputs=list(inputs)))
	try:
		yield
	finally:
		context_value.set({})


def test_rebuilt_header_does_not_navigate_on_its_own():
	# rec-select / rec-prev / rec-next are rebuilt into rec-body on every recording switch,
	# so Dash fires this callback with no trigger behind it. Stepping there walked to the
	# previous recording, which rebuilt the header and fired it again.
	with _triggered(), pytest.raises(PreventUpdate):
		recording._switch_recording("rec_b", None, None, _CONTEXT, "?recording=rec_b")


def test_next_click_steps_to_the_following_recording():
	with _triggered({"prop_id": "rec-next.n_clicks", "value": 1}):
		search = recording._switch_recording("rec_b", None, 1, _CONTEXT, "?recording=rec_b")
	assert search == "?recording=rec_c"


def test_prev_click_wraps_past_the_first_recording():
	context = {"location": "/project", "recording": "rec_a"}
	with _triggered({"prop_id": "rec-prev.n_clicks", "value": 1}):
		search = recording._switch_recording("rec_a", 1, None, context, "?recording=rec_a")
	assert search == "?recording=rec_c"
