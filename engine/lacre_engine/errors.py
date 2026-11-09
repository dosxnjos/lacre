"""Engine errors carrying a PROTOCOL error code, and the mapping from pymobiledevice3 exceptions."""
from __future__ import annotations

import asyncio

from pymobiledevice3 import exceptions as pe


class EngineError(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code
        self.detail = detail


# Connection-loss types: the device was unplugged or the link dropped mid-operation.
CONNECTION_LOST = (
    ConnectionResetError,
    ConnectionAbortedError,
    BrokenPipeError,
    pe.ConnectionTerminatedError,  # includes StreamClosedError
    pe.NotConnectedError,
    pe.BadDevError,
)


def short(e: BaseException, limit: int = 300) -> str:
    text = str(e).strip()
    line = text.splitlines()[-1] if text else type(e).__name__
    return f"{type(e).__name__}: {line}"[:limit]


def map_exception(e: BaseException) -> EngineError:
    """Translate any exception raised while talking to the device into a PROTOCOL error code."""
    if isinstance(e, EngineError):
        return e
    if isinstance(e, asyncio.CancelledError):
        return EngineError("cancelled")
    if isinstance(e, (pe.PasswordRequiredError, pe.PasscodeRequiredError)):
        return EngineError("passcode_required", short(e))
    if isinstance(e, (pe.NotTrustedError, pe.UserDeniedPairingError, pe.PairingDialogResponsePendingError,
                      pe.NotPairedError, pe.InvalidHostIDError, pe.PairingError, pe.FatalPairingError)):
        return EngineError("not_trusted", short(e))
    if isinstance(e, (pe.NoDeviceConnectedError, pe.DeviceNotFoundError)):
        return EngineError("no_device", short(e))
    if isinstance(e, pe.ConnectionFailedToUsbmuxdError):
        return EngineError("usbmux_unavailable", short(e))
    if isinstance(e, CONNECTION_LOST):
        return EngineError("device_gone", short(e))
    if isinstance(e, pe.ConnectionFailedError):
        # usbmux could not reach the device port: unplugged or locked down
        return EngineError("device_gone", short(e))
    if isinstance(e, pe.MuxException):
        return EngineError("usbmux_unavailable", short(e))
    if isinstance(e, (TimeoutError, asyncio.TimeoutError, pe.SysdiagnoseTimeoutError)):
        return EngineError("timeout", short(e))
    if isinstance(e, ConnectionRefusedError):
        return EngineError("usbmux_unavailable", short(e))
    return EngineError("internal", short(e))
