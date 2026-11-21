"""Check the d65 decision and maintenance record using local, read-only Git."""

from collections import Counter
from hashlib import file_digest, sha256
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from urllib.parse import urlsplit


LANE = Path(__file__).resolve().parent
WAVE = LANE.parent
WORK = WAVE.parent
CHECKOUT = WAVE / "checkout"
RECEIVING = Path("/workspace/cppulse")
ALTERNATE = RECEIVING / ".git/objects"
PYTHON = Path("/usr/bin/python3.13")
GIT = Path("/usr/bin/git")
NEW_TREE = "d65b9d69ef1ba5236af060c4b07b797b81d8ad1f"
PRIOR_TREE = "4cf0194a3313412511a688e5924f7bb28939d94d"
FIRST_PARENT = "d1e598028aec76f6455a7ed45602945274b72f8d"
NOMINATED = "82120d26b51f99b64068f9d66f6e000fcaee97c2"
TRACKING_TIP = "95966ee97db711b4a65c6f08d60a24abe93a6c71"
TRACKING_REF = "refs/remotes/origin/feat/health-score-v2"
DEFINITION = "e57e89fb7db188f1f4805b95c0bc6f2896c7ab9eef15d851723cc422a0bd2381"
LEDGER = "docs/plans/production-delivery-ledger.json"
DECISIONS = "docs/DECISIONS.md"
AUTHORITY = "docs/plans/production-scope-authority.md"
PLAN_TOOL = "docs/plans/verify_production_plan.py"
STRICT_TOOL = "scripts/verify_delivery.py"
ORIGINAL_SPEC = "docs/specs/production-platform"
PRESERVED = (
    "TASK_SPEC.md", f"{ORIGINAL_SPEC}/requirements.md", f"{ORIGINAL_SPEC}/tasks.md",
    f"{ORIGINAL_SPEC}/design.md", "docs/plans/cppulse-production-completion-plan.md",
    LEDGER, "docs/plans/production-completion-traceability.json", STRICT_TOOL,
)
SUPPORT = (
    PLAN_TOOL, DECISIONS, AUTHORITY, "AGENTS.md", "analyzer-core/CMakeLists.txt",
    ".clang-format", ".claude/rules/cpp-style.md", ".claude/rules/safety-critical.md",
    "python/cppulse/predictor/roadmap_generator.py", "tests/test_roadmap_order.py",
)
IDENTIFIER = r"D\d+|PROD-\d{8}-\d+"
HEADING = re.compile(rf"^## ({IDENTIFIER})(?:: | — )(.+)$", re.M)
INDEX = re.compile(rf"(?:\|\s|`)({IDENTIFIER})(?:\s\||`)")
TABLE = re.compile(rf"^\| ({IDENTIFIER}) \| [^|]+ \| (.+) \|$", re.M)
STATE_COUNTS = {"verified": 38, "open": 96, "active": 51, "blocked": 2}
BASE_ENV = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8"}
GIT_ENV = dict(
    BASE_ENV, GIT_CONFIG_GLOBAL="/dev/null", GIT_CONFIG_NOSYSTEM="1",
    GIT_OPTIONAL_LOCKS="0", GIT_NO_LAZY_FETCH="1", GIT_ALLOW_PROTOCOL="",
)


def digest(path):
    assert path.is_file() and not path.is_symlink(), path
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def digest_body(body):
    return sha256(body).hexdigest()


def read_json(path):
    return json.loads(path.read_bytes())


def write_json(path, body):
    with path.open("x", encoding="utf-8") as stream:
        json.dump(body, stream, indent=2, sort_keys=True)
        stream.write("\n")


def git(repo, *args, alternate=False, expected=0):
    env = {**GIT_ENV, "GIT_ALTERNATE_OBJECT_DIRECTORIES": str(ALTERNATE)} if alternate else GIT_ENV
    result = subprocess.run([str(GIT), "-C", str(repo), *args], env=env,
                            capture_output=True, check=False, timeout=15)
    assert result.returncode == expected, (result.args, result.returncode, result.stderr)
    return result


