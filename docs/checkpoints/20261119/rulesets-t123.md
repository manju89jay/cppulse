# T1–T3 development checkpoint

This checkpoint implements the approved local-ruleset, clang-tidy-family and configuration-forwarding batch on `codex/cppulse-local-core-20261114`, starting at `a8c0d9431d86590d6603c2c6a4cb233d8204570e`. It is not a production release. All 187 original definitions (118 requirements, 60 tasks, nine obligations), P0–P14 and the final acceptance criteria remain intact.

## Implemented and tested scope

- Strict local data-only JSON packs, bounded inheritance, explicit selection/option precedence, content identity and retained configuration. Existing JSON/YAML profiles, including empty YAML, remain supported. Detector selection, scoring profile, evidence completeness and policy results stay separate.
- Genuine clang-tidy 19.1.7 positive and clean/control fixtures for `bugprone-use-after-move`, `bugprone-dangling-handle` and `bugprone-unused-return-value`, through the existing importer/collector and installed public workflows. Import origin and unverified completeness remain explicit; notes do not create extra findings or confirmation.
- Native/predictor container entrypoints share one resolved config. Predictor stages both outputs inside the validated destination directory, completes schemas and the original-input guard, closes writers and atomically replaces each file. This fixes actual Docker bind-mount EXDEV without a copy fallback. The two replacements are not a transaction; second-replace failure is an error and may leave the first updated. Symlink/nonregular boundaries and owned-stage cleanup remain guarded.
- Configuration settings/profile and their identity use a single validated byte read. Controlled file-mutation regressions preserve the selected input rather than a later live value.

## Exact qualification inputs and results

Wheel: `6b33d180f23cf94547b03628f61096d778491ac5f15f2adcd1ed3e1ee105631d` (`cppulse-0.2.0.dev2-py3-none-any.whl`, 242 package payloads). Build-source freeze: `work/coverage-t123/final-candidate/candidate-source-freeze.json`, 404 source/build/test files plus 102 unchanged native/editor inputs. The six additional test-only inputs in the combined gate require their genuine retained pre/post run-hash bridge; they are not retroactively inserted into the build freeze.

Unchanged native component SHA-256: `1a34a3ad2a344728af729ec6d54c0277e01bac9503435e7462982d06f45d17c1`. Actual clang-tidy tool SHA-256: `9ebd2c4f2a123c058f4744e9a02a8000ab9ba22f9b835958dfda7c4d7de2527c`.

| Gate | Command / retained record | Actual result |
| --- | --- | --- |
| Affected source | `.venv/bin/python -B work/coverage-t123/run_source_final_epoch.py`; `source-final-epoch-record.json` | 427 passed, no skips; stable source |
| Installed public composition | `.venv/bin/python -B work/coverage-t123/qualify_final_candidate.py`; `final-durable-qualification.json` | Prior 264-case bank plus 172 batch cases and two arithmetic controls passed; core socket denial and required API local IPC qualified separately |
| Docker mounted output | Existing resource wrapper invokes `work/coverage-t123/docker-smoke-final/run.py`; `docker-smoke-final/result.json` | Prepare/native/predictor all exit 0; one expected native finding; matching safety-critical profile; partial scope retains null health |
| Generated references | `.venv/bin/python -B scripts/check_generated.py` | Exit 0; generated references current |
| Local documentation links | `work/coverage-t123/docs-link-check.json` | All 24 checked local targets exist; remote HTTP and all anchors not claimed |

The source fixture archive is SHA-256 `54ba223270462fa290cf731a239b0ec0acd9b55e3a116afb577e62b609056de0`. Complete installed qualification archive: `735f3f7998c71e4e17c8b85e897b74329dc9a03feeb3ea98b824c84f0e3a86d3`. These machine-local evidence packets, full inputs, commands, logs, indices and recovery registry remain in `work/coverage-t123/`; generated runtime dumps, archives and dependencies are excluded from Git. The small genuine producer fixtures are included under `tests/fixtures/clang_tidy19_qualification/`.

The Docker test uses cached image `sha256:d64d2edfc93b0ee9dc8b6452c53bbd66017a01b7f7ab60e3bb15408ee1ad34b7`, Docker server 29.9.2 and Compose 2.40.3, with read-only host Python/native/dependency bindings, network none, 1 GiB memory, one CPU and 128 PIDs. It qualifies this actual mounted-output configuration path, not Alpine distribution compatibility, product image builds, six-service deployment or the platform matrix.

## Use and limitations

See [ruleset contracts and examples](../../contracts/rulesets.md). For a validated local pack, prepare the single component config with:

