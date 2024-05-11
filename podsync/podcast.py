#! /usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import uuid
from datetime import datetime
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

import dateparser

if TYPE_CHECKING:
    from pathlib import Path

"""Apple Podcast Specification

https://help.apple.com/itc/podcasts_connect/#/itcb54353390
https://github.com/Podcast-Standards-Project/PSP-1-Podcast-RSS-Specification
"""


def generate_pod_header(feed_info: dict, config: dict, pod_type: str) -> dict:
    """Generate podcast header for RSS feed.

    Args:
        feed_info (dict): feed info parsed from feedparser
        config (dict): custom configuration of this feed
        pod_type (str): podcast type. Choices: "audio", "video"

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
    feed_url = f"https://github.com/{os.environ['GITHUB_REPOSITORY']}/releases/download/{pod_type}/{config['name']}.xml"
    return {
        "rss": {
            "@version": "2.0",
            "@xmlns:itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
            "@xmlns:podcast": "https://podcastindex.org/namespace/1.0",
            "xmlns:atom": "http://www.w3.org/2005/Atom",
            "xmlns:content": "http://purl.org/rss/1.0/modules/content/",
            "channel": {
                # Required tags
                "atom:link": {
                    "@href": feed_url,
                    "@rel": "self",
                    "@type": "application/rss+xml",
                },
                "title": config.get("title", feed_info["title"]),
                "description": config.get("description", feed_info["title"]),
                "itunes:image": {"@href": config["cover"]},
                "language": "en-us",
                "itunes:category": {"@text": "TV & Film"},
                "itunes:explicit": "false",
                # Recommended tags
                "podcast:locked": "yes",
                "podcast:guid": generate_podcast_uuid(feed_url),
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
        "guid": feed_entry["link"],
        # Recommended tags
        "pubDate": f"{pub_date:%a, %d %b %Y %H:%M:%S %z}",
        "description": feed_entry["summary"],
        "itunes:duration": duration,
        "link": feed_entry["link"],
        "itunes:image": {"@href": cover},
        "itunes:explicit": "false",
    }


def generate_podcast_uuid(url: str):
    """Generate podcast UUID from URL.

    Docs: https://github.com/Podcastindex-org/podcast-namespace/blob/main/docs/1.0.md#guid
    The value is a UUIDv5, and is generated from the RSS feed url,
    with the protocol scheme and trailing slashes stripped off,
    combined with a unique "podcast" namespace which has a UUID of ead4c236-bf58-58c6-a2c6-a6b28d128cb6

    Args:
        url (str): feed url
    """
    url = url.strip().strip("/").removeprefix("http://").removeprefix("https://")
    pod_uuid = uuid.uuid5(uuid.UUID("ead4c236-bf58-58c6-a2c6-a6b28d128cb6"), url)
    return str(pod_uuid)
