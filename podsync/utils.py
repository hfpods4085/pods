#! /usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

import xmltodict
from loguru import logger


def load_xml(path: str | Path, template: str = "rss") -> dict:
    path = Path(path)
    if path.exists():
        logger.debug(f"Loading xml from {path.as_posix()}")
        with path.open() as f:
            return xmltodict.parse(f.read())

    if template == "rss":
        logger.warning(f"{path} is not exist, use default rss template")
        return {"rss": {"@version": "2.0", "@xmlns:itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd", "channel": {}}}

    logger.warning(f"{path} is not exist, use default opml template")
    return {"opml": {"@version": "1.0", "head": {"title": "Podcast"}, "body": {"outline": []}}}


def save_xml(header: dict, items: list[dict], save_path: str | Path):
    header["rss"]["channel"]["item"] = items
    xml_str = xmltodict.unparse(header, pretty=True, full_document=True)
    save_path = Path(save_path)
    save_path.parent.mkdir(parents=True, exist_ok=True)
    with save_path.open("w") as f:
        f.write(xml_str)
