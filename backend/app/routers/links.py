import logging
from datetime import datetime, timezone, timedelta
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.database import get_db
from app.models import Link
from app.schemas import LinkOut, LinksListOut, CreateLinkIn
from app.utils import to_short_code

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/api/links")
def list_links(
    user_id: str | None = Query(default=None),
    include_expired: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    if not user_id or not user_id.strip():
        logger.warning("Validation failure: user_id is required")
        return JSONResponse(status_code=400, content={"error": "user_id is required"})

    user_id = user_id.strip()
    now = datetime.now(timezone.utc)

    query = db.query(Link).filter(Link.user_id == user_id)
    if not include_expired:
        query = query.filter(Link.expires_at > now)

    links = query.all()
    return LinksListOut(links=[LinkOut.model_validate(link) for link in links])


@router.post("/api/links", status_code=201)
def create_link(body: CreateLinkIn, db: Session = Depends(get_db)):
    if not body.user_id or not body.user_id.strip():
        logger.warning("Validation failure: user_id is required")
        return JSONResponse(status_code=400, content={"error": "user_id is required"})

    user_id = body.user_id.strip()

    if not body.long_url or not body.long_url.strip():
        logger.warning("Validation failure: long_url is required, user_id=%s", user_id)
        return JSONResponse(status_code=400, content={"error": "long_url is required"})

    long_url = body.long_url.strip()

    if len(long_url) > 2048:
        logger.warning(
            "Validation failure: long_url exceeds 2048 chars, user_id=%s, url=%.100s",
            user_id,
            long_url,
        )
        return JSONResponse(
            status_code=400,
            content={"error": "long_url must not exceed 2048 characters"},
        )

    try:
        parsed = urlparse(long_url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise ValueError("invalid scheme or missing host")
    except Exception:
        logger.warning(
            "Validation failure: invalid URL, user_id=%s, url=%.100s", user_id, long_url
        )
        return JSONResponse(
            status_code=400,
            content={"error": "long_url must be a valid http or https URL"},
        )

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(days=7)

    link = Link(
        user_id=user_id,
        short_code="0000000",
        long_url=long_url,
        created_at=now,
        expires_at=expires_at,
    )
    db.add(link)
    db.flush()

    short_code = to_short_code(link.id)
    link.short_code = short_code
    db.commit()
    db.refresh(link)

    logger.info(
        "Link created: user_id=%s short_code=%s long_url=%.100s",
        user_id,
        short_code,
        long_url,
    )
    return JSONResponse(
        status_code=201,
        content=LinkOut.model_validate(link).model_dump(mode="json"),
    )
