#!/usr/bin/env python3
"""
Seeds 10 well-known CTI RSS feeds. Idempotent — safe to run multiple times.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.session import SessionLocal
from app.models import Source
from app.db.base import new_uuid

SOURCES = [
    {"name": "Krebs on Security", "url": "https://krebsonsecurity.com/feed/"},
    {"name": "Bleeping Computer", "url": "https://www.bleepingcomputer.com/feed/"},
    {"name": "The Hacker News", "url": "https://feeds.feedburner.com/TheHackersNews"},
    {"name": "Schneier on Security", "url": "https://www.schneier.com/feed/atom"},
    {"name": "Threatpost", "url": "https://threatpost.com/feed/"},
    {"name": "Dark Reading", "url": "https://www.darkreading.com/rss.xml"},
    {"name": "SANS Internet Storm Center", "url": "https://isc.sans.edu/rssfeed_full.xml"},
    {"name": "Unit42 (Palo Alto)", "url": "https://unit42.paloaltonetworks.com/feed/"},
    {"name": "Securelist (Kaspersky)", "url": "https://securelist.com/feed/"},
    {"name": "Google Project Zero", "url": "https://googleprojectzero.blogspot.com/feeds/posts/default"},
]


def seed():
    db = SessionLocal()
    try:
        added = 0
        for src in SOURCES:
            exists = db.query(Source).filter(Source.url == src["url"]).first()
            if not exists:
                db.add(Source(id=new_uuid(), name=src["name"], url=src["url"], source_type="rss"))
                added += 1
        db.commit()
        print(f"Seeded {added} new sources ({len(SOURCES) - added} already existed)")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
