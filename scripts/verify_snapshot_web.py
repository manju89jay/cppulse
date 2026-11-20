"""Verify bundled snapshot UI/API/PDF using an unrelated cwd and no Node PATH."""

from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request

from playwright.sync_api import sync_playwright
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    """Run real browser requests against explicit historical snapshot identities."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--python", type=Path, default=Path(sys.executable))
    parser.add_argument("--source-package", type=Path)
    parser.add_argument(
        "--verification",
        type=Path,
        default=ROOT / "output/evidence-reports/verification.json",
    )
    parser.add_argument("--consumer-summary", type=Path)
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    output = args.evidence.absolute()
    output.mkdir(parents=True, exist_ok=True)
    cases = json.loads(args.verification.read_text())["cases"]
    if args.consumer_summary:
        consumers = json.loads(args.consumer_summary.read_text())
        for case in consumers["cases"]:
            cases.append(
                {
                    "scenario": "consumer-" + case["scenario"],
                    "source_store": str(Path(case["comparison_run_path"]).parents[1]),
                    "run_id": case["comparison_run_id"],
                    "manifest_sha256": case["comparison_manifest_sha256"],
                    "gate": None,
                }
            )
    results = []
    with (
        tempfile.TemporaryDirectory(prefix="cppulse-web-unrelated-") as temporary,
        sync_playwright() as playwright,
    ):
        unrelated = Path(temporary)
        empty_path = unrelated / "no-command-tools"
        empty_path.mkdir()
        browser = playwright.chromium.launch(
            executable_path=os.environ.get("CPPULSE_BROWSER"), args=["--no-sandbox"]
        )
        try:
            for case in cases:
                case_output = output / case["scenario"]
                case_output.mkdir()
                with socket.socket() as reservation:
                    reservation.bind(("127.0.0.1", 0))
                    port = reservation.getsockname()[1]
                base = f"http://127.0.0.1:{port}"
                environment = {
                    **os.environ,
                    "DATA_DIR": case["source_store"],
                    "PATH": str(empty_path),
                }
                environment.pop("CPPULSE_API_KEY", None)
                environment.pop("PYTHONPATH", None)
                if args.source_package:
                    environment["PYTHONPATH"] = str(args.source_package.absolute())
                assert shutil.which("node", path=environment["PATH"]) is None
                with (case_output / "server.log").open("w") as log:
                    process = subprocess.Popen(
                        [
                            str(args.python.absolute()),
                            "-m",
                            "uvicorn",
                            "cppulse.report_engine.api:app",
                            "--host",
                            "127.0.0.1",
                            "--port",
                            str(port),
                        ],
                        cwd=unrelated,
                        env=environment,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                    )
                    page = None
                    try:
                        for _ in range(150):
                            if process.poll() is not None:
                                raise RuntimeError(
                                    f"Server exited; see {case_output/'server.log'}"
                                )
                            try:
                                with urllib.request.urlopen(
                                    base + "/health", timeout=1
                                ) as response:
                                    assert response.status == 200
                                break
                            except OSError:
                                time.sleep(0.1)
                        else:
                            raise RuntimeError("Snapshot server did not become ready")
                        pin = urllib.parse.urlencode(
                            {
                                "run_id": case["run_id"],
                                "manifest_sha256": case["manifest_sha256"],
                            }
                        )
                        with urllib.request.urlopen(
                            base + "/api/v1/view?" + pin
                        ) as response:
                            view = json.load(response)
                        assert view["run"]["id"] == case["run_id"]
                        assert view["run"]["manifest_sha256"] == case["manifest_sha256"]
                        (case_output / "view.json").write_text(
                            json.dumps(view, indent=2) + "\n"
                        )
                        page = browser.new_page(
                            viewport={"width": 1440, "height": 1000}
                        )
                        errors = []
                        requests = []
                        page.on("pageerror", lambda error: errors.append(str(error)))
                        page.on(
                            "request",
                            lambda request: (
                                requests.append(request.url)
                                if "/api/" in request.url
                                else None
                            ),
                        )
                        page.goto(base + "/?" + pin)
                        if view["assessment"]:
                            expected = view["assessment"]["display"]["gate"]
                            assert expected == case["gate"]
                            assert (
                                page.get_by_role(
                                    "status", name="Stored policy gate"
                                ).inner_text()
                                == expected
                            )
                        else:
                            page.get_by_text(
                                "No stored assessment selected.", exact=True
                            ).wait_for()
                            assert case["gate"] is None
                        page.get_by_text(case["run_id"], exact=True).wait_for()
                        page.screenshot(
                            path=str(case_output / "overview.png"), full_page=True
                        )
                        assert (
                            len(requests) == 1 and "/api/v1/view?" in requests[0]
                        ), requests
                        page.get_by_role("button", name="Findings", exact=True).click()
                        expected_observations = Counter()
                        for fact in view["facts"]:
                            raw = json.loads(fact["raw_json"])
                            if fact["kind"] == "observations":
                                expected_observations.update(
                                    item["message"] for item in raw["items"]
                                )
                            elif fact["kind"] == "external_analysis_facts":
                                expected_observations.update(
                                    item["message"] for item in raw["observations"]
                                )
                        for message, count in expected_observations.items():
                            assert (
                                page.get_by_text(message, exact=True).count() == count
                            ), (message, count)
                        page.screenshot(
                            path=str(case_output / "findings.png"), full_page=True
                        )
                        page.get_by_role("button", name="Evidence", exact=True).click()
                        for fact in view["facts"]:
                            raw = json.loads(fact["raw_json"])
                            if fact["kind"] == "consumer_comparison":
                                for row in raw["cases"]:
                                    assert (
                                        page.get_by_text(
                                            row["reason"], exact=True
                                        ).count()
                                        >= 1
                                    )
                                    for missing in row["missing_local_checks"]:
                                        assert (
                                            missing in page.locator("main").inner_text()
                                        )
                            if fact["kind"] == "coverage_facts":
                                for file in raw["files"]:
                                    for measurement in file["measurements"]:
                                        assert (
                                            f'{measurement["covered"]} / {measurement["total"]}'
                                            in page.locator("main").inner_text()
                                        )
                            if fact["kind"] == "sanitizer_facts":
                                assert (
                                    f'{raw["sanitizer"]} outcome: {raw["outcome"]}'
                                    in page.locator("main").inner_text()
                                )
                        page.screenshot(
                            path=str(case_output / "evidence.png"), full_page=True
                        )
                        page.get_by_role(
                            "button", name="Raw Artifacts", exact=True
                        ).click()
                        artifact = view["artifacts"][0] if view["artifacts"] else None
                        if artifact:
                            with page.expect_download() as selected_download:
                                page.get_by_role(
                                    "button",
                                    name="Download " + artifact["path"],
                                    exact=True,
                                ).click()
                            download = selected_download.value
                            path = case_output / "raw-artifact.bin"
                            download.save_as(path)
                            assert (
                                hashlib.sha256(path.read_bytes()).hexdigest()
                                == artifact["sha256"]
                            )
                            selected_url = next(
                                url for url in requests if "/artifacts/" in url
                            )
                            assert (
                                f'/runs/{case["run_id"]}/' in selected_url
                                and case["manifest_sha256"] in selected_url
                            )
                        with page.expect_download(timeout=60000) as pdf_download:
                            page.get_by_role(
                                "button", name="Download snapshot PDF", exact=True
                            ).click()
                        pdf = case_output / "snapshot.pdf"
                        pdf_download.value.save_as(pdf)
                        assert (
                            pdf.read_bytes().startswith(b"%PDF")
                            and pdf.stat().st_size > 1000
                        )
                        text = "\n".join(
                            page.extract_text() or "" for page in PdfReader(pdf).pages
                        )
                        assert (
                            case["run_id"] in text and case["manifest_sha256"] in text
                        )
                        assert not errors, errors
                        results.append(
                            {
                                "scenario": case["scenario"],
                                "run_id": case["run_id"],
                                "manifest_sha256": case["manifest_sha256"],
                                "gate": case["gate"],
                                "browser_errors": errors,
                                "api_requests": requests,
                                "typed_observation_rows": sum(
                                    expected_observations.values()
                                ),
                                "pdf_size": pdf.stat().st_size,
                                "server_path_contains_node": False,
                                "cwd": "unrelated temporary directory",
                                "package_mode": (
                                    "source-explicit"
                                    if args.source_package
                                    else "installed"
                                ),
                            }
                        )
                    finally:
                        if page:
                            page.close()
                        process.terminate()
                        try:
                            process.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            process.kill()
                            process.wait(timeout=10)
        finally:
            browser.close()
    (output / "verification.json").write_text(
        json.dumps({"cases": results}, indent=2) + "\n"
    )
    print(
        json.dumps({"result": "passed", "cases": len(results), "evidence": str(output)})
    )


if __name__ == "__main__":
    main()
