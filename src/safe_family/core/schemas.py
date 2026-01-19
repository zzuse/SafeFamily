"""Schemas for serializing and deserializing core models."""

from pydantic import BaseModel, ConfigDict


class UserOut(BaseModel):
    """Schema for serializing User objects."""

    id: str | None = None
    username: str
    email: str

    model_config = ConfigDict(from_attributes=True)
