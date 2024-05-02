#! /usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from datetime import datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

import dateparser

if TYPE_CHECKING:
    from pathlib import Path

"""Apple Podcast Specification

https://help.apple.com/itc/podcasts_connect/#/itcb54353390
"""


def generate_pod_header(feed_info: dict, config: dict) -> dict:
    """Generate podcast header for RSS feed.

    Args:
        feed_info (dict): feed info parsed from feedparser
        config (dict): custom configuration of this feed

    Returns:
        dict: header of RSS feed
    """
    now = datetime.now(tz=ZoneInfo("UTC"))
    if "published" in feed_info:
        pub_date = dateparser.parse(feed_info["published"], settings={"TO_TIMEZONE": os.getenv("TZ", "UTC")})
    elif "updated" in feed_info:
        pub_date = dateparser.parse(feed_info["updated"], settings={"TO_TIMEZONE": os.getenv("TZ", "UTC")})
    else:
        pub_date = now
    return {
        "rss": {
            "@version": "2.0",
            "@xmlns:itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
            "@xmlns:podcast": "https://podcastindex.org/namespace/1.0",
            "channel": {
                # Required tags
                "title": config.get("title", feed_info["title"]),
                "description": config.get("description", feed_info["title"]),
                "itunes:image": {"@href": config["cover"]},
                "language": "en-us",
                "itunes:category": {"@text": "TV & Film"},
                "itunes:explicit": "no",
                # Recommended tags
                "itunes:author": config.get("title", feed_info["title"]),
                "link": feed_info["link"],
                # Situational tags
                "itunes:title": feed_info["title"],
                "itunes:type": "Episodic",
                "itunes:block": "yes",
                # Common tags for rss
                "category": "TV & Film",
                "generator": "PodSync",
                "lastBuildDate": f"{now:%a, %d %b %Y %H:%M:%S %z}",
                "pubDate": f"{pub_date:%a, %d %b %Y %H:%M:%S %z}",
                "image": {
                    "url": config["cover"],
                    "title": feed_info["title"],
                    "link": feed_info["link"],
                },
                "item": [],
            },
        }
    }


def generate_pod_item(
    feed_entry: dict,
    pod_type: str,
    release_name: str,
    filepath: Path,
    cover: str,
    duration: int,
) -> dict:
    """Generate podcast item for RSS feed.

    We will upload audio and video files to GitHub release, and generate RSS feed for podcast.

    Args:
        feed_entry (dict): entry parsed from feedparser
        pod_type (str): podcast type. Choices: "audio", "video"
        release_name (str): GitHub release name
        filepath (Path): path to the media file
        cover (str): cover image url
        duration (int): duration of the media file in seconds

    Returns:
        dict: podcast item for RSS feed
    """
    pub_date = dateparser.parse(feed_entry["published"], settings={"TO_TIMEZONE": os.getenv("TZ", "UTC")})
    if pod_type == "audio":
        enclosure = {
            "@url": f"https://github.com/{os.environ['GITHUB_REPOSITORY']}/releases/download/{release_name}/{filepath.name}",
            "@length": filepath.stat().st_size,
            "@type": "audio/x-m4a",
        }
    else:
        enclosure = {
            "@url": f"https://github.com/{os.environ['GITHUB_REPOSITORY']}/releases/download/{release_name}/{filepath.name}",
            "@length": filepath.stat().st_size,
            "@type": "video/mp4",
        }

    return {
        # Required tags
        "title": feed_entry["title"],
        "enclosure": enclosure,
        "guid": filepath.stem,
        # Recommended tags
        "pubDate": f"{pub_date:%a, %d %b %Y %H:%M:%S %z}",
        "description": feed_entry["summary"],
        "itunes:duration": duration,
        "link": feed_entry["link"],
        "itunes:image": {"@href": cover},
        "itunes:explicit": "no",
    }
