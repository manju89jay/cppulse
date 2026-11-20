# Current public store integration

Uncommitted continuation on HEAD6f8b662a89b367f8c6883298dc97950150d7ba4f.

Public migration/export preserve both original manifest identities. In-place export is refused. Recovery inspection accepts paired exact lock pins and rejects incomplete pairs before opening a store. Capability negotiation describes supported store formats without project execution. API layout detection fails closed on v3 metadata and dangling metadata symlinks.

- `.venv/bin/python -m pytest -q tests/test_store_layout_public_cli.py tests/test_store_recovery_public_cli.py tests/test_client_capabilities.py --basetemp /tmp/cppulse-public-store-layout-v1`:9passed; log `work/cloud-resume/public-store-layout-v1.log`.
- API layout/run binding checks across explicit v2 and v3:25passed; log `work/cloud-resume/store-api-v3-hints-v2.log`.
- New complete root test run is in progress under `review/cloud-20261116-post-v3-root-integration/`; no passing outcome claimed.
- `.venv/bin/python scripts/verify_delivery.py --require-complete`:exit3,120open/65active/2blocked; exact current187IDs and definition digest recorded in `work/cloud-resume/require-complete-post-v3-public-adapters.json`.

Mapped open scope: PR-03,FR-UX-08,M1-03,M2-05,M2-06,NFR-SCL-06,NFR-MNT-06,AC-06,AC-12,AC-13. These checks do not accept entire requirements. Installed post-v3 wheel, full integration, representative scale and platform gates remain open.
