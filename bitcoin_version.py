#!/usr/bin/env python3
"""
Scrape ALL bitcoin/bitcoin tags (versions) and their dates
from the GitHub tags pages and save as CSV.

Requires:
    pip install requests beautifulsoup4

Outputs:
    bitcoin_tags.csv
"""

import csv
import time
from dataclasses import dataclass, asdict
from typing import List, Dict, Optional, Tuple
from urllib.parse import urljoin, urlparse, parse_qs

import requests
from bs4 import BeautifulSoup
import urllib3
from urllib3.exceptions import InsecureRequestWarning

BASE_URL = "https://github.com"
TAGS_PATH = "/bitcoin/bitcoin/tags"
START_URL = BASE_URL + TAGS_PATH

HEADERS = {
    "User-Agent": "bitcoin-tag-scraper/1.1 (educational script)"
}

# If you’re behind Charles / corporate MITM:
# CUSTOM_CA = "/absolute/path/to/your/mitm-root.pem"
CUSTOM_CA: Optional[str] = None  # or set to your CA path


@dataclass
class TagInfo:
    name: str               # e.g. "v30.0rc1"
    date_iso: Optional[str] # e.g. "2017-02-17T17:34:06Z" or None


def fetch_html(url: str, session: requests.Session) -> str:
    resp = session.get(url, headers=HEADERS, timeout=20)
    resp.raise_for_status()
    return resp.text


def parse_tags_and_next(html: str) -> Tuple[List[TagInfo], Optional[str]]:
    """
    Parse a GitHub tags page and return:
      - list of TagInfo
      - absolute URL of the "Next" page (or None if there is no next)
    """
    soup = BeautifulSoup(html, "html.parser")
    tags: List[TagInfo] = []

    # Each tag row is in a Box-row
    for row in soup.select("div.Box-row"):
        name_el = row.select_one("h2.f4 a")
        if not name_el:
            continue

        name = name_el.get_text(strip=True)

        # Find the <li> that has the clock icon, then the relative-time next to it.
        date_iso: Optional[str] = None
        li_with_clock = None
        for li in row.select("li"):
            if li.select_one("svg.octicon-clock"):
                li_with_clock = li
                break

        if li_with_clock is not None:
            time_el = li_with_clock.find("relative-time")
            if time_el is not None:
                if time_el.has_attr("datetime"):
                    date_iso = time_el["datetime"].strip()
                else:
                    # Fallback to the rendered text (e.g. "Feb 17, 2017")
                    date_iso = time_el.get_text(strip=True)

        tags.append(TagInfo(name=name, date_iso=date_iso))

    # Find "Next" link (older tags)
    next_url: Optional[str] = None
    pag = soup.select_one(".paginate-container .pagination")
    if pag:
        for a in pag.find_all("a", href=True):
            if "Next" in a.get_text(strip=True):
                href = a["href"]
                next_url = urljoin(BASE_URL, href)
                break

    return tags, next_url


def scrape_all_tags(start_url: str = START_URL,
                    delay_seconds: float = 0.7) -> Dict[str, TagInfo]:
    """
    Follow pagination (Next links) through all tag pages and
    return a dict {tag_name: TagInfo}, deduplicated by tag name.
    """
    session = requests.Session()
    session.verify = False
    urllib3.disable_warnings(category=InsecureRequestWarning)

    # If you need to trust a custom CA (e.g. Charles), set CUSTOM_CA above
    if CUSTOM_CA:
        session.verify = CUSTOM_CA

    seen_urls = set()
    all_tags: Dict[str, TagInfo] = {}

    url = start_url
    page_num = 1

    while url and url not in seen_urls:
        print(f"[page {page_num}] Fetching {url}")
        seen_urls.add(url)

        html = fetch_html(url, session)
        page_tags, next_url = parse_tags_and_next(html)

        if not page_tags:
            print("  Warning: no tags found on this page.")
        else:
            # Optional sanity check: `after=` matches last tag on the page
            if next_url:
                parsed = urlparse(next_url)
                after_vals = parse_qs(parsed.query).get("after", [])
                if after_vals:
                    after_tag = after_vals[0]
                    last_tag_on_page = page_tags[-1].name
                    if after_tag != last_tag_on_page:
                        print(
                            f"  ⚠ after={after_tag} (from Next link) "
                            f"!= last tag '{last_tag_on_page}' on this page"
                        )

        # Deduplicate by tag name
        for t in page_tags:
            existing = all_tags.get(t.name)
            if existing is None:
                all_tags[t.name] = t
            else:
                # prefer entry that has a date
                if existing.date_iso is None and t.date_iso is not None:
                    all_tags[t.name] = t

        url = next_url
        page_num += 1
        if url and delay_seconds > 0:
            time.sleep(delay_seconds)

    print(f"\nTotal unique tags scraped: {len(all_tags)}")
    return all_tags

def save_csv(tags: Dict[str, TagInfo], path: str = "bitcoin_tags.csv") -> None:
    items = sorted(
        tags.values(),
        key=lambda x: ((x.date_iso or ""), x.name)
    )
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["name", "date_iso"])
        for t in items:
            writer.writerow([t.name, t.date_iso or ""])
    print(f"Wrote {len(items)} tags to {path}")


def main():
    tags = scrape_all_tags()
    # quick debug: print a few old + new tags to eyeball dates
    print("\nSample tags (first 5 by date):")
    for t in sorted(tags.values(), key=lambda x: (x.date_iso or "", x.name))[:5]:
        print(f"  {t.name:15}  {t.date_iso}")

    print("\nSample tags (last 5 by date):")
    for t in sorted(tags.values(), key=lambda x: (x.date_iso or "", x.name))[-5:]:
        print(f"  {t.name:15}  {t.date_iso}")

    save_csv(tags)


if __name__ == "__main__":
    main()
