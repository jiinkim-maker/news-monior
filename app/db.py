import os
import sqlite3
from datetime import datetime
import json

from app.utils.security import hash_password

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "news_monitor.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def now_iso():
    return datetime.now().isoformat(timespec="seconds")


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    # users
    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT NOT NULL UNIQUE,
        password_hash TEXT NOT NULL,
        display_name TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'admin',
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """)

    # keyword rules
    cur.execute("""
    CREATE TABLE IF NOT EXISTS keyword_rules (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        rule_type TEXT NOT NULL,
        keyword TEXT NOT NULL,
        match_rule TEXT NOT NULL,
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        created_by TEXT,
        updated_by TEXT
    )
    """)

    # keyword analysis runs
    cur.execute("""
    CREATE TABLE IF NOT EXISTS keyword_analysis_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        input_text TEXT NOT NULL,
        input_count INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'completed',
        total_links INTEGER NOT NULL DEFAULT 0,
        total_articles INTEGER NOT NULL DEFAULT 0,
        flagged_articles INTEGER NOT NULL DEFAULT 0,
        missing_required_articles INTEGER NOT NULL DEFAULT 0,
        error_articles INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        created_by TEXT,
        updated_by TEXT
    )
    """)

    # keyword analysis article results
    cur.execute("""
    CREATE TABLE IF NOT EXISTS keyword_analysis_articles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER NOT NULL,
        short_url TEXT,
        long_url TEXT,
        title TEXT,
        published_at_raw TEXT,
        published_at_normalized TEXT,
        body_text TEXT,
        tags_json TEXT NOT NULL DEFAULT '[]',
        categories_json TEXT NOT NULL DEFAULT '[]',
        captions_json TEXT NOT NULL DEFAULT '[]',
        forbidden_findings_json TEXT NOT NULL DEFAULT '[]',
        required_missing_json TEXT NOT NULL DEFAULT '[]',
        forbidden_found_count INTEGER NOT NULL DEFAULT 0,
        required_missing_count INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'clean',
        error TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        created_by TEXT,
        updated_by TEXT,
        FOREIGN KEY (run_id) REFERENCES keyword_analysis_runs(id)
    )
    """)

    # keyword article bookmarks (shared)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS keyword_article_bookmarks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        article_key TEXT NOT NULL UNIQUE,
        short_url TEXT,
        title TEXT,
        bookmark_level INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        updated_by TEXT
    )
    """)

    # shared bookmarks
    cur.execute("""
    CREATE TABLE IF NOT EXISTS shared_bookmarks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        target_type TEXT NOT NULL,
        target_key TEXT NOT NULL UNIQUE,
        title TEXT,
        short_url TEXT,
        bookmark_level INTEGER NOT NULL DEFAULT 0,
        note TEXT,
        extra_json TEXT NOT NULL DEFAULT '{}',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        updated_by TEXT
    )
    """)


    # media analysis runs
    cur.execute("""
    CREATE TABLE IF NOT EXISTS media_analysis_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        input_text TEXT NOT NULL,
        total_links INTEGER NOT NULL DEFAULT 0,
        total_media_count INTEGER NOT NULL DEFAULT 0,
        error_count INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'completed',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        created_by TEXT,
        updated_by TEXT
    )
    """)

    # media analysis items
    cur.execute("""
    CREATE TABLE IF NOT EXISTS media_analysis_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER NOT NULL,
        short_url TEXT,
        long_url TEXT,
        article_title TEXT,
        media_url TEXT,
        media_type TEXT,
        filename TEXT,
        width INTEGER,
        height INTEGER,
        size_bytes INTEGER,
        size_display TEXT,
        preview_url TEXT,
        error TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        created_by TEXT,
        updated_by TEXT,
        FOREIGN KEY (run_id) REFERENCES media_analysis_runs(id)
    )
    """)
    # banner monitor runs
    cur.execute("""
    CREATE TABLE IF NOT EXISTS banner_monitor_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_type TEXT NOT NULL,
        target_code TEXT,
        total_targets INTEGER NOT NULL DEFAULT 0,
        completed_targets INTEGER NOT NULL DEFAULT 0,
        error_targets INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'completed',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        created_by TEXT,
        updated_by TEXT
    )
    """)

    # banner monitor snapshots
    cur.execute("""
    CREATE TABLE IF NOT EXISTS banner_monitor_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER NOT NULL,
        region TEXT NOT NULL,
        country TEXT NOT NULL,
        code TEXT NOT NULL,
        url_code TEXT,
        page_url TEXT NOT NULL,
        generation TEXT NOT NULL,
        page_title TEXT,
        kv_json TEXT NOT NULL,
        banner_json TEXT NOT NULL,
        kv_count INTEGER NOT NULL DEFAULT 0,
        banner_count INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        created_by TEXT,
        updated_by TEXT,
        FOREIGN KEY (run_id) REFERENCES banner_monitor_runs(id)
    )
    """)

    conn.commit()
    conn.close()

    seed_admin_user()


