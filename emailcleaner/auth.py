"""OAuth2 authentication for Gmail API."""

import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES_MODIFY = ["https://www.googleapis.com/auth/gmail.modify"]
SCOPES_FULL = ["https://mail.google.com/"]

DEFAULT_TOKEN_DIR = Path(__file__).parent.parent / ".emailcleaner"


def get_gmail_service(
    credentials_path: str = "credentials.json",
    token_dir: str | Path = DEFAULT_TOKEN_DIR,
    full_access: bool = False,
):
    """Authenticate and return a Gmail API service object.

    Args:
        credentials_path: Path to the OAuth2 client secrets JSON file.
        token_dir: Directory to store/load the persistent token.
        full_access: If True, request full mail scope (needed for permanent delete).
    """
    token_dir = Path(token_dir)
    token_dir.mkdir(parents=True, exist_ok=True)
    token_path = token_dir / "token.json"

    scopes = SCOPES_FULL if full_access else SCOPES_MODIFY

    creds = None
    if token_path.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(token_path), scopes)
        except Exception:
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                creds = None

        if not creds or not creds.valid:
            if not os.path.exists(credentials_path):
                raise FileNotFoundError(
                    f"OAuth credentials file not found: {credentials_path}\n"
                    "Download it from Google Cloud Console:\n"
                    "  1. Go to console.cloud.google.com\n"
                    "  2. Create a project and enable the Gmail API\n"
                    "  3. Create OAuth 2.0 credentials (Desktop app)\n"
                    "  4. Download the JSON and save it as credentials.json"
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                credentials_path, scopes
            )
            creds = flow.run_local_server(port=0)

        token_path.write_text(creds.to_json())
        os.chmod(token_path, 0o600)

    return build("gmail", "v1", credentials=creds)
