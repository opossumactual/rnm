"""Check for installed external dependencies."""

from __future__ import annotations

import shutil
from dataclasses import dataclass


@dataclass
class Dependency:
    command: str
    description: str
    required: bool = True
    found: bool = False
    path: str | None = None


# All external tools that RNM can manage
ALL_DEPENDENCIES = [
    Dependency("direwolf", "Direwolf (VHF/UHF software TNC)"),
    Dependency("freedvtnc2", "FreeDV TNC2 (HF data modem)"),
    Dependency("rigctld", "Hamlib rigctld (PTT/CAT control)"),
    Dependency("rnsd", "Reticulum network daemon"),
]

OPTIONAL_DEPENDENCIES = [
    Dependency("nomadnet", "NomadNet (mesh messaging)", required=False),
    Dependency("lxmrd", "LXMF propagation daemon", required=False),
]


def check_dependencies(include_optional: bool = False) -> list[Dependency]:
    """Check which dependencies are installed and return their status."""
    deps = list(ALL_DEPENDENCIES)
    if include_optional:
        deps.extend(OPTIONAL_DEPENDENCIES)

    for dep in deps:
        path = shutil.which(dep.command)
        dep.found = path is not None
        dep.path = path

    return deps


def get_missing_required() -> list[Dependency]:
    """Return list of required dependencies that are not installed."""
    return [d for d in check_dependencies() if d.required and not d.found]