# ---------------- users ----------------

def seed_admin_user():
    existing_user = get_user_by_username("Admin")
    if existing_user:
        return

    now = now_iso()

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO users (
        username,
        password_hash,
        display_name,
        role,
        is_active,
        created_at,
        updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        "Admin",
        hash_password("Cheilnews!"),
        "Admin",
        "admin",
        1,
        now,
        now,
    ))

    conn.commit()
    conn.close()


def get_user_by_username(username: str):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    SELECT *
    FROM users
    WHERE username = ?
    LIMIT 1
    """, (username,))

    row = cur.fetchone()
    conn.close()

    return dict(row) if row else None

def create_user(username: str, password_hash: str, display_name: str, role: str = "user"):
    conn = get_connection()
    cur = conn.cursor()
    now = now_iso()

    cur.execute("""
    INSERT INTO users (
        username,
        password_hash,
        display_name,
        role,
        is_active,
        created_at,
        updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        username,
        password_hash,
        display_name,
        role,
        1,
        now,
        now,
    ))

    conn.commit()
    conn.close()


def list_users():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    SELECT *
    FROM users
    ORDER BY id DESC
    """)

    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def update_user_password(username: str, password_hash: str):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    UPDATE users
    SET password_hash = ?, updated_at = ?
    WHERE username = ?
    """, (
        password_hash,
        now_iso(),
        username,
    ))

    conn.commit()
    conn.close()

def find_users_by_display_name(display_name: str):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    SELECT *
    FROM users
    WHERE display_name = ?
    ORDER BY id DESC
    """, (display_name,))

    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_user_by_id(user_id: int):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    SELECT *
    FROM users
    WHERE id = ?
    """, (user_id,))

    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def delete_user_by_id(user_id: int):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    DELETE FROM users
    WHERE id = ?
    """, (user_id,))

    conn.commit()
    conn.close()

# ---------------- keyword rules ----------------

def create_keyword_rule(rule_type: str, keyword: str, match_rule: str, created_by: str):
    conn = get_connection()
    cur = conn.cursor()
    now = now_iso()

    cur.execute("""
    INSERT INTO keyword_rules (
        rule_type,
        keyword,
        match_rule,
        is_active,
        created_at,
        updated_at,
        created_by,
        updated_by
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        rule_type,
        keyword,
        match_rule,
        1,
        now,
        now,
        created_by,
        created_by,
    ))

    conn.commit()
    conn.close()


def list_keyword_rules(rule_type: str | None = None):
    conn = get_connection()
    cur = conn.cursor()

    if rule_type:
        cur.execute("""
        SELECT *
        FROM keyword_rules
        WHERE rule_type = ?
        ORDER BY is_active DESC, id DESC
        """, (rule_type,))
    else:
        cur.execute("""
        SELECT *
        FROM keyword_rules
        ORDER BY rule_type, is_active DESC, id DESC
        """)

    rows = cur.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def get_active_keyword_rules(rule_type: str):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    SELECT *
    FROM keyword_rules
    WHERE rule_type = ? AND is_active = 1
    ORDER BY id ASC
    """, (rule_type,))

    rows = cur.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def delete_keyword_rule(rule_id: int):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    DELETE FROM keyword_rules
    WHERE id = ?
    """, (rule_id,))

    conn.commit()
    conn.close()


