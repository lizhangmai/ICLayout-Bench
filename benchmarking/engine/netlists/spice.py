"""SPICE logical lines, dialect-aware tokens and scalar engineering values."""

import re
import shlex
from dataclasses import dataclass

_SUFFIXES = {
    "t": 1e12, "g": 1e9, "meg": 1e6, "k": 1e3, "m": 1e-3,
    "u": 1e-6, "n": 1e-9, "p": 1e-12, "f": 1e-15, "a": 1e-18,
}


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
