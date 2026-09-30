"""Tests for recording devices: what the model accepts, and how events refer to them."""

import pytest
import strategies
from pydantic import ValidationError

from deepecohab.core.data_model import Bout, Device, Event, Recording


def device(name: str = "lick_1", position: str = "tunnel_1", **fields) -> Device:
	fields = {"device_type": "Lickometer", "description": "", "antenna": "1", **fields}
	return Device(name=name, position=position, **fields)


def event(*devices: str) -> Event:
	bout = Bout(start=strategies.at(2023, 5, 24, 13), end=strategies.at(2023, 5, 24, 14))
	return Event(name="sucrose", description="", bouts=[bout], devices=list(devices) or None)


# --- the model ---------------------------------------------------------------
@pytest.mark.parametrize(
	("antenna", "ttl_port"), [("1", None), (None, "2"), ("1", "2")], ids=["antenna", "TTL", "both"]
)
def test_device_is_read_by_an_antenna_a_ttl_port_or_both(antenna, ttl_port):
	device(antenna=antenna, TTL_port=ttl_port)


def test_device_without_antenna_or_ttl_port_is_rejected():
	with pytest.raises(ValidationError, match="needs an antenna, a TTL_port or both"):
		device(antenna=None, TTL_port=None)


@pytest.mark.parametrize("field", ["name", "device_type", "antenna", "TTL_port"])
def test_blank_identifiers_are_rejected(field):
	with pytest.raises(ValidationError, match="at least 1 character"):
		device(**{field: " "})


def test_device_type_matches_exactly():
	"""Types are generated, so no case folding: two spellings are two types."""
	assert device(device_type="LickoMeter").device_type == "LickoMeter"


def test_misspelt_device_field_is_rejected():
	with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
		Device.model_validate({**device().model_dump(), "postion": "tunnel_1"})


def test_event_needs_a_device_if_it_names_any():
	"""An empty list is ambiguous: an event without devices leaves ``devices`` out."""
	with pytest.raises(ValidationError):
		Event(name="x", description="", bouts=event().bouts, devices=[])


def test_devices_of_one_type_may_share_a_recording():
	"""Two lickometers in different places, grouped later by their shared type."""
	recording = strategies.analysis_recording(
		devices=[device("lick_1", "tunnel_1"), device("lick_2", "cage_3")],
		events=[event("lick_1", "lick_2")],
	)

	assert {d.device_type for d in recording.devices} == {"Lickometer"}
	assert recording.events[0].devices == ["lick_1", "lick_2"]


@pytest.mark.parametrize(
	("devices", "events", "match"),
	[
		pytest.param([device(), device()], [], "unique", id="duplicate name"),
		pytest.param(
			[device(position="tunnel_9")], [], "layout does not have", id="unknown position"
		),
		pytest.param(
			[device(position="undefined")], [], "layout does not have", id="undefined sentinel"
		),
		pytest.param(
			[device(position="c1_c2")], [], "layout does not have", id="directional tunnel"
		),
		pytest.param([device()], [event("pump")], "does not have", id="unknown device"),
		pytest.param([], [event("lick_1")], "does not have", id="no devices declared"),
	],
)
def test_recording_rejects_devices_it_cannot_place(devices, events, match):
	with pytest.raises(ValidationError, match=match):
		strategies.analysis_recording(devices=devices, events=events)


# --- persistence -------------------------------------------------------------
def test_config_without_devices_still_loads():
	"""Configs written before devices existed have no such key."""
	recording = strategies.analysis_recording(events=[event()])
	config = recording.model_dump(mode="json")
	del config["devices"]
	del config["events"][0]["devices"]

	restored = Recording.model_validate({**config, "data": recording.data})

	assert restored.devices == []
	assert restored.events[0].devices is None


def test_devices_survive_a_config_round_trip():
	recording = strategies.analysis_recording(
		devices=[device(TTL_port="2")], events=[event("lick_1")]
	)
	restored = Recording.model_validate(
		{**recording.model_dump(mode="json"), "data": recording.data}
	)

	assert restored.devices == recording.devices
	assert restored.events == recording.events