def update_keyword_rule_active(rule_id: int, is_active: bool, updated_by: str):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    UPDATE keyword_rules
    SET is_active = ?, updated_at = ?, updated_by = ?
    WHERE id = ?
    """, (
        1 if is_active else 0,
        now_iso(),
        updated_by,
        rule_id,
    ))

    conn.commit()
    conn.close()


# ---------------- keyword analysis ----------------

def create_keyword_analysis_run(
    input_text: str,
    input_count: int,
    total_links: int,
    total_articles: int,
    flagged_articles: int,
    missing_required_articles: int,
    error_articles: int,
    created_by: str,
):
    conn = get_connection()
    cur = conn.cursor()
    now = now_iso()

    cur.execute("""
    INSERT INTO keyword_analysis_runs (
        input_text,
        input_count,
        status,
        total_links,
        total_articles,
        flagged_articles,
        missing_required_articles,
        error_articles,
        created_at,
        updated_at,
        created_by,
        updated_by
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        input_text,
        input_count,
        "completed",
        total_links,
        total_articles,
        flagged_articles,
        missing_required_articles,
        error_articles,
        now,
        now,
        created_by,
        created_by,
    ))

    run_id = cur.lastrowid
    conn.commit()
    conn.close()
    return run_id


def create_keyword_analysis_article(
    run_id: int,
    short_url: str,
    long_url: str,
    title: str,
    published_at_raw: str,
    published_at_normalized: str,
    body_text: str,
    tags: list,
    categories: list,
    captions: list,
    forbidden_findings: list,
    required_missing: list,
    forbidden_found_count: int,
    required_missing_count: int,
    status: str,
    error: str | None,
    created_by: str,
):
    conn = get_connection()
    cur = conn.cursor()
    now = now_iso()

    cur.execute("""
    INSERT INTO keyword_analysis_articles (
        run_id,
        short_url,
        long_url,
        title,
        published_at_raw,
        published_at_normalized,
        body_text,
        tags_json,
        categories_json,
        captions_json,
        forbidden_findings_json,
        required_missing_json,
        forbidden_found_count,
        required_missing_count,
        status,
        error,
        created_at,
        updated_at,
        created_by,
        updated_by
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        run_id,
        short_url,
        long_url,
        title,
        published_at_raw,
        published_at_normalized,
        body_text,
        json.dumps(tags or [], ensure_ascii=False),
        json.dumps(categories or [], ensure_ascii=False),
        json.dumps(captions or [], ensure_ascii=False),
        json.dumps(forbidden_findings or [], ensure_ascii=False),
        json.dumps(required_missing or [], ensure_ascii=False),
        forbidden_found_count,
        required_missing_count,
        status,
        error,
        now,
        now,
        created_by,
        created_by,
    ))

    conn.commit()
    conn.close()


def get_latest_keyword_analysis_run():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    SELECT *
    FROM keyword_analysis_runs
    ORDER BY id DESC
    LIMIT 1
    """)

    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def get_keyword_analysis_articles_by_run(run_id: int):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    SELECT *
    FROM keyword_analysis_articles
    WHERE run_id = ?
    ORDER BY id ASC
    """, (run_id,))

    rows = cur.fetchall()
    conn.close()

    results = []
    for row in rows:
        item = dict(row)
        item["tags"] = json.loads(item["tags_json"] or "[]")
        item["categories"] = json.loads(item["categories_json"] or "[]")
        item["captions"] = json.loads(item["captions_json"] or "[]")
        item["forbidden_findings"] = json.loads(item["forbidden_findings_json"] or "[]")
        item["required_missing"] = json.loads(item["required_missing_json"] or "[]")
        results.append(item)

    return results


def get_recent_keyword_analysis_runs(limit: int = 20):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    SELECT *
    FROM keyword_analysis_runs
    ORDER BY id DESC
    LIMIT ?
    """, (limit,))

    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_recent_keyword_analysis_articles(limit: int = 20):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    SELECT *
    FROM keyword_analysis_articles
    ORDER BY id DESC
    LIMIT ?
    """, (limit,))

    rows = cur.fetchall()
    conn.close()

    results = []
    for row in rows:
        item = dict(row)
        item["tags"] = json.loads(item["tags_json"] or "[]")
        item["categories"] = json.loads(item["categories_json"] or "[]")
        item["captions"] = json.loads(item["captions_json"] or "[]")
        item["forbidden_findings"] = json.loads(item["forbidden_findings_json"] or "[]")
        item["required_missing"] = json.loads(item["required_missing_json"] or "[]")
        results.append(item)

    return results



# ---------------- media analysis ----------------

def create_media_analysis_run(
    input_text: str,
    total_links: int,
    total_media_count: int,
    error_count: int,
    created_by: str,
):
    conn = get_connection()
    cur = conn.cursor()
    now = now_iso()

    cur.execute("""
    INSERT INTO media_analysis_runs (
        input_text,
        total_links,
        total_media_count,
        error_count,
        status,
        created_at,
        updated_at,
        created_by,
        updated_by
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        input_text,
        total_links,
        total_media_count,
        error_count,
        "completed",
        now,
        now,
        created_by,
        created_by,
    ))

    run_id = cur.lastrowid
    conn.commit()
    conn.close()
    return run_id


