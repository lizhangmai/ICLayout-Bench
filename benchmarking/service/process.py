"""Durable identity of the local service process, independent of its launcher."""

from pathlib import Path


def process_start(pid):
    """Linux process identity: a recycled PID must never authorize adoption/stop."""
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(") ", 1)[1].split()
        if fields[0] == "Z":
            return None
        return {"ticks": fields[19], "boot": Path("/proc/sys/kernel/random/boot_id").read_text().strip()}
    except (OSError, IndexError):
        return None
