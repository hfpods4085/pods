#! /usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from datetime import datetime
from zoneinfo import ZoneInfo

"""Apple Podcast Specification

https://help.apple.com/itc/podcasts_connect/#/itcb54353390
"""

def generate_pod_header(feed_info: dict, cover_url: str) -> dict:
    """Generate podcast header for RSS feed.

    Args:
        feed_info (dict): feed info parsed from feedparser
        cover_url (str): corver image url

    Returns:
        dict: header of RSS feed
    """
    pub_date = datetime.strptime(feed_info["published"], "%Y-%m-%dT%H:%M:%S%z")
    now = datetime.now(tz=ZoneInfo("UTC")).strftime("%a, %d %b %Y %H:%M:%S %z")
    return {
        "rss": {
            "@version": "2.0",
            "@xmlns:itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
            "@xmlns:podcast": "https://podcastindex.org/namespace/1.0",
            "channel": {
                # Required tags
                "title": feed_info["title"],
                "description": feed_info["title"],
                "itunes:image": {"@href": cover_url},
                "language": "en-us",
                "itunes:category": {"@text": "TV & Film"},
                "itunes:explicit": "no",
                # Recommended tags
                "itunes:author": feed_info["author"],
                "link": feed_info["link"],
                # Situational tags
                "itunes:title": feed_info["title"],
                "itunes:type": "Episodic",
                "itunes:block": "yes",
                # Common tags for rss
                "category": "TV & Film",
                "generator": "PodSync",
                "lastBuildDate": now,
                "pubDate": pub_date.strftime("%a, %d %b %Y %H:%M:%S %z"),
                "image": {
                    "url": cover_url,
                    "title": feed_info["title"],
                    "link": feed_info["link"],
                },
                "item": [],
            },
        }
    }


def generate_pod_item(feed_entry: dict, pod_type: str, release_name: str, filesize: int, duration: int) -> dict:
    """Generate podcast item for RSS feed.

    We will upload audio and video files to GitHub release, and generate RSS feed for podcast.

    Args:
        feed_entry (dict): entry parsed from feedparser
        pod_type (str): podcast type. Choices: "audio", "video"
        release_name (str): GitHub release name
        filesize (int): Size of the file in bytes
        duration (int): duration of the media file in seconds

    Returns:
        dict: podcast item for RSS feed
    """
    pub_date = datetime.strptime(feed_entry["published"], "%Y-%m-%dT%H:%M:%S%z")
    if pod_type == "audio":
        enclosure = {
            "@url": f"https://github.com/{os.environ['GITHUB_REPOSITORY']}/releases/download/{release_name}/{feed_entry['yt_videoid']}.m4a",
            "@length": filesize,
            "@type": "audio/x-m4a",
        }
    else:
        enclosure = {
            "@url": f"https://github.com/{os.environ['GITHUB_REPOSITORY']}/releases/download/{release_name}/{feed_entry['yt_videoid']}.mp4",
            "@length": filesize,
            "@type": "video/mp4",
        }

    return {
        # Required tags
        "title": feed_entry["title"],
        "enclosure": enclosure,
        "guid": feed_entry["yt_videoid"],
        # Recommended tags
        "pubDate": pub_date.strftime("%a, %d %b %Y %H:%M:%S %z"),
        "description": feed_entry["summary"],
        "itunes:duration": duration,
        "link": feed_entry["link"],
        "itunes:image": {"@href": feed_entry["media_thumbnail"][0]["url"]},
        "itunes:explicit": "no",
    }