def create_media_analysis_item(
    run_id: int,
    short_url: str,
    long_url: str,
    article_title: str,
    media_url: str,
    media_type: str,
    filename: str,
    width: int | None,
    height: int | None,
    size_bytes: int | None,
    size_display: str,
    preview_url: str,
    error: str | None,
    created_by: str,
):
    conn = get_connection()
    cur = conn.cursor()
    now = now_iso()

    cur.execute("""
    INSERT INTO media_analysis_items (
        run_id,
        short_url,
        long_url,
        article_title,
        media_url,
        media_type,
        filename,
        width,
        height,
        size_bytes,
        size_display,
        preview_url,
        error,
        created_at,
        updated_at,
        created_by,
        updated_by
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        run_id,
        short_url,
        long_url,
        article_title,
        media_url,
        media_type,
        filename,
        width,
        height,
        size_bytes,
        size_display,
        preview_url,
        error,
        now,
        now,
        created_by,
        created_by,
    ))

    conn.commit()
    conn.close()


def get_latest_media_analysis_run():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    SELECT *
    FROM media_analysis_runs
    ORDER BY id DESC
    LIMIT 1
    """)

    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def get_media_analysis_items_by_run(run_id: int):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    SELECT *
    FROM media_analysis_items
    WHERE run_id = ?
    ORDER BY id ASC
    """, (run_id,))

    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]



def get_recent_media_analysis_items(limit: int = 20):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    SELECT *
    FROM media_analysis_items
    ORDER BY id DESC
    LIMIT ?
    """, (limit,))

    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]



def create_banner_monitor_run(
    run_type: str,
    target_code: str | None,
    total_targets: int,
    completed_targets: int,
    error_targets: int,
    created_by: str,
):
    conn = get_connection()
    cur = conn.cursor()
    now = now_iso()

    cur.execute("""
    INSERT INTO banner_monitor_runs (
        run_type,
        target_code,
        total_targets,
        completed_targets,
        error_targets,
        status,
        created_at,
        updated_at,
        created_by,
        updated_by
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        run_type,
        target_code,
        total_targets,
        completed_targets,
        error_targets,
        "completed",
        now,
        now,
        created_by,
        created_by,
    ))

    run_id = cur.lastrowid
    conn.commit()
    conn.close()
    return run_id


def create_banner_monitor_snapshot(
    run_id: int,
    region: str,
    country: str,
    code: str,
    url_code: str,
    page_url: str,
    generation: str,
    page_title: str,
    kv_items: list,
    banner_items: list,
    created_by: str,
):
    conn = get_connection()
    cur = conn.cursor()
    now = now_iso()

    cur.execute("""
    INSERT INTO banner_monitor_snapshots (
        run_id,
        region,
        country,
        code,
        url_code,
        page_url,
        generation,
        page_title,
        kv_json,
        banner_json,
        kv_count,
        banner_count,
        created_at,
        updated_at,
        created_by,
        updated_by
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        run_id,
        region,
        country,
        code,
        url_code,
        page_url,
        generation,
        page_title,
        json.dumps(kv_items or [], ensure_ascii=False),
        json.dumps(banner_items or [], ensure_ascii=False),
        len(kv_items or []),
        len(banner_items or []),
        now,
        now,
        created_by,
        created_by,
    ))

    conn.commit()
    conn.close()


