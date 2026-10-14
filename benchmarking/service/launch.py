"""Launch the installed local service with caller-declared runtime settings."""

import os
import selectors
import signal
import subprocess
import sys
from contextlib import contextmanager
from dataclasses import dataclass


def stop(process, signum=signal.SIGTERM, *, timeout=15):
    """Stop the owned process group, escalating after a bounded grace period."""
    if process.poll() is None:
        try:
            os.killpg(process.pid, signum)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=10)


@dataclass
class ServiceProcess:
    endpoint: str
    process: subprocess.Popen
    _retained: bool = False

    def retain(self):
        """Leave a ready service alive for caller-managed recovery."""
        self._retained = True


@contextmanager
def launch_service(arguments, *, output, environment, on_event=None,
                   startup_timeout=600, shutdown_timeout=15):
    """Own service startup and shutdown, keeping operator configuration explicit.

    ``arguments`` are the installed service CLI options; credentials belong in
    the supplied process environment. The caller owns the output directory and
    any retained service's durable identity and recovery. Failed startup always
    stops the process. Event callbacks receive lifecycle facts, never settings.
    """
    def event(kind, **data):
        if on_event is not None:
            on_event(kind, **data)

    with (output / "service.log").open("a") as log:
        process = subprocess.Popen([sys.executable, "-I", "-m", "benchmarking.service", *arguments],
                                   cwd=output, env=environment, stdout=subprocess.PIPE, stderr=log,
                                   text=True, start_new_session=True)
        ready = None
        try:
            event("service_spawned", pid=process.pid)
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                if not selector.select(timeout=startup_timeout):
                    raise TimeoutError("Local service did not start; see service.log")
            line = process.stdout.readline().strip()
            prefix = "Local development service: "
            if not line.startswith(prefix) or not line.removeprefix(prefix):
                raise RuntimeError("Local service failed; see service.log")
            ready = ServiceProcess(line.removeprefix(prefix), process)
            event("service_ready", pid=process.pid)
            yield ready
        finally:
            try:
                if ready is None or not ready._retained:
                    stop(process, signal.SIGINT, timeout=shutdown_timeout)
                    event("service_exit", pid=process.pid, exit_code=process.returncode, ready=ready is not None)
            finally:
                process.stdout.close()
