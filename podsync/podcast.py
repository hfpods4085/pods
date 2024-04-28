#! /usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import annotations

import os
from datetime import datetime
from zoneinfo import ZoneInfo


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
            "channel": {
                "title": feed_info["title"],
                "link": feed_info["link"],
                "description": feed_info["title"],
                "category": "TV & Film",
                "generator": "PodSync",
                "language": "en-us",
                "lastBuildDate": now,
                "pubDate": pub_date.strftime("%a, %d %b %Y %H:%M:%S %z"),
                "image": {
                    "url": cover_url,
                    "title": feed_info["title"],
                    "link": feed_info["link"],
                },
                "itunes:author": feed_info["author"],
                "itunes:block": "yes",
                "itunes:category": {"@text": "TV & Film"},
                "itunes:explicit": "no",
                "itunes:image": {"@href": cover_url},
                "itunes:subtitle": feed_info["title"],
                "itunes:summary": feed_info["title"],
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
        "guid": feed_entry["yt_videoid"],
        "title": feed_entry["title"],
        "link": feed_entry["link"],
        "description": feed_entry["summary"],
        "pubDate": pub_date.strftime("%a, %d %b %Y %H:%M:%S %z"),
        "enclosure": enclosure,
        "itunes:author": feed_entry["author"],
        "itunes:subtitle": feed_entry["title"],
        "itunes:summary": feed_entry["summary"],
        "itunes:image": {"@href": f"https://i.ytimg.com/vi/{feed_entry['yt_videoid']}/maxresdefault.jpg"},
        "itunes:duration": duration,
        "itunes:explicit": "no",
        "itunes:order": "1",
    }
