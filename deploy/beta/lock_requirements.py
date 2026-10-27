"""Generate the Linux x86_64 CPython beta closure offline from local metadata.

Use --prepare-only before obtaining target-only wheels. This never installs or
downloads packages. The deployment keeps --loop asyncio even when uvloop is in
the uvicorn[standard] dependency closure.
"""
import argparse
from importlib.metadata import distribution, PackageNotFoundError, PathDistribution
from email.parser import BytesParser
from email.policy import default as email_policy
import hashlib
import json
from pathlib import Path
import re
import tomllib
import zipfile

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.utils import parse_wheel_filename

ROOT = Path(__file__).resolve().parents[2]
TARGET_ENVIRONMENT = {
    "implementation_name": "cpython", "implementation_version": "3.13.7",
    "os_name": "posix", "platform_machine": "x86_64",
    "platform_python_implementation": "CPython", "platform_release": "",
    "platform_system": "Linux", "platform_version": "",
    "python_full_version": "3.13.7", "python_version": "3.13", "sys_platform": "linux",
}
TARGET_BASE_IMAGE = f"python:{TARGET_ENVIRONMENT['python_full_version']}-slim-bookworm"
# A Docker tag does not fix the host kernel. Normalize these two variables on
# both sides, and reject any dependency that needs their unknown target values.
UNSPECIFIED_KERNEL_MARKERS = {"platform_release", "platform_version"}


def environment_matches_target(environment=None):
    actual = dict(default_environment() if environment is None else environment)
    if actual.keys() != TARGET_ENVIRONMENT.keys():
        raise ValueError("Marker variable set differs from the deployment contract")
    for name in UNSPECIFIED_KERNEL_MARKERS:
        actual[name] = ""
    return actual == TARGET_ENVIRONMENT


def evaluate_marker(marker, environment, extras):
    if marker is None:
        return True
    if re.search(r"\b(platform_release|platform_version)\b", str(marker)):
        raise ValueError(f"Dependency needs an unspecified target kernel marker: {marker}")
    return any(marker.evaluate(dict(environment, extra=extra)) for extra in extras)


def distribution_metadata(installed):
    return {
        "name": canonicalize_name(installed.metadata["Name"]),
        "version": installed.version,
        "requires_dist": [re.sub(r"\s*\n\s*", " ", value) for value in installed.requires or []],
        "license_expression": installed.metadata.get("License-Expression"),
        "license": installed.metadata.get("License"),
        "license_classifiers": [value for value in installed.metadata.get_all("Classifier", [])
                                if value.startswith("License ::")],
        "license_files": list(installed.metadata.get_all("License-File", [])),
    }


def target_wheel_tags(filename):
    name, version, _, tags = parse_wheel_filename(filename)
    compatible = {tag for tag in tags if tag.interpreter == "cp313" and tag.abi == "cp313"
                  and tag.platform.startswith("manylinux") and tag.platform.endswith("_x86_64")}
    if not compatible:
        raise ValueError(f"Expected a manylinux x86_64 cp313 wheel: {filename}")
    return canonicalize_name(name), str(version), compatible


def read_wheel_metadata(path):
    """Read a local target wheel without extracting or installing any code."""
    name, version, tags = target_wheel_tags(path.name)
    with zipfile.ZipFile(path) as archive:
        metadata_files = [entry for entry in archive.namelist() if entry.endswith(".dist-info/METADATA")]
        if len(metadata_files) != 1:
            raise ValueError(f"Expected one METADATA file: {path.name}")
        member = metadata_files[0]
        # Use importlib's public metadata reader on the zip path, just as for
        # an installed distribution (including folded-header normalization).
        installed = PathDistribution(zipfile.Path(archive, member.rsplit('/', 1)[0] + '/'))
        result = distribution_metadata(installed)
        if result["name"] != name or result["version"] != version:
            raise ValueError(f"Wheel filename and METADATA identity differ: {path.name}")
        wheel = BytesParser(policy=email_policy).parsebytes(archive.read(member.rsplit('/', 1)[0] + '/WHEEL'))
        if not {str(tag) for tag in tags} & set(wheel.get_all("Tag", [])):
            raise ValueError(f"Wheel filename and WHEEL tags differ: {path.name}")
    for value in result["requires_dist"]:
        Requirement(value)
    result["wheel"] = {"filename": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    return result


def wheel_metadata_for(name, directory):
    candidates = []
    for path in sorted(directory.glob("*.whl")):
        candidate_name, _, _, _ = parse_wheel_filename(path.name)
        if canonicalize_name(candidate_name) == name:
            target_wheel_tags(path.name)
            candidates.append(path)
    if len(candidates) > 1:
        raise ValueError(f"Ambiguous target wheels for {name}: {[path.name for path in candidates]}")
    return read_wheel_metadata(candidates[0]) if candidates else None


def dependency_closure(project, read_metadata, environment):
    """Return the target closure and every unresolved package without guessing."""
    pending = [Requirement(value) for value in (
        project["dependencies"] + project["optional-dependencies"]["webapi"] + ["psycopg[binary]"])]
    visited, versions, records, missing = set(), {}, {}, {}
    while pending:
        requirement = pending.pop()
        if not evaluate_marker(requirement.marker, environment, {""}):
            continue
        name = canonicalize_name(requirement.name)
        record = read_metadata(name)
        if record is None:
            missing.setdefault(name, set()).add(str(requirement))
            continue
        if record["name"] != name or not requirement.specifier.contains(record["version"], prereleases=True):
            raise ValueError(f"Metadata does not satisfy {requirement}")
        versions[name], records[name] = record["version"], record
        extras = frozenset(requirement.extras)
        if (name, extras) in visited:
            continue
        visited.add((name, extras))
        for value in record["requires_dist"]:
            dependency = Requirement(value)
            if not evaluate_marker(dependency.marker, environment, extras | {""}):
                continue
            dependency.marker = None
            pending.append(dependency)
    return {"versions": dict(sorted(versions.items())), "records": records,
            "missing": {name: sorted(values) for name, values in sorted(missing.items())}}


def project_requirements():
    return tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]


