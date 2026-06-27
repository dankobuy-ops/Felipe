"""Google auth + Drive/Sheets clients for the PJUD scraper.

Auth model: a **user-owned OAuth Desktop client** (we bring our own client ID, so
Google doesn't block the Sheets scope the way it does for gcloud's default client).

One-time setup (see pjud/HANDOFF.md for the console steps):
  1. Google Cloud Console → new project → enable Drive API + Sheets API.
  2. OAuth consent screen: External; **Publish** so the refresh token doesn't
     expire after 7 days (Testing tokens die in 7 days).
  3. Credentials → OAuth client ID → Desktop app → download as
     `pjud/scraper/client_secret.json` (gitignored).
  4. `python run.py --setup` runs the consent flow once, opens the real browser,
     and saves the refresh token to `pjud/scraper/token.json` (gitignored).

Every later run loads token.json headlessly and refreshes silently — it never
re-prompts, on any device. For CI the token.json contents are provided via the
PJUD_TOKEN_JSON env var (a GitHub secret); client_secret.json via PJUD_CLIENT_SECRET.

`drive.file` limits us to files this app creates — enough, since setup creates the
folder, Sheet, and Documentos subfolder itself.
"""

import json
import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/spreadsheets",
]

_HERE = Path(__file__).resolve().parent
CLIENT_SECRET_PATH = _HERE / "client_secret.json"
TOKEN_PATH = _HERE / "token.json"


def _load_client_secret_dict():
    """OAuth client config: env (CI) first, then client_secret.json on disk.
    Accepts GOOGLE_* (shared with JPL) or PJUD_* env var names."""
    raw = os.environ.get("GOOGLE_CLIENT_SECRET") or os.environ.get("PJUD_CLIENT_SECRET")
    if raw:
        return json.loads(raw)
    if CLIENT_SECRET_PATH.exists():
        return json.loads(CLIENT_SECRET_PATH.read_text(encoding="utf-8"))
    return None


def _load_saved_creds():
    """Existing user creds: env (CI) first, then token.json on disk.
    Accepts GOOGLE_* (shared with JPL) or PJUD_* env var names."""
    raw = os.environ.get("GOOGLE_TOKEN_JSON") or os.environ.get("PJUD_TOKEN_JSON")
    if raw:
        return Credentials.from_authorized_user_info(json.loads(raw), SCOPES)
    if TOKEN_PATH.exists():
        return Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    return None


def credentials(allow_login=False):
    """Return valid user credentials.

    Loads token.json (or PJUD_TOKEN_JSON), refreshes if expired. If no token
    exists, only triggers the interactive consent flow when `allow_login=True`
    (i.e. `run.py --setup`); otherwise raises with a clear instruction so a normal
    headless run never blocks on a browser prompt.
    """
    creds = _load_saved_creds()

    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _save_token(creds)
        return creds

    if not allow_login:
        raise SystemExit(
            "[FATAL] No Google credentials. Run the one-time login first:\n"
            "  python run.py --setup\n"
            "(needs pjud/scraper/client_secret.json — a Desktop OAuth client; "
            "see pjud/HANDOFF.md).")

    secret = _load_client_secret_dict()
    if not secret:
        raise SystemExit(
            "[FATAL] client_secret.json not found. Create a Desktop OAuth client "
            "in Google Cloud Console and save it to pjud/scraper/client_secret.json "
            "(or set PJUD_CLIENT_SECRET). See pjud/HANDOFF.md.")
    flow = InstalledAppFlow.from_client_config(secret, SCOPES)
    creds = flow.run_local_server(port=0)
    _save_token(creds)
    return creds


def _save_token(creds):
    """Persist refreshed/new creds to token.json (skip in CI, where it's an env)."""
    if os.environ.get("GOOGLE_TOKEN_JSON") or os.environ.get("PJUD_TOKEN_JSON"):
        return
    TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")


def drive_client(creds=None):
    return build("drive", "v3", credentials=creds or credentials(),
                 cache_discovery=False)


def sheets_client(creds=None):
    return build("sheets", "v4", credentials=creds or credentials(),
                 cache_discovery=False)
