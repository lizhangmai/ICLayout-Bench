"""Serialize native Magic SI parameters in the declared model interface units.

Magic's .ext parameter records say which outputs are lengths or areas and
which explicit SI multipliers the exporter applies. KPEX's technology says
how its geometry parameters (micrometres and micrometres squared) enter the
simulator models. Only these two native declarations determine conversions.
The original devices, terminal order, multiplicities and interconnect remain.
"""

import json
import math
import re
from pathlib import Path

from klayout_pex.netlist.spice_reader import SpiceReader
from klayout_pex.netlist.spice_syntax import spice_lines
from klayout_pex.tech_info import TechInfo


def declarations(paths):
    result = {}
    pattern = re.compile(r'([awpl]\d*)=([A-Za-z_][A-Za-z0-9_]*)(?:\*([-+0-9.eE]+))?(?:[+-][0-9.eE]+)?')
    for path in paths:
        for line in path.read_text().splitlines():
            if not line.startswith('parameters '):
                continue
            _, model, *items = line.split()
            table = result.setdefault(model.casefold(), {})
            for item in items:
                match = pattern.fullmatch(item)
                if match is None:
                    raise ValueError(f'Unsupported Magic parameter declaration: {item}')
                kind, name, factor = match.groups()
                value = (2 if kind[0] == 'a' else 1, float(factor or 1))
                if not math.isfinite(value[1]) or value[1] <= 0:
                    raise ValueError('Invalid Magic parameter multiplier')
                name = name.casefold()
                if name in table and table[name] != value:
                    raise ValueError(f'Conflicting Magic parameter declarations: {model}.{name}')
                table[name] = value
    return result


def finite(value):
    if type(value) not in {float, int} or not math.isfinite(value):
        raise ValueError('Native extraction must provide finite numerical parameters')
    return value


def bind(native, metadata, technology, output):
    declared = declarations(metadata)
    tech = TechInfo.from_json(str(technology), dielectric_filter=None)
    models = tech.device_models.mappings_by_spice_model
    data = SpiceReader().read(str(native))
    original = {line.text.split()[0].casefold(): '\n'.join(line.physical_lines)
                for line in spice_lines(Path(native).read_text())
                if line.text and line.text[0].upper() in {'R', 'C'}}
    if data.scale != 1 or data.elements or data.parameters or len(data.subcircuits) != 1 or data.global_nodes:
        raise ValueError('Model binding requires one flat native SI subcircuit')
    sub = data.subcircuits[0]
    if sub.parameters or sub.local_parameters:
        raise ValueError('Native extraction must provide evaluated geometry')
    lines = ['* Native Magic SI extraction; model units from the declared technology.',
             f'.subckt {sub.name} {" ".join(sub.ports)}']
    for element in sub.elements:
        if element.kind in {'R', 'C'} and element.model is None:
            if element.parameters or len(element.nodes) != 2:
                raise ValueError('Unsupported native interconnect element')
            finite(element.value)
            lines.append(original[element.name.casefold()])
            continue
        if element.kind != 'X' or element.model is None:
            raise ValueError('Unsupported native modeled element')
        mappings = models.get(('X', element.model.upper()), [])
        if len(mappings) != 1:
            raise ValueError(f'Missing or ambiguous native model interface: {element.model}')
        mapping = mappings[0]
        if len(element.nodes) != len(mapping.terminal_names):
            raise ValueError('Native device terminal count differs from its model interface')
        dimensions = declared.get(element.model.casefold(), {})
        specs = {p.name.casefold(): p for p in mapping.parameters}
        values = dict(element.parameters)
        for name, raw in values.items():
            value = finite(raw)
            if name == 'm':
                if value <= 0:
                    raise ValueError('Invalid native multiplicity')
                continue
            spec = specs.get(name)
            if spec is None:
                raise ValueError(f'Undeclared native model parameter: {element.model}.{name}')
            if spec.WhichOneof('value') == 'constant':
                if value != spec.constant:
                    raise ValueError('Native extraction differs from a declared model constant')
                continue
            if name not in dimensions:
                raise ValueError(f'Missing Magic units: {element.model}.{name}')
            dimension, multiplier = dimensions[name]
            factor = spec.lvs_parameter_factor if spec.HasField('lvs_parameter_factor') else 1
            values[name] = finite(value / multiplier * 1e6 ** dimension * factor)
        required = {name for name, spec in specs.items() if spec.WhichOneof('value') != 'constant'}
        if required - values.keys():
            raise ValueError(f'Native extraction lacks model geometry: {element.model}')
        lines.append(f'{element.name} {" ".join(element.nodes)} {element.model} ' +
                     ' '.join(f'{name}={value:.17g}' for name, value in values.items()))
    lines.append(f'.ends {sub.name}')
    Path(output).write_text('\n'.join(lines) + '\n')


if __name__ == '__main__':
    config = json.loads(Path('model-interface.json').read_text())
    native = Path('extracted.spice')
    bind(native, sorted(Path('.').glob('*.ext')), config['technology'], 'modeled.spice')
    native.rename('native.spice')
    Path('modeled.spice').rename(native)