def blob(tree, path):
    return git(CHECKOUT, "show", f"{tree}:{path}", alternate=tree == FIRST_PARENT).stdout


def records(body):
    return [row.split(b"\t", 1) for row in body.split(b"\0") if row]


def checkout_readback():
    tree = records(git(CHECKOUT, "ls-tree", "-r", "-z", NEW_TREE).stdout)
    index = records(git(CHECKOUT, "ls-files", "--stage", "-z").stdout)
    normalized = []
    for attrs, path in tree:
        mode, kind, name = attrs.split()
        assert kind == b"blob" and mode in {b"100644", b"100755"}
        normalized.append([b" ".join((mode, name, b"0")), path])
    assert normalized == index and len(tree) == 1396
    assert not git(CHECKOUT, "diff", "--no-ext-diff", "--no-textconv", "--name-only", "-z", NEW_TREE).stdout
    assert not git(CHECKOUT, "ls-files", "--others", "--exclude-standard", "-z").stdout
    return {"tree": NEW_TREE, "tracked_paths": len(tree),
            "exact_index_sha256": digest_body(git(CHECKOUT, "ls-files", "--stage", "-z").stdout)}


def object_view():
    objects = git(RECEIVING, "rev-parse", "--path-format=absolute", "--git-path", "objects").stdout
    assert Path(os.fsdecode(objects.strip())) == ALTERNATE and ALTERNATE.is_dir()
    missing = git(CHECKOUT, "cat-file", "-t", NOMINATED, expected=128)
    absent = git(CHECKOUT, "show-ref", "--verify", "--quiet", TRACKING_REF, alternate=True, expected=1)
    received = git(RECEIVING, "show-ref", "--verify", TRACKING_REF)
    tip, name = received.stdout.decode().split()
    assert (tip, name) == (TRACKING_TIP, TRACKING_REF)
    supplied = git(CHECKOUT, "cat-file", "commit", NOMINATED, alternate=True).stdout
    original = git(RECEIVING, "cat-file", "commit", NOMINATED).stdout
    assert supplied == original
    parents = re.findall(rb"^parent ([0-9a-f]{40})$", original.split(b"\n\n", 1)[0], re.M)
    assert [p.decode() for p in parents] == ["8bb02b04f4a387ef840f5205b76a4b25a06dac49", TRACKING_TIP]
    tracking = git(RECEIVING, "cat-file", "commit", TRACKING_TIP).stdout
    assert tracking == git(CHECKOUT, "cat-file", "commit", TRACKING_TIP, alternate=True).stdout
    return {
        "checkout_without_alternate_nominated_exit": missing.returncode,
        "read_only_alternate_object_directory": str(ALTERNATE),
        "nominated_merge": NOMINATED, "nominated_commit_body_sha256": digest_body(original),
        "nominated_merge_parents": [p.decode() for p in parents],
        "isolated_tracking_ref_exit": absent.returncode, "receiving_tracking_ref_exit": received.returncode,
        "receiving_tracking_ref": name, "receiving_tracking_tip": tip,
        "receiving_tracking_commit_body_sha256": digest_body(tracking),
        "relationship": "The receiving tracking tip is parent two of the nominated merge commit.",
    }


def verify_links(authority):
    links = re.findall(r"\[[^\]]+\]\(([^)]*)\)", authority)
    assert len(links) == 8
    for link in links:
        link = urlsplit(link)
        target = (CHECKOUT / AUTHORITY).parent / link.path
        assert not (link.scheme or link.netloc or link.query) and target.resolve().is_relative_to(CHECKOUT)
        assert target.is_file() and not target.is_symlink()
        if link.fragment:
            slugs = [re.sub(r"[^\w -]", "", row.lower()).replace(" ", "-")
                     for row in re.findall(r"^#+ (.+)$", target.read_text(encoding="utf-8"), re.M)]
            assert link.fragment in slugs, link.fragment
    return links


