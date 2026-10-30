import struct


def universe(fixtures, addresses):
    """Write RGB at one-based starts, leaving every other channel zero.

    At starts 1/5/9 this also fits Profile Plus Ch04: each fourth (UV) channel
    stays off. Callers must allow for the full fixture footprint when choosing
    addresses; this helper only checks overlap between the RGB triplets.
    """
    if len(fixtures) != len(addresses):
        raise ValueError("Each fixture needs an address")
    occupied = set()
    data = bytearray(512)
    for rgb, address in zip(fixtures, addresses):
        if not 1 <= address <= 510 or len(rgb) != 3:
            raise ValueError("RGB fixture addresses must be 1..510")
        channels = set(range(address - 1, address + 2))
        if occupied & channels:
            raise ValueError("Fixture channel ranges overlap")
        occupied |= channels
        data[address - 1:address + 2] = bytes(rgb)
    return bytes(data)


def pro_packet(data):
    if len(data) != 512:
        raise ValueError("Expected a 512-channel DMX universe")
    payload = b'\x00' + data  # DMX start code
    return b'\x7e\x06' + struct.pack('<H', len(payload)) + payload + b'\xe7'


class EnttecPro:
    """Buffered ENTTEC USB Pro protocol; not Open DMX or generic USB serial."""

    def __init__(self, port):
        import serial
        self.serial = serial.Serial(port, 57600, timeout=1, write_timeout=1)

    def send(self, data):
        packet = pro_packet(data)
        if self.serial.write(packet) != len(packet):
            raise IOError("Incomplete USB DMX write")

    def close(self):
        try:
            self.send(bytes(512))
            self.serial.flush()
        finally:
            self.serial.close()
