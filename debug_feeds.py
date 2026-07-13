"""Debug script: test every RSS feed in config.py independently.

Run this locally (or on your Render/Railway shell) whenever /fetch seems
stuck or a newly-added source might be broken:

    python debug_feeds.py

For each feed it prints:
  - OK / BROKEN / EMPTY
  - number of entries found
  - the bozo_exception (parse error) if feedparser choked on it
  - the newest entry title, so you can eyeball whether it's actually fresh

This does NOT touch posted_ids.json, so it's safe to run anytime without
affecting what the bot considers "already posted".
"""

import feedparser

from config import RSS_FEEDS


def check_feed(url: str) -> None:
    print(f"\n{'=' * 70}")
    print(f"URL: {url}")
    try:
        feed = feedparser.parse(url)
    except Exception as e:
        print(f"STATUS: BROKEN (raised exception: {e!r})")
        return

    status = getattr(feed, "status", None)
    print(f"HTTP status: {status}")

    if feed.bozo:
        print(f"bozo=True — parser had trouble: {feed.bozo_exception!r}")
        if not feed.entries:
            print("STATUS: BROKEN — 0 entries recovered despite parse error")
            return
        else:
            print("(recovered some entries anyway, see below)")

    entry_count = len(feed.entries)
    if entry_count == 0:
        print("STATUS: EMPTY — feed parsed fine but returned 0 entries")
        return

    print(f"STATUS: OK — {entry_count} entries found")
    newest = feed.entries[0]
    print(f"Newest entry title: {newest.get('title', '(no title)')}")
    print(f"Newest entry link:  {newest.get('link', '(no link)')}")
    published = newest.get("published", newest.get("updated", "(no date field)"))
    print(f"Newest entry date:  {published}")


def main() -> None:
    print(f"Testing {len(RSS_FEEDS)} feeds from config.py ...")
    for url in RSS_FEEDS:
        check_feed(url)
    print(f"\n{'=' * 70}")
    print("Done. Any feed marked BROKEN or EMPTY above is why /fetch")
    print("might come back with nothing new — especially check feeds")
    print("you just added.")


if __name__ == "__main__":
    main()
