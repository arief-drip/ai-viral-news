#!/usr/bin/env python3
"""
AI Viral News — Aggregator & RSS Feed Generator
Polls Reddit (public JSON) + RSS sources → filters AI keywords + engagement → RSS feed
"""

import json
import os
import re
import sys
import time
import traceback
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import format_datetime

import requests
from feedgen.feed import FeedGenerator
import yaml

# ─── Paths ───────────────────────────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config.yaml")

def load_config():
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)

CONFIG = load_config()

# ─── Headers (browser-like to avoid Reddit 403) ──────────────────────────────
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.5",
}

# ─── Keyword matching ────────────────────────────────────────────────────────
KEYWORD_PATTERNS = [
    re.compile(r'\b' + re.escape(kw) + r'\b', re.IGNORECASE)
    for kw in CONFIG["keywords"]
]

def matches_keywords(text: str) -> bool:
    """Check if text contains any AI keyword."""
    if not text:
        return False
    for pattern in KEYWORD_PATTERNS:
        if pattern.search(text):
            return True
    return False


# ═══════════════════════════════════════════════════════════════════════════════
#  REDDIT POLLER (Public JSON — no API key needed!)
# ═══════════════════════════════════════════════════════════════════════════════

def fetch_reddit_posts():
    """Fetch posts from configured subreddits via public JSON endpoint."""
    entries = []
    cfg = CONFIG["reddit"]

    for subreddit in cfg["subreddits"]:
        urls = [
            f"https://www.reddit.com/r/{subreddit}/{cfg['sort']}.json?t={cfg['time_filter']}&limit=25",
            f"https://old.reddit.com/r/{subreddit}/{cfg['sort']}.json?t={cfg['time_filter']}&limit=25",
        ]
        resp = None
        for url in urls:
            try:
                resp = requests.get(url, headers=HEADERS, timeout=15)
                if resp.status_code == 200:
                    break
            except Exception:
                continue
        if resp is None or resp.status_code != 200:
            print(f"  ⚠️  r/{subreddit}: HTTP {resp.status_code if resp else 'timeout'}")
            continue

        data = resp.json()
        posts = data.get("data", {}).get("children", [])

        for post_data in posts:
            post = post_data.get("data", {})
            title = post.get("title", "")
            selftext = post.get("selftext", "")
            ups = post.get("ups", 0)
            url = post.get("url", "")
            permalink = post.get("permalink", "")
            num_comments = post.get("num_comments", 0)
            created_utc = post.get("created_utc", 0)
            post_id = post.get("id", "")
            domain = post.get("domain", "")

            # Skip stickied posts
            if post.get("stickied", False):
                continue

            # Skip if below upvote threshold
            if ups < cfg["min_upvotes"]:
                continue

            # Check keywords in title or selftext
            text_to_check = f"{title} {selftext}"
            if not matches_keywords(text_to_check):
                continue

            # Build entry
            reddit_link = f"https://reddit.com{permalink}"
            description = selftext[:500] + ("..." if len(selftext) > 500 else "") if selftext else title
            if domain and domain != "self." + subreddit:
                description += f"\n\n🔗 Source: {domain}"

            entries.append({
                "id": f"reddit-{post_id}",
                "platform": "Reddit",
                "icon": "🤖",
                "title": title,
                "description": description,
                "link": url if url.startswith("http") else reddit_link,
                "source_link": reddit_link,
                "engagement": f"👍 {ups:,} · 💬 {num_comments}",
                "subreddit": f"r/{subreddit}",
                "published": datetime.fromtimestamp(created_utc, tz=timezone.utc),
            })

        print(f"  ✅ r/{subreddit}: {len(posts)} posts → {sum(1 for p in entries if p['subreddit'] == f'r/{subreddit}')} matches")

    return entries


# ═══════════════════════════════════════════════════════════════════════════════
#  RSS SOURCES POLLER
# ═══════════════════════════════════════════════════════════════════════════════

