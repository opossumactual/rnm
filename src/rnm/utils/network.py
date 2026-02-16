"""Network utilities for health checking KISS TCP and rigctld."""

from __future__ import annotations

import asyncio


async def check_kiss_tcp(host: str, port: int, timeout: float = 5.0) -> bool:
    """Check if a KISS TCP port is accepting connections."""
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=timeout,
        )
        writer.close()
        await writer.wait_closed()
        return True
    except (ConnectionRefusedError, asyncio.TimeoutError, OSError):
        return False


async def check_rigctld(host: str, port: int, timeout: float = 5.0) -> bool:
    """Check if rigctld is responding to commands."""
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=timeout,
        )
        writer.write(b"\\get_info\n")
        await writer.drain()
        data = await asyncio.wait_for(reader.readline(), timeout=timeout)
        writer.close()
        await writer.wait_closed()
        return len(data) > 0
    except (ConnectionRefusedError, asyncio.TimeoutError, OSError):
        return False
