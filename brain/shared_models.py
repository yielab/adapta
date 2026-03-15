"""Shared data models"""

from typing import List
from pydantic import BaseModel


class AgentInfo(BaseModel):
    """Agent information"""

    id: str
    name: str
    description: str | None = None
    model: str
    capabilities: List[str]
    created: int
    active: bool = True
