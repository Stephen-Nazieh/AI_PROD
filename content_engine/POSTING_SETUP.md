# Posting setup — going live

`poster.py` is **dry-run by default** (safe preview, QA-gated). To post for real you add credentials
once, then pass `--live`. Nothing posts to your accounts until both are in place.

## YouTube Shorts (recommended first — self-serve)
1. [Google Cloud Console](https://console.cloud.google.com/) → new project → enable **YouTube Data API v3**.
2. Create an **OAuth client ID** of type **Desktop app**; download its `client_secret.json`.
3. Authorize once (opens a browser):
   ```
   pip install google-auth-oauthlib google-api-python-client
   env/bin/python3 content_engine/auth_youtube.py path/to/client_secret.json
   ```
   This writes the `youtube` block of `config/credentials.json` (with a refresh token, so no re-auth).
4. Go live:
   ```
   env/bin/python3 content_engine/poster.py --channel daily-curiosities --platform youtube --live
   ```
   Uploads land as **private** by default (`privacyStatus` in `poster.py`) — review, then flip to public.

## TikTok (needs app review)
TikTok's **Content Posting API** requires an approved developer app. Once approved:
1. Create an app at [developers.tiktok.com](https://developers.tiktok.com/), request the
   `video.publish` scope, complete the OAuth flow to get a **user access token**.
2. Put it in `config/credentials.json` under `tiktok.access_token` (+ `open_id`).
3. `env/bin/python3 content_engine/poster.py --channel daily-curiosities --platform tiktok --live`
   Posts default to `SELF_ONLY` (private) until you raise `privacy_level` in `poster.py`.

## Notes
- `config/credentials.json` holds secrets — it is git-ignored; never commit it.
- The poster runs the **QA gate** on every short before posting; failures are skipped, not uploaded.
- Manifests (`runs/<run>/out/publish.json`) carry the title, caption, and hashtags used per post.
