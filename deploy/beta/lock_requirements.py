"""Generate the tested runtime closure, without resolving or installing packages.

Run with the test interpreter: python deploy/beta/lock_requirements.py
Markers are evaluated on the tested platform. Docker deliberately installs this
same set without dependency resolution and uses asyncio (no untested uvloop).
"""
from importlib.metadata import distribution
from pathlib import Path
import tomllib

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name


def runtime_versions():
    root = Path(__file__).resolve().parents[2]
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    pending = [Requirement(value) for value in (
        project["dependencies"] + project["optional-dependencies"]["webapi"] + ["psycopg[binary]"]
    )]
    environment = default_environment()
    visited, versions = set(), {}
    while pending:
        requirement = pending.pop()
        if requirement.marker and not requirement.marker.evaluate(dict(environment, extra="")):
            continue
        name = canonicalize_name(requirement.name)
        installed = distribution(name)
        if not requirement.specifier.contains(installed.version, prereleases=True):
            raise ValueError(f"installed runtime dependency does not satisfy {name}")
        versions[name] = installed.version
        extras = frozenset(requirement.extras)
        key = name, extras
        if key in visited:
            continue
        visited.add(key)
        for value in installed.requires or []:
            dependency = Requirement(value)
            if dependency.marker and not any(dependency.marker.evaluate(dict(environment, extra=extra))
                                             for extra in extras | {""}):
                continue
            # The selected marker was already evaluated in the parent's extras.
            dependency.marker = None
            pending.append(dependency)
    return dict(sorted(versions.items()))


def lock_text():
    return "".join(f"{name}=={version}\n" for name, version in runtime_versions().items())


if __name__ == "__main__":
    Path(__file__).with_name("requirements.lock").write_text(lock_text(), encoding="utf-8")
