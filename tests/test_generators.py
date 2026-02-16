"""Tests for config generators (direwolf, freedvtnc2, rigctld, reticulum)."""

import pytest

from rnm.config.schema import (
    DirewolfInterface,
    DirewolfPTT,
    DirewolfTiming,
    FreeDVInterface,
    FreeDVMode,
    FreeDVPTT,
    NodeConfig,
    RNMConfig,
    ReticulumConfig,
    ReticulumInterfaceConfig,
)
from rnm.generators.direwolf import generate_direwolf_conf
from rnm.generators.freedvtnc2 import build_freedvtnc2_args, build_rigctld_args
from rnm.generators.reticulum import generate_reticulum_config


# --- Direwolf ---

class TestDirewolfGenerator:
    def _make_iface(self, **overrides) -> DirewolfInterface:
        defaults = dict(
            audio_device="plughw:1,0",
            callsign="W6EZE-10",
            ptt=DirewolfPTT(type="none"),
        )
        defaults.update(overrides)
        return DirewolfInterface(**defaults)

    def test_basic_output(self):
        iface = self._make_iface()
        conf = generate_direwolf_conf("vhf", iface)
        assert "ADEVICE plughw:1,0" in conf
        assert "MYCALL W6EZE-10" in conf
        assert "MODEM 1200" in conf
        assert "KISSPORT 8001" in conf
        assert "AGWPORT 0" in conf
        assert "CHANNEL 0" in conf

    def test_serial_ptt(self):
        iface = self._make_iface(
            ptt=DirewolfPTT(type="serial", device="/dev/ttyUSB0", line="RTS"),
        )
        conf = generate_direwolf_conf("vhf", iface)
        assert "PTT /dev/ttyUSB0 RTS" in conf

    def test_gpio_ptt(self):
        iface = self._make_iface(
            ptt=DirewolfPTT(type="gpio", gpio_pin=17),
        )
        conf = generate_direwolf_conf("vhf", iface)
        assert "PTT GPIO 17" in conf

    def test_cm108_ptt(self):
        iface = self._make_iface(
            ptt=DirewolfPTT(type="cm108"),
        )
        conf = generate_direwolf_conf("vhf", iface)
        assert "PTT CM108" in conf

    def test_no_ptt(self):
        iface = self._make_iface()
        conf = generate_direwolf_conf("vhf", iface)
        assert "PTT" not in conf or "PTT CM108" not in conf
        # Should not have a PTT line when type is none
        lines = conf.splitlines()
        ptt_lines = [l for l in lines if l.startswith("PTT")]
        assert len(ptt_lines) == 0

    def test_9600_baud(self):
        iface = self._make_iface(modem=9600)
        conf = generate_direwolf_conf("vhf", iface)
        assert "MODEM 9600" in conf

    def test_timing_params(self):
        iface = self._make_iface(
            timing=DirewolfTiming(txdelay=50, txtail=20, slottime=20, persist=127),
        )
        conf = generate_direwolf_conf("vhf", iface)
        assert "TXDELAY 50" in conf
        assert "TXTAIL 20" in conf
        assert "SLOTTIME 20" in conf
        assert "PERSIST 127" in conf

    def test_extra_config(self):
        iface = self._make_iface(extra_config="FIX_BITS 1 NONE")
        conf = generate_direwolf_conf("vhf", iface)
        assert "FIX_BITS 1 NONE" in conf

    def test_custom_kiss_port(self):
        iface = self._make_iface(kiss_port=9001)
        conf = generate_direwolf_conf("vhf", iface)
        assert "KISSPORT 9001" in conf


# --- FreeDV TNC2 ---

class TestFreeDVTNC2Generator:
    def _make_iface(self, **overrides) -> FreeDVInterface:
        defaults = dict(
            input_device="plughw:2,0",
            output_device="plughw:2,0",
        )
        defaults.update(overrides)
        return FreeDVInterface(**defaults)

    def test_basic_args(self):
        iface = self._make_iface()
        args = build_freedvtnc2_args(iface)
        assert args[0] == "freedvtnc2"
        assert "--input-device" in args
        assert "plughw:2,0" in args
        assert "--mode" in args
        assert "DATAC1" in args
        assert "--kiss-tcp-port" in args
        assert "8002" in args
        assert "--no-cli" in args

    def test_rigctld_ptt(self):
        iface = self._make_iface()
        args = build_freedvtnc2_args(iface)
        assert "--rigctld-host" in args
        assert "127.0.0.1" in args
        assert "--rigctld-port" in args
        assert "4532" in args

    def test_vox_ptt(self):
        iface = self._make_iface(ptt=FreeDVPTT(type="vox"))
        args = build_freedvtnc2_args(iface)
        assert "--rigctld-host" not in args

    def test_custom_delays(self):
        iface = self._make_iface(ptt_on_delay_ms=500, ptt_off_delay_ms=300)
        args = build_freedvtnc2_args(iface)
        assert "--ptt-on-delay-ms" in args
        assert "500" in args
        assert "--ptt-off-delay-ms" in args
        assert "300" in args

    def test_default_delays_omitted(self):
        iface = self._make_iface()
        args = build_freedvtnc2_args(iface)
        assert "--ptt-on-delay-ms" not in args
        assert "--ptt-off-delay-ms" not in args

    def test_output_volume(self):
        iface = self._make_iface(output_volume=-3)
        args = build_freedvtnc2_args(iface)
        assert "--output-volume" in args
        assert "-3" in args

    def test_follow_mode(self):
        iface = self._make_iface(follow_mode=True)
        args = build_freedvtnc2_args(iface)
        assert "--follow" in args

    def test_max_packets_combined(self):
        iface = self._make_iface(max_packets_combined=3)
        args = build_freedvtnc2_args(iface)
        assert "--max-packets-combined" in args
        assert "3" in args

    def test_datac3_mode(self):
        iface = self._make_iface(mode=FreeDVMode.DATAC3)
        args = build_freedvtnc2_args(iface)
        assert "DATAC3" in args


