# Coordinator CLI fix independently rechecked

The portfolio source owner independently rechecked the coordinator's final CLI
change with all five public CLI cases: **5 passed**, retained command/result in
`portfolio-cli-review.log`. The single exhausted-event fixture now explicitly
uses lookback_days=1; the previous shared helper's two-day catch-up correctly
created two jobs. The original expected exhausted count of one was retained,
not weakened. The earlier combined red log remains at
`work/cloud-resume/hotspot-portfolio-public.log`.

Current CLI returns operational exit 2 for active failed/exhausted jobs of the
selected configuration even on a no-op; successful/no-due ticks remain 0 and do
not claim a policy gate. Empty explicit replay time is rejected. Relative output
roots are normalized without following symlinks. This closes finding 1 for these
source bytes; installed candidate/platform/provider qualification is separate.

Reviewed CLI SHA-256: `faa9487db6d1ba2b4689ec7f3297f858b16440b64ec3e4f7e48e39745a857800`.
Reviewed CLI-test SHA-256: `815fd0d3626d589cc0fbc0cfb7494d714a34a62fae97c235e0b8a050ac0af821`.
