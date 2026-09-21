"""Check public checkout independence without reading any sibling repositories."""

import ast
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIBLING = re.compile(r'(?:\.\./|["\'])ICLayout-(?:Designs|Bench-Designs|Bench-Private|Bench-UserTrial)(?:/|["\'])|\.\./ICLayout-Bench(?:/|["\'])')
PERSONAL = re.compile(r'/(?:home|Users)/lizhangmai(?:/|\b)')
INTERNAL = ('iclayout_bench_private', 'iclayout_designs')
DATA_ROOTS = {'tasks', 'qualification', 'data.jsonl', 'web'}


def check(root=ROOT):
    paths = subprocess.check_output(
        ['git', 'ls-files', '--cached', '--others', '--exclude-standard', '-z'], cwd=root
    ).decode().split('\0')
    errors = []
    for name in sorted(set(paths)):
        if not name or name.startswith('third_party/'):
            continue
        path = root / name
        if not path.exists() and not path.is_symlink():
            continue  # A staged deletion is not a publication input.
        if Path(name).parts[0] in DATA_ROOTS:
            errors.append(f'{name}: Dataset or application content in the engine checkout')
        if path.is_symlink() and not path.resolve().is_relative_to(root.resolve()):
            errors.append(f'{name}: external symlink')
            continue
        if not path.is_file():
            continue
        try:
            source = path.read_text()
        except UnicodeError:
            continue
        if name.endswith('.md') and re.search(r'ICLayout-(?:Designs|Bench-Designs|Bench-Private|Bench-UserTrial)', source):
            errors.append(f'{name}: internal repository organization in public documentation')
        if SIBLING.search(source) or PERSONAL.search(source):
            errors.append(f'{name}: implicit workspace or maintainer path')
        if name.endswith('.py'):
            for node in ast.walk(ast.parse(source, filename=name)):
                modules = ([x.name for x in node.names] if isinstance(node, ast.Import)
                           else [node.module or ''] if isinstance(node, ast.ImportFrom) else [])
                if any(m.split('.')[0] in INTERNAL for m in modules):
                    errors.append(f'{name}:{node.lineno}: internal application import')
    return errors


if __name__ == '__main__':
    failures = check()
    for failure in failures:
        print(failure, file=sys.stderr)
    print(f'Public repository boundary: {len(failures)} error(s).')
    raise SystemExit(bool(failures))
