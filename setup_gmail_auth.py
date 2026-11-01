"""
Run this ONCE locally to generate Gmail OAuth credentials.
Outputs a JSON token you paste into GMAIL_TOKEN_JSON in your .env / Render env vars.

Usage:
    pip install google-auth-oauthlib
    python setup_gmail_auth.py
"""

import json
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar",
]

def main():
    print("This will open a browser to authorize your Gmail account.")
    print("Make sure you have downloaded your OAuth client_secret JSON from Google Cloud Console.\n")

    client_secrets_file = input("Path to your client_secret JSON file: ").strip()

    flow = InstalledAppFlow.from_client_secrets_file(client_secrets_file, SCOPES)
    creds = flow.run_local_server(port=8080)

    token_data = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "token_uri": creds.token_uri,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
        "scopes": list(creds.scopes),
    }

    print("\n✅ Authorization successful!")
    print("\nPaste this into your .env as GMAIL_TOKEN_JSON (all on one line):")
    print("\n" + json.dumps(token_data) + "\n")

    with open("gmail_token.json", "w") as f:
        json.dump(token_data, f, indent=2)
    print("Also saved to gmail_token.json for reference.")

if __name__ == "__main__":
    main()
