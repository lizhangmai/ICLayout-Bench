"""Check native circuits and bind their declared top-level interface.

Device cards belong to the extractor. This module never changes models,
terminals, physical parameters or the extracted RC network.
"""

import math
import re

from benchmarking.eda.netlists.spice import logical_lines
from benchmarking.eda.netlists.spice import number as spice_number


def bind_ports(text, top, ports, *, case_insensitive=False):
    """Reorder an existing named interface without adding or removing ports."""
    lines = logical_lines(text)
    matches = [line for line in lines
               if re.match(r'(?i)^\s*\.subckt\s+' + re.escape(top) + r'\s+', line.text)]
    canonical = str.upper if case_insensitive else str
    if (len(matches) != 1 or not ports or len(ports) != len({canonical(p) for p in ports})
            or len(matches[0].text.split()[2:]) != len(ports)
            or {canonical(p) for p in matches[0].text.split()[2:]} != {canonical(p) for p in ports}):
        raise ValueError('Extracted top-level ports differ from the declared interface')
    # Preserve every device card byte-for-byte, including continuations,
    # annotations and parameters unknown to this interface reader.
    physical = text.splitlines(keepends=True)
    header = matches[0].physical_lines
    physical[header[0]] = '.SUBCKT ' + top + ' ' + ' '.join(ports) + '\n'
    for index in header[1:]:
        physical[index] = ''
    return ''.join(physical)


def _positive_parameters(tail, required, *, nonnegative=()):
    params = {name.lower(): value for name, value in
              re.findall(r'\b(\w+)=([^\s]+)', tail)}
    if not set(required) <= params.keys():
        raise ValueError('Extracted device is missing required geometry')
    for name in required:
        value = spice_number(params[name])
        if not math.isfinite(value) or value < 0 or (name not in nonnegative and value == 0):
            raise ValueError('Invalid extracted device geometry')


def bind_extracted_netlist(text, top, ports, *, require_junctions=False,
                          junctionless_models=(), subcircuit_mos_models=(),
                          case_insensitive_ports=False):
    """Validate native four-terminal MOS/primitive R/Q cards without rewriting.

    Model compatibility is established by author qualification of the native
    extraction/model combination, never by a circuit conversion here.
    """
    has_device = False
    kinds = set()
    for row in logical_lines(text):
        line = row.text.lstrip()
        fields = line.split()
        if not fields or line.startswith(('*', ';', '.')):
            continue
        kind = fields[0][0].upper()
        kinds.add(kind)
        wrapped_mos = kind == 'X' and len(fields) >= 7 and fields[5] in subcircuit_mos_models
        if kind == 'M' or wrapped_mos:
            if len(fields) < 7:
                raise ValueError('Incomplete extracted MOS')
            junctions = {'as', 'ad', 'ps', 'pd'} if (
                require_junctions and fields[5] not in junctionless_models) else set()
            _positive_parameters(' '.join(fields[6:]), {'l', 'w'} | junctions,
                                 nonnegative=junctions)
            has_device = True
        elif kind == 'Q':
            if len(fields) < 6:
                raise ValueError('Incomplete extracted bipolar device')
            tail = ' '.join(fields[5:])
            names = re.findall(r'(?i)\b(area|m)=', tail)
            _positive_parameters(tail, {name.lower() for name in names})
            has_device = True
        elif kind == 'R':
            if len(fields) < 4:
                raise ValueError('Incomplete extracted resistor')
            try:
                value = spice_number(fields[3])
            except ValueError:
                _positive_parameters(' '.join(fields[4:]), {'l', 'w'})
                has_device = True
            else:
                if not math.isfinite(value) or value < 0:
                    raise ValueError('Invalid extracted interconnect resistance')
                if re.search(r'(?i)\b(?:segr|segw|segl|effw|effl)\s*=', ' '.join(fields[4:])):
                    raise ValueError('Numeric process resistor lost its model; enable model-preserving extraction')
    if not has_device or not {'R', 'C'} <= kinds:
        raise ValueError('Native extraction lacks physical devices or RC elements')
    return bind_ports(text, top, ports, case_insensitive=case_insensitive_ports)
