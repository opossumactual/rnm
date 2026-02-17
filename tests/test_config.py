"""Tests for config schema validation and loading."""

import textwrap
from pathlib import Path

import pytest
import yaml

from rnm.config.loader import ConfigError, load_config, validate_config
from rnm.config.schema import (
    DirewolfInterface,
    DirewolfPTT,
    FreeDVInterface,
    FreeDVMode,
    RNMConfig,
    SerialKISSInterface,
)


# --- Schema tests ---

class TestDirewolfInterface:
    def test_minimal(self):
        iface = DirewolfInterface(
            audio_device="plughw:1,0",
            callsign="W6EZE-10",
            ptt=DirewolfPTT(type="none"),
        )
        assert iface.modem == 1200
        assert iface.kiss_port == 8001
        assert iface.timing.txdelay == 40

    def test_serial_ptt_requires_device(self):
        with pytest.raises(ValueError, match="requires 'device'"):
            DirewolfPTT(type="serial")

    def test_gpio_ptt_requires_pin(self):
        with pytest.raises(ValueError, match="requires 'gpio_pin'"):
            DirewolfPTT(type="gpio")

    def test_serial_ptt_with_device(self):
        ptt = DirewolfPTT(type="serial", device="/dev/ttyUSB0")
        assert ptt.line == "RTS"

    def test_invalid_modem(self):
        with pytest.raises(Exception):
            DirewolfInterface(
                audio_device="plughw:1,0",
                callsign="TEST",
                modem=2400,
                ptt=DirewolfPTT(type="none"),
            )

    def test_kiss_port_range(self):
        with pytest.raises(Exception):
            DirewolfInterface(
                audio_device="plughw:1,0",
                callsign="TEST",
                kiss_port=80,
                ptt=DirewolfPTT(type="none"),
            )


class TestFreeDVInterface:
    def test_minimal(self):
        iface = FreeDVInterface(
            input_device="plughw:2,0",
            output_device="plughw:2,0",
        )
        assert iface.mode == FreeDVMode.DATAC1
        assert iface.kiss_port == 8002
        assert iface.ptt.type == "rigctld"

    def test_all_modes(self):
        for mode in ("DATAC1", "DATAC3", "DATAC4"):
            iface = FreeDVInterface(
                input_device="hw:0", output_device="hw:0", mode=mode,
            )
            assert iface.mode.value == mode

    def test_invalid_mode(self):
        with pytest.raises(Exception):
            FreeDVInterface(
                input_device="hw:0", output_device="hw:0", mode="DATAC99",
            )


class TestSerialKISSInterface:
    def test_minimal(self):
        iface = SerialKISSInterface(device="/dev/ttyACM0")
        assert iface.speed == 9600
        assert iface.preamble == 150
        assert iface.txtail == 10
        assert iface.persistence == 64
        assert iface.slottime == 20
        assert iface.flow_control is False
        assert iface.type == "serial_kiss"

    def test_speed_range(self):
        with pytest.raises(Exception):
            SerialKISSInterface(device="/dev/ttyACM0", speed=100)
        with pytest.raises(Exception):
            SerialKISSInterface(device="/dev/ttyACM0", speed=200000)

    def test_custom_speed(self):
        iface = SerialKISSInterface(device="/dev/ttyACM0", speed=38400)
        assert iface.speed == 38400

    def test_persistence_range(self):
        with pytest.raises(Exception):
            SerialKISSInterface(device="/dev/ttyACM0", persistence=256)


class TestRNMConfig:
    def test_empty_config(self):
        config = RNMConfig()
        assert config.node.callsign == "N0CALL"
        assert len(config.interfaces) == 0

    def test_discriminate_direwolf(self):
        data = {
            "interfaces": {
                "vhf": {
                    "type": "direwolf",
                    "audio_device": "plughw:1,0",
                    "callsign": "TEST-10",
                    "ptt": {"type": "none"},
                }
            }
        }
        config = RNMConfig(**data)
        assert isinstance(config.interfaces["vhf"], DirewolfInterface)

    def test_discriminate_freedvtnc2(self):
        data = {
            "interfaces": {
                "hf": {
                    "type": "freedvtnc2",
                    "input_device": "hw:0",
                    "output_device": "hw:0",
                }
            }
        }
        config = RNMConfig(**data)
        assert isinstance(config.interfaces["hf"], FreeDVInterface)

    def test_discriminate_serial_kiss(self):
        data = {
            "interfaces": {
                "ht": {
                    "type": "serial_kiss",
                    "device": "/dev/ttyACM0",
                }
            }
        }
        config = RNMConfig(**data)
        assert isinstance(config.interfaces["ht"], SerialKISSInterface)

    def test_unknown_type_raises(self):
        data = {
            "interfaces": {
                "bad": {"type": "unknown", "audio_device": "hw:0"}
            }
        }
        with pytest.raises(Exception, match="unknown type"):
            RNMConfig(**data)

    def test_full_config(self):
        data = {
            "node": {"name": "TestNode", "callsign": "W6EZE"},
            "interfaces": {
                "vhf": {
                    "type": "direwolf",
                    "audio_device": "plughw:1,0",
                    "callsign": "W6EZE-10",
                    "ptt": {"type": "serial", "device": "/dev/ttyUSB0"},
                },
                "hf": {
                    "type": "freedvtnc2",
                    "input_device": "plughw:2,0",
                    "output_device": "plughw:2,0",
                    "ptt": {
                        "type": "rigctld",
                        "rig_model": 1,
                        "rig_device": "/dev/ttyUSB1",
                    },
                },
            },
            "reticulum": {
                "enable_transport": True,
                "interface_config": {
                    "vhf": {"announce_rate_target": 3600},
                    "hf": {"announce_rate_target": 14400},
                },
            },
        }
        config = RNMConfig(**data)
        assert config.node.callsign == "W6EZE"
        assert len(config.interfaces) == 2

    def test_full_config_with_serial_kiss(self):
        data = {
            "node": {"name": "TestNode", "callsign": "W6EZE"},
            "interfaces": {
                "vhf": {
                    "type": "direwolf",
                    "audio_device": "plughw:1,0",
                    "callsign": "W6EZE-10",
                    "ptt": {"type": "none"},
                },
                "ht": {
                    "type": "serial_kiss",
                    "device": "/dev/ttyACM0",
                    "speed": 9600,
                },
            },
        }
        config = RNMConfig(**data)
        assert len(config.interfaces) == 2
        assert isinstance(config.interfaces["vhf"], DirewolfInterface)
        assert isinstance(config.interfaces["ht"], SerialKISSInterface)


