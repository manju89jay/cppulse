"""Complete private generated examples; never register examples in the product.

Run directly against an installed package as well as through pytest. These are
synthetic extension-development fixtures, not producer/platform qualification.
Every untouched stub is exercised before its reviewed example is implemented.
"""

from __future__ import annotations

from copy import deepcopy
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from cppulse.contracts import validate
from cppulse.native_rule_generator import native_rule_headers
from cppulse.policy import evaluate_policy
from cppulse.tooling import load_rule_registry, scaffold

ROOT = Path(__file__).resolve().parents[1]


def clang_toolchain() -> tuple[Path, Path]:
    """Use declared installed inputs or an actual system LLVM development kit."""
    include = os.environ.get("CPPULSE_EXTENSION_CLANG_INCLUDE")
    library = os.environ.get("CPPULSE_EXTENSION_LIBCLANG")
    if include or library:
        if not (include and library):
            raise RuntimeError("Declare both the libclang include and library inputs")
        selected = Path(include), Path(library)
        if (selected[0] / "clang-c/Index.h").is_file() and selected[1].is_file():
            return selected
        raise RuntimeError("Declared libclang development inputs are unavailable")
    for prefix in sorted(Path("/usr/lib").glob("llvm-*"), reverse=True):
        headers, shared = prefix / "include", prefix / "lib/libclang.so"
        if (headers / "clang-c/Index.h").is_file() and shared.is_file():
            return headers, shared
    raise RuntimeError(
        "A real LLVM development kit is required; declare its include and library inputs"
    )


RULE_IMPLEMENTATION = r"""#include "rules/forbid_gets.h"
void cppulse::ForbidGetsRule::check_impl(CXCursor cursor, const std::string& path) {
  if (clang_getCursorKind(cursor) != CXCursor_CallExpr) return;
  auto referenced = clang_getCursorReferenced(cursor);
  if (clang_getCursorKind(referenced) != CXCursor_FunctionDecl) return;
  auto spelling = clang_getCursorSpelling(referenced);
  std::string name = clang_getCString(spelling);
  clang_disposeString(spelling);
  if (name != "gets") return;
  unsigned line = 0, column = 0;
  clang_getSpellingLocation(clang_getCursorLocation(cursor), nullptr, &line, &column, nullptr);
  Finding f;
  f.rule_id = std::string(rule_id()); f.category = std::string(category());
  f.severity = "warning"; f.file = path; f.line = line; f.column = column;
  f.message = "Direct gets call in the private extension fixture";
  f.suggestion = "Use a bounded input operation";
  add_finding(std::move(f));
}
"""

RULE_RUNNER = r"""#include "generated_rule_registration.h"
#include <iostream>
struct State { cppulse::ForbidGetsRule rule; std::string path; };
CXChildVisitResult visit(CXCursor cursor, CXCursor, CXClientData data) {
  auto& state = *static_cast<State*>(data);
  state.rule.check(cursor, state.path);
  return CXChildVisit_Recurse;
}
int main(int argc, char** argv) {
  if (argc != 2) return 2;
  State state; state.path = argv[1];
  cppulse::register_generated_native_rules(
    [&](auto rule, bool enabled) { if (!enabled) throw std::runtime_error("disabled"); state.rule = std::move(rule); },
    [](auto&) {});
  auto index = clang_createIndex(0, 0);
  const char* arguments[] = {"-std=c++17"};
  auto tu = clang_parseTranslationUnit(index, argv[1], arguments, 1, nullptr, 0, CXTranslationUnit_None);
  if (!tu) return 3;
  for (unsigned i = 0; i < clang_getNumDiagnostics(tu); ++i) {
    auto diagnostic = clang_getDiagnostic(tu, i);
    auto severity = clang_getDiagnosticSeverity(diagnostic);
    clang_disposeDiagnostic(diagnostic);
    if (severity >= CXDiagnostic_Error) return 4;
  }
  try {
    // Fail the untouched draft outside a C callback, without crossing C frames.
    state.rule.check(clang_getTranslationUnitCursor(tu), state.path);
    clang_visitChildren(clang_getTranslationUnitCursor(tu), visit, &state);
  } catch (const std::logic_error& error) {
    std::cerr << error.what() << '\n';
    clang_disposeTranslationUnit(tu); clang_disposeIndex(index); return 42;
  }
  for (const auto& f : state.rule.findings())
    std::cout << f.rule_id << ' ' << f.line << ' ' << f.column << '\n';
  clang_disposeTranslationUnit(tu); clang_disposeIndex(index);
}
"""

