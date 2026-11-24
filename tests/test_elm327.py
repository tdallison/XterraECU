import unittest

from nissecu.protocol.elm327 import ELM327, OBDConnectionError, parse_mode01


class FakeSerial:
    def __init__(self, *args, **kwargs):
        self.commands = []
        self.buffer = b''
        self.closed = False

    def reset_input_buffer(self):
        self.buffer = b''

    def write(self, data):
        command = data.decode().strip()
        self.commands.append(command)
        response = {
            '0100': '41 00 08 19 00 00',
            '0105': '41 05 7B',
            '010C': '41 0C 1A F8',
            '010D': '41 0D 32',
            '0110': '41 10 04 D2',
        }.get(command, 'OK')
        self.buffer = (response + '\r>').encode()

    def read(self, size):
        result, self.buffer = self.buffer[:size], self.buffer[size:]
        return result

    def close(self):
        self.closed = True


class ELMTests(unittest.TestCase):
    def test_initialize_and_poll_supported_pids(self):
        elm = ELM327('fake', serial_factory=FakeSerial)
        elm.open()
        adapter = elm._serial
        self.assertEqual(adapter.commands, ['AT E0', 'AT L0', 'AT S1', 'AT H0', 'AT TP 3', '0100'])
        samples = [elm.read_live_data().values for _ in range(4)]
        self.assertEqual(samples, [{'coolant_temp': 83}, {'rpm': 1726}, {'vspeed': 50}, {'maf': 12.34}])
        self.assertNotIn('0111', adapter.commands)
        elm.close()
        self.assertTrue(adapter.closed)

    def test_response_validation(self):
        self.assertEqual(parse_mode01('SEARCHING...\r41 0C 1A F8\r', 12, 2), b'\x1a\xf8')
        for response in ('NO DATA', '41 0D 01 02', '41 0C 01', '41 0C 01 02 FF'):
            with self.subTest(response=response), self.assertRaises(OBDConnectionError):
                parse_mode01(response, 12, 2)

    def test_rejected_adapter_command_closes_port(self):
        class Reject(FakeSerial):
            instance = None
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                Reject.instance = self
            def write(self, data):
                self.buffer = b'?\r>'
        elm = ELM327('fake', serial_factory=Reject)
        with self.assertRaises(OBDConnectionError):
            elm.open()
        self.assertTrue(Reject.instance.closed)


if __name__ == '__main__':
    unittest.main()