# --- Loader tests ---

class TestLoadConfig:
    def test_load_example(self, tmp_path):
        example = Path(__file__).parent.parent / "config" / "example.yaml"
        if example.exists():
            config = load_config(example)
            assert config.node.callsign == "W6EZE"
            assert "vhf_uhf" in config.interfaces
            assert "hf" in config.interfaces

    def test_load_missing_file(self, tmp_path):
        with pytest.raises(ConfigError, match="not found"):
            load_config(tmp_path / "nope.yaml")

    def test_load_invalid_yaml(self, tmp_path):
        bad = tmp_path / "bad.yaml"
        bad.write_text(": : : not valid yaml [[[", encoding="utf-8")
        with pytest.raises(ConfigError, match="Invalid YAML"):
            load_config(bad)

    def test_load_empty_file(self, tmp_path):
        empty = tmp_path / "empty.yaml"
        empty.write_text("", encoding="utf-8")
        config = load_config(empty)
        assert config.node.callsign == "N0CALL"

    def test_load_minimal(self, tmp_path):
        minimal = tmp_path / "minimal.yaml"
        minimal.write_text(textwrap.dedent("""\
            node:
              name: TestNode
              callsign: W6EZE
            interfaces:
              vhf:
                type: direwolf
                audio_device: "plughw:1,0"
                callsign: "W6EZE-10"
                ptt:
                  type: none
        """), encoding="utf-8")
        config = load_config(minimal)
        assert config.node.name == "TestNode"
        assert isinstance(config.interfaces["vhf"], DirewolfInterface)


class TestValidateConfig:
    def test_validate_valid(self, tmp_path):
        cfg = tmp_path / "valid.yaml"
        cfg.write_text(textwrap.dedent("""\
            node:
              name: Test
              callsign: W6EZE
            interfaces:
              vhf:
                type: direwolf
                audio_device: "plughw:1,0"
                callsign: "W6EZE-10"
                ptt:
                  type: none
        """), encoding="utf-8")
        issues = validate_config(cfg)
        assert len(issues) == 0

    def test_validate_default_callsign(self, tmp_path):
        cfg = tmp_path / "default.yaml"
        cfg.write_text("node:\n  name: Test\n", encoding="utf-8")
        issues = validate_config(cfg)
        assert any("N0CALL" in i for i in issues)

    def test_validate_port_conflict(self, tmp_path):
        cfg = tmp_path / "conflict.yaml"
        cfg.write_text(textwrap.dedent("""\
            node:
              callsign: W6EZE
            interfaces:
              a:
                type: direwolf
                audio_device: "hw:0"
                callsign: "A"
                kiss_port: 8001
                ptt:
                  type: none
              b:
                type: direwolf
                audio_device: "hw:1"
                callsign: "B"
                kiss_port: 8001
                ptt:
                  type: none
        """), encoding="utf-8")
        issues = validate_config(cfg)
        assert any("conflict" in i.lower() for i in issues)

    def test_validate_serial_device_conflict(self, tmp_path):
        cfg = tmp_path / "conflict.yaml"
        cfg.write_text(textwrap.dedent("""\
            node:
              callsign: W6EZE
            interfaces:
              a:
                type: serial_kiss
                device: "/dev/ttyACM0"
              b:
                type: serial_kiss
                device: "/dev/ttyACM0"
        """), encoding="utf-8")
        issues = validate_config(cfg)
        assert any("conflict" in i.lower() for i in issues)

    def test_validate_serial_kiss_valid(self, tmp_path):
        cfg = tmp_path / "valid_serial.yaml"
        cfg.write_text(textwrap.dedent("""\
            node:
              callsign: W6EZE
            interfaces:
              ht:
                type: serial_kiss
                device: "/dev/ttyACM0"
        """), encoding="utf-8")
        issues = validate_config(cfg)
        assert len(issues) == 0

    def test_validate_missing_file(self, tmp_path):
        issues = validate_config(tmp_path / "nope.yaml")
        assert any("not found" in i for i in issues)
