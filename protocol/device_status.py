"""Device status report: built by the client, validated by the server."""

from typing import Annotated

from pydantic import BaseModel, Field, StringConstraints

# Agent names and statuses are bounded strings, not enums: clients release
# independently, and a client that learns a new agent must not be rejected by
# an older server.
AgentName = Annotated[str, StringConstraints(min_length=1, max_length=32)]


class AgentHealth(BaseModel):
    configured: bool
    endpoint_matches: bool | None = None
    configured_endpoint: str | None = Field(default=None, max_length=512)
    expected_endpoint: str | None = Field(default=None, max_length=512)
    status: str = Field(max_length=32)


class AgentDetected(BaseModel):
    found: bool


class DeviceStatusReport(BaseModel):
    device_name: str = Field(max_length=64)
    client_version: str | None = Field(default=None, max_length=32)
    client_commit: str | None = Field(default=None, max_length=64)
    collected_at: int
    agents: dict[AgentName, AgentHealth] = Field(max_length=32)
    detected: dict[AgentName, AgentDetected] = Field(max_length=32)
