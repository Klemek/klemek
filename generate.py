import requests
import os
import sys

from dotenv import load_dotenv

load_dotenv()

GITHUB_USERNAME = os.getenv("GITHUB_USERNAME")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")


def make_request(path: str, method: str = "GET") -> dict | list:
    response = requests.request(
        method=method,
        url=f"https://api.github.com{path}",
        headers={
            "User-Agent": GITHUB_USERNAME,
            "Accept": "application/json",
            "Authorization": f"Bearer {GITHUB_TOKEN}",
        },
    )
    print(f"{method} {path}: {response.status_code} {response.reason}")
    if response.status_code != 200:
        sys.exit(1)
    return response.json()


with open("README.md", mode="w") as readme:
    readme.write(
        f"""
[![{GITHUB_USERNAME}'s GitHub stats](https://github-readme-stats.vercel.app/api?username={GITHUB_USERNAME}&count_private=true&show_icons=true&theme=gruvbox)](https://github.com/anuraghazra/github-readme-stats)

[![Top Langs](https://github-readme-stats.vercel.app/api/top-langs/?username={GITHUB_USERNAME}&layout=compact&count_private=true&show_icons=true&theme=gruvbox)](https://github.com/anuraghazra/github-readme-stats)

---

## Quick access

| Project | Description | Created |
|---|---|---|
"""
    )

    for data in make_request(f"/user/repos?sort=created&direction=desc&per_page=100"):
        if (
            data["homepage"] is not None
            and len(data["homepage"])
            and not data["archived"]
        ):
            created_at = data["created_at"].split("-")[0]
            readme.write(
                f"| **[{data['name']}]({data['homepage']})** <sub> ([repo]({data['html_url']})) </sub> | {data['description']} | {created_at} |\n"
            )
