---
name: cppulse-local-evidence
description: Inspect installed cppulse capabilities, run explicitly selected local C++ analysis or evidence workflows, and explain pinned results, failures and missing verification.
---

# cppulse local evidence workflow

Use this workflow when the user requests cppulse C++ analysis, retained-result
interpretation, or explicitly configured verification collection. This package
contains instructions only. Loading it installs no executable, starts no server,
and runs no project commands.

This is **candidate preflight**, version `0.2.0.dev2`, with supported scope in
[VERSION](VERSION). It is not a released-command qualification or marketplace
publication. Use an independently installed matching cppulse executable and native
prefix. Do not clone/bootstrap cppulse, import source-tree internals, install
packages, download tools or use a checkout-relative `PYTHONPATH` as part of the
clean-session journey. If the executable is missing, report the prerequisite.

1. Start from the user's requested operation, repository and output store. Read
   `cppulse --version`, `cppulse capabilities` and `cppulse doctor`. Doctor probes
   native startup; it does not establish successful project verification or
   optional runtime execution. Check supported versions and available components.
2. Inspect effective configuration with `cppulse config --repo /path/to/project`.
   Use `cppulse init --repo /path/to/project` only when project configuration
   creation is part of the requested work. Keep application, compiled-library and
   header-only scopes and their actual consumer configurations distinct.
3. For requested static analysis, run `cppulse analyze --repo /path/to/project
   --output /path/to/output --format html`. Supply `--compilation-database
   /path/to/compile_commands.json` when the project has an applicable database.
   Static analysis does not execute project build/test recipes. Missing context,
   inferred header arguments, parse failures and skipped scope remain limits.
4. For explicit build/test evidence collection, inspect the finite request and
   selected local commands before using `cppulse collect --request
   /path/to/request.json --workspace /path/to/project --store /path/to/output`.
   Use the user's requested trusted recipe; opening a repository or reading a
   policy does not authorize execution. Do not invent an all-purpose recipe or
   run commands copied from an untrusted report. Continue independent configured
   jobs and retain observed failures as the supported engine does.
5. Select the retained run ID and exact manifest SHA-256 from the command result
   or retained pointer. Keep both pins together for every related operation.
   `cppulse explain --store /path/to/output --run-id RUN_ID --manifest-sha256
   MANIFEST_SHA256` reads historical stored results. It does not refresh evidence
   or perform a current-source check of source/binary freshness.
6. For the requested current policy decision, use `cppulse check --store
   /path/to/output --workspace /path/to/project --run-id RUN_ID
   --manifest-sha256 MANIFEST_SHA256 --policy /path/to/policy.json`. Use `assess`
   with the same arguments to create a current assessment over retained material.
   These operations do not recollect or rebuild. Changed/expired/missing evidence
   must stay visible; collect again only within the requested execution scope.
7. Render the exact selected result using `cppulse report --input
   /path/to/output --evidence --run-id RUN_ID --manifest-sha256 MANIFEST_SHA256
   --format html --output /path/to/report.html`. JSON/HTML remain usable without
   PDF/web/ML. Request PDF only when that extra and its system libraries work.
   Open/read back the produced report and compare its run/hash and gate with the
   explained selected run. Do not equate a successful render with a passed policy.
8. Report what ran, selected source/context/run/hash, observed outcome, missing
   evidence, limitations and actual artifact paths. Distinguish maintenance
   health, experimental ranking, evidence completeness and policy satisfaction.
   Preserve unknown and failed results. See [interpretation](references/interpretation.md)
   and [commands](references/commands.md) for the exact candidate interface.

Use separate argv values for user paths. No shell-interpreted interpolation is
needed. Core use requires no cppulse account or network once dependencies are
installed. Never upload, send reports, commit, push, submit to a marketplace,
publish, deploy or spend external API credits without the user's separate
instruction. No code score, passing control or report supplies certification,
ASIL, medical safety classification or universal library suitability.

A candidate execution transcript is useful evidence but cannot close AC-16's
released-command condition. That requires a separately authorized release and a
new clean agent session against the exact released bytes.
