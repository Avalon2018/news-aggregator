"""
Minimal local RSS aggregator.
Polls feeds, stores new items in SQLite, prints latest headlines.
"""

import sqlite3
from datetime import datetime
from pathlib import Path

import feedparser
import requests

from feeds import FEEDS

# Database lives in data/ relative to project root
DB_PATH = Path(__file__).resolve().parent.parent / "data" / "news.db"


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS articles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guid TEXT UNIQUE,
            title TEXT,
            link TEXT,
            summary TEXT,
            source TEXT,
            published TEXT,
            fetched_at TEXT
        )
    """)
    conn.commit()
    return conn


def fetch_feed(url: str) -> feedparser.FeedParserDict:
    """Fetch and parse a feed, with a simple timeout and user-agent."""
    headers = {"User-Agent": "LocalNewsAggregator/0.1"}
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    return feedparser.parse(resp.content)


def store_new_items(conn: sqlite3.Connection, source_name: str, parsed):
    """Insert items that are not already in the database. Return count of new items."""
    new_count = 0
    now = datetime.utcnow().isoformat()

    for entry in parsed.entries:
        guid = entry.get("id") or entry.get("link") or entry.get("title")
        if not guid:
            continue

        title = entry.get("title", "(no title)")
        link = entry.get("link", "")
        summary = entry.get("summary", entry.get("description", ""))[:500]
        published = entry.get("published", entry.get("updated", ""))

        try:
            conn.execute(
                """
                INSERT INTO articles (guid, title, link, summary, source, published, fetched_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (guid, title, link, summary, source_name, published, now),
            )
            new_count += 1
        except sqlite3.IntegrityError:
            # already stored
            pass

    conn.commit()
    return new_count


def print_recent(conn: sqlite3.Connection, limit: int = 10):
    print("\n--- Latest articles ---")
    rows = conn.execute(
        """
        SELECT source, title, published, link
        FROM articles
        ORDER BY fetched_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    for source, title, published, link in rows:
        print(f"[{source}] {title}")
        if published:
            print(f"  {published}")
        if link:
            print(f"  {link}")
        print()


def main():
    print("Local News Aggregator")
    print("---------------------")
    conn = init_db()

    total_new = 0
    for feed in FEEDS:
        name = feed["name"]
        url = feed["url"]
        print(f"Fetching {name} ...", end=" ")
        try:
            parsed = fetch_feed(url)
            added = store_new_items(conn, name, parsed)
            total_new += added
            print(f"{added} new")
        except Exception as exc:
            print(f"error: {exc}")

    print(f"\nDone. {total_new} new articles stored.")
    print_recent(conn)
    conn.close()


if __name__ == "__main__":
    main()