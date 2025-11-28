#!/usr/bin/env python3
"""
Plot Bitcoin Core tag (version) releases over time.

Input:
    CSV file produced by your scraping script (bitcoin_tags.csv)

Output:
    bitcoin_tags_timeline.png

Usage:
    python plot_bitcoin_tags.py \
        --input bitcoin_tags.csv \
        --output bitcoin_tags_timeline.png
"""

import argparse
import datetime as dt
import csv
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

import matplotlib.dates as mdates
import matplotlib.pyplot as plt

from collections import Counter

@dataclass
class Tag:
    """Single git tag with parsed metadata."""
    name: str
    date: dt.datetime
    is_prerelease: bool  # rc / alpha / beta / test
    is_major: bool       # "major" stable (used for annotations)


def parse_iso8601(s: str) -> dt.datetime:
    """
    Parse an ISO 8601 datetime like '2017-02-17T17:34:06Z'
    into a timezone-aware datetime.
    """
    # Ensure we turn 'Z' into +00:00 so fromisoformat can handle it.
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    return dt.datetime.fromisoformat(s)


def classify_tag(name: str) -> Tuple[bool, bool]:
    """
    Classify a tag name.

    Returns:
        (is_prerelease, is_major_stable)
    """
    lower = name.lower()

    # Anything with rc/beta/alpha/test we’ll treat as pre-release.
    is_prerelease = any(x in lower for x in ("rc", "beta", "alpha", "test"))

    # We call something "major" if it looks like:
    #   vX.Y, vX.Y.0 or vX.Y.z where z = 0
    # and is not a pre-release.
    major = False
    m = re.match(r"^v(\d+)\.(\d+)(?:\.(\d+))?$", name)
    if m and not is_prerelease:
        patch = m.group(3)
        major = (patch is None) or (patch == "0")

    return is_prerelease, major


def load_tags(path: str) -> List[Tag]:
    """Load tags from the CSV file and parse into Tag objects."""
    with open(path, "r", encoding="utf-8") as f:
        raw = list(csv.DictReader(f))


    tags: List[Tag] = []
    for item in raw:
        name = item.get("name")
        date_str: Optional[str] = item.get("date_iso")
        if not name or not date_str:
            # Skip tags with no usable date
            continue

        try:
            dt_obj = parse_iso8601(date_str)
        except Exception:
            # If parsing fails for some odd entry, just skip it.
            continue

        is_pr, is_major = classify_tag(name)
        tags.append(Tag(name=name, date=dt_obj, is_prerelease=is_pr, is_major=is_major))

    # Sort chronologically
    tags.sort(key=lambda t: t.date)
    return tags

def bitcoin_halving_dates() -> List[dt.datetime]:
    """Return known Bitcoin halving dates."""
    return [
        dt.datetime(2012, 11, 28, 15, 46, tzinfo=dt.timezone.utc),
        dt.datetime(2016, 7, 9, 16, 46, tzinfo=dt.timezone.utc),
        dt.datetime(2020, 5, 11, 19, 23, tzinfo=dt.timezone.utc),
        dt.datetime(2024, 4, 26, 0, 9, tzinfo=dt.timezone.utc),  
    ]

def build_cumulative_series(tags: List[Tag]):
    """
    Build two cumulative series:
      - all_tags: (dates, counts)
      - stable_tags: list of (Tag, cumulative_stable_count)
    """
    all_dates = [t.date for t in tags]
    all_counts = list(range(1, len(tags) + 1))

    stable_tags: List[Tuple[Tag, int]] = []
    stable_dates: List[dt.datetime] = []
    stable_counts: List[int] = []

    cum = 0
    for t in tags:
        if not t.is_prerelease:
            cum += 1
            stable_tags.append((t, cum))
            stable_dates.append(t.date)
            stable_counts.append(cum)

    return (all_dates, all_counts), (stable_dates, stable_counts), stable_tags

