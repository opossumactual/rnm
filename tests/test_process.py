"""Tests for process service building and dependency resolution."""

import pytest

from rnm.config.schema import RNMConfig
from rnm.process.services import build_services


class TestBuildServices:
    def _make_config(self, **overrides) -> RNMConfig:
        data = {
            "node": {"name": "TestNode", "callsign": "W6EZE"},
        }
        data.update(overrides)
        return RNMConfig(**data)

    def test_direwolf_only(self):
        config = self._make_config(
            interfaces={
                "vhf": {
                    "type": "direwolf",
                    "audio_device": "plughw:1,0",
                    "callsign": "W6EZE-10",
                    "ptt": {"type": "none"},
                }
            }
        )
        services = build_services(config, "/tmp/rnm-test")
        names = [s.name for s in services]
        assert "direwolf_vhf" in names
        assert "rnsd" in names
        assert "rigctld" not in names

    def test_freedvtnc2_with_rigctld(self):
        config = self._make_config(
            interfaces={
                "hf": {
                    "type": "freedvtnc2",
                    "input_device": "hw:0",
                    "output_device": "hw:0",
                    "ptt": {"type": "rigctld", "rig_model": 1},
                }
            }
        )
        services = build_services(config, "/tmp/rnm-test")
        names = [s.name for s in services]
        assert "rigctld" in names
        assert "freedvtnc2_hf" in names
        assert "rnsd" in names

    def test_freedvtnc2_depends_on_rigctld(self):
        config = self._make_config(
            interfaces={
                "hf": {
                    "type": "freedvtnc2",
                    "input_device": "hw:0",
                    "output_device": "hw:0",
                    "ptt": {"type": "rigctld", "rig_model": 1},
                }
            }
        )
        services = build_services(config, "/tmp/rnm-test")
        fdv = next(s for s in services if s.name == "freedvtnc2_hf")
        assert "rigctld" in fdv.depends_on

    def test_rnsd_depends_on_all_tncs(self):
        config = self._make_config(
            interfaces={
                "vhf": {
                    "type": "direwolf",
                    "audio_device": "hw:0",
                    "callsign": "TEST",
                    "ptt": {"type": "none"},
                },
                "hf": {
                    "type": "freedvtnc2",
                    "input_device": "hw:1",
                    "output_device": "hw:1",
                    "ptt": {"type": "rigctld", "rig_model": 1},
                },
            }
        )
        services = build_services(config, "/tmp/rnm-test")
        rnsd = next(s for s in services if s.name == "rnsd")
        assert "direwolf_vhf" in rnsd.depends_on
        assert "freedvtnc2_hf" in rnsd.depends_on

    def test_disabled_interface_excluded(self):
        config = self._make_config(
            interfaces={
                "vhf": {
                    "type": "direwolf",
                    "audio_device": "hw:0",
                    "callsign": "TEST",
                    "enabled": False,
                    "ptt": {"type": "none"},
                }
            }
        )
        services = build_services(config, "/tmp/rnm-test")
        names = [s.name for s in services]
        assert "direwolf_vhf" not in names

    def test_vox_ptt_no_rigctld(self):
        config = self._make_config(
            interfaces={
                "hf": {
                    "type": "freedvtnc2",
                    "input_device": "hw:0",
                    "output_device": "hw:0",
                    "ptt": {"type": "vox"},
                }
            }
        )
        services = build_services(config, "/tmp/rnm-test")
        names = [s.name for s in services]
        assert "rigctld" not in names

    def test_direwolf_command_includes_config_path(self):
        config = self._make_config(
            interfaces={
                "vhf": {
                    "type": "direwolf",
                    "audio_device": "hw:0",
                    "callsign": "TEST",
                    "ptt": {"type": "none"},
                }
            }
        )
        services = build_services(config, "/tmp/rnm-test")
        dw = next(s for s in services if s.name == "direwolf_vhf")
        assert "-c" in dw.command
        assert "/tmp/rnm-test/direwolf_vhf.conf" in dw.command

    def test_rnsd_command_includes_config_dir(self):
        config = self._make_config(
            interfaces={
                "vhf": {
                    "type": "direwolf",
                    "audio_device": "hw:0",
                    "callsign": "TEST",
                    "ptt": {"type": "none"},
                }
            }
        )
        services = build_services(config, "/tmp/rnm-test")
        rnsd = next(s for s in services if s.name == "rnsd")
        assert "--config" in rnsd.command
        assert "/tmp/rnm-test/reticulum" in rnsd.command

    def test_serial_kiss_no_service(self):
        config = self._make_config(
            interfaces={
                "ht": {
                    "type": "serial_kiss",
                    "device": "/dev/ttyACM0",
                }
            }
        )
        services = build_services(config, "/tmp/rnm-test")
        names = [s.name for s in services]
        # No TNC service for serial_kiss — only rnsd
        assert names == ["rnsd"]

    def test_serial_kiss_only_rnsd(self):
        config = self._make_config(
            interfaces={
                "ht": {
                    "type": "serial_kiss",
                    "device": "/dev/ttyACM0",
                }
            }
        )
        services = build_services(config, "/tmp/rnm-test")
        rnsd = next(s for s in services if s.name == "rnsd")
        # rnsd should have no TNC dependencies
        assert rnsd.depends_on == []

    def test_serial_kiss_with_direwolf(self):
        config = self._make_config(
            interfaces={
                "vhf": {
                    "type": "direwolf",
                    "audio_device": "hw:0",
                    "callsign": "TEST",
                    "ptt": {"type": "none"},
                },
                "ht": {
                    "type": "serial_kiss",
                    "device": "/dev/ttyACM0",
                },
            }
        )
        services = build_services(config, "/tmp/rnm-test")
        names = [s.name for s in services]
        # Direwolf creates a service, serial_kiss does not
        assert "direwolf_vhf" in names
        assert "rnsd" in names
        assert len(names) == 2
        # rnsd depends on direwolf but NOT on serial_kiss
        rnsd = next(s for s in services if s.name == "rnsd")
        assert "direwolf_vhf" in rnsd.depends_on
