"""Google auth + Drive/Sheets clients for the JPL scraper.

Same model as the PJUD scraper: a user-owned OAuth Desktop client (our own client
ID, so the Sheets scope isn't blocked). One Google account (danko.buy@gmail.com)
backs both scrapers, so this reuses the existing creds when present.

Resolution order for each of client_secret.json / token.json:
  1. env var (CI): GOOGLE_CLIENT_SECRET / GOOGLE_TOKEN_JSON (or the PJUD_* aliases)
  2. felipe/scraper/<file>            (JPL's own copy, if you drop one here)
  3. felipe/pjud/scraper/<file>       (reuse the PJUD setup already on disk)

So if PJUD is already set up on this machine, JPL works with zero extra steps.
`python run.py --setup` runs the one-time browser consent and writes token.json.

`drive.file` scope = only files this app creates — enough, since setup creates the
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
_PJUD = _HERE.parent / "pjud" / "scraper"          # sibling scraper, same account
CLIENT_SECRET_PATHS = [_HERE / "client_secret.json", _PJUD / "client_secret.json"]
TOKEN_PATHS = [_HERE / "token.json", _PJUD / "token.json"]
TOKEN_WRITE_PATH = _HERE / "token.json"            # where --setup saves a new token


def _first_existing(paths):
    return next((p for p in paths if p.exists()), None)


def _load_client_secret_dict():
    raw = os.environ.get("GOOGLE_CLIENT_SECRET") or os.environ.get("PJUD_CLIENT_SECRET")
    if raw:
        return json.loads(raw)
    path = _first_existing(CLIENT_SECRET_PATHS)
    return json.loads(path.read_text(encoding="utf-8")) if path else None


def _load_saved_creds():
    raw = os.environ.get("GOOGLE_TOKEN_JSON") or os.environ.get("PJUD_TOKEN_JSON")
    if raw:
        return Credentials.from_authorized_user_info(json.loads(raw), SCOPES)
    path = _first_existing(TOKEN_PATHS)
    return Credentials.from_authorized_user_file(str(path), SCOPES) if path else None


def credentials(allow_login=False):
    """Valid user credentials. Refreshes silently; only opens a browser when
    `allow_login=True` (i.e. `run.py --setup`) and no token exists yet."""
    creds = _load_saved_creds()

    if creds and creds.valid:
        return creds
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _save_token(creds)
        return creds

    if not allow_login:
        raise SystemExit(
            "[FATAL] No Google credentials. Run the one-time login:\n"
            "  python run.py --setup\n"
            "(needs client_secret.json — a Desktop OAuth client — in felipe/scraper/ "
            "or felipe/pjud/scraper/; see pjud/HANDOFF.md).")

    secret = _load_client_secret_dict()
    if not secret:
        raise SystemExit(
            "[FATAL] client_secret.json not found (felipe/scraper/, felipe/pjud/scraper/, "
            "or the GOOGLE_CLIENT_SECRET env var). See pjud/HANDOFF.md.")
    creds = InstalledAppFlow.from_client_config(secret, SCOPES).run_local_server(port=0)
    _save_token(creds)
    return creds


def _save_token(creds):
    """Persist refreshed/new creds to token.json (skip in CI, where it's an env)."""
    if os.environ.get("GOOGLE_TOKEN_JSON") or os.environ.get("PJUD_TOKEN_JSON"):
        return
    TOKEN_WRITE_PATH.write_text(creds.to_json(), encoding="utf-8")


def drive_client(creds=None):
    return build("drive", "v3", credentials=creds or credentials(),
                 cache_discovery=False)


def sheets_client(creds=None):
    return build("sheets", "v4", credentials=creds or credentials(),
                 cache_discovery=False)
