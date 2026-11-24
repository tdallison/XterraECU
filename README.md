# NissECU — 2005 Nissan Xterra diagnostics

This checkout is being adapted specifically for a **2005 Nissan Xterra N50 with the VQ40DE**. The default interface is a wired USB KKL 409.1 K-Line cable, using an experimental, read-only generic OBD-II implementation. It has been tested with simulated serial responses, not yet on the target vehicle.

The [2005 Xterra engine control service manual](https://boredmder.com/FSMs/Nissan/Xterra/2005/EC.pdf), EC-140 and EC-725, identifies ISO 9141 for the generic scan tool and shows DLC pin 7 connected to the ECM K-Line. This does not establish the proprietary ECU programming protocol or ROM layout.

## Current capabilities

- Initialize an echoing KKL cable using a 5-baud ISO 9141 wakeup, then communicate at 10,400 baud.
- Query the supported generic Mode 01 PIDs and poll the implemented values the ECU reports as supported: coolant temperature, bank 1 short- and long-term fuel trims, engine speed, vehicle speed, ignition timing, mass air flow, and throttle position.
- View live readings and log them to CSV. Each CSV sample contains the one PID just polled; other columns are empty in that row.
- An optional ELM327 serial interface is available for future use, including a Bluetooth adapter exposed by the operating system as a serial port. It has not been tested with the target vehicle.

Trouble-code reading, Nissan-specific diagnostics, ECU identification, ROM backup, flash programming, and VQ40DE map definitions are **not implemented or validated**. The map editor and ECU ROM operations are unavailable for this vehicle. Existing VQ35DE-related source files are legacy code and should not be assumed compatible with the Xterra. Do not use them to program the vehicle.

## Setup

Install Python 3.9+ and dependencies, then run:

```bash
python -m pip install -r requirements.txt
python nissecu_gui.py
```

### Wired KKL 409.1 (current adapter)

1. Connect the cable to the computer's USB port and the Xterra's diagnostic connector, then turn the ignition on.
2. In NissECU, select the cable's serial port. **KKL 409.1 USB K-Line** is the default interface; its 10,400 baud K-Line speed is automatic.
3. Click **Connect**. Initialization takes several seconds. The application reports connected only after a valid ECU response to the supported-PID query.

### ELM327 Bluetooth or serial (optional future adapter)

1. Connect the adapter to the Xterra and turn the ignition on. For Bluetooth, pair the adapter using the operating system and configure it to expose a serial port.
2. In NissECU, select that port and **ELM327 serial / Bluetooth**. Select the adapter's host serial baud rate; the default is 38,400 baud.
3. Click **Connect**. The ELM327 path selects ISO 9141 for the vehicle and reports connected after a valid ECU response.

The ELM327 path requires a serial port provided by the operating system; it does not scan or pair Bluetooth devices itself and does not support direct Bluetooth Low Energy connections. It has been tested only with simulated responses, not with an adapter or this Xterra.

### Cable and connection notes

The KKL path assumes the cable echoes transmitted bytes and exposes UART break control. USB chipset, driver, cable wiring and timing can affect initialization; no specific KKL variant has yet been validated. It collects responses from multiple modules and prefers an address in the conventional engine-controller range, but the chosen module still needs confirmation on this Xterra. On Linux, the user may need access to the serial device (commonly through the `dialout` group). Never connect a bare USB UART directly to the vehicle's 12 V K-Line.

After connecting the cable, `python -m serial.tools.list_ports -v` can show its serial port and, where available, its USB manufacturer and device IDs. Some USB serial devices buffer received data; for example, FTDI documents a typical 16 ms default latency timer. The short ISO 9141 handshake timing can be affected by driver latency and operating-system scheduling. If initialization fails, record the cable's USB IDs, port, driver and the exact error before changing driver settings. See [FTDI's driver options guide](https://www.ftdichip.com/Documents/AppNotes/AN_107_AdvancedDriverOptions_AN_000073.pdf).

## Tests

```bash
python -m unittest discover -s tests -v
```

The tests use simulated serial devices. A passing test does not prove timing, electrical compatibility, or operation on a vehicle.

## License

The original project was distributed under a non-commercial source license. Removing its local license file does not change the terms that apply to existing code.