ADAPTER_IMPLEMENTATION = '''"""Private, explicitly selected generic-JUnit adapter version 1 example."""
from cppulse.test_import import normalize_test_import

def normalize(document):
    if document["format_version"] != 1:
        raise ValueError("Unsupported example format version")
    return normalize_test_import(
        document["snapshot"], report_artifact_id="raw-report",
        context_id=document["context_id"], scope_files=["src/main.cpp"],
        adapter="generic-junit", producer={"name": "example-fixture", "version": "1"})
'''


class ExtensionLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        selected = os.environ.get("CPPULSE_EXTENSION_EVIDENCE_DIR")
        cls.temporary = None if selected else tempfile.TemporaryDirectory()
        cls.output = Path(selected or cls.temporary.name)
        cls.output.mkdir(parents=True, exist_ok=True)
        prefix = os.environ.get("CPPULSE_EXTENSION_QUALIFIED_PREFIX")
        if prefix:
            import cppulse.tooling

            assert Path(cppulse.tooling.__file__).is_relative_to(Path(prefix))
        cls.registry_before = load_rule_registry(include_native_bindings=True)

    @classmethod
    def tearDownClass(cls) -> None:
        assert load_rule_registry(include_native_bindings=True) == cls.registry_before
        if cls.temporary:
            cls.temporary.cleanup()

    def command(
        self, name: str, argv: list[str], cwd: Path
    ) -> subprocess.CompletedProcess:
        result = subprocess.run(
            argv, cwd=cwd, text=True, capture_output=True, timeout=120
        )
        (self.output / (name + ".json")).write_text(
            json.dumps(
                {
                    "argv": argv,
                    "cwd": str(cwd),
                    "exit_status": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                },
                indent=2,
            )
            + "\n"
        )
        return result

    def test_rule_draft_and_completed_native_implementation(self) -> None:
        parent = self.output / "rule"
        parent.mkdir()
        draft = scaffold("rule", "forbid-gets", parent)
        registry = json.loads((draft / "registry-entry.json").read_text())
        validate("rule_registry", registry)  # Structural validity is not qualification.
        with self.assertRaisesRegex(ValueError, "binding required"):
            native_rule_headers(registry)
        shutil.copytree(draft, parent / "untouched-draft")
        (draft / "rules").mkdir()
        entry = registry["rules"][0]
        entry.update(
            id="EXAMPLE-GETS-001", version="1.0.0", category="extension_example"
        )
        entry["documentation"] = (
            "Private fixture: direct gets calls only; no alias/interprocedural claim."
        )
        entry["configuration_schema"]["properties"]["enabled"]["default"] = True
        entry["configuration_schema"]["x-cppulse-native"] = {
            "class": "ForbidGetsRule",
            "header": "rules/forbid_gets.h",
            "order": 0,
        }
        header = (
            (draft / "rule.h")
            .read_text()
            .replace("DRAFT-forbid-gets", entry["id"])
            .replace("TODO-review-category", entry["category"])
        )
        (draft / "rules/forbid_gets.h").write_text(header)
        (draft / "rule.h").write_text(header)
        (draft / "registry-entry.json").write_text(
            json.dumps(registry, indent=2) + "\n"
        )
        validate("rule_registry", registry)
        for name, content in native_rule_headers(registry).items():
            (draft / Path(name).name).write_text(content)
        positive = draft / "cases/positive.cpp"
        positive.write_text(
            'extern "C" char* gets(char*);\nvoid f() { char b[8]; gets(b); gets(b); }\n'
        )
        negative = draft / "cases/negative.cpp"
        negative.write_text(
            'void fgets(char*);\nvoid f() { char b[8]; fgets(b); const char* text = "gets(b)"; } // gets(b)\n'
        )
        (draft / "runner.cpp").write_text(RULE_RUNNER)
        includes, libclang = clang_toolchain()
        compiler = shutil.which("c++")
        self.assertIsNotNone(
            compiler, "Real C++ compiler required; never skip this gate"
        )
        binaries = Path(os.environ.get("CPPULSE_EXTENSION_BINARY_DIR", str(draft)))
        binaries.mkdir(parents=True, exist_ok=True)
        draft_binary = binaries / "draft-example"
        complete_binary = binaries / "complete-example"
        command = [
            compiler,
            "-std=c++17",
            "-Os",
            "-g0",
            "-pipe",
            "-I",
            str(draft),
            "-I",
            str(ROOT / "analyzer-core/src"),
            "-isystem",
            str(includes),
            str(draft / "runner.cpp"),
            str(draft / "rule.cpp"),
            str(libclang),
            "-o",
            str(draft_binary),
        ]
        compiled = self.command("rule-draft-compile", command, draft)
        self.assertEqual(compiled.returncode, 0, compiled.stderr)
        rejected = self.command(
            "rule-draft-rejection", [str(draft_binary), str(positive)], draft
        )
        self.assertEqual(rejected.returncode, 42)
        self.assertIn("Draft detector has not been implemented", rejected.stderr)
        (draft / "rule.cpp").write_text(RULE_IMPLEMENTATION)
        command[-1] = str(complete_binary)
        compiled = self.command("rule-complete-compile", command, draft)
        self.assertEqual(compiled.returncode, 0, compiled.stderr)
        trigger = self.command(
            "rule-positive", [str(complete_binary), str(positive)], draft
        )
        clean = self.command(
            "rule-negative", [str(complete_binary), str(negative)], draft
        )
        self.assertEqual((trigger.returncode, clean.returncode), (0, 0))
        self.assertEqual(
            [line.split()[:2] for line in trigger.stdout.splitlines()],
            [[entry["id"], "2"], [entry["id"], "2"]],
        )
        self.assertNotEqual(
            trigger.stdout.splitlines()[0], trigger.stdout.splitlines()[1]
        )
        self.assertEqual(clean.stdout, "")

    def test_toolchain_inputs_fail_closed(self) -> None:
        with patch.dict(os.environ, {"CPPULSE_EXTENSION_CLANG_INCLUDE": "/missing"}):
            with self.assertRaises(RuntimeError):
                clang_toolchain()
        with patch.dict(
            os.environ,
            {
                "CPPULSE_EXTENSION_CLANG_INCLUDE": "/missing",
                "CPPULSE_EXTENSION_LIBCLANG": "/missing/library",
            },
        ):
            with self.assertRaises(RuntimeError):
                clang_toolchain()

    def test_adapter_draft_and_implemented_contract_fixtures(self) -> None:
        # This existing helper creates real local source/artifact identities, but
        # the XML is clearly synthetic imported data, not an executed test claim.
        from test_external_import import archive

        parent = self.output / "adapter"
        parent.mkdir()
        draft = scaffold("adapter", "junit-example", parent)
        original = runpy.run_path(str(draft / "adapter.py"))["normalize"]
        with self.assertRaisesRegex(NotImplementedError, "Draft adapter"):
            original({})
        shutil.copytree(draft, parent / "untouched-draft")
        (draft / "adapter.py").write_text(ADAPTER_IMPLEMENTATION)
        normalize = runpy.run_path(str(draft / "adapter.py"))["normalize"]
        fixtures = {
            "positive": b'<testsuite tests="3" failures="1" skipped="1"><testcase name="retry"><failure/></testcase><testcase name="retry"/><testcase name="skip"><skipped/></testcase></testsuite>',
            "negative": b'<testsuite tests="1"><testcase name="clean"/></testsuite>',
            "malformed": b"<testsuite>",
        }
        outcomes = {}
        for name, raw in fixtures.items():
            snapshot, _, _ = archive(parent / name, raw)
            context = snapshot.manifest["contexts"][0]["id"]
            selection = {
                "format_version": 1,
                "snapshot": snapshot,
                "context_id": context,
            }
            evidence = normalize(selection)
            validate("evidence", evidence)
            row = evidence["records"][0]
            self.assertEqual(row["context_id"], context)
            self.assertEqual(row["origin"], "import")
            self.assertIsNone(row["receipt_id"])
            self.assertEqual(row["artifact_ids"], ["raw-report"])
            self.assertEqual(snapshot.read_bytes("raw-report"), raw)
            if name == "positive":
                self.assertEqual(
                    row["test_counts"],
                    {"total": 3, "passed": 1, "failed": 1, "skipped": 1, "errors": 0},
                )
                self.assertEqual(row["status"], "failed")
                self.assertEqual(
                    len({case["identity"] for case in row["test_cases"]}), 3
                )
            elif name == "negative":
                self.assertEqual(row["test_counts"]["passed"], 1)
                self.assertEqual(row["status"], "passed")
            else:
                self.assertIsNone(row["test_counts"])
                self.assertEqual(row["status"], "error")
                self.assertNotEqual(row["usability"], "usable")
            with self.assertRaisesRegex(ValueError, "format version"):
                normalize({**selection, "format_version": 2})
            outcomes[name] = evidence
        (parent / "outcomes.json").write_text(json.dumps(outcomes, indent=2) + "\n")

    def test_policy_draft_and_completed_evaluation_fixtures(self) -> None:
        from test_policy import facts, NOW

        parent = self.output / "policy"
        parent.mkdir()
        draft = scaffold("policy", "tests-example", parent)
        policy = json.loads((draft / "policy.json").read_text())
        validate("policy", policy)
        supplied = facts.__wrapped__()
        result = evaluate_policy(policy, supplied, generated_at=NOW)
        self.assertEqual(result["controls"][0]["status"], "unknown")
        self.assertEqual(result["scores"]["readiness"], 0)
        shutil.copytree(draft, parent / "untouched-draft")
        policy.update(id="example-tests", policy_version="1.0.0", contexts=["gcc17"])
        control = policy["controls"][0]
        control.update(id="tests", title="Require the supplied unit-test result")
        control["parameters"]["evidence_ids"] = ["unit-tests"]
        (draft / "policy.json").write_text(json.dumps(policy, indent=2) + "\n")
        validate("policy", policy)
        results = {"untouched_draft": result}
        for name in ["positive", "failed", "missing"]:
            bundle = deepcopy(supplied)
            if name == "failed":
                bundle["evidence"]["records"][0]["status"] = "failed"
                receipt = bundle["execution_receipt"][0]
                receipt.update(status="failed", exit_code=1)
                receipt["tests"].update(passed=0, failed=1)
            elif name == "missing":
                bundle["evidence"]["records"] = []
                bundle["execution_receipt"] = []
            assessed = evaluate_policy(policy, bundle, generated_at=NOW)
            validate("assessment", assessed)
            expected = {"positive": "passed", "failed": "failed", "missing": "unknown"}[
                name
            ]
            self.assertEqual(assessed["controls"][0]["status"], expected)
            self.assertEqual(
                assessed["scores"]["readiness"], 100 if name == "positive" else 0
            )
            results[name] = assessed
        (parent / "outcomes.json").write_text(json.dumps(results, indent=2) + "\n")


if __name__ == "__main__":
    # Direct execution intentionally avoids checkout conftest path injection.
    unittest.main(verbosity=2)