def fetch_rss_sources():
    """Fetch and parse RSS feeds from AI/tech blogs."""
    entries = []
    for source in CONFIG["rss_sources"]:
        name = source["name"]
        url = source["url"]
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            if resp.status_code != 200:
                print(f"  ⚠️  {name}: HTTP {resp.status_code}")
                continue

            root = ET.fromstring(resp.content)

            # Handle both RSS 2.0 and Atom
            ns = {}
            if root.tag == "{http://www.w3.org/2005/Atom}feed":
                is_atom = True
                items = root.findall("{http://www.w3.org/2005/Atom}entry")
            elif root.tag == "rss":
                is_atom = False
                items = root.findall(".//item")
            else:
                print(f"  ⚠️  {name}: Unknown feed format (tag={root.tag})")
                continue

            count = 0
            for item in items[:10]:  # max 10 per source
                try:
                    if is_atom:
                        title_el = item.find("{http://www.w3.org/2005/Atom}title")
                        link_el = item.find("{http://www.w3.org/2005/Atom}link")
                        desc_el = item.find("{http://www.w3.org/2005/Atom}summary")
                        pub_el = item.find("{http://www.w3.org/2005/Atom}published")
                    else:
                        title_el = item.find("title")
                        link_el = item.find("link")
                        desc_el = item.find("description")
                        pub_el = item.find("pubDate")

                    title = title_el.text if title_el is not None and title_el.text else ""
                    link = link_el.text if link_el is not None else ""
                    if link_el is not None and is_atom:
                        link = link_el.get("href", link_el.text or "")
                    description = ""
                    if desc_el is not None and desc_el.text:
                        description = desc_el.text[:500] + ("..." if len(desc_el.text) > 500 else "")
                    pub_text = pub_el.text if pub_el is not None and pub_el.text else ""

                    if not title:
                        continue

                    # Parse published time
                    published = datetime.now(timezone.utc)
                    if pub_text:
                        for fmt in [
                            "%a, %d %b %Y %H:%M:%S %z",
                            "%a, %d %b %Y %H:%M:%S %Z",
                            "%Y-%m-%dT%H:%M:%S%z",
                            "%Y-%m-%dT%H:%M:%S.%f%z",
                            "%Y-%m-%dT%H:%M:%SZ",
                        ]:
                            try:
                                published = datetime.strptime(pub_text, fmt)
                                if published.tzinfo is None:
                                    published = published.replace(tzinfo=timezone.utc)
                                break
                            except ValueError:
                                continue

                    # Check keywords
                    if not matches_keywords(title + " " + description):
                        continue

                    entries.append({
                        "id": f"rss-{name}-{count}",
                        "platform": name,
                        "icon": "📰",
                        "title": title,
                        "description": description,
                        "link": link,
                        "source_link": link,
                        "engagement": f"📡 {name}",
                        "subreddit": "",
                        "published": published,
                    })
                    count += 1
                except Exception as e:
                    print(f"    ⚠️  {name} item error: {e}")
                    continue

            print(f"  ✅ {name}: {count} matches")

        except ET.ParseError as e:
            print(f"  ⚠️  {name}: XML parse error: {e}")
        except Exception as e:
            print(f"  ❌ {name}: {e}")

    return entries


# ═══════════════════════════════════════════════════════════════════════════════
#  HACKER NEWS POLLER (bonus source!)
# ═══════════════════════════════════════════════════════════════════════════════

def fetch_hackernews():
    """Fetch top AI-related posts from Hacker News (free API)."""
    entries = []
    try:
        # Get top story IDs
        resp = requests.get("https://hacker-news.firebaseio.com/v0/topstories.json", timeout=15)
        if resp.status_code != 200:
            return entries
        top_ids = resp.json()[:30]  # top 30

        for story_id in top_ids:
            try:
                sresp = requests.get(f"https://hacker-news.firebaseio.com/v0/item/{story_id}.json", timeout=10)
                if sresp.status_code != 200:
                    continue
                story = sresp.json()
                if not story:
                    continue

                title = story.get("title", "")
                url = story.get("url", "") or f"https://news.ycombinator.com/item?id={story_id}"
                score = story.get("score", 0)
                created_utc = story.get("time", 0)
                story_type = story.get("type", "")

                if story_type != "story":
                    continue
                if score < 50:  # min HN score
                    continue
                if not matches_keywords(title):
                    continue

                entries.append({
                    "id": f"hn-{story_id}",
                    "platform": "Hacker News",
                    "icon": "📰",
                    "title": title,
                    "description": title,
                    "link": url,
                    "source_link": f"https://news.ycombinator.com/item?id={story_id}",
                    "engagement": f"👍 {score:,}",
                    "subreddit": "",
                    "published": datetime.fromtimestamp(created_utc, tz=timezone.utc),
                })
            except Exception:
                continue

        print(f"  ✅ Hacker News: {len(entries)} matches")
    except Exception as e:
        print(f"  ❌ Hacker News: {e}")

    return entries


