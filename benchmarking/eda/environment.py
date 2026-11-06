"""Read-only installations declared by a process manifest."""

import hashlib
import ipaddress
import json
import os
import re
import shlex
import tomllib
from pathlib import Path

from benchmarking.files import Asset, keys, read_file, relative


class ExternalRuntime:
    """Bind declared host resources without exposing credentials to identities."""

    def __init__(self, name, profile):
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', name):
            raise ValueError('Invalid external runtime name')
        keys(profile, {'image', 'mounts', 'environment'},
             {'network', 'pass_environment', 'modules', 'license_hosts', 'tool_environment',
              'control_files'}, 'external runtime')
        self.name, self.profile = name, profile
        self.image = profile['image']
        self.network = profile.get('network', 'none')
        if not re.fullmatch(r'[A-Za-z0-9_.-]+', self.network) or self.network in {'bridge', 'default'}:
            raise ValueError('External runtime requires none, host or an operator-selected named network')
        self.environment = profile['environment']
        self.control_files = profile.get('control_files', {})
        if not isinstance(self.control_files, dict):
            raise TypeError('Native process control files must be a table')
        for filename, content in self.control_files.items():
            relative(filename, 'native process control file')
            if not isinstance(content, str) or not content or '\0' in content:
                raise ValueError('Native process control files require nonempty text')
        for key, value in self.environment.items():
            if not re.fullmatch(r'[A-Z][A-Z0-9_]*', key) or not isinstance(value, str) or '\0' in value:
                raise ValueError('Invalid external environment')
        forwarded = profile.get('pass_environment', [])
        if (not isinstance(forwarded, list)
                or any(not isinstance(key, str)
                       or not re.fullmatch(r'[A-Z][A-Z0-9_]*', key)
                       or not re.search(r'LIC|LICENSE', key) for key in forwarded)
                or len(forwarded) != len(set(forwarded))):
            raise ValueError('Only named license environment settings may be forwarded')
        self.license_hosts = profile.get('license_hosts', {})
        if not isinstance(self.license_hosts, dict) or not set(self.license_hosts) <= set(forwarded):
            raise ValueError('License host mappings must select forwarded license settings')
        for address in self.license_hosts.values():
            if not isinstance(address, str):
                raise TypeError('License host mapping requires an operator-selected IP address')
            try:
                ipaddress.ip_address(address)
            except ValueError:
                raise ValueError('License host mapping requires an operator-selected IP address') from None
        self.modules = profile.get('modules', {})
        if not isinstance(self.modules, dict):
            raise TypeError('External modules must be a table')
        for tool, names in self.modules.items():
            if (not re.fullmatch(r'[a-z][a-z0-9_-]*', tool)
                    or not isinstance(names, list) or not names
                    or any(not isinstance(name, str)
                           or not re.fullmatch(r'[A-Za-z0-9_./+-]+', name)
                           or '..' in name.split('/') for name in names)):
                raise ValueError('Invalid external module selection')
        self.tool_environment = profile.get('tool_environment', {})
        if not isinstance(self.tool_environment, dict) or not set(self.tool_environment) <= set(self.modules):
            raise ValueError('Tool environment must select declared modules')
        for environment in self.tool_environment.values():
            if (not isinstance(environment, dict)
                    or any(not isinstance(key, str) or not re.fullmatch(r'[A-Z][A-Z0-9_]*', key)
                           or not isinstance(value, str) or '\0' in value
                           or re.search(r'LIC|LICENSE', key) for key, value in environment.items())):
                raise ValueError('Invalid tool environment; license settings must be forwarded by name')
        self.mounts = []
        targets = []
        for mount in profile['mounts']:
            keys(mount, {'source', 'target', 'release'}, {'identity_paths', 'credential'}, 'external mount')
            source = Path(mount['source'])
            target = Path(mount['target'])
            if (not source.is_absolute() or not source.exists() or not target.is_absolute()
                    or '..' in target.parts or ',' in str(source) or ',' in str(target)
                    or str(target) == '/' or any(target == Path(p) or Path(p) in target.parents
                                               for p in ('/workspace', '/tmp', '/proc', '/sys', '/dev'))):
                raise ValueError('Invalid external installation mount')
            if any(target == other or target in other.parents or other in target.parents for other in targets):
                raise ValueError('External mounts overlap')
            if not mount['release'] or not isinstance(mount['release'], str):
                raise ValueError('External installation needs a release identity')
            if mount.get('credential') and (not source.is_file() or mount.get('identity_paths')):
                raise ValueError('Credential mount must be one file without identity paths')
            if not mount.get('credential') and not mount.get('identity_paths'):
                raise ValueError('External installation needs identity_paths')
            if source.is_file() and not mount.get('credential') and mount['identity_paths'] != [source.name]:
                raise ValueError('A file mount identifies its own basename')
            targets.append(target)
            self.mounts.append(mount)
        self._identity = self.identity

    @classmethod
    def from_manifest(cls, manifest):
        """Bind the declared process runtime to its installed host resources."""
        manifest = Path(manifest).absolute()
        declaration = tomllib.loads(manifest.read_text())
        source = declaration['source']
        if source.get('kind') != 'external':
            raise ValueError('Process does not declare external resources')
        profile = dict(declaration['runtime'])
        controls = {}
        for name, spec in profile.get('control_files', {}).items():
            if isinstance(spec, dict):
                keys(spec, {'path'}, set(), 'native process control file reference')
                controls[name] = read_file(manifest.parent, spec['path']).decode('utf-8')
            else:
                controls[name] = spec  # Retained datasets may still carry literal control text.
        if controls:
            profile['control_files'] = controls
        return cls(source['runtime'], profile)

    @property
    def identity(self):
        mounts = []
        for mount in self.mounts:
            digest = hashlib.sha256()
            source = Path(mount['source'])
            for name in sorted(mount.get('identity_paths', [])):
                path = source if source.is_file() else source / relative(name, 'external identity path')
                if not path.exists():
                    raise ValueError('External installation identity file is missing')
                paths = sorted(p for p in path.rglob('*') if p.is_file()) if path.is_dir() else [path]
                for item in paths:
                    label = item.name if source.is_file() else str(item.relative_to(source))
                    digest.update(label.encode() + b'\0')
                    with item.open('rb') as stream:
                        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                            digest.update(chunk)
                    digest.update(b'\0')
            mounts.append({'target': mount['target'], 'release': mount['release'],
                           'credential': bool(mount.get('credential')), 'sha256': digest.hexdigest()})
        return {'name': self.name, 'mounts': mounts, 'network': self.network,
                'environment': self.environment, 'pass_environment': self.profile.get('pass_environment', []),
                'modules': self.modules, 'license_hosts': self.license_hosts,
                'tool_environment': self.tool_environment,
                'control_files': {name: hashlib.sha256(content.encode()).hexdigest()
                                  for name, content in self.control_files.items()},
                'adapter_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}

    def control_assets(self):
        """Stage explicitly declared native syntax unchanged in the tool workspace."""
        return {'process/' + name: Asset(content.encode(), 'text')
                for name, content in self.control_files.items()}

    def control_path(self, name):
        """Resolve an @ reference to a declared native process control file."""
        if not isinstance(name, str) or not name.startswith('@') or name[1:] not in self.control_files:
            raise ValueError('Unknown native process control file')
        return 'process/' + name[1:]

    def select_pdk(self, root_env=None):
        """Select an explicitly mounted process variant without changing defaults."""
        if root_env is None:
            return self
        root = self.environment.get(root_env)
        if not root or not self.pdk_mounts(root):
            raise ValueError('Process variant must name an explicitly mounted PDK')
        environment = self.environment | {'PDK_ROOT': root}
        original = Path(self.environment['PDK_ROOT'])
        for key in ('PDK_DIR', 'PDK_TECH_PATH', 'PDK_LAYER_MAP', 'PDK_LIBRARY_DEFINITIONS'):
            value = self.environment.get(key)
            if value and Path(value).is_relative_to(original):
                environment[key] = str(Path(root) / Path(value).relative_to(original))
        return ExternalRuntime(self.name, self.profile | {
            'environment': environment})

    def pdk_mounts(self, root=None):
        """Return the exact PDK mount or its explicitly selected subdirectories."""
        root = Path(root or self.environment['PDK_ROOT'])
        return [m for m in self.mounts if not m.get('credential')
                and (Path(m['target']) == root or root in Path(m['target']).parents)]

    def pdk_file(self, name):
        """Resolve a process file only inside an explicitly mounted resource."""
        target = Path(self.environment['PDK_ROOT']) / relative(name, 'process file')
        mounts = [m for m in self.pdk_mounts()
                  if Path(m['target']) == target or Path(m['target']) in target.parents]
        if len(mounts) != 1:
            raise ValueError('Process file is outside the declared PDK resource mounts')
        source = Path(mounts[0]['source']).resolve(strict=True)
        host = source / target.relative_to(mounts[0]['target'])
        if not host.resolve(strict=True).is_relative_to(source):
            raise ValueError('Process file escapes its declared PDK resource mount')
        return host, str(target)

    def select_module(self, tool, profile=None):
        """Select another operator-declared module profile for one tool."""
        if profile is None:
            return self
        if tool not in self.modules or profile not in self.modules:
            raise ValueError('Tool module profile must be explicitly declared')
        return ExternalRuntime(self.name, {**self.profile,
            'modules': {**self.modules, tool: self.modules[profile]}})

    def module_setup(self, tool):
        """Shell setup for a tool selected by the operator's module profile."""
        names = self.modules.get(tool)
        if not names:
            return ''
        setup = '. /usr/share/Modules/init/bash && module load ' + shlex.join(names)
        environment = self.tool_environment.get(tool, {})
        if environment:
            setup += ' && export ' + shlex.join(f'{key}={value}' for key, value in environment.items())
        return setup

    def module_command(self, tool, command):
        setup = self.module_setup(tool)
        if not setup:
            return command
        return ['bash', '-c', setup + ' && exec "$@"', 'eda-module', *command]

    def docker_args(self):
        if self.identity != self._identity:
            raise ValueError('External installation changed since preparation')
        args = []
        for mount in self.mounts:
            args += ['--mount', f"type=bind,src={mount['source']},dst={mount['target']},readonly"]
        for key, value in self.environment.items():
            args += ['--env', f'{key}={value}']
        for key in self.profile.get('pass_environment', []):
            if not re.fullmatch(r'[A-Z][A-Z0-9_]*', key) or not os.environ.get(key):
                raise ValueError('Missing external runtime environment setting')
            args += ['--env', key]
        for key, address in self.license_hosts.items():
            # Preserve the operator's license setting; resolve only its server
            # aliases that are unavailable in the container's DNS namespace.
            hosts = re.findall(r'(?:^|:)\d+@([A-Za-z0-9_.-]+)(?=:|$)', os.environ[key])
            if not hosts:
                raise ValueError('License host mapping needs a port@server environment setting')
            for host in sorted(set(hosts)):
                args += ['--add-host', f'{host}={address}']
        return args

    def evidence(self):
        return json.dumps(self.identity, sort_keys=True).encode()
