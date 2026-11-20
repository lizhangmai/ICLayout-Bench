"""Package import directions required by the implementation map stay acyclic."""

import ast
from pathlib import Path

import pytest

import benchmarking

pytestmark = pytest.mark.unit

ROOT = Path(benchmarking.__file__).parent
# Each importing package must not reach the forbidden prefix, even inside functions.
FORBIDDEN = [
    ("benchmarking.files", "benchmarking."),
    ("benchmarking.protocol", "benchmarking."),
    ("benchmarking.execution", "benchmarking.evaluation"),
    ("benchmarking.results", "benchmarking.participants"),
    ("benchmarking.participants.attempt", "benchmarking.participants.batch"),
]


def module_name(path):
    return ".".join(path.relative_to(ROOT.parent).with_suffix("").parts).removesuffix(".__init__")


def runtime_imports(path):
    """Yield imported modules and names, excluding type-checking-only blocks."""
    module = module_name(path).split(".")
    package = module if path.name == "__init__.py" else module[:-1]
    tree = ast.parse(path.read_text())
    type_only = {id(child) for node in ast.walk(tree)
                 if isinstance(node, ast.If) and isinstance(node.test, ast.Name)
                 and node.test.id == "TYPE_CHECKING"
                 for child in ast.walk(node)}
    for node in ast.walk(tree):
        if id(node) in type_only:
            continue
        if isinstance(node, ast.Import):
            yield from (alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                base = ".".join(package[:len(package) - node.level + 1] + ([node.module] if node.module else []))
            yield base
            yield from (f"{base}.{alias.name}" for alias in node.names)


def violations(source, forbidden):
    found = []
    for path in sorted(ROOT.rglob("*.py")):
        module = module_name(path)
        if "_scripts" in path.parts or not (module == source or module.startswith(source + ".")):
            continue
        found += [f"{module} -> {target}" for target in runtime_imports(path)
                  if target.startswith(forbidden) and not target.startswith(source)]
    return found


@pytest.mark.parametrize(("source", "forbidden"), FORBIDDEN)
def test_package_import_direction(source, forbidden):
    assert violations(source, forbidden) == []


def test_boundary_check_detects_function_level_imports():
    # EDA adapters intentionally use evaluation contracts, so the check must report them.
    assert any(item.startswith("benchmarking.eda.backends.")
               for item in violations("benchmarking.eda", "benchmarking.evaluation"))
