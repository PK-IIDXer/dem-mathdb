"""Offline lock tests use synthetic metadata; real wheel identity is checked in CI.

No runtime package is downloaded, installed, or imported from a wheel here.
"""
from email.message import Message
import copy
import importlib.util
import json
from pathlib import Path
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("target_lock", ROOT / "deploy/beta/lock_requirements.py")
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)


def synthetic_wheel(tmp_path, *, tag="cp313-cp313-manylinux_2_17_x86_64", metadata_name="uvloop"):
    path = tmp_path / f"uvloop-1.2.3-{tag}.whl"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("uvloop-1.2.3.dist-info/METADATA", (
            f"Metadata-Version: 2.4\nName: {metadata_name}\nVersion: 1.2.3\n"
            "Requires-Dist: click>=8\nLicense-Expression: MIT\nLicense-File: LICENSE\n\n"))
        archive.writestr("uvloop-1.2.3.dist-info/WHEEL", f"Wheel-Version: 1.0\nTag: {tag}\n\n")
    return path


def test_target_wheel_metadata_includes_identity_dependencies_license_and_provenance(tmp_path):
    wheel = synthetic_wheel(tmp_path)
    record = generator.read_wheel_metadata(wheel)
    assert record["name"] == "uvloop" and record["version"] == "1.2.3"
    assert record["requires_dist"] == ["click>=8"]
    assert record["license_expression"] == "MIT"
    assert record["license_files"] == ["LICENSE"]
    assert record["wheel"]["filename"] == wheel.name
    assert len(record["wheel"]["sha256"]) == 64


@pytest.mark.parametrize("tag", ["cp313-cp313-win_amd64", "cp312-cp312-manylinux_2_17_x86_64",
                                 "cp313-cp313-manylinux_2_17_aarch64"])
def test_reject_non_target_wheel(tmp_path, tag):
    with pytest.raises(ValueError, match="manylinux x86_64 cp313"):
        generator.read_wheel_metadata(synthetic_wheel(tmp_path, tag=tag))


def test_wheel_filename_cannot_disagree_with_metadata(tmp_path):
    with pytest.raises(ValueError, match="identity differ"):
        generator.read_wheel_metadata(synthetic_wheel(tmp_path, metadata_name="other"))


def test_wheel_and_installed_folded_metadata_have_identical_normalization(tmp_path):
    wheel = synthetic_wheel(tmp_path)
    raw = (b"Metadata-Version: 2.4\nName: uvloop\nVersion: 1.2.3\n"
           b"License: first line\n        second line\nRequires-Dist: click>=8;\n        python_version >= '3.0'\n\n")
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("uvloop-1.2.3.dist-info/METADATA", raw)
        archive.writestr("uvloop-1.2.3.dist-info/WHEEL", "Wheel-Version: 1.0\nTag: cp313-cp313-manylinux_2_17_x86_64\n\n")
    local = tmp_path / "installed.dist-info"
    local.mkdir()
    (local / "METADATA").write_bytes(raw)
    installed = generator.distribution_metadata(generator.PathDistribution(local))
    read = generator.read_wheel_metadata(wheel)
    assert installed == {key: value for key, value in read.items() if key != "wheel"}


class SyntheticDistribution:
    def __init__(self, name, version, requirements=(), license_expression=None, license_files=()):
        self.version, self.requires = version, list(requirements)
        self.metadata = Message()
        self.metadata["Name"], self.metadata["Version"] = name, version
        if license_expression:
            self.metadata["License-Expression"] = license_expression
        for filename in license_files:
            self.metadata["License-File"] = filename


@pytest.fixture
def closure_case(tmp_path, monkeypatch):
    """Synthetic target-only uvloop with a real dependency edge to click."""
    records = {
        "core": SyntheticDistribution("core", "1.2.3"),
        "server": SyntheticDistribution("server", "2.0", [
            'uvloop>=1; extra == "standard" and sys_platform == "linux"',
            'colorama; sys_platform == "win32"']),
        "psycopg": SyntheticDistribution("psycopg", "3.0", [
            'psycopg-binary==3.0; extra == "binary"', 'tzdata; sys_platform == "win32"']),
        "psycopg-binary": SyntheticDistribution("psycopg-binary", "3.0"),
        "click": SyntheticDistribution("click", "8.4.2"),
    }
    monkeypatch.setattr(generator, "project_requirements", lambda: {
        "dependencies": ["core>=1"], "optional-dependencies": {"webapi": ["server[standard]>=2"]}})
    row = generator.read_wheel_metadata(synthetic_wheel(tmp_path))
    pins = {name: value.version for name, value in records.items()} | {"uvloop": "1.2.3"}
    sidecar = {"schema_version": 1, "target_environment": generator.TARGET_ENVIRONMENT,
               "distributions": {"uvloop": row}}
    lock, metadata = tmp_path / "requirements.lock", tmp_path / "target.json"

    def install_branch(target):
        local = dict(records)
        if target:
            local["uvloop"] = SyntheticDistribution("uvloop", "1.2.3", ["click>=8"], "MIT", ["LICENSE"])

        def lookup(name):
            if name not in local:
                raise generator.PackageNotFoundError(name)
            return local[name]
        monkeypatch.setattr(generator, "distribution", lookup)
        environment = dict(generator.TARGET_ENVIRONMENT)
        if not target:
            environment.update(sys_platform="win32", os_name="nt", platform_system="Windows", platform_machine="AMD64")
        return environment

    def write(mutated_pins=None, mutated_sidecar=None):
        lock.write_text("".join(f"{name}=={version}\n" for name, version in sorted((pins if mutated_pins is None else mutated_pins).items())))
        metadata.write_text(json.dumps(sidecar if mutated_sidecar is None else mutated_sidecar))
    write()
    return pins, sidecar, lock, metadata, install_branch, write


