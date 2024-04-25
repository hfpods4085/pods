#! /usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import os.path as osp
import subprocess

import requests
from loguru import logger


class Github:
    def __init__(self, repo: str = os.getenv("GITHUB_REPOSITORY", "")) -> None:
        self.repo = repo
        assert self.repo, "Repo is not set"
        self.releases = {}

    def get_releases(self) -> dict[str, list]:
        logger.debug(f"Fetching releases for {self.repo}")
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        all_releases = []
        per_page = 100  # maximum is 100
        page = 1
        res = requests.get(f"https://api.github.com/repos/{self.repo}/releases?per_page={per_page}&page={page}", headers=headers, timeout=30).json()
        all_releases.extend(res)
        while len(res) == per_page:
            page += 1
            res = requests.get(f"https://api.github.com/repos/{self.repo}/releases?per_page={per_page}&page={page}", headers=headers, timeout=30).json()
            all_releases.extend(res)
        logger.debug(f"Found {len(all_releases)} releases")
        return {release["name"]: [asset["name"] for asset in release["assets"]] for release in all_releases}

    def upload_release(self, path: str, release_name: str, *, clean=True):
        if not self.releases:
            self.releases = self.get_releases()
        if release_name not in self.releases:
            logger.info(f"Creating release {release_name} [{self.repo}]")
            command = f"gh release create '{release_name}' --prerelease -n '{release_name}' -t '{release_name}' -R '{self.repo}' > /dev/null 2>&1 || true"
            subprocess.run(command, shell=True, check=False)  # noqa: S602
            self.releases[release_name] = []
        logger.info(f"Uploading {path} to {release_name} [{self.repo}]")
        command = f"gh release upload --clobber '{release_name}' -- '{path}'"
        subprocess.run(command, shell=True, check=False)  # noqa: S602
        self.releases[release_name].append(osp.basename(path))
        if clean:
            os.remove(path)

    def trigger_workflow(self, feed_name: str) -> int:
        logger.info(f"Triggering workflow for {feed_name}")
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        api = f"https://api.github.com/repos/{self.repo}/actions/workflows/single.yml/dispatches"
        data = {"ref": "main", "inputs": {"name": feed_name}}
        response = requests.post(api, headers=headers, json=data, timeout=30)
        assert response.status_code == 204, f"Failed to trigger workflow: {response.text}"
        return response.status_code


gh = Github()