# --- rigctld ---

class TestRigctldGenerator:
    def test_basic_args(self):
        ptt = FreeDVPTT(rig_model=3085, rig_device="/dev/ttyUSB1", rig_speed=9600)
        args = build_rigctld_args(ptt)
        assert args[0] == "rigctld"
        assert "-m" in args
        assert "3085" in args
        assert "-r" in args
        assert "/dev/ttyUSB1" in args
        assert "-s" in args
        assert "9600" in args

    def test_dummy_rig(self):
        ptt = FreeDVPTT(rig_model=1)
        args = build_rigctld_args(ptt)
        assert "-m" in args
        assert "1" in args
        assert "-r" not in args  # No device for dummy rig

    def test_port(self):
        ptt = FreeDVPTT(rigctld_port=5000)
        args = build_rigctld_args(ptt)
        assert "-t" in args
        assert "5000" in args


# --- Reticulum ---

class TestReticulumGenerator:
    def _make_config(self, **overrides) -> RNMConfig:
        data = {
            "node": {"name": "TestNode", "callsign": "W6EZE"},
            "interfaces": {
                "vhf": {
                    "type": "direwolf",
                    "audio_device": "plughw:1,0",
                    "callsign": "W6EZE-10",
                    "kiss_port": 8001,
                    "ptt": {"type": "none"},
                },
            },
        }
        data.update(overrides)
        return RNMConfig(**data)

    def test_basic_output(self):
        config = self._make_config()
        out = generate_reticulum_config(config)
        assert "[reticulum]" in out
        assert "enable_transport = True" in out
        assert "[logging]" in out
        assert "[interfaces]" in out

    def test_kiss_interface(self):
        config = self._make_config()
        out = generate_reticulum_config(config)
        assert "[[TestNode vhf]]" in out
        assert "type = TCPClientInterface" in out
        assert "kiss_framing = True" in out
        assert "target_port = 8001" in out

    def test_disabled_interface_excluded(self):
        config = self._make_config(
            interfaces={
                "vhf": {
                    "type": "direwolf",
                    "audio_device": "plughw:1,0",
                    "callsign": "TEST",
                    "enabled": False,
                    "ptt": {"type": "none"},
                },
            }
        )
        out = generate_reticulum_config(config)
        assert "[[TestNode vhf]]" not in out

    def test_announce_rate_config(self):
        config = self._make_config(
            reticulum={
                "interface_config": {
                    "vhf": {
                        "announce_rate_target": 3600,
                        "announce_rate_grace": 7200,
                    }
                }
            }
        )
        out = generate_reticulum_config(config)
        assert "announce_rate_target = 3600" in out
        assert "announce_rate_grace = 7200" in out

    def test_additional_interfaces(self):
        config = self._make_config(
            reticulum={
                "additional_interfaces": {
                    "tcp_server": {
                        "type": "TCPServerInterface",
                        "enabled": "true",
                        "listen_ip": "0.0.0.0",
                        "listen_port": 4242,
                    }
                }
            }
        )
        out = generate_reticulum_config(config)
        assert "[[tcp_server]]" in out
        assert "type = TCPServerInterface" in out
        assert "listen_port = 4242" in out

    def test_multiple_interfaces(self):
        config = self._make_config(
            interfaces={
                "vhf": {
                    "type": "direwolf",
                    "audio_device": "plughw:1,0",
                    "callsign": "W6EZE-10",
                    "kiss_port": 8001,
                    "ptt": {"type": "none"},
                },
                "hf": {
                    "type": "freedvtnc2",
                    "input_device": "plughw:2,0",
                    "output_device": "plughw:2,0",
                    "kiss_port": 8002,
                },
            }
        )
        out = generate_reticulum_config(config)
        assert "target_port = 8001" in out
        assert "target_port = 8002" in out

    def test_share_instance_config(self):
        config = self._make_config(
            reticulum={
                "share_instance": True,
                "shared_instance_port": 37428,
                "instance_control_port": 37429,
            }
        )
        out = generate_reticulum_config(config)
        assert "share_instance = True" in out
        assert "shared_instance_port = 37428" in out
