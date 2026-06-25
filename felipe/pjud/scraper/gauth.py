"""Google auth + Drive/Sheets clients for the PJUD scraper.

Auth model: gcloud Application Default Credentials (ADC). One-time login:

    gcloud auth application-default login \
        --scopes=https://www.googleapis.com/auth/drive.file,\
https://www.googleapis.com/auth/spreadsheets,openid

stores a refresh token at the ADC well-known path. Every run loads it headlessly
— it never re-prompts, regardless of which device triggers the run. For CI, the
ADC JSON is provided via the GOOGLE_APPLICATION_CREDENTIALS env var (a secret).

`drive.file` limits us to files this app creates — enough, since setup creates the
folder, Sheet, and Documentos subfolder itself.
"""

import google.auth
from googleapiclient.discovery import build

SCOPES = [
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/spreadsheets",
]


def credentials():
    """Load ADC user credentials. Raises a clear error if login hasn't run."""
    try:
        creds, _ = google.auth.default(scopes=SCOPES)
    except google.auth.exceptions.DefaultCredentialsError as e:
        raise SystemExit(
            "[FATAL] No Google credentials. Run one-time login:\n"
            "  gcloud auth application-default login "
            "--scopes=https://www.googleapis.com/auth/drive.file,"
            "https://www.googleapis.com/auth/spreadsheets,openid\n"
            f"(underlying: {e})")
    return creds


def drive_client(creds=None):
    return build("drive", "v3", credentials=creds or credentials(),
                 cache_discovery=False)


def sheets_client(creds=None):
    return build("sheets", "v4", credentials=creds or credentials(),
                 cache_discovery=False)
