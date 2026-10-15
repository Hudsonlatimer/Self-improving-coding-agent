"""Structured replies from the planner, editor, repair, and strategist."""

from pydantic import BaseModel, Field


class Plan(BaseModel):
    file: str
    symbol: str = ""
    reason: str
    edit_production: bool = False
    instructions: str


class FileEdit(BaseModel):
    path: str
    content: str


class EditBatch(BaseModel):
    files: list[FileEdit] = Field(default_factory=list)


class StrategyUpdate(BaseModel):
    checklist: str
