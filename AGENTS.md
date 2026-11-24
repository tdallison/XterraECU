# NissECU project context

## Target and user priorities

- The only target is the user's 2005 Nissan Xterra N50, VQ40DE. Do not add support for other vehicles unless the user requests it. The exact ECU part number and ROM ID are not yet known.
- The user ultimately wants diagnostics/live data, ECU ROM backup, and editing/flashing. Start with read-only diagnostics and live data.
- The default interface is the user's hard-wired USB KKL 409.1 VAG-COM cable: a raw USB-to-K-Line interface, not an ELM327. No reader was connected to the computer or vehicle when this context was recorded.
- The user has backups and has authorized code changes in this checkout.

## Evidence and implementation status

- The [2005 Xterra engine control service manual](https://boredmder.com/FSMs/Nissan/Xterra/2005/EC.pdf) identifies ISO 9141 for generic scan-tool diagnostics (EC-140) and shows DLC pin 7 connected to ECM K-Line (EC-725). This is not evidence for the proprietary programming protocol, memory layout, seed/key, checksums, or map definitions.
- `nissecu/protocol/iso9141.py` provides an **experimental, unverified on-vehicle** read-only ISO 9141 Mode 01 path for an echoing KKL cable. It uses UART break for the 5-baud wakeup and 10,400 baud afterward. Timing, echo behavior, cable wiring, chipset, and driver support need validation with the real cable and vehicle. USB receive buffering can affect handshake timing; inspect the actual device IDs and error before changing driver settings. Requests send all bytes before validating echoes, and the code drains multiple module responses and selects a likely engine-controller address; this heuristic needs vehicle validation. The connection must not be presented as verified until the ECU responds.
- An optional ELM327 serial path is retained for a possible future Bluetooth adapter. Bluetooth pairing and a serial port must be provided by the operating system; this path has not been vehicle-tested.
- Current supported readings are limited to implemented PIDs advertised by the ECU. DTC reading and clearing, Nissan-specific diagnostics and ECU identification are not yet implemented for this target.
- Xterra ROM reading, writing and map editing are not supported. The original code contains VQ35DE-specific and unverified addresses, assumptions and programming logic. Do not reuse those assumptions on VQ40DE or expose an unverified write/erase path as working. Obtain evidence specific to the identified ECU before implementing any programming or map definitions.
- Tests simulate serial traffic; they do not verify physical timing or target-vehicle behavior. Run `python -m unittest discover -s tests -v` after protocol changes and check the GUI when changing its integration.

## License

The original project license restricted commercial use. The user removed the local `LICENSE` file for this private development checkout; removing the file does not relicense the existing code. Avoid assuming redistribution rights have changed.
