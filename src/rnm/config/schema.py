"""Pydantic models for the RNM unified YAML configuration."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, Literal, Optional, Union

from pydantic import BaseModel, Field, model_validator


# --- Enums ---

class PTTType(str, Enum):
    SERIAL = "serial"
    GPIO = "gpio"
    CM108 = "cm108"
    NONE = "none"
    RIGCTLD = "rigctld"
    VOX = "vox"


class FreeDVMode(str, Enum):
    DATAC1 = "DATAC1"
    DATAC3 = "DATAC3"
    DATAC4 = "DATAC4"


# --- Direwolf models ---

class DirewolfPTT(BaseModel):
    type: Literal["serial", "gpio", "cm108", "none"] = "serial"
    device: Optional[str] = None
    line: Literal["RTS", "DTR"] = "RTS"
    gpio_pin: Optional[int] = None

    @model_validator(mode="after")
    def validate_ptt(self) -> "DirewolfPTT":
        if self.type == "serial" and not self.device:
            raise ValueError("PTT type 'serial' requires 'device' to be set")
        if self.type == "gpio" and self.gpio_pin is None:
            raise ValueError("PTT type 'gpio' requires 'gpio_pin' to be set")
        return self


class DirewolfTiming(BaseModel):
    txdelay: int = Field(default=40, ge=0, le=255)
    txtail: int = Field(default=10, ge=0, le=255)
    slottime: int = Field(default=10, ge=0, le=255)
    persist: int = Field(default=63, ge=0, le=255)


class DirewolfInterface(BaseModel):
    enabled: bool = True
    type: Literal["direwolf"] = "direwolf"
    audio_device: str
    callsign: str
    modem: Literal[1200, 9600] = 1200
    ptt: DirewolfPTT = DirewolfPTT(type="none")
    kiss_port: int = Field(default=8001, ge=1024, le=65535)
    timing: DirewolfTiming = DirewolfTiming()
    channel: int = Field(default=0, ge=0, le=7)
    extra_config: Optional[str] = None


# --- FreeDV TNC2 models ---

class FreeDVPTT(BaseModel):
    type: Literal["rigctld", "vox"] = "rigctld"
    rigctld_host: str = "127.0.0.1"
    rigctld_port: int = Field(default=4532, ge=1, le=65535)
    rig_model: int = 1
    rig_device: Optional[str] = None
    rig_speed: int = 9600


class FreeDVInterface(BaseModel):
    enabled: bool = True
    type: Literal["freedvtnc2"] = "freedvtnc2"
    input_device: str
    output_device: str
    mode: FreeDVMode = FreeDVMode.DATAC1
    ptt: FreeDVPTT = FreeDVPTT()
    kiss_port: int = Field(default=8002, ge=1024, le=65535)
    ptt_on_delay_ms: int = Field(default=200, ge=0)
    ptt_off_delay_ms: int = Field(default=100, ge=0)
    output_volume: int = 0
    follow_mode: bool = False
    max_packets_combined: int = Field(default=1, ge=1)


# --- Reticulum models ---

class ReticulumInterfaceConfig(BaseModel):
    announce_rate_target: Optional[int] = None
    announce_rate_grace: Optional[int] = None
    bandwidth: Optional[int] = None


class ReticulumConfig(BaseModel):
    enable_transport: bool = True
    share_instance: bool = True
    shared_instance_port: int = Field(default=37428, ge=1, le=65535)
    instance_control_port: int = Field(default=37429, ge=1, le=65535)
    loglevel: int = Field(default=4, ge=0, le=7)
    interface_config: Dict[str, ReticulumInterfaceConfig] = {}
    additional_interfaces: Dict[str, Dict[str, Any]] = {}


# --- Process / Logging / TUI ---

class ProcessConfig(BaseModel):
    restart_policy: Literal["always", "on-failure", "never"] = "always"
    restart_delay: int = Field(default=3, ge=0)
    max_restarts: int = Field(default=10, ge=0)
    restart_window: int = Field(default=300, ge=0)
    health_check_interval: int = Field(default=15, ge=1)
    startup_grace_period: int = Field(default=10, ge=0)


class LoggingConfig(BaseModel):
    level: Literal["debug", "info", "warning", "error"] = "info"
    file: Optional[str] = None
    max_size_mb: int = Field(default=10, ge=1)
    backup_count: int = Field(default=3, ge=0)


class TUIConfig(BaseModel):
    enabled: bool = True
    refresh_rate: float = Field(default=1.0, gt=0)
    show_log_panel: bool = True
    log_lines: int = Field(default=50, ge=1)


class NodeConfig(BaseModel):
    name: str = "Reticulum Node"
    callsign: str = "N0CALL"


# --- Root config ---

InterfaceType = Union[DirewolfInterface, FreeDVInterface]


class RNMConfig(BaseModel):
    """Root configuration model for Reticulum Node Manager."""

    node: NodeConfig = NodeConfig()
    interfaces: Dict[str, InterfaceType] = {}
    reticulum: ReticulumConfig = ReticulumConfig()
    process: ProcessConfig = ProcessConfig()
    logging: LoggingConfig = LoggingConfig()
    tui: TUIConfig = TUIConfig()

    @model_validator(mode="before")
    @classmethod
    def discriminate_interfaces(cls, data: Any) -> Any:
        """Route each interface dict to the correct model based on 'type'."""
        if isinstance(data, dict) and "interfaces" in data:
            parsed: Dict[str, Any] = {}
            for name, iface in data["interfaces"].items():
                if not isinstance(iface, dict):
                    parsed[name] = iface
                    continue
                itype = iface.get("type", "")
                if itype == "direwolf":
                    parsed[name] = DirewolfInterface(**iface)
                elif itype == "freedvtnc2":
                    parsed[name] = FreeDVInterface(**iface)
                else:
                    raise ValueError(
                        f"Interface '{name}' has unknown type '{itype}'. "
                        "Must be 'direwolf' or 'freedvtnc2'."
                    )
            data["interfaces"] = parsed
        return data
