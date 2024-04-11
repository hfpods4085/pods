#! /usr/bin/env python
# -*- coding: utf-8 -*-

import argparse
import os
import os.path as osp
import re
import subprocess
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests
import xmltodict


class Pods:
    def __init__(self, remote_host: str, remote_path: str, cache_dir: str, save_dir: str, pod_type: str) -> None:
        self.host = remote_host
        self.path = remote_path
        self.pod_type = pod_type
        self.cache_dir = cache_dir
        self.save_dir = save_dir
        self.repo = os.environ["GITHUB_REPOSITORY"]
        Path(save_dir).mkdir(exist_ok=True)
        self.releases = self.get_github_releases()

    def get_github_releases(self) -> dict[str, list]:
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        all_releases = []
        per_page = 100  # maximum is 100
        page = 1
        res = requests.get(
            f"https://api.github.com/repos/{self.repo}/releases?per_page={per_page}&page={page}", headers=headers, timeout=5
        ).json()
        all_releases.extend(res)
        while len(res) == per_page:
            page += 1
            res = requests.get(
                f"https://api.github.com/repos/{self.repo}/releases?per_page={per_page}&page={page}", headers=headers, timeout=5
            ).json()
            all_releases.extend(res)

        return {release["name"]: [asset["name"] for asset in release["assets"]] for release in all_releases}

    def parse_remote_opml(self) -> tuple[str, list]:
        url = f"https://{self.host}/{self.path}"
        content = requests.get(url, timeout=5).text
        feeds = re.findall(r'xmlUrl="([^"]+)"', content)
        return content, sorted(feeds)

    def save_revise_opml(self, opml: str) -> str:
        opml = opml.replace(self.host, f"github.com/{self.repo}/releases/download/{self.pod_type}")
        with open(f"{self.save_dir}/{self.path}", "w") as f:
            f.write(opml)
        return f"{self.save_dir}/{self.path}"

    @staticmethod
    def parse_url(url: str) -> tuple[str, str]:
        parsed_url = urlparse(url)
        filename = unquote(parsed_url.path.split("/")[-1])
        stem, ext = osp.splitext(filename)
        return stem, ext

    @staticmethod
    def check_external_url_exists(url) -> bool:
        response = requests.head(url, timeout=5)
        if response.ok:
            print(f"OK [{response.status_code}]: external url exists")
            return True

        print(f"ERROR [{response.status_code}]: external url not available")
        return False

    def download_remote_file(self, url: str) -> str:
        stem, ext = self.parse_url(url)
        save_path = f"{self.save_dir}/{stem}{ext}"
        if osp.exists(save_path):
            print(f"File '{save_path}' already exists.")
            return save_path
        print(f"Downloading '{url}' to '{save_path}'...")
        # Send a GET request to the URL with streaming enabled
        with requests.get(url, stream=True, timeout=5) as response:
            # Check if the request was successful
            response.raise_for_status()  # This will raise an error for bad responses
            # Open a binary file in write mode
            with open(save_path, "wb") as file:
                # Iterate over the response data in chunks
                for chunk in response.iter_content(chunk_size=8192):  # Chunk size is 8 Kilobytes
                    file.write(chunk)
            print(f"File '{save_path}' downloaded successfully.")
        return save_path

    def need_upload(self, channel: str, item: dict) -> bool:
        releases = self.releases.get(channel, [])
        if enclosure := item.get("enclosure", {}).get("@url"):
            stem, ext = self.parse_url(enclosure)
            return f"{stem}{ext}" not in releases
        return False

    def process_feed(self, feed_url):
        channel, ext = self.parse_url(feed_url)
        assert ext == ".xml"

        # download new feed
        feed_path = self.download_remote_file(feed_url)
        with open(feed_path) as f:
            xml_dict = xmltodict.parse(f.read())

        # process per item
        channel_title = xml_dict.get("rss", {}).get("channel", {}).get("title", "Unknown")
        items = xml_dict.get("rss", {}).get("channel", {}).get("item", [])
        items = [items] if isinstance(items, dict) else items  # single item

        for item in items:
            # change enclosure url to github asset url
            enclosure_url = item["enclosure"]["@url"]
            stem, ext = self.parse_url(enclosure_url)
            github_asset_url = f"https://github.com/{self.repo}/releases/download/{channel}/{stem}{ext}"

            # check if already uploaded to github
            if not self.need_upload(channel, item):
                print(f"Skip {channel_title} | {item['title']} | {item['link']}")
                item["enclosure"]["@url"] = github_asset_url
                continue

            print(f"Processing {channel_title} | {item['title']} | {item['link']}")
            enclosure_url = item["enclosure"]["@url"]
            enclosure_path = self.download_remote_file(enclosure_url)
            self.upload_github(enclosure_path, channel, clean=True)
            item["enclosure"]["@url"] = github_asset_url

        # save new feed
        new_feed_path = self.save_new_feed_xml(channel, xml_dict)
        self.upload_github(new_feed_path, self.pod_type, clean=False)

    def save_new_feed_xml(self, channel: str, feed_data: dict) -> str:
        feed_items = feed_data.get("rss", {}).get("channel", {}).get("item", [])
        feed_items = [feed_items] if isinstance(feed_items, dict) else feed_items  # single item
        guids = [item.get("guid") for item in feed_items]
        # load cache
        cache_path = f"{self.cache_dir}/{channel}.xml"
        cache_data = {}
        if osp.exists(cache_path):
            with open(cache_path) as f:
                cache_data = xmltodict.parse(f.read())
        cache_items = cache_data.get("rss", {}).get("channel", {}).get("item", [])
        cache_items = [cache_items] if isinstance(cache_items, dict) else cache_items  # single item
        for item in cache_items:
            if item.get("guid") not in guids:
                feed_items.append(item)

        out_path = f"{self.save_dir}/{channel}.xml"
        xml_str = xmltodict.unparse(feed_data, pretty=True, full_document=True)
        # inject CDATA tag
        xml_str = xml_str.replace("<itunes:summary>", "<itunes:summary><![CDATA[").replace("</itunes:summary>", "]]></itunes:summary>")
        with open(f"{out_path}", "w") as f:
            f.write(xml_str)
        return out_path

    def upload_github(self, path: str, release_name: str, *, clean=True):
        if release_name not in self.releases:
            print(f"Creating release {release_name}")
            command = f"gh release create '{release_name}' --prerelease -n '{release_name}' -t '{release_name}' > /dev/null 2>&1 || true"
            subprocess.run(command, shell=True, check=False)  # noqa: S602
            self.releases[release_name] = []
        print(f"Uploading {path} to {release_name}")
        command = f"gh release upload --clobber '{release_name}' -- '{path}'"
        subprocess.run(command, shell=True, check=False)  # noqa: S602
        self.releases[release_name].append(osp.basename(path))
        if clean:
            os.remove(path)


def main():
    pod = Pods(args.remote_host, args.remote_path, args.cache_dir, args.save_dir, args.pod_type)
    opml, feeds = pod.parse_remote_opml()
    revised_opml_path = pod.save_revise_opml(opml)
    pod.upload_github(revised_opml_path, args.pod_type, clean=False)
    for feed_url in feeds:
        print(f"Processing {feed_url}")
        pod.process_feed(feed_url)


if __name__ == "__main__":
    # parse arguments
    parser = argparse.ArgumentParser()
    parser.add_argument("--remote-host", type=str, required=True, help="Hostname")
    parser.add_argument("--remote-path", type=str, required=False, default="podsync.opml", help="URI Path")
    parser.add_argument("--cache-dir", type=str, required=False, default="old", help="Cache directory")
    parser.add_argument("--save-dir", type=str, required=False, default="new", help="Save directory")
    parser.add_argument("--pod-type", type=str, choices=["video", "audio"], required=False, help="Pods type")
    args = parser.parse_args()

    main()
