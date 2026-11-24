"""Experimental ISO 9141-2 generic diagnostics for an echoing KKL cable.

The UART break signal is used to generate the 5-baud wakeup. USB driver and
cable timing vary; this implementation has not yet been tested on a vehicle.
"""
from dataclasses import dataclass
import time
import serial


class OBDConnectionError(Exception):
    """The cable or ECU did not provide a usable response."""


@dataclass
class LiveDataFrame:
    timestamp: float
    values: dict


# Mode 01 PID, number of data bytes, conversion to the displayed units.
PIDS = {
    "coolant_temp": (0x05, 1, lambda b: b[0] - 40),
    "fuel_trim_st": (0x06, 1, lambda b: (b[0] - 128) * 100 / 128),
    "fuel_trim_lt": (0x07, 1, lambda b: (b[0] - 128) * 100 / 128),
    "rpm": (0x0C, 2, lambda b: (256 * b[0] + b[1]) / 4),
    "vspeed": (0x0D, 1, lambda b: b[0]),
    "ign_timing": (0x0E, 1, lambda b: b[0] / 2 - 64),
    "maf": (0x10, 2, lambda b: (256 * b[0] + b[1]) / 100),
    "tps": (0x11, 1, lambda b: b[0] * 100 / 255),
}

KLINE_BAUD = 10400


class ISO9141:
    def __init__(self, port, serial_factory=serial.Serial, sleep=time.sleep):
        self.port = port
        self._serial_factory = serial_factory
        self._sleep = sleep
        self._serial = None
        self._supported = []
        self._next = 0
        self._ecu_source = None

    def open(self):
        try:
            self._ecu_source = None
            self._next = 0
            self._supported = []
            self._serial = self._serial_factory(self.port, KLINE_BAUD, timeout=0.5, write_timeout=1)
            self._serial.break_condition = False
            self._sleep(3)  # bus idle before 5-baud address
            # Start, 0x33 LSB first, stop; break drives UART TX low.
            for low in (True, False, False, True, True, False, False, True, True):
                self._serial.break_condition = low
                self._sleep(0.2)
            self._serial.break_condition = False
            # Remove the UART's local echo of the slow waveform before the ECU sync.
            self._serial.reset_input_buffer()
            self._sleep(0.2)
            sync = self._read_exact(3)
            if sync[0] != 0x55 or sync[1] != sync[2]:
                raise OBDConnectionError(f"Invalid ISO 9141 handshake: {sync.hex(' ')}")
            # The USB adapter may buffer received bytes before delivering them.
            # Wait at least 25 ms from receipt, not 30 ms plus USB latency.
            self._sleep(0.025)
            self._write_echo(bytes((sync[2] ^ 0xff,)))
            if self._read_exact(1) != b'\xcc':
                raise OBDConnectionError("ECU did not acknowledge ISO 9141 initialization")
            self._sleep(0.055)
            mask = int.from_bytes(self._read_pid(0, 4), 'big')
            self._supported = [name for name, (pid, _, _) in PIDS.items()
                               if mask & (1 << (32 - pid))]
            if not self._supported:
                raise OBDConnectionError("ECU responded but none of the implemented PIDs are supported")
        except Exception:
            self.close()
            raise

    def _read_exact(self, length):
        data = self._serial.read(length)
        if len(data) != length:
            raise OBDConnectionError(f"K-Line response incomplete: expected {length} bytes, got {len(data)}")
        return data

    def _write_echo(self, data):
        # USB serial adapters can buffer each echoed byte for many milliseconds.
        # Do not wait for an echo between bytes: that makes on-wire timing depend
        # on USB receive latency. Validate all echoes after sending the frame.
        for byte in data:
            written = self._serial.write(bytes((byte,)))
            if written != 1:
                raise OBDConnectionError("Incomplete K-Line serial write")
            if len(data) > 1:
                self._sleep(0.010)
        echo = self._read_exact(len(data))
        if echo != data:
            raise OBDConnectionError("K-Line echo mismatch; check cable and connection")

    def _read_pid(self, pid, length):
        body = bytes((0x68, 0x6a, 0xf1, 0x01, pid))
        self._write_echo(body + bytes((sum(body) & 0xff,)))
        responses = [self._read_exact(6 + length)]
        # Multiple modules can answer a functional request. Drain complete
        # responses before sending the next PID, so they cannot be mistaken for
        # the next response. Stop at an idle gap and bound the number of frames.
        old_timeout = self._serial.timeout
        try:
            self._serial.timeout = 0.15
            while len(responses) < 8:
                first = self._serial.read(1)
                if not first:
                    break
                responses.append(first + self._read_exact(5 + length))
            else:
                raise OBDConnectionError("Too many ISO 9141 responses")
        finally:
            self._serial.timeout = old_timeout
        self._sleep(0.055)
        for response in responses:
            if (response[:2] != b'\x48\x6b' or response[3:5] != bytes((0x41, pid))
                    or sum(response[:-1]) & 0xff != response[-1]):
                raise OBDConnectionError(f"Invalid ISO 9141 response: {response.hex(' ')}")
        if self._ecu_source is None:
            # Prefer a conventional engine-controller address; otherwise use
            # the first responding module. Verify this choice on the vehicle.
            self._ecu_source = next((r[2] for r in responses if 0x10 <= r[2] <= 0x17), responses[0][2])
        for response in responses:
            if response[2] == self._ecu_source:
                return response[5:-1]
        raise OBDConnectionError(f"No PID {pid:02X} response from selected ECU {self._ecu_source:02X}")

    def read_live_data(self, param_names=None):
        names = [n for n in self._supported if param_names is None or n in param_names]
        if not names:
            return None
        name = names[self._next % len(names)]
        self._next += 1
        pid, length, decode = PIDS[name]
        return LiveDataFrame(time.monotonic(), {name: decode(self._read_pid(pid, length))})

    def close(self):
        if self._serial is not None:
            try:
                self._serial.break_condition = False
            finally:
                self._serial.close()
                self._serial = None
