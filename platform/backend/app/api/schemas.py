from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field

from app.domain.workflow import ApprovalDecision


class TaskCreate(BaseModel):
    title: Annotated[str, Field(min_length=1, max_length=240)]
    capability_pack: Annotated[str, Field(min_length=1, max_length=120)]
    source_mount_path: Annotated[str, Field(min_length=1, max_length=1000)]
    created_by: Annotated[str, Field(min_length=1, max_length=160)] = "operator"


class ApprovalDecisionRequest(BaseModel):
    decision: ApprovalDecision
    decided_by: Annotated[str, Field(min_length=1, max_length=160)]
    comment: Annotated[str | None, Field(max_length=2000)] = None
