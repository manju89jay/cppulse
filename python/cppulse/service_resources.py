"""Finite Linux per-process resource setup for explicitly trusted service steps."""

from __future__ import annotations

from typing import Any

from cppulse.errors import ContractError
from cppulse.identities import canonical_json_bytes

RESOURCE_EXEC = """import json,os,resource,sys
requested=json.loads(sys.argv[1]);receipt=sys.argv[2];selected_step=sys.argv[3];sys.argv=[sys.argv[0],*sys.argv[4:]]
def limits():
 return {"cpu_seconds":list(resource.getrlimit(resource.RLIMIT_CPU)),"address_space_bytes":list(resource.getrlimit(resource.RLIMIT_AS))}
before=limits();status="applied";reason=""
try:
 if requested["cpu_seconds"] is not None:
  resource.setrlimit(resource.RLIMIT_CPU,tuple(requested["cpu_seconds"]))
 if requested["address_space_bytes"] is not None:
  resource.setrlimit(resource.RLIMIT_AS,(requested["address_space_bytes"],requested["address_space_bytes"]))
except (OSError,ValueError) as error:
 status="setup_failed";reason=type(error).__name__+": "+str(error)
record={"version":"1.0.0","scope":"linux-per-process-inherited-rlimit","pid":os.getpid(),"step_id":selected_step,"argv":sys.argv[1:],"requested":requested,"inherited":before,"actual":limits(),"status":status,"reason":reason}
fd=os.open(receipt,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
with os.fdopen(fd,"w") as stream:
 json.dump(record,stream,sort_keys=True,separators=(",",":"));stream.flush();os.fsync(stream.fileno())
if status!="applied":sys.exit(125)
"""


def validate_process_resources(document: dict[str, Any]) -> None:
    """Require ordered CPU limits; JSON schema establishes finite scalar bounds."""
    for limits in document.values():
        cpu = limits["cpu_seconds"]
        if cpu is not None and cpu[0] > cpu[1]:
            raise ContractError("CPU soft limit cannot exceed hard limit")


def validate_resource_receipt(
    document: dict[str, Any],
    requested: dict[str, Any],
    *,
    step_id: str | None = None,
    argv: list[str] | None = None,
) -> None:
    """Reconcile actual setup observations; process exit alone proves no cause."""
    if (
        not isinstance(document, dict)
        or set(document)
        != {
            "version",
            "scope",
            "pid",
            "step_id",
            "argv",
            "requested",
            "inherited",
            "actual",
            "status",
            "reason",
        }
        or document["version"] != "1.0.0"
        or document["scope"] != "linux-per-process-inherited-rlimit"
    ):
        raise ContractError("Invalid per-process resource receipt")
    if (
        (not isinstance(document["pid"], int) or isinstance(document["pid"], bool))
        or document["pid"] <= 0
        or canonical_json_bytes(document["requested"])
        != canonical_json_bytes(requested)
    ):
        raise ContractError("Resource receipt changes process/request identity")
    if (
        not isinstance(document["step_id"], str)
        or not document["step_id"]
        or not isinstance(document["argv"], list)
        or not document["argv"]
        or any(
            not isinstance(value, str) or not value or "\x00" in value
            for value in document["argv"]
        )
        or (step_id is not None and document["step_id"] != step_id)
        or (argv is not None and document["argv"] != argv)
    ):
        raise ContractError(
            "Resource receipt identifies another selected process step/argv"
        )
    for name in ("inherited", "actual"):
        limits = document[name]
        if (
            not isinstance(limits, dict)
            or set(limits) != {"cpu_seconds", "address_space_bytes"}
            or any(
                not isinstance(pair, list)
                or len(pair) != 2
                or any(
                    not isinstance(value, int) or isinstance(value, bool) or value < -1
                    for value in pair
                )
                for pair in limits.values()
            )
        ):
            raise ContractError("Invalid observed process limits")
        if any(
            hard != -1 and (soft == -1 or soft > hard) for soft, hard in limits.values()
        ):
            raise ContractError("Observed process soft limit exceeds its hard limit")
    if document["status"] != "applied" or document["reason"] != "":
        raise ContractError("Selected process resource limits were not applied")
    for name in ("cpu_seconds", "address_space_bytes"):
        selected = requested[name]
        expected = (
            document["inherited"][name]
            if selected is None
            else (selected if isinstance(selected, list) else [selected, selected])
        )
        if document["actual"][name] != expected:
            raise ContractError("Actual process resource limits differ from request")
