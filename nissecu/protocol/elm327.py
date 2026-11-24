"""Read-only generic OBD-II over an ELM327-compatible serial adapter.

The 2005 Xterra service manual specifies ISO 9141 for generic diagnostics.
This is not an implementation of Nissan CONSULT or ECU programming.
"""
import re
import time

import serial

from nissecu.protocol.iso9141 import LiveDataFrame, OBDConnectionError, PIDS


def parse_mode01(response: str, pid: int, length: int) -> bytes:
    """Extract a complete headerless 41 PID response, rejecting malformed data."""
    for line in response.replace('\n', '\r').split('\r'):
        compact = re.sub(r'\s+', '', line).upper()
        if not re.fullmatch(r'[0-9A-F]+', compact) or len(compact) % 2:
            continue
        raw = bytes.fromhex(compact)
        if raw[:2] == bytes((0x41, pid)) and len(raw) == length + 2:
            return raw[2:]
    raise OBDConnectionError(f"No valid response for PID {pid:02X}: {response.strip()}")


class ELM327:
    def __init__(self, port, baudrate=38400, serial_factory=serial.Serial):
        self.port = port
        self.baudrate = baudrate
        self._serial_factory = serial_factory
        self._serial = None
        self._supported = []
        self._next = 0

    def open(self):
        try:
            self._serial = self._serial_factory(self.port, self.baudrate, timeout=0.2, write_timeout=2)
            self._serial.reset_input_buffer()
            # TP selects protocol for this session without persisting adapter settings.
            for command in ("AT E0", "AT L0", "AT S1", "AT H0", "AT TP 3"):
                result = self._command(command, 3)
                if "OK" not in result.upper().split():
                    raise OBDConnectionError(f"Adapter rejected {command}: {result.strip()}")
            mask = int.from_bytes(parse_mode01(self._command("0100", 12), 0, 4), 'big')
            self._supported = [name for name, (pid, _, _) in PIDS.items()
                               if mask & (1 << (32 - pid))]
            if not self._supported:
                raise OBDConnectionError("ECU responded but none of the implemented PIDs are supported")
        except Exception:
            self.close()
            raise

    def _command(self, command, timeout):
        self._serial.write((command + '\r').encode('ascii'))
        deadline = time.monotonic() + timeout
        data = bytearray()
        while time.monotonic() < deadline:
            ch = self._serial.read(1)
            if ch == b'>':
                return data.decode('ascii', errors='replace')
            data.extend(ch)
            if len(data) > 4096:
                raise OBDConnectionError("Adapter response too long")
        raise OBDConnectionError(f"Timed out waiting for adapter response to {command}")

    def read_live_data(self, param_names=None):
        names = [n for n in self._supported if param_names is None or n in param_names]
        if not names:
            return None
        name = names[self._next % len(names)]
        self._next += 1
        pid, length, decode = PIDS[name]
        raw = parse_mode01(self._command(f"01{pid:02X}", 3), pid, length)
        return LiveDataFrame(time.monotonic(), {name: decode(raw)})

    def close(self):
        if self._serial is not None:
            self._serial.close()
            self._serial = None
