#! /usr/bin/env python
# -*- coding: utf-8 -*-
from pathlib import Path

from videogram.utils import load_json, save_json

from podsync.github import gh

config_path = Path("config/bilibili.json")

configs = load_json(config_path)
for conf in configs:
    name = conf["name"]
    meta = load_json(f"metadata/{name}.json")
    releases = gh.get_releases().get(name, [])
    new_meta = [x for x in meta if f"{x['vid']}.mp4" in releases]
    if meta != new_meta:
        print(f"save {name}")
        save_json(new_meta, f"metadata/{name}.json")
        gh.upload_release(f"metadata/{name}.json", "metadata", clean=False)