def get_latest_banner_monitor_run():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    SELECT *
    FROM banner_monitor_runs
    ORDER BY id DESC
    LIMIT 1
    """)

    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def get_banner_monitor_snapshots_by_run(run_id: int):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    SELECT s.*, r.run_type
    FROM banner_monitor_snapshots s
    LEFT JOIN banner_monitor_runs r ON s.run_id = r.id
    WHERE s.run_id = ?
    ORDER BY s.id ASC
    """, (run_id,))

    rows = cur.fetchall()
    conn.close()

    results = []
    for row in rows:
        item = dict(row)
        item["kv_items"] = json.loads(item["kv_json"] or "[]")
        item["banner_items"] = json.loads(item["banner_json"] or "[]")
        results.append(item)

    return results


def get_banner_monitor_snapshots_by_code(code: str, limit: int = 20):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    SELECT s.*, r.run_type
    FROM banner_monitor_snapshots s
    LEFT JOIN banner_monitor_runs r ON s.run_id = r.id
    WHERE s.code = ?
    ORDER BY s.id DESC
    LIMIT ?
    """, (code, limit))

    rows = cur.fetchall()
    conn.close()

    results = []
    for row in rows:
        item = dict(row)
        item["kv_items"] = json.loads(item["kv_json"] or "[]")
        item["banner_items"] = json.loads(item["banner_json"] or "[]")
        results.append(item)

    return results


# ---------------- shared bookmarks ----------------

def get_bookmark_level(article_key: str):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    SELECT bookmark_level
    FROM keyword_article_bookmarks
    WHERE article_key = ?
    LIMIT 1
    """, (article_key,))

    row = cur.fetchone()
    conn.close()

    if not row:
        return 0
    return row["bookmark_level"] or 0


def upsert_bookmark(article_key: str, short_url: str, title: str, bookmark_level: int, updated_by: str):
    conn = get_connection()
    cur = conn.cursor()
    now = now_iso()

    cur.execute("""
    SELECT id
    FROM keyword_article_bookmarks
    WHERE article_key = ?
    LIMIT 1
    """, (article_key,))

    existing = cur.fetchone()

    if existing:
        cur.execute("""
        UPDATE keyword_article_bookmarks
        SET short_url = ?, title = ?, bookmark_level = ?, updated_at = ?, updated_by = ?
        WHERE article_key = ?
        """, (
            short_url,
            title,
            bookmark_level,
            now,
            updated_by,
            article_key,
        ))
    else:
        cur.execute("""
        INSERT INTO keyword_article_bookmarks (
            article_key,
            short_url,
            title,
            bookmark_level,
            created_at,
            updated_at,
            updated_by
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            article_key,
            short_url,
            title,
            bookmark_level,
            now,
            now,
            updated_by,
        ))

    conn.commit()
    conn.close()


def cycle_bookmark_level(article_key: str, short_url: str, title: str, updated_by: str):
    current_level = get_bookmark_level(article_key)

    if current_level == 0:
        next_level = 1
    elif current_level == 1:
        next_level = 2
    else:
        next_level = 0

    upsert_bookmark(
        article_key=article_key,
        short_url=short_url,
        title=title,
        bookmark_level=next_level,
        updated_by=updated_by,
    )

    return next_level


def list_bookmarked_articles():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    SELECT *
    FROM keyword_article_bookmarks
    WHERE bookmark_level > 0
    ORDER BY updated_at DESC, id DESC
    """)

    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]

