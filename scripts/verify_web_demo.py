"""Exercise the built dashboard against fresh artifacts through the real HTTP API."""

from __future__ import annotations
from collections import Counter
import argparse
import math
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright


def main() -> None:
    """Start local services, inspect all dashboard sections, and retain evidence."""
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=root / "output/demo")
    parser.add_argument("--evidence", type=Path, default=root / "review")
    args = parser.parse_args()
    evidence = args.evidence.resolve()
    evidence.mkdir(parents=True, exist_ok=True)
    logs = evidence / "logs"
    logs.mkdir(exist_ok=True)
    data_dir = args.data.resolve()
    local = {
        name: json.loads((data_dir / f"{name}.json").read_text())
        for name in ["findings", "risk_scores", "git_metrics", "roadmap"]
    }
    env = {**os.environ, "DATA_DIR": str(data_dir)}
    processes = []
    with (
        (logs / "web-api.log").open("w") as api_log,
        (logs / "web-dashboard.log").open("w") as ui_log,
    ):
        try:
            processes.append(
                subprocess.Popen(
                    [
                        sys.executable,
                        "-m",
                        "uvicorn",
                        "src.api:app",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        "8000",
                    ],
                    cwd=root / "report-engine",
                    env=env,
                    stdout=api_log,
                    stderr=subprocess.STDOUT,
                )
            )
            processes.append(
                subprocess.Popen(
                    [
                        "npm",
                        "run",
                        "preview",
                        "--",
                        "--host",
                        "127.0.0.1",
                        "--port",
                        "3000",
                        "--strictPort",
                    ],
                    cwd=root / "dashboard",
                    stdout=ui_log,
                    stderr=subprocess.STDOUT,
                )
            )
            for port, path in [(8000, "/health"), (3000, "/")]:
                for _ in range(100):
                    try:
                        urllib.request.urlopen(f"http://127.0.0.1:{port}{path}").close()
                        break
                    except OSError:
                        time.sleep(0.1)
                else:
                    raise RuntimeError(f"Service on {port} did not become ready")
            payloads = {}
            for name in [
                "summary",
                "findings",
                "hotspots",
                "risks",
                "silos",
                "roadmap",
            ]:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:3000/api/v1/{name}"
                ) as response:
                    payloads[name] = json.load(response)
            assert (
                payloads["summary"]["findings_summary"] == local["findings"]["summary"]
            )
            assert payloads["findings"]["total"] == len(local["findings"]["findings"])
            assert payloads["risks"]["items"] == local["risk_scores"]["file_risks"]
            with urllib.request.urlopen(
                "http://127.0.0.1:3000/api/v1/report/pdf"
            ) as response:
                pdf = response.read()
                assert response.headers["Content-Type"] == "application/pdf"
                assert pdf.startswith(b"%PDF") and len(pdf) > 1000
            with urllib.request.urlopen(
                "http://127.0.0.1:3000/api/v1/view"
            ) as response:
                view = json.load(response)
            assert view["mode"] == "legacy-flat"
            assert view["input_verification"] == "unverified"
            assert "run" not in view
            for kind, document in local.items():
                assert view["legacy"][kind]["document"] == document, kind
            (evidence / "legacy-view.json").write_text(json.dumps(view, indent=2))
            (evidence / "api-responses.json").write_text(json.dumps(payloads, indent=2))
            with sync_playwright() as playwright:
                executable = os.environ.get("CPPULSE_BROWSER")
                browser = playwright.chromium.launch(
                    executable_path=executable, args=["--no-sandbox"]
                )
                page = browser.new_page(viewport={"width": 1440, "height": 1000})
                errors = []
                browser_api_requests = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.on(
                    "request",
                    lambda request: (
                        browser_api_requests.append(request.url)
                        if "/api/v1/" in request.url
                        else None
                    ),
                )
                page.goto("http://127.0.0.1:3000")
                page.get_by_text("Legacy flat compatibility", exact=True).wait_for()
                for label, expected in {
                    "Repository": local["findings"]["metadata"]["repo_path"],
                    "Total findings": local["findings"]["summary"]["total_findings"],
                    "Critical ranked files": sum(
                        item["risk_level"] == "critical"
                        for item in local["risk_scores"]["file_risks"]
                    ),
                    "Knowledge silos": len(local["git_metrics"]["knowledge_silos"]),
                }.items():
                    card = page.get_by_text(label, exact=True).locator("..")
                    card.wait_for()
                    assert card.locator("p").nth(1).inner_text() == str(expected), label
                assert (
                    page.get_by_role("status", name="Stored policy gate").count() == 0
                )
                score = local["risk_scores"]["health_score"]["overall"]
                if score is None:
                    page.get_by_text(re.compile("No score")).wait_for()
                else:
                    page.get_by_text(
                        str(math.floor(score + 0.5)), exact=True
                    ).first.wait_for()
                page.screenshot(
                    path=str(evidence / "dashboard-overview.png"), full_page=True
                )
                text = {}
                for name in [
                    "Findings",
                    "Hotspots",
                    "Knowledge Silos",
                    "Risk Prediction",
                    "Roadmap",
                ]:
                    page.get_by_role(
                        "button", name=re.compile(re.escape(name) + r"$"), exact=False
                    ).click()
                    page.wait_for_timeout(100)
                    text[name] = page.inner_text("main")
                    assert "Error:" not in text[name]
                    assert "[object Object]" not in text[name]
                    records = {
                        "Findings": local["findings"]["findings"],
                        "Hotspots": local["risk_scores"]["hotspots"],
                        "Knowledge Silos": local["git_metrics"]["knowledge_silos"],
                        "Risk Prediction": local["risk_scores"]["file_risks"],
                        "Roadmap": local["roadmap"]["items"],
                    }.get(name, [])
                    if records:
                        assert all(
                            Path(record["file"]).name in text[name]
                            for record in records
                        )
                    if name == "Findings":
                        page.get_by_role(
                            "heading",
                            name=f"Findings ({len(records)})",
                            exact=True,
                        ).wait_for()
                        for message, count in Counter(
                            record["message"] for record in records
                        ).items():
                            assert (
                                page.get_by_text(message, exact=True).count() == count
                            )
                    if name == "Knowledge Silos":
                        page.get_by_role(
                            "heading",
                            name=f"Knowledge Silos ({len(records)})",
                            exact=True,
                        ).wait_for()
                        for record in records:
                            assert record["sole_contributor"] in text[name]
                            assert record["last_commit_date"] in text[name]
                assert not errors, errors
                assert browser_api_requests == [
                    "http://127.0.0.1:3000/api/v1/view"
                ], browser_api_requests
                (evidence / "dashboard-sections.json").write_text(
                    json.dumps(text, indent=2)
                )
                (evidence / "legacy-browser-verification.json").write_text(
                    json.dumps(
                        {
                            "mode": view["mode"],
                            "total_findings": local["findings"]["summary"][
                                "total_findings"
                            ],
                            "health_score": score,
                            "knowledge_silos": len(
                                local["git_metrics"]["knowledge_silos"]
                            ),
                            "browser_api_requests": browser_api_requests,
                            "checked_sections": list(text),
                            "browser_errors": errors,
                        },
                        indent=2,
                    )
                )
                browser.close()
            print(
                "PASS: production legacy-flat dashboard, exact summary totals/all finding rows, 6 compatibility routes plus one view via Vite proxy, API PDF, all navigation sections, no browser errors"
            )
        finally:
            for process in reversed(processes):
                process.terminate()
                process.wait(timeout=10)


if __name__ == "__main__":
    main()
