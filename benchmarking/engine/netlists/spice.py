"""SPICE logical lines, dialect-aware tokens and scalar engineering values."""

import re
import shlex
from dataclasses import dataclass

_SUFFIXES = {
    "t": 1e12, "g": 1e9, "meg": 1e6, "k": 1e3, "m": 1e-3,
    "u": 1e-6, "n": 1e-9, "p": 1e-12, "f": 1e-15, "a": 1e-18,
}


def expand_mos_multiplicity(text):
    """Give native LVS explicit copies of MOS cards with literal integer m.

    Native planar reducers scale W by m but do not necessarily scale custom
    fin/sheet properties. Explicit copies preserve every per-unit parameter,
    including nfin, so the same property reducer handles source and layout.
    Simulation and extracted device cards remain unchanged.
    """
    rows = logical_lines(text)
    occupied = {line.text.split()[0].lower() for line in rows if line.text.split()}
    output = []
    for line in rows:
        raw = line.text
        if not re.match(r'\s*[mM]\S+\s', raw):
            output.append(raw)
            continue
        matches = list(re.finditer(r'(?i)\bm\s*=\s*([^\s]+)', raw))
        if not matches:
            output.append(raw)
            continue
        if len(matches) != 1:
            raise ValueError('MOS multiplicity must be specified once')
        match = matches[0]
        count = number(match[1])
        if count < 1 or count != int(count):
            raise ValueError('Native LVS requires positive integer MOS multiplicity')
        if count == 1:
            output.append(raw)
            continue
        card = (raw[:match.start()] + raw[match.end():]).strip()
        name, tail = card.split(None, 1)
        for index in range(int(count)):
            ident = name + '_parallel_' + str(index)
            while ident.lower() in occupied:
                ident += '_'
            occupied.add(ident.lower())
            output.append(ident + ' ' + tail)
    return '\n'.join(output) + '\n'


@dataclass(frozen=True)
class LogicalLine:
    text: str
    physical_lines: tuple[int, ...]


def logical_lines(raw: bytes | str) -> tuple[LogicalLine, ...]:
    """Join leading '+' continuations and retain zero-based source line indices."""
    content = raw.decode("utf-8") if isinstance(raw, bytes) else raw
    lines = []
    current = None
    for line_number, physical in enumerate(content.splitlines()):
        stripped = physical.strip()
        if not stripped:
            current = None
            continue
        if stripped.startswith(("*", ";")):
            # Comments remain in source order for DSPF/evidence, but a comment
            # between a card and its continuation is not itself that card.
            lines.append(LogicalLine(physical.rstrip(), (line_number,)))
            continue
        if stripped.startswith("+"):
            target = current
            if target is None and lines and lines[-1].text.lstrip().startswith(("*", ";")):
                # Exporters also wrap standalone comments with '+'. Without
                # an active card, the continuation belongs to that comment.
                target = len(lines) - 1
            if target is None:
                raise ValueError(f"SPICE continuation appears without a device line at {line_number + 1}")
            card = lines[target]
            lines[target] = LogicalLine(card.text + " " + stripped[1:].strip(),
                                        (*card.physical_lines, line_number))
            continue
        current = len(lines)
        lines.append(LogicalLine(physical.rstrip(), (line_number,)))
    return tuple(lines)


def tokens(line: LogicalLine, *, inline_comments: tuple[str, ...] = (";",),
           preserve_parameters: bool = False) -> list[str]:
    """Read quoted/escaped names; only standalone dialect markers start comments.

    '#' and dollar-bearing identifiers are legal nets. CDL callers may opt in
    to the standalone '$' comment marker without losing names such as Q$1/$10.
    Display callers may preserve parameter spelling, including quoted expressions.
    """
    if line.text.lstrip().startswith(("*", ";")):
        return []
    lexer = shlex.shlex(line.text, posix=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    words = []
    start = 0
    try:
        for word in lexer:
            end = lexer.instream.tell()
            spelling = line.text[start:end].strip()
            start = end
            if spelling in inline_comments:
                break
            words.append(spelling if preserve_parameters and "=" in word else word)
    except ValueError as error:
        raise ValueError(f"Invalid SPICE line at {line.physical_lines[0] + 1}: {error}") from error
    return words


def number(value: str) -> float:
    """Parse a scalar with an optional engineering suffix; reject expressions."""
    match = re.fullmatch(r"([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)([A-Za-z]*)", value.strip())
    if not match:
        raise ValueError(f"Unsupported non-scalar SPICE value: {value}")
    result = float(match.group(1))
    suffix = match.group(2).casefold()
    if suffix:
        if suffix not in _SUFFIXES:
            raise ValueError(f"Unsupported SPICE unit suffix: {suffix}")
        result *= _SUFFIXES[suffix]
    return result