# ═══════════════════════════════════════════════════════════════════════════════
#  RSS FEED GENERATOR
# ═══════════════════════════════════════════════════════════════════════════════

def generate_feed(all_entries):
    """Generate RSS feed XML file."""
    cfg = CONFIG["output"]
    feed_path = os.path.join(BASE_DIR, cfg["feed_path"])

    # Sort by published time (newest first)
    all_entries.sort(key=lambda e: e["published"], reverse=True)

    # Limit entries
    all_entries = all_entries[:cfg["max_entries"]]

    fg = FeedGenerator()
    fg.title(cfg["title"])
    fg.description(cfg["description"])
    fg.link(href=cfg["link"], rel="alternate")
    fg.language("en")
    fg.lastBuildDate(datetime.now(timezone.utc))
    fg.generator("AI-Viral-News v1.0")

    for entry in all_entries:
        fe = fg.add_entry()
        fe.id(entry["id"])
        fe.title(f"[{entry['icon']}] {entry['title']}")
        fe.link(href=entry["link"], rel="alternate")
        fe.published(entry["published"])

        # Build description
        desc = entry["description"]
        eng = entry["engagement"]
        source = entry["subreddit"] if entry["subreddit"] else entry["platform"]
        desc_html = f"<p>{desc}</p><p><strong>{eng}</strong> · 📍 {source}</p>"

        fe.description(desc_html)
        fe.category(term="AI News", label="AI News")

    # Write feed
    os.makedirs(os.path.dirname(feed_path), exist_ok=True)
    fg.rss_file(feed_path, pretty=True)
    print(f"\n  📝 Feed written: {feed_path}")
    print(f"  📊 Total entries: {len(all_entries)}")

    # Also write a JSON copy
    json_path = os.path.join(BASE_DIR, "docs", "feed.json")
    json_data = []
    for e in all_entries:
        json_data.append({
            "id": e["id"],
            "title": e["title"],
            "description": e["description"],
            "link": e["link"],
            "source_link": e["source_link"],
            "engagement": e["engagement"],
            "source": e["subreddit"] or e["platform"],
            "icon": e["icon"],
            "published": e["published"].isoformat(),
        })

    with open(json_path, "w") as f:
        json.dump(json_data, f, indent=2)
    print(f"  📝 JSON copy: {json_path}")

    return len(all_entries)


# ═══════════════════════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    print("=" * 55)
    print("  AI VIRAL NEWS — Feed Aggregator")
    print(f"  {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}")
    print("=" * 55)

    all_entries = []

    # 1. Reddit
    print("\n📡 Fetching Reddit...")
    all_entries.extend(fetch_reddit_posts())

    # 2. RSS Sources
    print("\n📰 Fetching RSS sources...")
    all_entries.extend(fetch_rss_sources())

    # 3. Hacker News (bonus)
    print("\n📰 Fetching Hacker News...")
    all_entries.extend(fetch_hackernews())

    # 4. Generate Feed
    print("\n🔨 Generating RSS feed...")
    total = generate_feed(all_entries)

    print(f"\n{'=' * 55}")
    print(f"  ✅ Done! {total} entries in feed.")
    print(f"{'=' * 55}")

    return 0 if total > 0 else 1

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"\n💥 FATAL: {e}")
        traceback.print_exc()
        sys.exit(1)
