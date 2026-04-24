import logging
from datetime import datetime, timezone

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import text

from app.database import SessionLocal

logger = logging.getLogger(__name__)


def cleanup_expired_links():
    db = SessionLocal()
    try:
        result = db.execute(text("DELETE FROM links WHERE expires_at < NOW()"))
        db.commit()
        logger.info(
            "Cleanup job: deleted %d expired rows at %s",
            result.rowcount,
            datetime.now(timezone.utc).isoformat(),
        )
    except Exception as exc:
        logger.error(
            "Cleanup job failed at %s: %s",
            datetime.now(timezone.utc).isoformat(),
            exc,
            exc_info=True,
        )
        db.rollback()
    finally:
        db.close()


def start_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler()
    scheduler.add_job(cleanup_expired_links, "interval", hours=1, id="cleanup")
    scheduler.start()
    cleanup_expired_links()
    return scheduler
