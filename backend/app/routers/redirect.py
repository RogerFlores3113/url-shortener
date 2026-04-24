import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Link

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/{short_code}")
def redirect_link(short_code: str, db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    link = (
        db.query(Link)
        .filter(Link.short_code == short_code, Link.expires_at > now)
        .first()
    )

    if not link:
        logger.info("Redirect 404: short_code=%s ts=%s", short_code, now.isoformat())
        return JSONResponse(status_code=404, content={"error": "Not found"})

    logger.info("Redirect 302: short_code=%s ts=%s", short_code, now.isoformat())
    return RedirectResponse(url=link.long_url, status_code=302)
