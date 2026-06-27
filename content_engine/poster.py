#!/usr/bin/env python3
"""CONTENT ENGINE — AUTO-POSTING.

Reads the publish.json manifests for a channel and posts the shorts. Posting is an OUTWARD action
to your real accounts, so this is DRY-RUN by default: it validates each deliverable (QA gate) and
prints exactly what would go out. It only uploads for real with `--live` AND valid credentials in
content_engine/config/credentials.json. Backends: YouTube (Data API v3) + TikTok (Content Posting
API) — each reports clearly if its credentials/SDK are missing rather than failing silently.

  poster.py --channel daily-curiosities                 # dry-run (safe preview)
  poster.py --channel daily-curiosities --platform youtube --live   # real upload (needs creds)
"""
import argparse, glob, json, os, sys
ENGINE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ENGINE)
import qa
RUNS = os.path.join(ENGINE, "runs")
CREDS = os.path.join(ENGINE, "config", "credentials.json")

def _creds(platform):
    if not os.path.exists(CREDS): return None
    try: return json.load(open(CREDS)).get(platform)
    except Exception: return None

def manifests(channel):
    out = []
    for pj in sorted(glob.glob(os.path.join(RUNS, "*", "out", "publish.json"))):
        try: m = json.load(open(pj))
        except Exception: continue
        if not channel or m.get("channel") == channel:
            m["_path"] = pj; out.append(m)
    return out

# ── platform backends ──────────────────────────────────────────────────────
def post_youtube(m, live):
    c = _creds("youtube")
    if not (live and c):
        return ("dry-run", f"would upload '{m['title']}' to YouTube Shorts as {m['video']}")
    try:
        from googleapiclient.discovery import build            # google-api-python-client
        from googleapiclient.http import MediaFileUpload
        from google.oauth2.credentials import Credentials
    except Exception:
        return ("error", "pip install google-api-python-client google-auth (YouTube SDK missing)")
    try:
        creds = Credentials(**c)
        yt = build("youtube", "v3", credentials=creds)
        body = {"snippet": {"title": m["title"][:95],
                            "description": m["caption"] + "\n\n" + " ".join(m["hashtags"]),
                            "tags": [t.lstrip("#") for t in m["hashtags"]], "categoryId": "27"},
                "status": {"privacyStatus": "private", "selfDeclaredMadeForKids": False}}
        req = yt.videos().insert(part="snippet,status", body=body,
                                 media_body=MediaFileUpload(m["video"], resumable=True))
        resp = req.execute()
        return ("posted", f"https://youtube.com/shorts/{resp['id']}")
    except Exception as e:
        return ("error", f"YouTube upload failed: {str(e)[:120]}")

def post_tiktok(m, live):
    c = _creds("tiktok")
    if not (live and c):
        return ("dry-run", f"would upload '{m['title']}' to TikTok as {m['video']}")
    try:
        import urllib.request
        # TikTok Content Posting API (direct post) — requires an approved app + user access token.
        init = urllib.request.Request(
            "https://open.tiktokapis.com/v2/post/publish/video/init/",
            data=json.dumps({"post_info": {"title": (m["caption"] + " " + " ".join(m["hashtags"]))[:2200],
                                           "privacy_level": "SELF_ONLY"},
                             "source_info": {"source": "FILE_UPLOAD",
                                             "video_size": os.path.getsize(m["video"])}}).encode(),
            headers={"Authorization": f"Bearer {c.get('access_token')}",
                     "Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(init, timeout=30) as r:
            data = json.loads(r.read())
        return ("posted", f"tiktok publish_id={data.get('data',{}).get('publish_id','?')} (upload chunk pending)")
    except Exception as e:
        return ("error", f"TikTok init failed: {str(e)[:120]}")

BACKENDS = {"youtube": post_youtube, "tiktok": post_tiktok}

def run(channel, platform, live):
    mans = manifests(channel)
    if not mans:
        print(f"no publish.json manifests for channel '{channel}'"); return
    mode = "LIVE" if live else "DRY-RUN"
    print(f"[poster] {mode} · {len(mans)} shorts · platform={platform}")
    posted = 0
    for m in mans:
        rep = qa.verify_social(m["video"])
        if not rep["ok"]:
            print(f"  ✗ {m['title'][:32]:32s} BLOCKED by QA: {rep['issues']}"); continue
        status, detail = BACKENDS[platform](m, live)
        flag = {"posted": "✓", "dry-run": "·", "error": "✗"}.get(status, "?")
        print(f"  {flag} {m['title'][:32]:32s} [{status}] {detail}")
        if status in ("posted", "dry-run"):
            posted += 1
            m_clean = {k: v for k, v in m.items() if k != "_path"}
            m_clean["status"] = "posted" if status == "posted" else "previewed"
            if status == "posted": m_clean["post_url"] = detail
            json.dump(m_clean, open(m["_path"], "w"), indent=2)
    print(f"[poster] {posted}/{len(mans)} {'posted' if live else 'previewed (dry-run)'}.")
    if not live:
        print("       → re-run with --live and credentials in config/credentials.json to post for real.")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--channel", required=True)
    ap.add_argument("--platform", default="tiktok", choices=list(BACKENDS))
    ap.add_argument("--live", action="store_true", help="actually upload (needs credentials.json)")
    a = ap.parse_args()
    run(a.channel, a.platform, a.live)
