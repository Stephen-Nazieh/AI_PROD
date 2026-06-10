#!/usr/bin/env python3
"""
YouTube integration for the studio seams (publishing, trends, channel stats).

Auth comes from the gitignored client_secrets.json (installed-app OAuth client) +
token.json (a refresh_token you already consented). Credentials never touch git.

    youtube_client check                 # verify auth + print channel stats
    youtube_client trending [--region US --n 10]
    youtube_client upload <video> --title "…" [--privacy private] [--desc "…"] [--tags a,b]

Scope note: youtube.force-ssl enables upload + read. Revenue ($) needs the separate
yt-analytics-monetary.readonly scope (re-consent) + AdSense — not wired here.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
CLIENT_SECRETS = ROOT / "client_secrets.json"
TOKEN = ROOT / "token.json"


def _creds():
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    if not (CLIENT_SECRETS.exists() and TOKEN.exists()):
        raise SystemExit("❌ client_secrets.json / token.json not found in repo root")
    t = json.loads(TOKEN.read_text())
    cs = json.loads(CLIENT_SECRETS.read_text())
    cs = cs.get("installed") or cs.get("web") or cs
    creds = Credentials(
        token=t.get("access_token") or t.get("token"),
        refresh_token=t["refresh_token"],
        token_uri="https://oauth2.googleapis.com/token",
        client_id=cs["client_id"],
        client_secret=cs["client_secret"],
        scopes=(t.get("scope") or "").split() or t.get("scopes"),
    )
    creds.refresh(Request())  # mint a fresh access token from the refresh_token
    return creds


def _yt():
    from googleapiclient.discovery import build
    return build("youtube", "v3", credentials=_creds(), cache_discovery=False)


def channel_stats() -> dict:
    r = _yt().channels().list(part="snippet,statistics", mine=True).execute()
    items = r.get("items", [])
    if not items:
        return {}
    ch = items[0]
    s = ch["statistics"]
    return {
        "channel": ch["snippet"]["title"],
        "subscribers": int(s.get("subscriberCount", 0)),
        "views": int(s.get("viewCount", 0)),
        "videos": int(s.get("videoCount", 0)),
    }


def trending(region: str = "US", n: int = 10) -> list[str]:
    r = _yt().videos().list(part="snippet", chart="mostPopular",
                            regionCode=region, maxResults=n).execute()
    return [i["snippet"]["title"] for i in r.get("items", [])]


def video_stats(video_id: str) -> dict:
    """Views/likes/comments for one of our videos (for the analytics feedback loop)."""
    r = _yt().videos().list(part="snippet,statistics", id=video_id).execute()
    items = r.get("items", [])
    if not items:
        return {}
    v = items[0]
    s = v.get("statistics", {})
    return {"id": video_id, "title": v["snippet"]["title"],
            "views": int(s.get("viewCount", 0)), "likes": int(s.get("likeCount", 0)),
            "comments": int(s.get("commentCount", 0))}


def upload(video: str, title: str, description: str = "", tags=None,
           privacy: str = "private", category: str = "27") -> str:
    from googleapiclient.http import MediaFileUpload
    if not pathlib.Path(video).exists():
        raise SystemExit(f"❌ video not found: {video}")
    body = {
        "snippet": {"title": title[:100], "description": description,
                    "tags": tags or [], "categoryId": category},   # 27 = Education
        "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False},
    }
    req = _yt().videos().insert(part="snippet,status", body=body,
                                media_body=MediaFileUpload(video, resumable=True))
    resp = None
    while resp is None:
        _, resp = req.next_chunk()
    return resp["id"]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="youtube_client")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    pt = sub.add_parser("trending"); pt.add_argument("--region", default="US"); pt.add_argument("--n", type=int, default=10)
    pu = sub.add_parser("upload"); pu.add_argument("video"); pu.add_argument("--title", required=True)
    pu.add_argument("--desc", default=""); pu.add_argument("--tags", default=""); pu.add_argument("--privacy", default="private")
    a = ap.parse_args(argv)
    if a.cmd == "check":
        s = channel_stats()
        print(f"  ✅ authenticated as: {s.get('channel','(unknown)')}")
        print(f"     {s.get('subscribers',0):,} subscribers · {s.get('views',0):,} views · {s.get('videos',0)} videos")
    elif a.cmd == "trending":
        for i, t in enumerate(trending(a.region, a.n), 1):
            print(f"  {i:2}. {t}")
    elif a.cmd == "upload":
        vid = upload(a.video, a.title, a.desc, [t for t in a.tags.split(",") if t], a.privacy)
        print(f"  ✅ uploaded ({a.privacy}): https://youtu.be/{vid}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
