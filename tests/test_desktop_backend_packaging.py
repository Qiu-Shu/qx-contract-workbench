"""Execute the backend spec without building or downloading a frozen application."""

import importlib.metadata
from pathlib import Path
import runpy
import ssl
import sys
from types import ModuleType, SimpleNamespace

import pytest


@pytest.mark.parametrize("has_policy", [True, False], ids=["bundled-python", "ordinary-python"])
def test_frozen_backend_preserves_build_python_ssl_policy(tmp_path, monkeypatch, has_policy):
    runtime = tmp_path / "build-python" / "Lib"
    runtime.mkdir(parents=True)
    monkeypatch.setattr(ssl, "__file__", str(runtime / "ssl.py"))
    policy = runtime / "codex-rejected-cas.pem"
    policy_bytes = b"# synthetic rejected-root policy\r\n\x00fixture\xff\n"
    if has_policy:
        policy.write_bytes(policy_bytes)

    # The active ssl module, rather than a guessed Python prefix, owns this resource.
    other_runtime = tmp_path / "other-python"
    other_runtime.mkdir()
    (other_runtime / policy.name).write_bytes(b"unrelated policy")
    monkeypatch.setattr(sys, "base_prefix", str(other_runtime))
    monkeypatch.setattr(importlib.metadata, "distributions", lambda: [])
    hooks = ModuleType("PyInstaller.utils.hooks")
    hooks.collect_data_files = lambda package: []
    hooks.collect_submodules = lambda package: []
    for name in ("PyInstaller", "PyInstaller.utils"):
        monkeypatch.setitem(sys.modules, name, ModuleType(name))
    monkeypatch.setitem(sys.modules, hooks.__name__, hooks)

    def analysis(scripts, **options):
        return SimpleNamespace(pure=[], scripts=scripts, binaries=[], datas=options["datas"])

    spec = Path(__file__).resolve().parents[1] / "desktop" / "backend.spec"
    result = runpy.run_path(str(spec), init_globals={
        "SPECPATH": str(spec.parent),
        "Analysis": analysis,
        "PYZ": lambda pure: pure,
        "EXE": lambda *args, **kwargs: None,
        "COLLECT": lambda exe, binaries, datas, **kwargs: datas,
    })
    assets = [(Path(source), target) for source, target in result["coll"]
              if Path(source).name == policy.name]
    assert assets == ([(policy, ".")] if has_policy else [])
    if has_policy:
        # These are the actual spec-generated input and destination passed to COLLECT.
        source, destination = assets[0]
        bundle = tmp_path / "bundle" / destination
        bundle.mkdir(parents=True)
        packaged = bundle / source.name
        packaged.write_bytes(source.read_bytes())
        assert packaged.relative_to(tmp_path / "bundle") == Path("codex-rejected-cas.pem")
        assert packaged.read_bytes() == policy_bytes
