"""
TC-01 through TC-21 — all test cases from the spec.
"""
from datetime import datetime, timezone, timedelta

import pytest
from sqlalchemy import text


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_link(client, user_id="alice", long_url="https://example.com"):
    r = client.post("/api/links", json={"user_id": user_id, "long_url": long_url})
    assert r.status_code == 201
    return r.json()


# ---------------------------------------------------------------------------
# Happy Path
# ---------------------------------------------------------------------------

def test_tc01_create_link_valid(client):
    r = client.post(
        "/api/links",
        json={"user_id": "roger", "long_url": "https://www.notion.so/some-page"},
    )
    assert r.status_code == 201
    data = r.json()
    assert len(data["short_code"]) == 7
    assert data["long_url"] == "https://www.notion.so/some-page"
    created = datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))
    expires = datetime.fromisoformat(data["expires_at"].replace("Z", "+00:00"))
    diff = expires - created
    assert timedelta(days=6, hours=23) < diff <= timedelta(days=7, seconds=5)


def test_tc02_redirect_valid(client):
    link = make_link(client, long_url="https://example.com/page")
    r = client.get(f"/{link['short_code']}", follow_redirects=False)
    assert r.status_code == 302
    assert r.headers["location"] == "https://example.com/page"


def test_tc03_list_links_existing_user(client):
    make_link(client, user_id="roger")
    r = client.get("/api/links?user_id=roger")
    assert r.status_code == 200
    assert len(r.json()["links"]) >= 1


def test_tc04_list_links_unknown_user(client):
    r = client.get("/api/links?user_id=nobody")
    assert r.status_code == 200
    assert r.json()["links"] == []


def test_tc05_short_codes_sequential_unique(client):
    codes = [make_link(client)["short_code"] for _ in range(3)]
    assert len(set(codes)) == 3
    # Decode each back to integer and verify strictly increasing
    ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
    def decode(code):
        n = 0
        for ch in code:
            n = n * 62 + ALPHABET.index(ch)
        return n
    ids = [decode(c) for c in codes]
    assert ids[0] < ids[1] < ids[2]


# ---------------------------------------------------------------------------
# Expiry
# ---------------------------------------------------------------------------

def test_tc06_redirect_expired(client, db):
    link = make_link(client)
    db.execute(
        text("UPDATE links SET expires_at = NOW() - INTERVAL '1 second' WHERE short_code = :code"),
        {"code": link["short_code"]},
    )
    db.commit()
    r = client.get(f"/{link['short_code']}", follow_redirects=False)
    assert r.status_code == 404


def test_tc07_list_excludes_expired_by_default(client, db):
    active = make_link(client, long_url="https://active.com")
    expired = make_link(client, long_url="https://expired.com")
    db.execute(
        text("UPDATE links SET expires_at = NOW() - INTERVAL '1 second' WHERE short_code = :code"),
        {"code": expired["short_code"]},
    )
    db.commit()
    r = client.get("/api/links?user_id=alice")
    assert r.status_code == 200
    codes = [l["short_code"] for l in r.json()["links"]]
    assert active["short_code"] in codes
    assert expired["short_code"] not in codes


def test_tc08_list_include_expired(client, db):
    active = make_link(client, long_url="https://active.com")
    expired = make_link(client, long_url="https://expired.com")
    db.execute(
        text("UPDATE links SET expires_at = NOW() - INTERVAL '1 second' WHERE short_code = :code"),
        {"code": expired["short_code"]},
    )
    db.commit()
    r = client.get("/api/links?user_id=alice&include_expired=true")
    assert r.status_code == 200
    codes = [l["short_code"] for l in r.json()["links"]]
    assert active["short_code"] in codes
    assert expired["short_code"] in codes


def test_tc09_cleanup_deletes_expired(client, db):
    from app.scheduler import cleanup_expired_links

    link = make_link(client)
    db.execute(
        text("UPDATE links SET expires_at = NOW() - INTERVAL '1 second' WHERE short_code = :code"),
        {"code": link["short_code"]},
    )
    db.commit()

    cleanup_expired_links()

    row = db.execute(
        text("SELECT id FROM links WHERE short_code = :code"),
        {"code": link["short_code"]},
    ).fetchone()
    db.expire_all()
    assert row is None


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def test_tc10_create_missing_long_url(client):
    r = client.post("/api/links", json={"user_id": "roger"})
    assert r.status_code == 400
    assert "long_url" in r.json()["error"]


def test_tc11_create_invalid_scheme_javascript(client):
    r = client.post(
        "/api/links", json={"user_id": "roger", "long_url": "javascript:alert(1)"}
    )
    assert r.status_code == 400


def test_tc12_create_ftp_scheme_rejected(client):
    r = client.post(
        "/api/links",
        json={"user_id": "roger", "long_url": "ftp://files.example.com/file.txt"},
    )
    assert r.status_code == 400


def test_tc13_create_url_exceeds_2048(client):
    long_url = "http://x.com/" + "a" * 2036  # 14 + 2036 = 2050 > 2048
    r = client.post("/api/links", json={"user_id": "roger", "long_url": long_url})
    assert r.status_code == 400


def test_tc14_create_url_exactly_2048(client):
    long_url = "http://x.com/" + "a" * 2035  # 13 + 2035 = 2048
    assert len(long_url) == 2048
    r = client.post("/api/links", json={"user_id": "roger", "long_url": long_url})
    assert r.status_code == 201


def test_tc15_create_empty_user_id(client):
    r = client.post(
        "/api/links", json={"user_id": "", "long_url": "https://example.com"}
    )
    assert r.status_code == 400
    assert "user_id" in r.json()["error"]


def test_tc16_create_whitespace_user_id(client):
    r = client.post(
        "/api/links", json={"user_id": "   ", "long_url": "https://example.com"}
    )
    assert r.status_code == 400
    assert "user_id" in r.json()["error"]


def test_tc17_list_missing_user_id(client):
    r = client.get("/api/links")
    assert r.status_code == 400
    assert "user_id" in r.json()["error"]


# ---------------------------------------------------------------------------
# Redirect Behavior
# ---------------------------------------------------------------------------

def test_tc18_redirect_uses_302(client):
    link = make_link(client)
    r = client.get(f"/{link['short_code']}", follow_redirects=False)
    assert r.status_code == 302


def test_tc19_redirect_nonexistent(client):
    r = client.get("/0000000", follow_redirects=False)
    assert r.status_code == 404


# ---------------------------------------------------------------------------
# Short Code Generation
# ---------------------------------------------------------------------------

def test_tc20_first_link_short_code(client):
    r = client.post(
        "/api/links",
        json={"user_id": "roger", "long_url": "https://example.com"},
    )
    assert r.status_code == 201
    assert r.json()["short_code"] == "0000001"


def test_tc21_short_code_always_7_chars(client):
    for _ in range(10):
        link = make_link(client)
        assert len(link["short_code"]) == 7
