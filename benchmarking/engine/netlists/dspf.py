"""Strict adaptation of extracted DSPF into the declared SPICE interface."""

import math
import re

from benchmarking.files import keys

from .spice import logical_lines
from .spice import number as spice_number


def adapt_dspf(text, top, ports, mos_models, require_junctions=False, resistor_models=None,
               bipolar_models=None, junctionless_models=(), subcircuit_mos_models=(),
               case_insensitive_ports=False):
    """Bind named ports and explicit device wrappers, retaining numeric RC."""
    # Preserve native DSPF spelling and annotations for rewritten output;
    # physical continuation rules belong to the shared SPICE reader.
    text = '\n'.join(line.text.lstrip() for line in logical_lines(text)) + '\n'
    matches = list(re.finditer(r'(?im)^\.subckt[ \t]+'+re.escape(top)+r'[ \t]+([^\n]+)', text))
    canonical = (lambda p: p.upper()) if case_insensitive_ports else (lambda p: p)
    if (len(matches) != 1 or not ports or len(ports) != len({canonical(p) for p in ports})
            or len(matches[0][1].split()) != len(ports)
            or {canonical(p) for p in matches[0][1].split()} != {canonical(p) for p in ports}):
        raise ValueError('Extracted top-level ports differ from the declared interface')
    text = text[:matches[0].start()] + '.SUBCKT '+top+' '+' '.join(ports) + text[matches[0].end():]
    if not all(re.search(r'(?im)^'+prefix+r'\S*\s+', text) for prefix in ('R', 'C')):
        raise ValueError('Quantus output lacks physical devices or RC elements')
    lines = []
    has_device = False
    for line in text.splitlines():
        fields = line.split()
        wrapped_mos = (bool(re.match(r'(?i)^X\S+\s', line)) and len(fields) >= 7
                       and fields[5] in subcircuit_mos_models)
        if re.match(r'(?i)^M\S+\s', line) or wrapped_mos:
            has_device = True
            fields = line.split()
            if len(fields) < 7:
                raise ValueError('Incomplete extracted MOS')
            params = {name.lower(): value for name, value in
                          re.findall(r'\b(\w+)=([^\s]+)', ' '.join(fields[6:]))}
            required = {'l', 'w'} | ({'as', 'ad', 'ps', 'pd'}
                                    if require_junctions and fields[5] not in junctionless_models else set())
            if not required <= params.keys():
                raise ValueError('Extracted MOS is missing required geometry')
            for name in required:
                value = spice_number(params[name])
                if not math.isfinite(value) or value < 0 or (name in {'l', 'w'} and value == 0):
                    raise ValueError('Invalid extracted MOS geometry')
            if mos_models and not wrapped_mos:
                target = mos_models.get(fields[5])
                if not isinstance(target, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', target):
                    raise ValueError('Unmapped extracted MOS model')
                # fw/simw are extraction annotations, not compact-model parameters.
                tail = re.sub(r'\b(?:fw|simw)=\S+\s*', '', ' '.join(fields[6:]), flags=re.IGNORECASE)
                line = 'X'+fields[0]+' '+' '.join(fields[1:5])+' '+target+' '+tail
        elif re.match(r'(?i)^Q\S+\s', line):
            fields = line.split()
            if len(fields) < 6:
                raise ValueError('Incomplete extracted bipolar device')
            mapping = (bipolar_models or {}).get(fields[4])
            if not isinstance(mapping, dict):
                raise ValueError('Unmapped extracted bipolar model')
            keys(mapping, {'model', 'area_scale'}, set(), 'bipolar model mapping')
            target, scale = mapping['model'], mapping['area_scale']
            if (not isinstance(target, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', target)
                    or type(scale) not in {int, float} or not math.isfinite(scale) or scale <= 0):
                raise ValueError('Invalid bipolar model mapping')
            tail = ' '.join(fields[5:])
            areas = list(re.finditer(r'(?i)\barea=([^\s]+)', tail))
            if len(areas) != 1:
                raise ValueError('Extracted bipolar device requires one explicit area')
            try:
                area = spice_number(areas[0][1]) * scale
            except ValueError as error:
                raise ValueError('Invalid extracted bipolar area') from error
            if not math.isfinite(area) or area <= 0:
                raise ValueError('Invalid extracted bipolar area')
            tail = tail[:areas[0].start()] + f'area={area:.17g}' + tail[areas[0].end():]
            line = 'X'+fields[0]+' '+' '.join(fields[1:4])+' '+target+' '+tail
            has_device = True
        elif re.match(r'(?i)^R\S+\s', line):
            fields = line.split()
            if len(fields) < 4:
                raise ValueError('Incomplete extracted resistor')
            try:
                value = spice_number(fields[3])
            except ValueError:
                target = (resistor_models or {}).get(fields[3])
                if isinstance(target, dict):
                    keys(target, {'type', 'model'}, set(), 'primitive resistor mapping')
                    if (target['type'] != 'primitive' or not isinstance(target['model'], str)
                            or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', target['model'])):
                        raise ValueError('Invalid primitive resistor mapping')
                    params = {name.lower(): value for name, value in
                              re.findall(r'\b(\w+)=([^\s]+)', ' '.join(fields[4:]))}
                    try:
                        geometry = [spice_number(params[n]) for n in ('l', 'w')]
                    except (KeyError, ValueError) as error:
                        raise ValueError('Extracted primitive resistor lacks valid geometry') from error
                    if any(not math.isfinite(value) or value <= 0 for value in geometry):
                        raise ValueError('Extracted primitive resistor lacks valid geometry')
                    # A two-terminal compact resistor has no substrate pin.
                    # Keep all physical parameters, including multiplicity.
                    lines.append(' '.join([*fields[:3], target['model'], *fields[4:]]))
                    has_device = True
                    continue
                if not isinstance(target, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', target):
                    raise ValueError('Unmapped extracted resistor model')
                params = {name.lower(): value for name, value in
                          re.findall(r'\b(\w+)=([^\s]+)', ' '.join(fields[4:]))}
                if not {'l', 'w', 'sub'} <= params.keys():
                    raise ValueError('Extracted resistor lacks geometry or substrate')
                if any(not math.isfinite(spice_number(params[n])) or spice_number(params[n]) <= 0 for n in ('l', 'w')):
                    raise ValueError('Invalid extracted resistor geometry')
                line = (f'X{fields[0]} {fields[1]} {fields[2]} {params["sub"]} {target} '
                        f'l={params["l"]} w={params["w"]}')
                has_device = True
            else:
                if not math.isfinite(value) or value < 0:
                    raise ValueError('Invalid extracted interconnect resistance')
                if re.search(r'(?i)\b(?:segr|segw|segl|effw|effl)\s*=', ' '.join(fields[4:])):
                    raise ValueError('Numeric process resistor lost its model; enable model-preserving extraction')
        lines.append(line)
    if not has_device:
        raise ValueError('Quantus output lacks physical devices or RC elements')
    return '\n'.join(lines)+'\n'
