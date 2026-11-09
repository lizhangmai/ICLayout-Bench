"""Common filesystem and environment isolation for every participant harness.

Native CLIs never see the host home or project ancestors. Reviewed MCP servers
run outside that namespace and expose only their stdio protocol through relays.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import socket
import subprocess
import sys
import threading
import uuid
from dataclasses import replace
from pathlib import Path

from benchmarking.participants.harnesses.contracts import ParticipantSelection

POLICY = "native-filesystem-v1"
TRANSPORT_ENV = {
    "PATH", "LANG", "LC_ALL", "LC_CTYPE", "TZ", "TERM", "SSL_CERT_FILE", "SSL_CERT_DIR",
    "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY",
    "http_proxy", "https_proxy", "all_proxy", "no_proxy",
}
HARNESS_ENV = {
    "codex": {"CODEX_HOME", "OPENAI_API_KEY"},
    "claude-code": {"CLAUDE_CONFIG_DIR", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL",
                    "CLAUDE_CODE_EFFORT_LEVEL", "CLAUDE_CODE_MAX_OUTPUT_TOKENS", "MAX_THINKING_TOKENS",
                    "CLAUDE_CODE_ENABLE_GATEWAY_MODEL_DISCOVERY", "CLAUDE_CODE_MAX_RETRIES",
                    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC", "DISABLE_AUTOUPDATER", "API_TIMEOUT_MS"},
    "dsh": {"DSH_HOME", "DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL"},
    "kimi-code": {"KIMI_CODE_HOME", "KIMI_DISABLE_TELEMETRY"},
    "zcode": {"ZCODE_HOME", "ZCODE_DATA_BASE_DIR", "ZCODE_MODEL_RETRY_MAX_RETRIES",
              "ZCODE_PERSONAL_PROVIDER_CONFIG_FILE", "ZCODE_STORAGE_DIR", "ZCODE_SESSION_DB_PATH",
              "ZCODE_MODEL_TELEMETRY_ENABLED", "OTEL_SDK_DISABLED"},
    "command": set(),
}


def referenced_environment(value):
    """Environment references already selected by a provider adapter."""
    result = set()
    if isinstance(value, dict):
        for key, item in value.items():
            if key in {"env_key", "api_key_env", "apiKeyEnv"} and isinstance(item, str):
                result.add(item)
            elif key == "env_http_headers" and isinstance(item, dict):
                result.update(item.values())
            else:
                result.update(referenced_environment(item))
    elif isinstance(value, list):
        for item in value:
            result.update(referenced_environment(item))
    return result


class StdioRelay:
    """One scoped MCP connection; no host filesystem interface is exposed."""

    def __init__(self, spec, directory, environment, address):
        self.spec, self.directory = spec, directory
        self.environment = {k: v for k, v in environment.items() if k in TRANSPORT_ENV}
        self.environment.update(spec.get("env", {}))
        self.address = address
        self.errors = directory.parent / 'isolation' / (self.address + '.stderr')
        self.errors.parent.mkdir(mode=0o700, exist_ok=True)
        self.listener = socket.socket(socket.AF_UNIX)
        self.listener.bind("\0" + self.address)
        self.listener.listen(1)
        self.listener.settimeout(.2)
        self.closed = threading.Event()
        self.lock = threading.Lock()
        self.processes, self.connections, self.workers = set(), set(), []
        self.thread = threading.Thread(target=self.serve, daemon=True)
        self.thread.start()

    def serve(self):
        while not self.closed.is_set():
            try:
                connection, _ = self.listener.accept()
            except TimeoutError:
                continue
            except OSError:
                break
            with self.lock:
                self.connections.add(connection)
            worker = threading.Thread(target=self.serve_connection, args=(connection,), daemon=True)
            self.workers.append(worker)
            worker.start()

    def serve_connection(self, connection):
        upstream = None
        try:
            with connection, self.errors.open("ab") as errors:
                upstream = subprocess.Popen(
                    [self.spec["command"], *self.spec.get("args", [])], cwd=self.directory,
                    env=self.environment, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors)
                with self.lock:
                    self.processes.add(upstream)
                    if self.closed.is_set():
                        upstream.terminate()

                def send():
                    try:
                        while data := connection.recv(65536):
                            upstream.stdin.write(data)
                            upstream.stdin.flush()
                    except (OSError, ValueError):
                        pass
                    finally:
                        try:
                            upstream.stdin.close()
                        except OSError:
                            pass

                threading.Thread(target=send, daemon=True).start()
                try:
                    while data := os.read(upstream.stdout.fileno(), 65536):
                        connection.sendall(data)
                except OSError:
                    pass
        except OSError:
            pass
        finally:
            if upstream is not None:
                upstream.terminate()
                try:
                    upstream.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    upstream.kill()
                    upstream.wait()
                upstream.stdout.close()
            with self.lock:
                self.connections.discard(connection)
                self.processes.discard(upstream)

    def close(self):
        self.closed.set()
        self.thread.join(timeout=1)
        with self.lock:
            connections, processes = list(self.connections), list(self.processes)
        for connection in connections:
            try:
                connection.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        for process in processes:
            process.terminate()
        for worker in self.workers:
            worker.join(timeout=6)
        self.listener.close()


class NativeRuntime:
    """Mandatory common launch policy, independent of vendor discovery flags."""

    def __init__(self, context, *, harness=None, runtime_paths=(), files=(), env_vars=()):
        self.original = self.context = context
        self.harness = harness or context.selection.condition.get("harness")
        self.runtime_paths, self.files, self.env_vars = runtime_paths, files, env_vars
        self.relays = []
        self.servers = None

    def __enter__(self):
        if not sys.platform.startswith("linux") or not shutil.which("bwrap"):
            raise ValueError("Native harness isolation requires Linux and bubblewrap (bwrap); refusing host execution")
        context = self.original
        if context.selection.environment.get('ICLAYOUT_BENCH_RESUME_ID'):
            record = context.output / 'native-isolation.json'
            if not record.is_file() or json.loads(record.read_text()).get('policy') != POLICY:
                raise ValueError('Native history has no isolated origin; refusing to import undeclared host context')
        servers = json.loads(context.mcp.read_text()).get("mcpServers", {})
        servers.setdefault("layout", {"command": sys.executable, "args": ["-I", str(context.bridge)],
                           "env": {k: v for k, v in context.selection.environment.items()
                                   if k.startswith("ICLAYOUT_BENCH_")}})
        self.servers = servers
        wrapped = {}
        address_file = context.directory.parent / 'isolation/relays.json'
        address_file.parent.mkdir(mode=0o700, exist_ok=True)
        addresses = json.loads(address_file.read_text()) if address_file.exists() else {}
        try:
            for name, spec in servers.items():
                address = addresses.setdefault(name, 'iclayout-mcp-' + uuid.uuid4().hex)
                if not isinstance(address, str) or not address.startswith('iclayout-mcp-') or len(address) != 45:
                    raise ValueError('Invalid saved MCP relay address')
                relay = StdioRelay(spec, context.directory, context.selection.environment, address)
                self.relays.append(relay)
                wrapped[name] = {"command": os.path.abspath(sys.executable),
                                 "args": ["-I", str(Path(__file__).with_name("mcp_relay.py")), relay.address],
                                 "env": {}}
            context.mcp.write_text(json.dumps({"mcpServers": wrapped}))
            settings = dict(context.selection.settings, mcp_servers=wrapped)
            self.context = replace(context, selection=ParticipantSelection(
                context.selection.condition, context.selection.environment, settings))
            address_file.write_text(json.dumps(addresses))
            return self
        except BaseException:
            self.__exit__(None, None, None)
            raise

    def __exit__(self, *args):
        for relay in self.relays:
            relay.close()
        # A continuation must wrap the real server, not a dead relay.
        if self.servers is not None:
            self.original.mcp.write_text(json.dumps({"mcpServers": self.servers}))

    def command(self, argv):
        context = self.context
        private = context.directory.parent.resolve()
        env = context.selection.environment
        home = private / "host-home"
        selected_home = Path(env.get('HOME', '/')).resolve()
        if selected_home.is_relative_to(private):
            home = selected_home
        home.mkdir(mode=0o700, exist_ok=True)
        config = private / "isolation"
        config.mkdir(mode=0o700, exist_ok=True)
        (config / "passwd").write_text(f"participant:x:{os.getuid()}:{os.getgid()}::{home}:/bin/sh\n")
        (config / "group").write_text(f"participant:x:{os.getgid()}:\n")
        (config / "nsswitch.conf").write_text("passwd: files\ngroup: files\nhosts: files dns\n")
        harness = self.harness
        if harness not in HARNESS_ENV:
            raise ValueError("Harness has no declared native environment policy: " + harness)
        allowed = TRANSPORT_ENV | HARNESS_ENV[harness] | referenced_environment(context.selection.settings) | set(self.env_vars)
        isolated = {k: v for k, v in env.items() if k in allowed or k.startswith("ICLAYOUT_BENCH_")}
        isolated.update(HOME=str(home), USER="participant", LOGNAME="participant", TMPDIR="/tmp",
                        XDG_CONFIG_HOME=str(home / ".config"), XDG_CACHE_HOME=str(home / ".cache"),
                        XDG_DATA_HOME=str(home / ".local/share"), XDG_STATE_HOME=str(home / ".local/state"))
        binary = shutil.which(argv[0], path=env.get("PATH")) if "/" not in argv[0] else argv[0]
        if not binary:
            raise ValueError("Native harness executable is missing: " + argv[0])
        executable = Path(binary).resolve(strict=True)
        launch_executable = executable
        roots = {Path(sys.prefix), Path(sys.base_prefix), Path(__file__).parents[1]}
        interpreter_prefix = Path(os.path.abspath(binary)).parent.parent
        if (interpreter_prefix / 'pyvenv.cfg').is_file():
            # Invoking a venv through its resolved base binary loses its package
            # environment. Preserve the original, normalized interpreter path.
            roots.add(interpreter_prefix)
            launch_executable = Path(os.path.abspath(binary))
        # An ELF/native distribution keeps helper executables alongside its main
        # executable. JS distributions also need their package-local modules.
        roots.add(executable.parent)
        header = executable.open("rb").read(256)
        bins = [str(executable.parent), str(Path(os.path.abspath(sys.executable)).parent), "/usr/bin", "/bin"]
        node = shutil.which("node", path=env.get("PATH"))
        if node:
            node = Path(node).resolve(strict=True)
            roots.add(node.parent)
            bins.insert(0, str(node.parent))
        if header.startswith(b"#!"):
            interpreter = shlex.split(header.splitlines()[0][2:].decode())
            if interpreter and Path(interpreter[0]).name == "env" and len(interpreter) > 1:
                helper = shutil.which(interpreter[1], path=env.get("PATH"))
            else:
                helper = interpreter[0] if interpreter else None
            if helper:
                helper = Path(helper).resolve(strict=True)
                roots.add(helper.parent)
                if helper.name not in {"sh", "bash", "env"}:
                    bins.insert(0, str(helper.parent))
            for parent in executable.parents:
                if (parent / "package.json").is_file():
                    roots.add(parent)
                    break
        roots.update(Path(p).resolve(strict=True) for p in self.runtime_paths)
        roots.update(Path(p).resolve(strict=True) for p in self.files)
        isolated["PATH"] = os.pathsep.join(dict.fromkeys(bins))
        command = [shutil.which("bwrap"), "--unshare-all", "--share-net", "--die-with-parent", "--cap-drop", "ALL",
                   "--tmpfs", "/tmp", "--proc", "/proc", "--dev", "/dev"]
        for name in ("/usr", "/bin", "/sbin", "/lib", "/lib64"):
            if Path(name).exists():
                command += ["--ro-bind", name, name]
        for path in sorted(roots, key=lambda p: (len(p.parts), str(p))):
            if not any(path.is_relative_to(p) for p in (Path("/usr"), Path("/bin"), Path("/lib"), Path("/lib64"))):
                command += ["--ro-bind", str(path), str(path)]
        for name in ("/etc/ssl", "/etc/pki", "/etc/ca-certificates", "/etc/resolv.conf", "/etc/hosts", "/etc/localtime", "/etc/ld.so.cache"):
            if Path(name).exists():
                command += ["--ro-bind", name, name]
        for name in ("passwd", "group", "nsswitch.conf"):
            command += ["--ro-bind", str(config / name), "/etc/" + name]
        command += ["--bind", str(private), str(private)]
        task = env.get("ICLAYOUT_BENCH_TASK_FILE")
        if task and Path(task).is_file():
            command += ["--ro-bind", task, task]
        # Only provider-owned credential stores explicitly selected by the Kimi
        # adapter need shared refresh locks outside this attempt.
        settings = context.selection.settings
        if harness == "kimi-code" and settings.get("credentials"):
            for name in ("credentials", "oauth"):
                path = str(Path(settings["credential_home"]) / name)
                command += ["--bind", path, path]
        command += ["--chdir", str(context.directory.resolve()), "--", str(launch_executable), *argv[1:]]
        (context.output / 'native-isolation.json').write_text(json.dumps({
            'policy': POLICY, 'state': 'configured', 'harness': harness,
            'read_only_program_paths': sorted(str(p) for p in roots),
            'private_directory': str(private), 'environment_names': sorted(isolated),
            'mcp_servers': sorted(self.servers or {}),
            'builtin_skills': 'harness distribution', 'external_host_context': 'not mounted',
        }, indent=2) + '\n')
        return command, isolated