# ---------------- shared bookmarks ----------------

def get_shared_bookmark(target_key: str):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    SELECT *
    FROM shared_bookmarks
    WHERE target_key = ?
    LIMIT 1
    """, (target_key,))

    row = cur.fetchone()
    conn.close()

    return dict(row) if row else None


def get_shared_bookmark_level(target_key: str):
    row = get_shared_bookmark(target_key)
    if not row:
        return 0
    return row.get("bookmark_level", 0) or 0


def upsert_shared_bookmark(
    target_type: str,
    target_key: str,
    title: str,
    short_url: str,
    bookmark_level: int,
    note: str,
    extra: dict,
    updated_by: str,
):
    conn = get_connection()
    cur = conn.cursor()
    now = now_iso()
    extra_json = json.dumps(extra or {}, ensure_ascii=False)

    cur.execute("""
    SELECT id
    FROM shared_bookmarks
    WHERE target_key = ?
    LIMIT 1
    """, (target_key,))

    existing = cur.fetchone()

    if existing:
        cur.execute("""
        UPDATE shared_bookmarks
        SET
            target_type = ?,
            title = ?,
            short_url = ?,
            bookmark_level = ?,
            note = ?,
            extra_json = ?,
            updated_at = ?,
            updated_by = ?
        WHERE target_key = ?
        """, (
            target_type,
            title,
            short_url,
            bookmark_level,
            note,
            extra_json,
            now,
            updated_by,
            target_key,
        ))
    else:
        cur.execute("""
        INSERT INTO shared_bookmarks (
            target_type,
            target_key,
            title,
            short_url,
            bookmark_level,
            note,
            extra_json,
            created_at,
            updated_at,
            updated_by
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            target_type,
            target_key,
            title,
            short_url,
            bookmark_level,
            note,
            extra_json,
            now,
            now,
            updated_by,
        ))

    conn.commit()
    conn.close()


def save_shared_bookmark(
    target_type: str,
    target_key: str,
    title: str,
    short_url: str,
    bookmark_level: int,
    note: str,
    extra: dict,
    updated_by: str,
):
    upsert_shared_bookmark(
        target_type=target_type,
        target_key=target_key,
        title=title,
        short_url=short_url,
        bookmark_level=bookmark_level,
        note=note,
        extra=extra,
        updated_by=updated_by,
    )
    return bookmark_level


def list_shared_bookmarks(
    bookmark_level: int | None = None,
    target_type: str | None = None,
):
    conn = get_connection()
    cur = conn.cursor()

    query = """
    SELECT *
    FROM shared_bookmarks
    WHERE bookmark_level > 0
    """
    params = []

    if bookmark_level in (1, 2):
        query += " AND bookmark_level = ?"
        params.append(bookmark_level)

    if target_type:
        query += " AND target_type = ?"
        params.append(target_type)

    query += " ORDER BY updated_at DESC, id DESC"

    cur.execute(query, tuple(params))
    rows = cur.fetchall()
    conn.close()

    results = []
    for row in rows:
        item = dict(row)
        try:
            item["extra"] = json.loads(item.get("extra_json") or "{}")
        except Exception:
            item["extra"] = {}
        results.append(item)

    return results


def get_recent_media_analysis_items(limit: int = 20):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    SELECT *
    FROM media_analysis_items
    ORDER BY id DESC
    LIMIT ?
    """, (limit,))

    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]



def get_banner_monitor_snapshot_by_id(snapshot_id: int):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    SELECT s.*, r.run_type
    FROM banner_monitor_snapshots s
    LEFT JOIN banner_monitor_runs r ON s.run_id = r.id
    WHERE s.id = ?
    LIMIT 1
    """, (snapshot_id,))

    row = cur.fetchone()
    conn.close()

    if not row:
        return None

    item = dict(row)
    item["kv_items"] = json.loads(item["kv_json"] or "[]")
    item["banner_items"] = json.loads(item["banner_json"] or "[]")
    return item