# Independent local store protocol review

Recovery's bounded history deliberately permits equivalent retained prepared journals
from repeated pre-unlink interrupted recovery. Each selected candidate must validate
exact archived raw lock bytes, original SHA/token, store identity and the current
original stage identity. Selecting a qualified journal in sorted order is not a
claim that other historical receipts have been validated. Blanket refusal of
multiple journals would strand legitimate repeated interruption. The inspected
implementation limits total inventory and matching candidates and fails closed on
unsafe or corrupt selected candidates. Recovery replay checks control bytes and
stage directory identity, not a complete content inventory or source freshness.

The reviewer reproduced a distinct v3 migration resume failure: an interruption
after the migrating marker allowed original pinned manifest or artifact bytes to
change before resume; the old implementation activated migration without checking
those bytes again. Both meaningful failing tests and source-bound red evidence are
retained. The owner repaired production to revalidate exact references before
legacy pointer destruction and before activation. Subsequent 22 reviewer controls
passed. Final qualification still needs the source-stable gate.

Actual historical-wheel controls run the retained installed old wheel in isolated
Python (-I), with no repository PYTHONPATH. The old reader fails on directory
fences; the old publisher reaches immutable-run publication and then fails legacy
latest-attempt replacement, retaining an unreferenced run. The new heads authority
is unchanged. The same actual old reader accepts the explicitly exported separate
v2 snapshot. This establishes a fail-closed incompatibility boundary, not forward
compatibility or successful old-writer support.

No full-plan acceptance state follows from these component checks. No test here
qualifies network filesystems, Windows locking, multi-host storage, source cache
closure, or installed-current-code behavior. Final installed-artifact evidence
must use a newly built wheel containing the current protocol changes.
