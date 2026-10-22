"""Typed Calibre rule, check and extraction declarations without tool execution."""

import copy
import re
from dataclasses import asdict, dataclass, field, fields
from pathlib import Path


@dataclass(frozen=True)
class RuleSettings:
    deck: str
    rule_control: str | None = None
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
    require_erc_summary: bool = True


@dataclass(frozen=True)
class RCSettings:
    require_junctions: bool = True
    ground: str | None = None
    xcell_file: str | None = None
    subcircuit_mos_models: tuple[str, ...] = ()
    case_insensitive_ports: bool = False
    mos_parameters: dict = field(default_factory=dict)


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
    def parse(cls, check, deck, settings, *, connectivity):
        remaining = copy.deepcopy(dict(settings, deck=deck))
        configuration = cls(check, connectivity, _group(RuleSettings, remaining),
                            _group(DRCSettings, remaining), _group(LVSSettings, remaining),
                            _group(RCSettings, remaining))
        if remaining:
            raise TypeError('Unknown Calibre settings: ' + ', '.join(sorted(remaining)))
        configuration.validate()
        return configuration

    def validate(self):
        if self.check not in {'drc', 'lvs', 'rc'}:
            raise ValueError('Unknown Calibre operation')
        if self.connectivity not in {'xrc', 'cci'} or (self.connectivity == 'cci' and self.check != 'rc'):
            raise ValueError('CCI connectivity requires an extraction operation')
        if (type(self.drc.threads) is not int or self.drc.threads < 1
                or (self.drc.threads != 1 and self.check != 'drc')):
            raise ValueError('Calibre threads must be positive and are only configurable for DRC')
        if not isinstance(self.rc.mos_parameters, dict) or any(
                not isinstance(name, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]*', name)
                or rule not in {'positive', 'nonnegative', 'positive_integer'}
                for name, rule in self.rc.mos_parameters.items()):
            raise ValueError('MOS parameter checks require names and numeric validation rules')
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