```bash
cppulse config --repo /path/to/project --ruleset /path/to/review.json \
  --profile safety-critical --native-output /path/to/output/native.json
```

Choose a fresh output config path. Both component stages consume that same file; the native CLI has no `--profile` flag. Standalone predictor without `--config` does not discover CWD files. An explicit `--profile` overrides a valid supplied config profile, but supplied configs are intentionally still validated.

Native detection remains the existing 22 experimental rules. Move analysis is flow-sensitive, not path-sensitive; correlated conditions can warn falsely and member/global moves are outside the qualified family. Default dangling handles cover the explicitly recorded string-view classes, not arbitrary spans/borrowing types. The unused-return check pins function/return-type patterns; explicit void casts warn when `AllowCastToVoid=false`. Hashes identify bytes and do not authenticate producers or establish expertise, calibrated defect probabilities or upstream readiness.

Original FIFO capture rejection, fixture-directory collision, API socket-boundary failure, old candidate qualification and genuine Docker EXDEV failure remain retained. No nonregular capture guard or product assertion was weakened. Two verbatim producer default-dump stdout files retain their authentic blank EOF lines; `.gitattributes` disables only `blank-at-eof` for those exact paths, leaving source whitespace checks intact.

A single reviewed inactive `libclangCodeGen.a` duplicate was retired only after complete same-package restoration, body/metadata verification and live-input checks. The retained Debian package and restoration proof remain available. The existing 4 GiB reserve, admission margin and caps are unchanged. Restore the recorded AST/Sema/CodeGen static members before future native static linking, following `work/cloud-resume/resource-maintenance.json`; the qualified native/tool runtime needs none of those archives.

## Acceptance integration

Independent review accepted the exact current qualification, staged product bytes and complete prior38 refresh plan. Root published `work/coverage-t123/current38-source-proof.json`, SHA-256 `fad3d516c96e789e407d1956f360b27ae26f4f93c70e1db0c13f99b60de82a57`, with 31,986 final source/evidence pins. Accepted review SHA-256: `3cd76bc46a3362cae637b8647949e63c5efc629ee7b1796d41b46256de3c701b`. The rejected first refresh and its original inputs remain preserved; six omitted test-only inputs are bridged by the passing run's retained pre/post hashes, exact command and case coverage, with present-day freshness checked separately.

Actual command: `.venv/bin/python -B scripts/verify_delivery.py --require-complete --output work/coverage-t123/require-complete.json`. It exited **3** at `2026-11-19T17:28:37.515243+00:00`: current evidence valid, full program incomplete; no stale/invalid-proof error. The verifier itself is unchanged, SHA-256 `44f5aa3dbaf0673398f0737f0293898b1ea5bad8f968d1215ed140250dc161bf`. The resource wrapper record is `work/heavyweight-jobs/coverage-t123-strict-final/record.json`.

Ledger before: `3e29da674b12f0dd727bcc388ed08d94ae8c4f28a76c6279a5536298a50f8c17`; after: `dc07cf42487e77a4ff348a3e37bc84a2af62d25e924eb3cdefe5010c2e88845b`. All original definitions and all 187 states are identical: **38 verified, 96 open, 51 active, two blocked**. Definition SHA-256: `e57e89fb7db188f1f4805b95c0bc6f2896c7ab9eef15d851723cc422a0bd2381`. This batch closes no additional canonical item. PR-04/M0-05 retain their original broader scorer requirements; full completion still requires tasks section14, AC-01..16, P14 and strict exit0. Actual Windows/macOS matrix access and real usefulness participants remain the two recorded external blockers.

Elapsed from retained intake `2026-11-19T14:43:49.994929+00:00` to the actual strict result: approximately 164.8 minutes. Main delays were implementation/review repairs, installed fixture/capture and local-IPC qualification, storage admission, the genuine mounted-output EXDEV defect and evidence integration. The final source gate took 90.99 seconds; the final installed wrapper ran from 16:53:59 UTC to 16:57:44 UTC, and the final Docker smoke completed at 17:01:05 UTC. No new service outage was observed during this resumed final epoch. These are recorded checkpoint times, not a production ETA.

One development checkpoint commit and a normal fast-forward push to the same branch are authorized after the final administrative staged audit. No later feature batch, merge, force push, release or deployment is part of this checkpoint. After this checkpoint, further commits/pushes require user instruction. Product source/test pins, explicit staging manifest, final commit/tree/parent and remote confirmation are retained under `work/coverage-t123/`; machine-local proof packets are not shipped in Git.
