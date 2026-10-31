"""Small GDSII controls independent of EDA packages and process resources."""

import struct


def array_gds(*, geometry=True):
    """Six 1 um squares at x=-1,1,3 and y=1,4; ignore a distant text label."""
    def record(kind, datatype, data=b''):
        data += b'\0' * (len(data) % 2)
        return struct.pack('>HBB', len(data) + 4, kind, datatype) + data

    def xy(*values):
        return struct.pack('>' + 'i' * len(values), *values)

    def real8(value):
        exponent = 64
        while value < 1 / 16:
            value *= 16
            exponent -= 1
        while value >= 1:
            value /= 16
            exponent += 1
        return bytes([exponent]) + int(value * 2**56).to_bytes(7, 'big')

    dates = struct.pack('>12h', *([2026, 1, 1, 0, 0, 0] * 2))
    boundary = [record(8, 0), record(13, 2, struct.pack('>h', 17)),
                record(14, 2, struct.pack('>h', 3)),
                record(16, 3, xy(0, 0, 1000, 0, 1000, 1000, 0, 1000, 0, 0)), record(17, 0)]
    return b''.join([
        record(0, 2, struct.pack('>h', 600)), record(1, 2, dates), record(2, 6, b'control'),
        record(3, 5, real8(.001) + real8(1e-9)),
        record(5, 2, dates), record(6, 6, b'child'), *(boundary if geometry else []), record(7, 0),
        record(5, 2, dates), record(6, 6, b'dut'), record(11, 0), record(18, 6, b'child'),
        record(19, 2, struct.pack('>2h', 3, 2)),
        record(16, 3, xy(-1000, 1000, 5000, 1000, -1000, 7000)), record(17, 0),
        record(12, 0), record(13, 2, struct.pack('>h', 17)), record(22, 2, struct.pack('>h', 3)),
        record(16, 3, xy(100000, 100000)), record(25, 6, b'IGNORE_TEXT'), record(17, 0),
        record(7, 0), record(4, 0),
    ])


