#!/usr/bin/env python3
"""One-time YouTube OAuth → writes the `youtube` block of config/credentials.json.

Prereq: a Google Cloud project with the YouTube Data API v3 enabled, an OAuth 2.0 Desktop client,
and its client_secret.json downloaded. Then:

  pip install google-auth-oauthlib google-api-python-client
  env/bin/python3 content_engine/auth_youtube.py path/to/client_secret.json

A browser opens for consent; the refresh token is saved so posting never needs re-auth.
"""
import json, os, sys
ENGINE = os.path.dirname(os.path.abspath(__file__))
CREDS = os.path.join(ENGINE, "config", "credentials.json")
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

def main():
    if len(sys.argv) < 2:
        sys.exit("usage: auth_youtube.py <client_secret.json>")
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
    except Exception:
        sys.exit("pip install google-auth-oauthlib google-api-python-client first")
    flow = InstalledAppFlow.from_client_secrets_file(sys.argv[1], SCOPES)
    creds = flow.run_local_server(port=0)
    block = {"token": creds.token, "refresh_token": creds.refresh_token,
             "token_uri": creds.token_uri, "client_id": creds.client_id,
             "client_secret": creds.client_secret, "scopes": SCOPES}
    all_creds = {}
    if os.path.exists(CREDS):
        try: all_creds = json.load(open(CREDS))
        except Exception: pass
    all_creds["youtube"] = block
    json.dump(all_creds, open(CREDS, "w"), indent=2)
    os.chmod(CREDS, 0o600)
    print(f"✓ YouTube credentials saved → {CREDS}")
    print("  now: env/bin/python3 content_engine/poster.py --channel <ch> --platform youtube --live")

if __name__ == "__main__":
    main()
