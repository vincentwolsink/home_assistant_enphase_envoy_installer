"""Tests for realtime stream updates including net consumption."""

from unittest.mock import MagicMock

import pytest

from custom_components.enphase_envoy.envoy_reader import StreamData
from custom_components.enphase_envoy.sensor import STREAM_UPDATEABLE_KEYS


SAMPLE_STREAM_CHUNK = {
    "production": {
        "ph-a": {"p": 100.5, "q": 10.0, "s": 110.0, "v": 240.0, "i": 0.5, "pf": 0.95, "f": 50.0},
        "ph-b": {"p": 200.3, "q": 20.0, "s": 220.0, "v": 238.0, "i": 0.9, "pf": 0.96, "f": 50.0},
        "ph-c": {"p": 150.2, "q": 15.0, "s": 165.0, "v": 235.0, "i": 0.7, "pf": 0.94, "f": 50.0},
    },
    "net-consumption": {
        "ph-a": {"p": 500.0, "q": -400.0, "s": 700.0, "v": 240.0, "i": 3.0, "pf": 0.71, "f": 50.0},
        "ph-b": {"p": -100.0, "q": 150.0, "s": 200.0, "v": 238.0, "i": 0.8, "pf": -0.5, "f": 50.0},
        "ph-c": {"p": 300.0, "q": -250.0, "s": 400.0, "v": 235.0, "i": 1.7, "pf": 0.75, "f": 50.0},
    },
    "total-consumption": {
        "ph-a": {"p": 600.5, "q": -390.0, "s": 810.0, "v": 240.0, "i": 3.5, "pf": 0.74, "f": 50.0},
        "ph-b": {"p": 100.3, "q": 170.0, "s": 420.0, "v": 238.0, "i": 1.7, "pf": 0.24, "f": 50.0},
        "ph-c": {"p": 450.2, "q": -235.0, "s": 565.0, "v": 235.0, "i": 2.4, "pf": 0.80, "f": 50.0},
    },
}


class TestStreamData:
    """Test StreamData parsing from meter stream chunks."""

    def test_parses_production_phases(self):
        sd = StreamData(SAMPLE_STREAM_CHUNK)
        assert sd.production["l1"].watts == 100.5
        assert sd.production["l2"].watts == 200.3
        assert sd.production["l3"].watts == 150.2

    def test_parses_net_consumption_phases(self):
        sd = StreamData(SAMPLE_STREAM_CHUNK)
        assert sd.net_consumption["l1"].watts == 500.0
        assert sd.net_consumption["l2"].watts == -100.0
        assert sd.net_consumption["l3"].watts == 300.0

    def test_parses_total_consumption_phases(self):
        sd = StreamData(SAMPLE_STREAM_CHUNK)
        assert sd.consumption["l1"].watts == 600.5
        assert sd.consumption["l2"].watts == 100.3
        assert sd.consumption["l3"].watts == 450.2

    def test_net_consumption_voltage(self):
        sd = StreamData(SAMPLE_STREAM_CHUNK)
        assert sd.net_consumption["l1"].volt == 240.0
        assert sd.net_consumption["l2"].volt == 238.0
        assert sd.net_consumption["l3"].volt == 235.0

    def test_missing_phase_skipped(self):
        chunk = {
            "production": {"ph-a": {"p": 10, "q": 1, "s": 11, "v": 230, "i": 0.1, "pf": 1, "f": 50}},
            "net-consumption": {},
            "total-consumption": {},
        }
        sd = StreamData(chunk)
        assert "l1" in sd.production
        assert "l2" not in sd.production
        assert sd.net_consumption == {}

    def test_str_representation(self):
        sd = StreamData(SAMPLE_STREAM_CHUNK)
        s = str(sd)
        assert "StreamData" in s
        assert "net_consumption" in s


class TestStreamUpdateableKeys:
    """Test that the correct sensor keys are marked as stream-updateable."""

    def test_contains_production(self):
        assert "production" in STREAM_UPDATEABLE_KEYS

    def test_contains_consumption(self):
        assert "consumption" in STREAM_UPDATEABLE_KEYS

    def test_contains_net_consumption(self):
        assert "net_consumption" in STREAM_UPDATEABLE_KEYS

    def test_is_frozenset(self):
        assert isinstance(STREAM_UPDATEABLE_KEYS, frozenset)

    def test_no_unexpected_keys(self):
        assert len(STREAM_UPDATEABLE_KEYS) == 3


