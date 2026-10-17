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
    baseline: bool = Field(default=False, strict=True)
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


class Occupy(Command):
    kind: Literal["occupy"] = "occupy"
    expected_revision: int = Field(ge=0, strict=True)
    expected_assignment_revision: int | None = Field(default=None, ge=0, strict=True)


class Release(Command):
    kind: Literal["release"] = "release"
    bout_id: str = Field(min_length=1, max_length=128)
    expected_revision: int = Field(ge=0, strict=True)
    expected_assignment_revision: int | None = Field(default=None, ge=0, strict=True)


class LaneControl(Command):
    # Automatische Bilder dürfen unmittelbare Bedienung nicht ständig ablehnen.
    expected_control_revision: int = Field(ge=0, strict=True)


class ModeChange(LaneControl):
    kind: Literal["mode"] = "mode"
    mode: Literal["manual", "automatic", "mixed"]


class ManualTarget(LaneControl):
    # Alte Clients/Journale begannen eine Einlage beim ersten manuellen Fall.
    # Die neue Tablet-Bedienung belegt ausdrücklich und korrigiert nur Zustände.
    start_bout: bool = Field(default=True, strict=True)
    kind: Literal["manual_target"] = "manual_target"
    target_id: int = Field(ge=1, le=5, strict=True)
    state: Literal["standing", "fallen", "unknown"]


class OverrideRelease(LaneControl):
    kind: Literal["override_release"] = "override_release"
    target_id: int = Field(ge=1, le=5, strict=True)


class ManualReset(LaneControl):
    kind: Literal["manual_reset"] = "manual_reset"


EventCommand = Annotated[Observation | Assignment | Occupy | Release | ModeChange | ManualTarget |
                         OverrideRelease | ManualReset, Field(discriminator="kind")]
