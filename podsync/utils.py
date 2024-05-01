#! /usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os.path as osp

import xmltodict
from loguru import logger


def load_json(path: str) -> dict:
    if osp.exists(path):
        logger.debug(f"Loading json from {path}")
        with open(path) as f:
            return json.load(f)
    logger.warning(f"{path} is not exist, use default empty dict")
    return {}


def save_json(data: dict, path: str) -> None:
    logger.debug(f"Saving json to {path}")
    with open(path, "w") as f:
        json.dump(data, f, ensure_ascii=False)


def load_xml(path: str, template: str = "rss") -> dict:
    if osp.exists(path):
        logger.debug(f"Loading xml from {path}")
        with open(path) as f:
            return xmltodict.parse(f.read())

    if template == "rss":
        logger.warning(f"{path} is not exist, use default rss template")
        return {"rss": {"@version": "2.0", "@xmlns:itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd", "channel": {}}}

    logger.warning(f"{path} is not exist, use default opml template")
    return {"opml": {"@version": "1.0", "head": {"title": "Podcast"}, "body": {"outline": []}}}


def save_xml(header: dict, items: list[dict], save_path: str):
    header["rss"]["channel"]["item"] = items
    xml_str = xmltodict.unparse(header, pretty=True, full_document=True)
    with open(save_path, "w") as f:
        f.write(xml_str)
