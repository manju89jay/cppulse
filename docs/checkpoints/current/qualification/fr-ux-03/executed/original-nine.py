"""Exercise the nine original installed working-directory predicates on finite fixtures."""
import hashlib
import json
import os
from pathlib import Path
import pwd
import shutil
import subprocess
import sys

out = Path(sys.argv[1])
root = Path("/workspace/work/attribution-epoch")
installed = Path(sys.argv[2]) / "installed"
prefix = root / "installed/native/cppulse-native-0.2.0.dev2-linux-x86_64"
console = installed / "bin/cppulse"
tmp = Path("/tmp")
slash = Path("/")
home = Path(pwd.getpwuid(os.getuid()).pw_dir)
assert home == Path.home() == Path("/home/agent") and not any(home.iterdir())
from cppulse import pipeline
from cppulse.run_store import RunStore
from cppulse.workflows import read_documents
import cppulse
assert Path(cppulse.__file__).resolve().is_relative_to(installed)
assert not any(name in os.environ for name in ("CPPULSE_ANALYZER", "CPPULSE_WORK_UNIT_NATIVE", "LD_LIBRARY_PATH", "LD_PRELOAD"))
assert os.environ["CPPULSE_NATIVE_PREFIX"] == str(prefix)
assert shutil.which("cppulse") == str(console)
commands = []


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write(path, value):
    with path.open("x", encoding="utf8") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")


def pins(folder):
    result = {}
    for path in folder.rglob("*"):
        assert not path.is_symlink(), path
        if path.is_file():
            result[path.relative_to(folder).as_posix()] = sha(path)
    return result


def run(name, cwd, argv, expected):
    command = [str(console), *map(str, argv)]
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True, timeout=180, check=False)
    (out / f"{name}.stdout").write_text(result.stdout)
    (out / f"{name}.stderr").write_text(result.stderr)
    row = {"label": name, "argv": command, "cwd": str(cwd), "actual_exit": result.returncode, "expected_exit": expected}
    write(out / f"{name}.command.json", row)
    commands.append(row)
    assert result.returncode == expected, (name, result.returncode, result.stderr[-2000:])
    return result.stdout


def relative(path):
    return str(path.relative_to(slash))


def fixture(name, header):
    project = out / name
    project.mkdir()
    source = project / "selected ; touch escape-sentinel ; #.cpp"
    source.write_text(f"#include <{header}>\nvoid plain() {{}}\n")
    argv = ["clang++", "-std=c++17", "-c", str(source)]
    write(project / "compile_commands.json", [{"directory": str(project), "file": str(source), "arguments": argv}])
    return project, source, argv


def analyze(name, cwd, project, source, original_argv, *, use_relative=False, legacy=False, expected=0):
    stored = out / f"{name} ; outputs #"
    work = out / f"{name} ; native #"
    path = relative if use_relative else str
    args = ["analyze", "--repo", path(project), "--output", path(stored), "--format", "json",
            "--profile", "default", "--no-history", "--execution", "legacy" if legacy else "bounded"]
    if not legacy:
        args += ["--jobs", "1", "--work-directory", path(work)]
    before = pins(project)
    response = json.loads(run(name, cwd, args, expected))
    snapshot = RunStore.open_existing(stored).open_run(response["run_id"], manifest_sha256=response["manifest_sha256"])
    snapshot.verify()
    assert set(item["path"] for item in snapshot.manifest["source"]["files"]) == {source.name}
    observed = {"status": snapshot.manifest["status"], "verification": snapshot.manifest["input_verification"]}
    assert observed["status"] == ("partial" if expected == 3 else "completed")
    assert observed["verification"] == ("verified" if expected == 0 and not legacy else "unverified")
    report = json.loads(snapshot.read_bytes("findings"))
    row, = report["metadata"]["analysis"]["files"]
    assert row["status"] == "analyzed" and row["error_count"] == 0
    risk = json.loads(snapshot.read_bytes("risk_scores"))
    if legacy:
        assert response["analysis_status"] == "completed"
        assert row["compile_context"] == "database"
        assert row["parse_arguments"] and row["working_directory"] == "/"
        assert report["metadata"]["file_count"] == 1
        assert snapshot.manifest["contexts"] == []
        assert snapshot.manifest["source"]["inventory_complete"] is False
        assert snapshot.read_json("normalized-risk")["health_score"]["overall"] is None
        assert {entry["id"] for entry in snapshot.manifest["artifacts"]} >= {
            "findings", "risk_scores", "git_metrics", "roadmap", "report-json"
        }
        assert json.loads(snapshot.read_bytes("git_metrics"))["metadata"]["history_status"] == "unavailable"
    if expected == 0 and not legacy:
        assert risk["health_score"]["status"] == "scored" and risk["health_score"]["overall"] == 100
    else:
        assert risk["health_score"]["overall"] is None and risk["health_score"]["status"] == "partial"
    if not legacy:
        request, = sorted(snapshot.path.glob("execution/units/*/attempt-0000/request.json"))
        facts = json.loads(request.read_bytes())
        assert facts["context"]["argv"] == original_argv
        assert facts["context"]["working_directory"] == str(project)
        assert facts["process_working_directory"] == str(project)
        assert facts["native"]["sha256"] == sha(prefix / "libexec/cppulse/cppulse-analyzer")
        observed["actual_request_sha256"] = sha(request)
        observed["original_argv"] = original_argv
    assert before == pins(project)
    assert all(not (parent / "escape-sentinel").exists() for parent in (project, tmp, slash))
    observed["selected_path"] = source.name
    observed["actual_parse_status"] = row["status"]
    observed["scoped_health"] = risk["health_score"]
    observed["manifest_sha256"] = snapshot.manifest_sha256
    observed["source_inputs"] = before
    write(out / f"{name}.readback.json", observed)
    return stored, snapshot


