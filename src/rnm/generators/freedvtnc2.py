"""Build command-line arguments for FreeDV TNC2 and rigctld."""

from __future__ import annotations

from rnm.config.schema import FreeDVInterface, FreeDVPTT


def build_freedvtnc2_args(iface: FreeDVInterface) -> list[str]:
    """Build freedvtnc2 command-line arguments.

    Reference: https://github.com/xssfox/freedvtnc2
    Key flags:
      --input-device / --output-device  - PortAudio audio devices
      --mode          - FreeDV data modem (DATAC1/DATAC3/DATAC4)
      --kiss-tcp-port / --kiss-tcp-address - KISS TCP server
      --rigctld-host / --rigctld-port     - PTT via rigctld
      --ptt-on-delay-ms / --ptt-off-delay-ms - TX keying delays
      --output-volume - dB gain adjustment
      --follow        - auto-switch TX mode to match RX
      --max-packets-combined - KISS frames per TX burst
      --no-cli        - disable interactive prompt (critical for process mgmt)
    """
    args = ["freedvtnc2"]

    args.extend(["--input-device", iface.input_device])
    args.extend(["--output-device", iface.output_device])
    args.extend(["--mode", iface.mode.value])
    args.extend(["--kiss-tcp-port", str(iface.kiss_port)])
    args.extend(["--kiss-tcp-address", "127.0.0.1"])

    if iface.ptt.type == "rigctld":
        args.extend(["--rigctld-host", iface.ptt.rigctld_host])
        args.extend(["--rigctld-port", str(iface.ptt.rigctld_port)])

    if iface.ptt_on_delay_ms != 200:
        args.extend(["--ptt-on-delay-ms", str(iface.ptt_on_delay_ms)])
    if iface.ptt_off_delay_ms != 100:
        args.extend(["--ptt-off-delay-ms", str(iface.ptt_off_delay_ms)])
    if iface.output_volume != 0:
        args.extend(["--output-volume", str(iface.output_volume)])
    if iface.follow_mode:
        args.append("--follow")
    if iface.max_packets_combined != 1:
        args.extend(["--max-packets-combined", str(iface.max_packets_combined)])

    # Disable interactive CLI for process management
    args.append("--no-cli")

    return args


def build_rigctld_args(ptt: FreeDVPTT) -> list[str]:
    """Build rigctld command-line arguments.

    Reference: man rigctld (part of Hamlib)
    Key flags:
      -m  rig model number (use `rigctl -l` to list)
      -t  TCP listen port
      -r  serial device for CAT
      -s  serial baud rate
    """
    args = ["rigctld"]
    args.extend(["-m", str(ptt.rig_model)])
    args.extend(["-t", str(ptt.rigctld_port)])

    if ptt.rig_device:
        args.extend(["-r", ptt.rig_device])
    if ptt.rig_speed:
        args.extend(["-s", str(ptt.rig_speed)])

    return args
