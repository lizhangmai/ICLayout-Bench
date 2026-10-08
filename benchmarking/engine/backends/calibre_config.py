"""Typed Calibre rule, check and extraction declarations without tool execution."""

import copy
import re
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path


@dataclass(frozen=True)
class RuleSettings:
    deck: str
    includes: dict = field(default_factory=dict)
    defines: dict = field(default_factory=dict)
    rule_includes: tuple[str, ...] = ()
    inline_includes: dict = field(default_factory=dict)
    text_variables: dict = field(default_factory=dict)


@dataclass(frozen=True)
class DRCSettings:
    deck_member: str | None = None
    threads: int = 1
    exclude_checks: tuple[str, ...] = ()


@dataclass(frozen=True)
class LVSSettings:
    source_libraries: tuple[str, ...] = ()
    hcell_file: str | None = None
    finfet: bool = False
    require_erc_summary: bool = True


@dataclass(frozen=True)
class RCSettings:
    require_junctions: bool = True
    mos_junctions: dict = field(default_factory=dict)
    ground: str | None = None
    xcell_file: str | None = None
    mos_models: dict = field(default_factory=dict)
    subcircuit_mos_models: tuple[str, ...] = ()
    case_insensitive_ports: bool = False


def _group(kind, settings):
    values = {}
    for declaration in fields(kind):
        name = declaration.name
        if name not in settings:
            continue
        value = settings.pop(name)
        if isinstance(declaration.default, tuple):
            value = tuple(value)
        elif declaration.default_factory is dict:
            if value is not None and not isinstance(value, dict):
                raise TypeError('Calibre ' + name + ' must be a table')
            value = dict(value or {})
        values[name] = value
    return kind(**values)


@dataclass(frozen=True)
class CalibreConfiguration:
    check: str
    connectivity: str
    rules: RuleSettings
    drc: DRCSettings
    lvs: LVSSettings
    rc: RCSettings

    @classmethod
    def parse(cls, check, deck, settings, *, connectivity, thread_limit):
        remaining = copy.deepcopy(dict(settings, deck=deck))
        configuration = cls(check, connectivity, _group(RuleSettings, remaining),
                            _group(DRCSettings, remaining), _group(LVSSettings, remaining),
                            _group(RCSettings, remaining))
        if remaining:
            raise TypeError('Unknown Calibre settings: ' + ', '.join(sorted(remaining)))
        configuration.validate(thread_limit)
        return configuration

    def validate(self, thread_limit):
        if self.check not in {'drc', 'lvs', 'rc'}:
            raise ValueError('Unknown Calibre operation')
        if self.connectivity not in {'xrc', 'cci'} or (self.connectivity == 'cci' and self.check != 'rc'):
            raise ValueError('CCI connectivity requires an extraction operation')
        if (type(self.drc.threads) is not int or not 1 <= self.drc.threads <= thread_limit
                or (self.drc.threads != 1 and self.check != 'drc')):
            raise ValueError('Calibre DRC threads must fit the tool CPU allocation')
        if (type(self.lvs.finfet) is not bool
                or (self.lvs.finfet and (self.rc.require_junctions or self.rc.mos_models or self.rc.mos_junctions))):
            raise ValueError('FinFET extraction retains native MOS models and FinFET junction properties')
        if any(not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name) for name in self.drc.exclude_checks):
            raise ValueError('Invalid excluded Calibre check')
        if self.drc.exclude_checks and self.check != 'drc':
            raise ValueError('Check exclusion only applies to DRC')
        member = self.drc.deck_member
        if member is not None and (self.check != 'drc' or not isinstance(member, str)
                                   or Path(member).is_absolute() or '..' in Path(member).parts):
            raise ValueError('Invalid archived DRC deck member')

    def identity(self):
        return asdict(self)