def read_lock(path):
    versions = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not re.fullmatch(r"[a-z0-9-]+==[^=\s]+", line):
            raise ValueError(f"Invalid exact lock entry: {line}")
        name, version = line.split("==")
        if canonicalize_name(name) != name or name in versions:
            raise ValueError(f"Invalid or duplicate lock name: {name}")
        versions[name] = version
    return versions


def prepare(wheel_directory=None):
    directory = ROOT / "work/beta/wheels" if wheel_directory is None else wheel_directory

    def load(name):
        wheel = wheel_metadata_for(name, directory)
        try:
            installed = distribution_metadata(distribution(name))
        except PackageNotFoundError:
            return wheel
        if wheel is not None:
            if installed != {key: value for key, value in wheel.items() if key != "wheel"}:
                raise ValueError(f"Supplied wheel differs from installed metadata: {name}")
            return wheel
        return installed

    result = dependency_closure(project_requirements(), load, TARGET_ENVIRONMENT)
    previous = read_lock(Path(__file__).with_name("requirements.lock"))
    common = previous.keys() & result["versions"].keys()
    changed = {name for name in common if previous[name] != result["versions"][name]}
    added = result["versions"].keys() - previous.keys()
    removed = previous.keys() - result["versions"].keys()
    # Missing metadata makes the closure incomplete. Refuse any unknown change
    # even before writing, then repeat this check once every wheel is available.
    if changed or added - {"uvloop"} or removed - {"colorama", "tzdata"} - result["missing"].keys():
        raise ValueError(f"Unexpected runtime delta: changed={sorted(changed)}, added={sorted(added)}, removed={sorted(removed)}")
    result.update(status="needs target wheels" if result["missing"] else "ready",
                  target_environment=TARGET_ENVIRONMENT, base_image=TARGET_BASE_IMAGE,
                  wheel_directory=str(directory.resolve()),
                  missing_target_packages=result["missing"],
                  proposed_delta={"added": sorted(added), "removed": sorted(removed), "changed": sorted(changed)},
                  closure_complete=not result["missing"])
    return result


def runtime_versions():
    result = prepare()
    if result["missing"]:
        raise ValueError(f"Missing target metadata: {', '.join(result['missing'])}")
    return result["versions"]


def verify_runtime_lock(lock_path=None, metadata_path=None, actual_environment=None):
    """Check the whole target closure, never a Windows-only subset.

    Off target, local metadata and the generated sidecar check all available
    facts. The wheel's authenticity and its match to the installed target
    distribution must be confirmed in the deployment environment (CI).
    """
    directory = Path(__file__).parent
    pins = read_lock(directory / "requirements.lock" if lock_path is None else lock_path)
    sidecar = json.loads((directory / "requirements.target-metadata.json" if metadata_path is None else metadata_path).read_text(encoding="utf-8"))
    if sidecar["schema_version"] != 1 or sidecar["target_environment"] != TARGET_ENVIRONMENT:
        raise ValueError("Target metadata environment differs from deployment")
    rows = sidecar["distributions"]
    target = environment_matches_target(actual_environment)
    missing_local = set()
    for name, row in rows.items():
        wheel_name, wheel_version, _ = target_wheel_tags(row["wheel"]["filename"])
        if (name != row["name"] or wheel_name != name or wheel_version != row["version"]
                or not re.fullmatch(r"[0-9a-f]{64}", row["wheel"]["sha256"])):
            raise ValueError(f"Invalid wheel metadata identity: {name}")

    def load(name):
        try:
            record = distribution_metadata(distribution(name))
        except PackageNotFoundError:
            if target:
                raise ValueError(f"Target environment is missing installed package: {name}")
            missing_local.add(name)
            return rows.get(name)
        if name in rows and record != {key: value for key, value in rows[name].items() if key != "wheel"}:
            raise ValueError(f"Target wheel metadata differs from installed distribution: {name}")
        return record

    closure = dependency_closure(project_requirements(), load, TARGET_ENVIRONMENT)
    if closure["missing"]:
        raise ValueError(f"Missing local and target metadata: {sorted(closure['missing'])}")
    if closure["versions"] != pins:
        raise ValueError("Runtime lock does not exactly match target closure and installed versions")
    if not rows.keys() <= closure["versions"].keys() or not missing_local <= rows.keys():
        raise ValueError("Target metadata is not exactly accounted for in the closure")
    return {"target_environment": target, "missing_local": sorted(missing_local), "versions": closure["versions"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--wheel-directory", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = prepare(args.wheel_directory)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "records"}, indent=2))
    if result["missing"]:
        raise SystemExit(2)
    if not args.prepare_only:
        directory = Path(__file__).parent
        sidecar = {"schema_version": 1, "target_environment": TARGET_ENVIRONMENT,
                   "distributions": {name: row for name, row in result["records"].items() if "wheel" in row}}
        (directory / "requirements.target-metadata.json").write_text(json.dumps(sidecar, indent=2) + "\n", encoding="utf-8")
        (directory / "requirements.lock").write_text("".join(f"{name}=={version}\n" for name, version in result["versions"].items()), encoding="utf-8")


if __name__ == "__main__":
    main()