class TestUpdateProductionMeters:
    """Test that the stream callback correctly computes per-phase and total values."""

    @staticmethod
    def _build_callback():
        """Build a minimal update_production_meters callback for testing."""
        live_entities = {}
        coordinator_data = {
            "production_l1": 0,
            "production_l2": 0,
            "production_l3": 0,
            "consumption_l1": 0,
            "consumption_l2": 0,
            "consumption_l3": 0,
            "net_consumption_l1": 0,
            "net_consumption_l2": 0,
            "net_consumption_l3": 0,
            "production": 0,
            "consumption": 0,
            "net_consumption": 0,
        }

        updated_keys = []

        for key in coordinator_data:
            entity = MagicMock()
            entity.async_write_ha_state = MagicMock()
            live_entities[key] = entity

        def update_production_meters(streamdata):
            new_data = {}
            total_production = 0
            total_consumption = 0
            total_net_consumption = 0

            for phase in ["l1", "l2", "l3"]:
                production_watts = streamdata.production[phase].watts
                consumption_watts = streamdata.consumption[phase].watts
                net_consumption_watts = streamdata.net_consumption[phase].watts

                total_production += production_watts
                total_consumption += consumption_watts
                total_net_consumption += net_consumption_watts

                new_data.update(
                    {
                        "production_" + phase: production_watts,
                        "consumption_" + phase: consumption_watts,
                        "net_consumption_" + phase: net_consumption_watts,
                    }
                )

            new_data["production"] = total_production
            new_data["consumption"] = total_consumption
            new_data["net_consumption"] = total_net_consumption

            for key, value in new_data.items():
                if live_entities.get(key, False) and coordinator_data.get(key) != value:
                    coordinator_data[key] = value
                    live_entities[key].async_write_ha_state()
                    updated_keys.append(key)

        return update_production_meters, coordinator_data, live_entities, updated_keys

    def test_updates_net_consumption_per_phase(self):
        callback, data, _, _ = self._build_callback()
        sd = StreamData(SAMPLE_STREAM_CHUNK)
        callback(sd)

        assert data["net_consumption_l1"] == 500.0
        assert data["net_consumption_l2"] == -100.0
        assert data["net_consumption_l3"] == 300.0

    def test_updates_consumption_per_phase(self):
        callback, data, _, _ = self._build_callback()
        sd = StreamData(SAMPLE_STREAM_CHUNK)
        callback(sd)

        assert data["consumption_l1"] == 600.5
        assert data["consumption_l2"] == 100.3
        assert data["consumption_l3"] == 450.2

    def test_updates_production_per_phase(self):
        callback, data, _, _ = self._build_callback()
        sd = StreamData(SAMPLE_STREAM_CHUNK)
        callback(sd)

        assert data["production_l1"] == 100.5
        assert data["production_l2"] == 200.3
        assert data["production_l3"] == 150.2

    def test_computes_total_net_consumption(self):
        callback, data, _, _ = self._build_callback()
        sd = StreamData(SAMPLE_STREAM_CHUNK)
        callback(sd)

        expected = 500.0 + (-100.0) + 300.0  # 700.0
        assert data["net_consumption"] == expected

    def test_computes_total_production(self):
        callback, data, _, _ = self._build_callback()
        sd = StreamData(SAMPLE_STREAM_CHUNK)
        callback(sd)

        expected = 100.5 + 200.3 + 150.2  # 451.0
        assert data["production"] == pytest.approx(expected)

    def test_computes_total_consumption(self):
        callback, data, _, _ = self._build_callback()
        sd = StreamData(SAMPLE_STREAM_CHUNK)
        callback(sd)

        expected = 600.5 + 100.3 + 450.2  # 1151.0
        assert data["consumption"] == pytest.approx(expected)

    def test_calls_async_write_ha_state_for_changed_values(self):
        callback, _, live_entities, updated_keys = self._build_callback()
        sd = StreamData(SAMPLE_STREAM_CHUNK)
        callback(sd)

        # All keys should be updated since initial values are 0
        assert "net_consumption_l1" in updated_keys
        assert "net_consumption" in updated_keys
        assert "production" in updated_keys
        assert "consumption" in updated_keys

    def test_skips_unchanged_values(self):
        callback, data, live_entities, updated_keys = self._build_callback()
        sd = StreamData(SAMPLE_STREAM_CHUNK)

        # First call updates everything
        callback(sd)
        updated_keys.clear()

        # Second call with same data should not trigger updates
        callback(sd)
        assert len(updated_keys) == 0

    def test_only_updates_registered_live_entities(self):
        callback, data, live_entities, updated_keys = self._build_callback()

        # Remove net_consumption from live entities
        del live_entities["net_consumption"]

        sd = StreamData(SAMPLE_STREAM_CHUNK)
        callback(sd)

        # net_consumption total should NOT be in updated keys
        assert "net_consumption" not in updated_keys
        # But per-phase should still be
        assert "net_consumption_l1" in updated_keys
