#! /usr/bin/env python
# -*- coding: utf-8 -*-
from pathlib import Path

from podsync.github import gh
from podsync.utils import load_xml, save_xml

for pod_type in ["audio", "video"]:
    for xml in Path(pod_type).glob("*.xml"):
        data = load_xml(xml.as_posix())
        items = data["rss"]["channel"].get("item")
        if isinstance(items, dict):
            items = [items]
        guids = set()
        new_items = []
        for item in items:
            if item["guid"] not in guids:
                new_items.append(item)
                guids.add(item["guid"])
        if items != new_items:
            print(f"save {xml}")
            save_xml(data, new_items, xml.as_posix())
            gh.upload_release(xml.as_posix(), pod_type, clean=False)
