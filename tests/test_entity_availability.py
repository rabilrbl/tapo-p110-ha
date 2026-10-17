"""Tests for entity availability after coordinator poll failures."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from custom_components.tapo_p110.binary_sensor import BINARY_SENSORS, TapoP110BinarySensor
from custom_components.tapo_p110.sensor import SENSORS, TapoP110Sensor
from custom_components.tapo_p110.switch import SWITCHES, TapoP110PowerSwitch


def _coordinator(*, last_update_success: bool) -> SimpleNamespace:
    return SimpleNamespace(
        data={
            "device_info": {"device_on": True, "overheat_status": "normal"},
            "energy_usage": {"current_power": 1000},
        },
        host="192.0.2.1",
        last_update_success=last_update_success,
    )


@pytest.mark.parametrize(
    ("entity_type", "description"),
    [
        (TapoP110PowerSwitch, SWITCHES[0]),
        (TapoP110BinarySensor, BINARY_SENSORS[0]),
        (TapoP110Sensor, SENSORS[0]),
    ],
)
def test_entities_are_unavailable_when_last_poll_failed(entity_type, description):
    """Retained coordinator data must not keep entities available after failure."""
    entity = entity_type(_coordinator(last_update_success=False), description, "subentry")

    assert entity.available is False


@pytest.mark.parametrize(
    ("entity_type", "description"),
    [
        (TapoP110PowerSwitch, SWITCHES[0]),
        (TapoP110BinarySensor, BINARY_SENSORS[0]),
        (TapoP110Sensor, SENSORS[0]),
    ],
)
def test_entities_are_available_after_successful_poll(entity_type, description):
    """Entities remain available when their latest poll succeeded."""
    entity = entity_type(_coordinator(last_update_success=True), description, "subentry")

    assert entity.available is True
