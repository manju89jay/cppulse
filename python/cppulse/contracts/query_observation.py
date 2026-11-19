"""Private finite descriptive trace contracts; never cache closure authority."""

from __future__ import annotations

from importlib import resources
import json
from pathlib import PurePosixPath
from typing import Any

import jsonschema

from cppulse.errors import ContractError
from cppulse.identities import canonical_json_bytes


def validate_query_document(kind: str, document: dict[str, Any]) -> None:
    """Reject unknown fields, invalid finite limits and false cache authority."""
    if kind not in {"request", "report"}:
        raise ContractError("Unknown query observation contract")
    schema = json.loads(
        resources.files("cppulse.contracts")
        .joinpath("schemas/query_observation_private", kind + ".schema.json")
        .read_bytes()
    )
    try:
        jsonschema.Draft7Validator(schema).validate(document)
        raw = canonical_json_bytes(document)
        if len(raw) > (1024**2 if kind == "request" else 32 * 1024**2):
            raise ValueError("Query contract byte limit exceeded")
    except (jsonschema.ValidationError, ValueError, TypeError, RecursionError) as exc:
        raise ContractError("Invalid query observation " + kind) from exc
    if kind == "request":
        for key in ("native", "tracer"):
            path = PurePosixPath(document[key]["path"])
            if (
                not path.is_absolute()
                or ".." in path.parts
                or str(path) != document[key]["path"]
            ):
                raise ContractError(
                    "Selected trace tools require canonical absolute paths"
                )
        cwd = PurePosixPath(document["invocation"]["cwd"])
        if not cwd.is_absolute() or ".." in cwd.parts:
            raise ContractError("Selected trace cwd must be absolute")
        if document["invocation"]["argv"][0] != document["native"]["path"]:
            raise ContractError("Invocation changes selected native executable")
        if any(
            len(item.encode("utf-8")) > 4096 for item in document["invocation"]["argv"]
        ):
            raise ContractError(
                "Selected argv exceeds supported trace byte-string length"
            )
        if any("\x00" in item for item in document["invocation"]["argv"]):
            raise ContractError("Invalid selected argv bytes")
        for key, value in document["invocation"]["environment"].items():
            if len((key + "=" + value).encode("utf-8")) > 4096:
                raise ContractError(
                    "Selected environment exceeds supported trace byte-string length"
                )
            if (
                any(
                    token in key.upper()
                    for token in (
                        "TOKEN",
                        "SECRET",
                        "PASSWORD",
                        "CREDENTIAL",
                        "AUTH",
                        "PRIVATE_KEY",
                    )
                )
                or "\x00" in value
            ):
                raise ContractError(
                    "Sensitive/invalid trace environment is unsupported"
                )
    elif document["cache_eligible"] or document["closure"] != "unqualified":
        raise ContractError(
            "Descriptive query observations cannot authorize cache reuse"
        )
