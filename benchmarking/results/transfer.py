"""Portable terminal-result packages and authenticated website delivery (stdlib only)."""

import argparse
import hashlib
import json
import os
import shutil
import stat
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath

from benchmarking.files import read_file

FORMAT = "iclayout-results"
MAX_BYTES = 512 * 1024 * 1024
MAX_FILES = 20000
DEFAULT_FILES = (
    "final.gds",
    "layout.png",
    "evaluation/report.json",
    "evaluation/plan.json",
)


def safe_name(name):
    if not isinstance(name, str):
        raise TypeError("Package paths must be strings")
    path = PurePosixPath(name)
    if (
        not isinstance(name, str)
        or not name
        or "\\" in name
        or path.is_absolute()
        or path.as_posix() != name
        or any(p.startswith(".") or p in {"participant", "archive"} for p in path.parts)
    ):
        raise ValueError("Unsafe or private package path")
    return name


def pack(source, destination):
    """Copy only terminal exports and their declared artifacts, never scan auth homes."""
    source, destination = Path(source).resolve(), Path(destination)
    paths = [source] if source.is_file() else sorted(source.rglob("result.json"))
    entries = {}
    count = 0
    total = 0
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with (
            destination.open("xb") as output,
            zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as z,
        ):
            for path in paths:
                relative = path.relative_to(
                    source if source.is_dir() else source.parent
                )
                if any(
                    p.startswith(".") or p in {"participant", "archive"}
                    for p in relative.parts
                ):
                    continue
                if path.is_symlink() or any(p.is_symlink() for p in path.parents):
                    raise ValueError("Symlink inputs are forbidden")
                raw_bytes = read_file(path.parent, path.name)
                raw = json.loads(raw_bytes)
                evaluation = raw.get("evaluation", raw)
                if evaluation.get("state") not in {
                    "complete",
                    "error",
                } or evaluation.get("test_only"):
                    raise ValueError("Only terminal model exports can be packaged")
                names = dict.fromkeys(
                    ["result.json", *raw.get("files", []), *DEFAULT_FILES]
                )
                for name in names:
                    safe_name(name)
                    try:
                        data = (
                            raw_bytes
                            if name == "result.json"
                            else read_file(path.parent, name)
                        )
                    except FileNotFoundError:
                        if name in raw.get("files", []):
                            raise ValueError("A declared artifact is missing") from None
                        continue
                    key = f"runs/{count:06d}/{name}"
                    total += len(data)
                    if total > MAX_BYTES or len(entries) >= MAX_FILES:
                        raise ValueError("Package exceeds size or file limit")
                    z.writestr(key, data)
                    entries[key] = {
                        "sha256": hashlib.sha256(data).hexdigest(),
                        "size": len(data),
                    }
                count += 1
            if not count:
                raise ValueError("No terminal exports found")
            z.writestr(
                "manifest.json",
                json.dumps(
                    {"format": FORMAT, "runs": count, "files": entries}, sort_keys=True
                ),
            )
    except FileExistsError:
        raise
    except Exception:
        destination.unlink(missing_ok=True)
        raise
    return {"runs": count, "files": len(entries), "bytes": total}


def unpack(package, destination, *, max_bytes=MAX_BYTES):
    """Validate all members before extracting; never use ZipFile.extractall."""
    destination = Path(destination)
    destination.mkdir(parents=True, exist_ok=False, mode=0o700)
    try:
        with zipfile.ZipFile(package) as z:
            members = z.infolist()
            names = [i.filename for i in members]
            if len(names) != len(set(names)) or len(names) > MAX_FILES + 1:
                raise ValueError("Duplicate members or too many files")
            if (
                sum(i.file_size for i in members) > max_bytes
                or "manifest.json" not in names
            ):
                raise ValueError("Invalid package size or missing manifest")
            for member in members:
                safe_name(member.filename)
                mode = member.external_attr >> 16
                if member.is_dir() or stat.S_ISLNK(mode) or member.flag_bits & 1:
                    raise ValueError("Only unencrypted regular files are accepted")
            if z.getinfo("manifest.json").file_size > 8 * 1024 * 1024:
                raise ValueError("Manifest too large")
            manifest = json.loads(z.read("manifest.json"))
            files = manifest["files"]
            if manifest.get("format") != FORMAT or set(files) != set(names) - {
                "manifest.json"
            }:
                raise ValueError("Manifest does not match archive")
            for name, expected in files.items():
                parts = PurePosixPath(name).parts
                if (
                    len(parts) < 3
                    or parts[0] != "runs"
                    or len(parts[1]) != 6
                    or not parts[1].isdigit()
                ):
                    raise ValueError("Invalid run path")
                data = z.read(name)
                if (
                    len(data) != expected["size"]
                    or hashlib.sha256(data).hexdigest() != expected["sha256"]
                ):
                    raise ValueError("Artifact digest mismatch")
                target = destination / name
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                target.write_bytes(data)
            exports = list(destination.glob("runs/*/result.json"))
            if not exports or len(exports) != manifest["runs"]:
                raise ValueError("Run count mismatch")
            for path in exports:
                raw = json.loads(path.read_bytes())
                for name in raw.get("files", []):
                    safe_name(name)
                    if not (path.parent / name).is_file():
                        raise ValueError("Missing declared artifact")
            return manifest
    except Exception:
        shutil.rmtree(destination)
        raise


def request(endpoint, token, path, *, package=None, name=None):
    url = urllib.parse.urlsplit(endpoint)
    if (
        url.scheme not in {"http", "https"}
        or not url.hostname
        or url.username
        or url.password
        or url.query
        or url.fragment
    ):
        raise ValueError("Expected a website origin without credentials")
    if url.scheme != "https" and url.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ValueError("Remote uploads require HTTPS")
    headers = {"Authorization": "Bearer " + token, "X-Platform-Request": "1"}
    data = None
    if package:
        data = Path(package).read_bytes()
        if len(data) > MAX_BYTES:
            raise ValueError("Package exceeds upload limit")
        headers["Content-Type"] = "application/zip"
        path += "?" + urllib.parse.urlencode({"name": name})
    req = urllib.request.Request(
        endpoint.rstrip("/") + path, data=data, headers=headers
    )

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    try:
        with urllib.request.build_opener(NoRedirect).open(req, timeout=180) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        raise ValueError(
            f"Website request failed (HTTP {error.code}); check account, package and server diagnostics"
        ) from None


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    p = commands.add_parser("pack")
    p.add_argument("source", type=Path)
    p.add_argument("output", type=Path)
    p = commands.add_parser("upload")
    p.add_argument("package", type=Path)
    p.add_argument("--name", required=True)
    q = commands.add_parser("status")
    q.add_argument("job")
    for command in [p, q]:
        command.add_argument("--website", required=True)
        command.add_argument("--token-env", default="ICLAYOUT_UPLOAD_TOKEN")
    args = parser.parse_args(argv)
    try:
        if args.command == "pack":
            result = pack(args.source, args.output)
        else:
            token = os.environ.get(args.token_env)
            if not token:
                raise ValueError("Set the upload token environment variable first")
            path = (
                "/api/uploads"
                if args.command == "upload"
                else "/api/uploads/" + urllib.parse.quote(args.job, safe="")
            )
            result = request(
                args.website,
                token,
                path,
                package=getattr(args, "package", None),
                name=getattr(args, "name", None),
            )
        print(json.dumps(result, indent=2))
    except (ValueError, OSError, zipfile.BadZipFile) as error:
        parser.exit(1, str(error) + "\n")


if __name__ == "__main__":
    main()