@pytest.mark.parametrize("target", [False, True])
def test_full_closure_and_fallback_dependencies_are_checked_in_both_branches(closure_case, target):
    pins, _, lock, metadata, branch, _ = closure_case
    result = generator.verify_runtime_lock(lock, metadata, branch(target))
    assert result["versions"] == pins
    assert result["target_environment"] is target
    assert result["missing_local"] == ([] if target else ["uvloop"])


@pytest.mark.parametrize("target", [False, True])
@pytest.mark.parametrize("mutation", ["remove_uvloop", "add_colorama", "change_version", "change_target_version"])
def test_lock_mutations_fail_in_both_environment_branches(closure_case, target, mutation):
    pins, sidecar, lock, metadata, branch, write = closure_case
    pins, sidecar = dict(pins), copy.deepcopy(sidecar)
    if mutation == "remove_uvloop":
        del pins["uvloop"]
    elif mutation == "add_colorama":
        pins["colorama"] = "0.4.6"
    elif mutation == "change_version":
        pins["core"] = "9.9.9"
    else:
        sidecar["distributions"]["uvloop"]["version"] = "9.9.9"
    write(pins, sidecar)
    with pytest.raises(ValueError):
        generator.verify_runtime_lock(lock, metadata, branch(target))


def test_target_branch_never_falls_back_to_sidecar_for_missing_installation(closure_case):
    _, _, lock, metadata, branch, _ = closure_case
    branch(False)
    with pytest.raises(ValueError, match="Target environment is missing installed package: uvloop"):
        generator.verify_runtime_lock(lock, metadata, generator.TARGET_ENVIRONMENT)


@pytest.mark.parametrize("target", [False, True])
def test_target_metadata_dependencies_cannot_be_omitted(closure_case, target):
    pins, sidecar, lock, metadata, branch, write = closure_case
    sidecar = copy.deepcopy(sidecar)
    sidecar["distributions"]["uvloop"]["requires_dist"] = []
    write(pins, sidecar)
    with pytest.raises(ValueError):
        generator.verify_runtime_lock(lock, metadata, branch(target))


@pytest.mark.parametrize("marker", ['platform_release == "6.1"', 'platform_version != "unknown"'])
def test_unspecified_kernel_markers_are_rejected(marker):
    with pytest.raises(ValueError, match="unspecified target kernel"):
        generator.evaluate_marker(generator.Requirement(f"example; {marker}").marker, generator.TARGET_ENVIRONMENT, {""})


def test_target_contract_covers_all_marker_variables_and_matches_base_image():
    assert generator.TARGET_ENVIRONMENT.keys() == generator.default_environment().keys()
    source = (ROOT / "deploy/beta/api.Dockerfile").read_text()
    assert source.splitlines()[0] == "FROM " + generator.TARGET_BASE_IMAGE


def test_prepare_reports_missing_target_metadata_without_writing_lock(tmp_path, monkeypatch):
    original = (ROOT / "deploy/beta/requirements.lock").read_bytes()
    # Keep the old Windows closure as the explicit input to this regression,
    # even after the repository lock has been regenerated for Linux.
    previous = generator.read_lock(ROOT / "deploy/beta/requirements.lock")
    previous.pop("uvloop", None)
    previous.update(colorama="0.4.6", tzdata="2026.4")
    monkeypatch.setattr(generator, "read_lock", lambda path: dict(previous))
    real_distribution = generator.distribution

    def without_uvloop(name):
        if name == "uvloop":
            raise generator.PackageNotFoundError(name)
        return real_distribution(name)
    monkeypatch.setattr(generator, "distribution", without_uvloop)
    report = generator.prepare(tmp_path)
    assert report["status"] == "needs target wheels"
    assert report["closure_complete"] is False
    assert set(report["missing_target_packages"]) == {"uvloop"}
    assert report["proposed_delta"]["changed"] == []
    assert report["proposed_delta"]["removed"] == ["colorama", "tzdata"]
    assert (ROOT / "deploy/beta/requirements.lock").read_bytes() == original
