from datetime import datetime
from pydantic import BaseModel


class LinkOut(BaseModel):
    short_code: str
    long_url: str
    created_at: datetime
    expires_at: datetime

    model_config = {"from_attributes": True}


class LinksListOut(BaseModel):
    links: list[LinkOut]


class CreateLinkIn(BaseModel):
    user_id: str | None = None
    long_url: str | None = None
