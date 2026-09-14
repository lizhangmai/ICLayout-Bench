"""Read simple declared SPICE stimuli for independent waveform checks.

These probes support literal numbers and single named parameters. They do not
interpret simulator expressions or computed measurement vectors.
"""

import math
import re
from decimal import Decimal
from itertools import pairwise

import pytest


def number(token, values=None):
    if token.startswith('{') and token.endswith('}'):
        return values[token[1:-1]]
    match = re.fullmatch(r'([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?)(meg|gig|[tgkmunpf])?',
                         token.lower())
    assert match, f'Unsupported scalar stimulus: {token}'
    scales = {'t': 1e12, 'g': 1e9, 'gig': 1e9, 'meg': 1e6, 'k': 1e3,
              'm': 1e-3, 'u': 1e-6, 'n': 1e-9, 'p': 1e-12, 'f': 1e-15, None: 1}
    return float(Decimal(match[1]) * Decimal(str(scales[match[2]])))


def command(deck, name):
    matches = [line.split() for line in deck.splitlines()
               if line.split() and line.split()[0].lower() == name.lower()]
    assert len(matches) == 1, (name, matches)
    return matches[0]


def assert_ac_stimuli(deck, values, op, ac):
    """Check independent voltage sources and sweep endpoints from the input deck."""
    for line in deck.splitlines():
        fields = line.split()
        if not fields or not fields[0].lower().startswith('v'):
            continue
        positive, negative = fields[1:3]
        token = fields[4] if fields[3].lower() == 'dc' else fields[3]
        def voltage(node):
            return 0 if node == '0' else op[f'v({node.lower()})']
        assert voltage(positive) - voltage(negative) == pytest.approx(number(token, values), abs=1e-9)
    sweep = command(deck, 'ac')
    start, stop = map(number, sweep[-2:])
    frequencies = [row['frequency'].real for row in ac]
    assert len(frequencies) >= 2
    assert frequencies[0] == pytest.approx(start)
    assert frequencies[-1] == pytest.approx(stop)
    assert all(math.isfinite(value) for value in frequencies)
    assert all(a < b for a, b in pairwise(frequencies))


def testbench(task, job_id):
    specification = next(job for job in task.evaluation.jobs if job.id == job_id)
    reference = dict(specification.inputs)['deck']
    return task.input_assets()[reference.removeprefix('input:')].content.decode()
