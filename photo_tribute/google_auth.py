"""Google Photos OAuth2 using credentials from client_secrets.json."""

import json
from pathlib import Path

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/photoslibrary.appendonly",
]
TOKEN_FILE = Path("token.json")
SECRETS_FILE = Path("client_secrets.json")


def get_credentials() -> Credentials:
    """Return valid Google credentials, refreshing or re-authing as needed."""
    creds = None

    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not SECRETS_FILE.exists():
                raise FileNotFoundError(
                    f"{SECRETS_FILE} not found. Download OAuth client credentials "
                    "from Google Cloud Console and save as client_secrets.json."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(SECRETS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)

        TOKEN_FILE.write_text(creds.to_json())

    return creds