current_pipeline = Path("/workspace/work/git-scope-qualification/checkout/python/cppulse/pipeline.py")
assert sha(Path(pipeline.__file__)) == sha(current_pipeline)
project, source, argv = fixture("literal C++ ; root #", "__stddef_size_t.h")
unsupported, unsupported_source, unsupported_argv = fixture("unsupported preprocessor ; root #", "stddef.h")
doctor = json.loads(run("doctor-outside", tmp, ["doctor"], 0))
assert doctor["native"]["available"] and doctor["native"]["startup_exit"] == 0
assert Path(doctor["native"]["path"]).is_relative_to(prefix)
profile = json.loads(run("config-relative-outside", slash,
                         ["config", "--repo", relative(project), "--output", relative(out / "config sample")], 0))
assert profile["settings"]["profile"] == "default"
assert profile["repo"] == str(project)
assert profile["output"] == str(out / "config sample")
init_project = out / "init sample"
init_project.mkdir()
initialize = json.loads(run("init-outside", tmp, ["init", "--repo", init_project], 0))
assert Path(initialize["config"]).parent == init_project
assert Path(initialize["config"]).is_file()
absolute_store, absolute = analyze("absolute-from-tmp", tmp, project, source, argv)
relative_store, relative_snapshot = analyze("relative-from-root", slash, project, source, argv, use_relative=True)
absolute_documents = read_documents(absolute)
relative_documents = read_documents(relative_snapshot)
assert {row["aggregate"]["overall"] for row in absolute_documents["maintenance_health"]
        if not row["scorer"]["allow_inferred_parse"]} == {100}
assert {row["aggregate"]["overall"] for row in relative_documents["maintenance_health"]
        if not row["scorer"]["allow_inferred_parse"]} == {100}
assert absolute.manifest["source"] == relative_snapshot.manifest["source"]
for kind in ("html", "json"):
    path = out / f"snapshot report.{kind}"
    before = pins(absolute_store)
    run(f"report-{kind}", tmp, ["report", "--input", absolute_store, "--evidence",
                               "--run-id", absolute.run_id, "--manifest-sha256", absolute.manifest_sha256,
                               "--format", kind, "--output", path], 0)
    text = path.read_text()
    if kind == "json":
        data = json.loads(text)
        values = [json.loads(row["raw_json"]) for row in data["facts"] if row["kind"] == "maintenance_health"]
        assert all(row in values for row in absolute_documents["maintenance_health"])
    else:
        assert "Decl" in text and "Formula:" in text and "analyzed-kloc-context-v4" in text
    assert before == pins(absolute_store)
analyze("legacy-from-root", slash, project, source, argv, use_relative=True, legacy=True)
analyze("unsupported-from-tmp", tmp, unsupported, unsupported_source, unsupported_argv, expected=3)
assert len(commands) == 9
write(out / "receipt.json", {"commands": commands, "exact_nine_original_predicates": True,
      "installed_console_sha256": sha(console), "proof_native_prefix": str(prefix), "outside_home": str(home)})
