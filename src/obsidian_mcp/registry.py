"""Shared kwargs -> Pydantic model validation helper for tool handlers.

Every tool handler receives flat keyword arguments (see the SDK Addendum in
Plans/review-the-typescript-obsidian-mcp-parsed-shamir.md for why -- the installed
`mcp` SDK derives a tool's wire schema from a function's individual parameters,
not from a single Pydantic-model parameter). Each handler constructs its internal
Pydantic model from those kwargs via `validate()` for real validation, matching
TS's per-tool zod `.strict()`/non-strict behavior exactly, and mapping validation
failures to the same MCPError shape TS produced on `ZodError`.
"""

from __future__ import annotations

from typing import TypeVar

from mcp.shared.exceptions import MCPError
from mcp.types import INVALID_PARAMS
from pydantic import BaseModel, ValidationError

ModelT = TypeVar("ModelT", bound=BaseModel)


def validate(model_cls: type[ModelT], **kwargs: object) -> ModelT:
    try:
        return model_cls(**kwargs)
    except ValidationError as exc:
        formatted = "\n".join(f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in exc.errors())
        raise MCPError(INVALID_PARAMS, f"Invalid arguments:\n{formatted}") from exc
