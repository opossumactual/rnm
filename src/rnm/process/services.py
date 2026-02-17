"""Service definitions — how to launch and health-check each managed process."""

from __future__ import annotations

import functools
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Dict, Optional

from rnm.config.schema import (
    DirewolfInterface,
    FreeDVInterface,
    RNMConfig,
    SerialKISSInterface,
)
from rnm.generators.direwolf import generate_direwolf_conf
from rnm.generators.freedvtnc2 import build_freedvtnc2_args, build_rigctld_args
from rnm.utils.network import check_kiss_tcp, check_rigctld


@dataclass
class ServiceDefinition:
    """Defines how to launch and health-check a service."""

    name: str
    command: list[str]
    health_check: Optional[Callable[[], Awaitable[bool]]] = None
    depends_on: list[str] = field(default_factory=list)
    working_dir: Optional[str] = None
    env: Dict[str, str] = field(default_factory=dict)
    config_files: list[str] = field(default_factory=list)


def build_services(config: RNMConfig, generated_dir: str) -> list[ServiceDefinition]:
    """Build service definitions from the RNM config.

    Services are returned in dependency order:
      1. rigctld (if HF with rigctld PTT)
      2. freedvtnc2 (depends on rigctld)
      3. direwolf (independent)
      4. rnsd (depends on all TNCs)
    """
    services: list[ServiceDefinition] = []
    tnc_names: list[str] = []
    needs_rigctld = False

    for iface_name, iface in config.interfaces.items():
        if not iface.enabled:
            continue

        if isinstance(iface, FreeDVInterface):
            if iface.ptt.type == "rigctld":
                needs_rigctld = True

    # 1. rigctld (if needed for HF PTT)
    if needs_rigctld:
        for iface_name, iface in config.interfaces.items():
            if not iface.enabled or not isinstance(iface, FreeDVInterface):
                continue
            if iface.ptt.type != "rigctld":
                continue

            rigctld_args = build_rigctld_args(iface.ptt)
            services.append(ServiceDefinition(
                name="rigctld",
                command=rigctld_args,
                health_check=functools.partial(
                    check_rigctld,
                    iface.ptt.rigctld_host,
                    iface.ptt.rigctld_port,
                ),
            ))
            break  # Only one rigctld instance

    # 2-3. TNCs
    for iface_name, iface in config.interfaces.items():
        if not iface.enabled:
            continue

        if isinstance(iface, DirewolfInterface):
            conf_content = generate_direwolf_conf(iface_name, iface)
            conf_path = f"{generated_dir}/direwolf_{iface_name}.conf"
            services.append(ServiceDefinition(
                name=f"direwolf_{iface_name}",
                command=["direwolf", "-c", conf_path, "-t", "0"],
                health_check=functools.partial(
                    check_kiss_tcp, "127.0.0.1", iface.kiss_port,
                ),
                config_files=[conf_path],
            ))
            tnc_names.append(f"direwolf_{iface_name}")

        elif isinstance(iface, FreeDVInterface):
            args = build_freedvtnc2_args(iface)
            deps = ["rigctld"] if iface.ptt.type == "rigctld" and needs_rigctld else []
            services.append(ServiceDefinition(
                name=f"freedvtnc2_{iface_name}",
                command=args,
                health_check=functools.partial(
                    check_kiss_tcp, "127.0.0.1", iface.kiss_port,
                ),
                depends_on=deps,
            ))
            tnc_names.append(f"freedvtnc2_{iface_name}")

        elif isinstance(iface, SerialKISSInterface):
            # Serial KISS — no external process needed, Reticulum handles it directly
            pass

    # 4. rnsd (depends on all TNCs being up)
    reticulum_config_dir = f"{generated_dir}/reticulum"
    services.append(ServiceDefinition(
        name="rnsd",
        command=["rnsd", "--config", reticulum_config_dir],
        depends_on=tnc_names,
    ))

    return services