def scope_readback():
    hashes = {}
    for name in (*PRESERVED, *SUPPORT):
        path = CHECKOUT / name
        assert path.read_bytes() == blob(NEW_TREE, name)
        hashes[name] = digest(path)
    for name in PRESERVED:
        assert (CHECKOUT / name).read_bytes() == blob(PRIOR_TREE, name) == blob(FIRST_PARENT, name)
    for name in ("requirements", "design", "tasks"):
        assert re.search(r"^Status: Proposed\b", (CHECKOUT / ORIGINAL_SPEC / f"{name}.md").read_text(), re.M)
    ledger = read_json(CHECKOUT / LEDGER)
    rows = ledger["items"]
    assert len(rows) == len({r["id"] for r in rows}) == 187
    assert Counter(r["state"] for r in rows) == STATE_COUNTS
    phase_ids = [p["id"] for p in ledger["phases"]]
    assert len(phase_ids) == 15 and set(phase_ids) == {f"P{i}" for i in range(15)}
    assert DEFINITION.encode() in (CHECKOUT / LEDGER).read_bytes()

    decisions = (CHECKOUT / DECISIONS).read_bytes()
    prior, first_parent = [blob(tree, DECISIONS) for tree in (PRIOR_TREE, FIRST_PARENT)]
    assert decisions.startswith(prior) and prior.startswith(first_parent)
    current = dict(HEADING.findall(decisions.decode()))
    names = [name for name, _ in HEADING.findall(decisions.decode())]
    current_prior = [name for name, _ in HEADING.findall(prior.decode())]
    assert len(current) == len(names) == 100 and len(current_prior) == 99
    assert names == [*current_prior, "PROD-20261121-33"]
    assert len(HEADING.findall(first_parent.decode())) == 95
    append = decisions[len(prior):].decode()
    for field in ("Context", "Decision", "Why", "Tradeoffs", "Verification", "Interview angle"):
        assert f"**{field}**." in append
    assert "Qualification is pending." in append
    assert "file path and then category" in append

    authority = (CHECKOUT / AUTHORITY).read_text(encoding="utf-8")
    assert INDEX.findall(authority) == names
    indexed_titles = TABLE.findall(authority)
    assert indexed_titles and all(title == current[name] for name, title in indexed_titles)
    links = verify_links(authority)
    for text in (
        "historical six-component MVP", "“Proposed” headers", "C++ is the first supported analyzed language",
        "formatting source of truth", "preserve meaningful failures", "one heavyweight job",
        "4 GiB disk reserve", "one independent read-only batch reviewer", "exit 2 is an invalid or stale",
        "Exit 3 means valid evidence", "Full-program completion requires exit 0",
        "The object and reference observations in batch111 apply to its originating",
        "remaining M0-01 history requirements open", NOMINATED, TRACKING_REF,
    ):
        assert " ".join(text.split()).casefold() in " ".join(authority.split()).casefold(), text
    assert "CMAKE_CXX_STANDARD 17" in (CHECKOUT / "analyzer-core/CMakeLists.txt").read_text()
    style = (CHECKOUT / ".clang-format").read_text()
    assert all(text in style for text in ("BasedOnStyle: Google", "IndentWidth: 4", "ColumnLimit: 100"))
    return {
        "source_sha256": hashes, "decision_headings": names,
        "prior_decision_prefix_sha256": digest_body(prior), "first_parent_decision_prefix_sha256": digest_body(first_parent),
        "decision_append_sha256": digest_body(decisions[len(prior):]), "index_table_title_count": len(indexed_titles),
        "resolved_local_reference_count": len(links), "phase_ids": phase_ids, "states": STATE_COUNTS,
        "canonical_definition_sha256": DEFINITION, "records": len(rows),
    }


def snapshot():
    return {"checkout": checkout_readback(), "scope": scope_readback(), "object_view": object_view()}


