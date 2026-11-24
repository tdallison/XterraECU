import unittest

from nissecu.protocol.iso9141 import ISO9141, OBDConnectionError


class FakeKKL:
    def __init__(self, *args, **kwargs):
        self.queue = bytearray()
        self.writes = bytearray()
        self.breaks = []
        self.closed = False
        self.timeout = kwargs.get("timeout")
        self.events = []

    @property
    def break_condition(self):
        return self.breaks[-1] if self.breaks else False

    @break_condition.setter
    def break_condition(self, value):
        self.breaks.append(value)

    def reset_input_buffer(self):
        self.queue = bytearray(b'\x55\x08\x08')

    def write(self, data):
        self.events.append(("write", bytes(data)))
        self.queue.extend(data)  # KKL transmit echo
        if data == b'\xf7' and not self.writes:
            self.queue.extend(b'\xcc')
            return len(data)
        self.writes.extend(data)
        if len(self.writes) == 6:
            pid = self.writes[4]
            values = {0: bytes.fromhex('08 19 00 00'), 5: b'\x7b',
                      12: bytes.fromhex('1a f8'), 13: b'\x32',
                      16: bytes.fromhex('04 d2')}
            reply = bytes((0x48, 0x6b, 0x10, 0x41, pid)) + values[pid]
            self.queue.extend(reply + bytes((sum(reply) & 0xff,)))
            self.writes.clear()
        return len(data)

    def read(self, length):
        self.events.append(("read", length))
        data = self.queue[:length]
        del self.queue[:length]
        return bytes(data)

    def close(self):
        self.closed = True


class KKLTests(unittest.TestCase):
    def test_handshake_and_live_data(self):
        obd = ISO9141('fake', serial_factory=FakeKKL, sleep=lambda _: None)
        obd.open()
        cable = obd._serial
        self.assertEqual(cable.breaks[:11], [False, True, False, False, True, True,
                                            False, False, True, True, False])
        self.assertEqual([obd.read_live_data().values for _ in range(4)],
                         [{'coolant_temp': 83}, {'rpm': 1726}, {'vspeed': 50}, {'maf': 12.34}])
        obd.close()
        self.assertTrue(cable.closed)

    def test_request_writes_all_bytes_before_reading_echo(self):
        obd = ISO9141('fake', serial_factory=FakeKKL, sleep=lambda _: None)
        obd.open()
        cable = obd._serial
        cable.events.clear()
        obd.read_live_data()
        self.assertEqual([kind for kind, _ in cable.events[:6]], ['write'] * 6)
        self.assertEqual(cable.events[6], ('read', 6))

    def test_multiple_ecus_choose_engine_and_drain_other_responses(self):
        class MultipleECUs(FakeKKL):
            def write(self, data):
                result = super().write(data)
                # Once a full request is written, place transmission response
                # before the engine response, as a real bus may do.
                if len(self.queue) >= 7 and self.queue[6:8] == b'\x48\x6b':
                    pid = self.queue[10]
                    value = bytes.fromhex('08 00 00 00') if pid == 0 else b'\x50'
                    reply = bytes((0x48, 0x6b, 0x18, 0x41, pid)) + value
                    self.queue[6:6] = reply + bytes((sum(reply) & 0xff,))
                return result
        obd = ISO9141('fake', serial_factory=MultipleECUs, sleep=lambda _: None)
        obd.open()
        self.assertEqual(obd._ecu_source, 0x10)
        self.assertEqual(obd.read_live_data().values, {'coolant_temp': 83})
        self.assertEqual(obd._serial.queue, b'')

    def test_checksum_failure_is_rejected(self):
        class BadChecksum(FakeKKL):
            instance = None
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                BadChecksum.instance = self
            def write(self, data):
                written = super().write(data)
                if len(self.queue) == 16:  # six echoes plus the PID 00 response
                    self.queue[-1] ^= 1
                return written
        obd = ISO9141('fake', serial_factory=BadChecksum, sleep=lambda _: None)
        with self.assertRaises(OBDConnectionError):
            obd.open()
        self.assertTrue(BadChecksum.instance.closed)

    def test_echo_mismatch_closes_cable(self):
        class BadEcho(FakeKKL):
            instance = None
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                BadEcho.instance = self
            def write(self, data):
                result = super().write(data)
                if data == b'\xf7':
                    self.queue[0] ^= 1
                return result
        obd = ISO9141('fake', serial_factory=BadEcho, sleep=lambda _: None)
        with self.assertRaisesRegex(OBDConnectionError, "echo mismatch"):
            obd.open()
        self.assertTrue(BadEcho.instance.closed)

    def test_handshake_failure_closes_cable(self):
        class BadHandshake(FakeKKL):
            instance = None
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                BadHandshake.instance = self
            def reset_input_buffer(self):
                self.queue = bytearray(b'\x55\x08\x09')
        obd = ISO9141('fake', serial_factory=BadHandshake, sleep=lambda _: None)
        with self.assertRaises(OBDConnectionError):
            obd.open()
        self.assertTrue(BadHandshake.instance.closed)


if __name__ == '__main__':
    unittest.main()
