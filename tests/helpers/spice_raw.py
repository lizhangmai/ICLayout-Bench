"""Read ngspice binary waveforms for independent measurement checks."""

import struct


def read_raw(content):
    header, binary = content.split(b"Binary:\n", 1)
    fields, variables = header.decode().split("Variables:\n", 1)
    metadata = dict(line.split(":", 1) for line in fields.splitlines())
    names = [line.split()[1] for line in variables.splitlines() if line.strip()]
    values = [item[0] for item in struct.iter_unpack("<d", binary)]
    if "complex" in metadata["Flags"]:
        values = [complex(real, imag) for real, imag in zip(values[::2], values[1::2], strict=True)]
    assert len(names) == int(metadata["No. Variables"])
    assert len(values) == int(metadata["No. Points"]) * len(names)
    return [dict(zip(names, values[index:index + len(names)], strict=True))
            for index in range(0, len(values), len(names))]


def output_rows(report, directory, job, output):
    return read_raw((directory / report["jobs"][job]["outputs"][output]["path"]).read_bytes())