def registered_paths():
    previous = WORK / "governance-qualification/work-checks"
    public = WORK / "fr-git-01-public-stage/checkout/docs/checkpoints/current/qualification/nfr-mnt-08"
    owner = WAVE / "owner-review"
    return [
        Path(__file__), LANE / "launch.sh", LANE / "scope.md", GIT, PYTHON,
        *(CHECKOUT / name for name in (*PRESERVED, *SUPPORT)),
        previous / "independent-whole-review.json", previous / "results/governance.json",
        public / "NFR-MNT-08.structured-log.json", public / "NFR-MNT-08.proof.json",
        owner / "final-literals.json", owner / "source-delta.json",
        owner / "d65-plan-scope/plan.exit", owner / "d65-plan-scope/plan.stdout",
        owner / "isolated-d65-bare-strict.exit", owner / "isolated-d65-bare-strict.log",
    ]


def input_pins():
    return {str(path): digest(path) for path in sorted(registered_paths())}


def register():
    write_json(LANE / "lane-inputs.json", {
        "criterion": "NFR-MNT-08", "source_tree": NEW_TREE,
        "source_and_object_view": snapshot(), "file_sha256": input_pins(),
    })


def command(out, label, script, *arguments):
    argv = [str(PYTHON), "-I", "-B", str(CHECKOUT / script), *map(str, arguments)]
    result = subprocess.run(argv, cwd=CHECKOUT, env=BASE_ENV, capture_output=True, check=False, timeout=30)
    (out / f"{label}.stdout").write_bytes(result.stdout)
    (out / f"{label}.stderr").write_bytes(result.stderr)
    write_json(out / f"{label}.command.json", {
        "argv": argv, "cwd": str(CHECKOUT), "actual_exit": result.returncode,
        "stdout_sha256": digest_body(result.stdout), "stderr_sha256": digest_body(result.stderr),
    })
    return result


def run(out):
    manifest = LANE / "lane-inputs.json"
    prereg = read_json(manifest)
    manifest_sha = digest(manifest)
    assert prereg["source_tree"] == NEW_TREE and prereg["file_sha256"] == input_pins()
    before = snapshot()
    assert before == prereg["source_and_object_view"]
    write_json(out / "source-and-object-before.json", before)
    plan = command(out, "plan", PLAN_TOOL)
    strict_report = out / "strict-result.json"
    strict = command(out, "strict", STRICT_TOOL, "--require-complete", "--output", strict_report)
    after = snapshot()
    write_json(out / "source-and-object-after.json", after)
    assert before == after and digest(manifest) == manifest_sha and prereg["file_sha256"] == input_pins()
    assert plan.returncode == 0 and strict.returncode == 2
    plan_data, strict_data = json.loads(plan.stdout), json.loads(strict.stdout)
    assert plan_data == {"status": "passed", "numbered_requirements": 118, "milestone_tasks": 60,
                         "supplemental_obligations": 9, "unassigned_or_missing": 0,
                         "scope": "Planning traceability only; not product completion or new test results"}
    expected_path = CHECKOUT / "work/coverage-t123/current38-source-proof.json"
    assert not expected_path.exists() and not strict_report.exists()
    assert strict_data["status"] == "invalid" and str(expected_path) in strict_data["reason"]
    write_json(out / "qualification.json", {
        "criterion": prereg["criterion"], "source_tree": NEW_TREE,
        "registration_sha256": manifest_sha, "stable_registered_files": len(prereg["file_sha256"]),
        "identical_source_index_and_object_views": True,
        "actual_plan_exit": plan.returncode, "actual_strict_exit": strict.returncode,
        "plan_result": plan_data, "strict_result": strict_data, "decision_index_count": 100,
        "scope": "Code-owned decisions, upkeep instructions and plan authority with local object provenance.",
    })


if __name__ == "__main__":
    if sys.argv[1:] == ["register"]:
        register()
    else:
        assert len(sys.argv) == 3 and sys.argv[1] == "run" and not sys.flags.optimize
        run(Path(sys.argv[2]))
