"""Validierte Befehle für Bedienplätze und alle Erfassungsquellen."""

from datetime import datetime
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Command(Model):
    event_id: str = Field(default_factory=lambda: str(uuid4()), min_length=1, max_length=128)
    lane_id: int = Field(gt=0, strict=True)


class Observation(Command):
    kind: Literal["target", "reset"]
    source: str = Field(min_length=1, max_length=128)
    observed_at: datetime
    target_id: int | None = Field(default=None, ge=1, le=5, strict=True)
    state: Literal["standing", "fallen", "unknown"] | None = None

    @field_validator("observed_at")
    @classmethod
    def timezone_required(cls, value):
        if value.tzinfo is None:
            raise ValueError("Beobachtungszeit benötigt eine Zeitzone.")
        return value


class Assignment(Command):
    kind: Literal["assign"] = "assign"
    bib: int = Field(gt=0, strict=True)
    bout_id: str | None = Field(default=None, min_length=1, max_length=128)
    expected_revision: int = Field(ge=0, strict=True)
    # Optional für alte Clients/Journale; Tablets prüfen nur Bedienänderungen.
    expected_assignment_revision: int | None = Field(default=None, ge=0, strict=True)
    # Eingabebeginn ohne Einlage: nicht auf eine spätere Einlage umleiten.
    bout_after_sequence: int | None = Field(default=None, ge=0, strict=True)


class Release(Command):
    kind: Literal["release"] = "release"
    bout_id: str = Field(min_length=1, max_length=128)
    expected_revision: int = Field(ge=0, strict=True)
    expected_assignment_revision: int | None = Field(default=None, ge=0, strict=True)


EventCommand = Annotated[Observation | Assignment | Release, Field(discriminator="kind")]