def make_plot(tags: List[Tag], out_path: str):
    (all_dates, all_counts), (stable_dates, stable_counts), stable_tags = \
        build_cumulative_series(tags)

    # Release counts per year
    all_per_year = Counter(t.date.year for t in tags)
    stable_per_year = Counter(t.date.year for t in tags if not t.is_prerelease)

    years = sorted(all_per_year.keys())
    all_counts_y = [all_per_year[y] for y in years]
    stable_counts_y = [stable_per_year.get(y, 0) for y in years]

    # Use mid-year datetimes for the bar positions so they live on the same
    # datetime x-axis as the top plot.
    year_dates = [
        dt.datetime(y, 7, 1, tzinfo=dt.timezone.utc) for y in years
    ]

    fig, (ax_top, ax_bottom) = plt.subplots(
        2, 1, figsize=(12, 8), sharex=True,
        gridspec_kw={"height_ratios": [2, 1]}
    )

    # ---------- TOP: cumulative ----------
    ax = ax_top

    ax.plot(
        all_dates,
        all_counts,
        linestyle="none",
        marker="o",
        markersize=3,
        alpha=0.3,
        label="All tags",
    )

    ax.plot(
        stable_dates,
        stable_counts,
        marker="o",
        markersize=4,
        linewidth=1.5,
        label="Stable releases",
    )

    # annotate only "major" stable tags
    for tag, y in stable_tags:
        if not tag.is_major:
            continue
        ax.annotate(
            tag.name,
            xy=(tag.date, y),
            xytext=(3, 3),
            textcoords="offset points",
            fontsize=6,
            rotation=45,
            ha="left",
            va="bottom",
        )
    
    # add genesis block vertical green line 6:15 PM UTC
    genesis_date = dt.datetime(2009, 1, 3, 18, 15, tzinfo=dt.timezone.utc)
    ax.axvline(genesis_date, color="green", linestyle="--", alpha=0.7)
    ax.annotate(
        "Genesis Block",
        xy=(genesis_date, 1),
        xytext=(5, 15),
        textcoords="offset points",
        fontsize=8,
        rotation=45,
        ha="left",
        va="bottom",
        color="green",
    )

    # halving epoch shading (use tz-aware helper)
    HALVINGS = bitcoin_halving_dates()
    epoch_edges = [tags[0].date] + HALVINGS + [tags[-1].date]

    for i in range(len(epoch_edges) - 1):
        ax.axvspan(
            epoch_edges[i],
            epoch_edges[i + 1],
            alpha=0.05 if i % 2 == 0 else 0.1,
            zorder=0,
        )
    for h in HALVINGS:
        ax.axvline(h, linestyle="--", alpha=0.6)

    ax.set_title("Bitcoin Core Tag Releases Over Time")
    ax.set_ylabel("Cumulative number of tags")
    ax.grid(True, linestyle="--", alpha=0.3)

    # ---------- BOTTOM: releases / year ----------
    ax2 = ax_bottom

    # Width in "days" for date-based bars (~80% of a year)
    bar_width = 365 * 0.8

    ax2.bar(
        year_dates,
        all_counts_y,
        width=bar_width,
        alpha=0.3,
        label="All tags / year",
    )
    # add count labels inside the orange bars
    for x, y in zip(year_dates, stable_counts_y):
        if y > 0:
            ax2.text(
                x,
                y / 2,
                str(y),
                ha="center",
                va="center",
                fontsize=8,
                color="white",
            )

    ax2.bar(
        year_dates,
        stable_counts_y,
        width=bar_width * 0.6,
        label="Stable releases / year",
    )

    ax2.set_ylabel("Releases per year")
    ax2.set_xlabel("Release date")
    ax2.grid(True, axis="y", linestyle="--", alpha=0.3)

    # Date ticks for shared x-axis
    ax2.xaxis.set_major_locator(mdates.YearLocator(base=1))
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.autofmt_xdate()

    # ---------- shared legend ----------
    handles_top, labels_top = ax.get_legend_handles_labels()
    handles_bottom, labels_bottom = ax2.get_legend_handles_labels()

    fig.legend(
        handles_top + handles_bottom,
        labels_top + labels_bottom,
        loc="upper left",
        bbox_to_anchor=(0.01, 0.99),
    )

    plt.tight_layout()
    fig.savefig(out_path, dpi=200)
    print(f"Saved chart to {out_path}")

def main():
    parser = argparse.ArgumentParser(description="Plot Bitcoin Core tags over time.")
    parser.add_argument(
        "--input", "-i",
        default="bitcoin_tags.csv",
        help="Path to csv file containing scraped tag data.",
    )
    parser.add_argument(
        "--output", "-o",
        default="bitcoin_tag_plots.png",
        help="Output image filename.",
    )
    args = parser.parse_args()

    tags = load_tags(args.input)
    if not tags:
        raise SystemExit("No tags with valid dates found in input file.")
    print(f"Loaded {len(tags)} tags with valid dates.")
    make_plot(tags, args.output)


if __name__ == "__main__":
    main()
