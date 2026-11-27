"""Minimal Oura API v2 client: OAuth2 login via localhost and a first data request.

Usage:
    python3 oura.py   # requires .env with client id/secret, see README.md
"""
import json
import secrets
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

AUTHORIZE_URL = "https://cloud.ouraring.com/oauth/authorize"
TOKEN_URL = "https://api.ouraring.com/oauth/token"
API_URL = "https://api.ouraring.com/v2/usercollection"
SCOPES = "email personal daily heartrate workout tag session spo2 heart_health"

ROOT = Path(__file__).parent
TOKENS_FILE = ROOT / "tokens.json"


def load_env():
    env = {}
    for line in (ROOT / ".env").read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            env[key.strip()] = value.strip()
    return env


def post_form(url, data):
    body = urllib.parse.urlencode(data).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    with urllib.request.urlopen(req) as resp:
        return json.load(resp)


def save_tokens(tokens):
    tokens["expires_at"] = time.time() + tokens.get("expires_in", 0)
    tokens["requested_scope"] = SCOPES
    TOKENS_FILE.write_text(json.dumps(tokens, indent=2))
    return tokens


def wait_for_code(redirect_uri):
    """Listen on the redirect URI's port for one request and return its query params."""
    parsed = urllib.parse.urlparse(redirect_uri)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.server.params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write("Ferdig, du kan lukke fanen.".encode())

        def log_message(self, *args):
            pass

    server = HTTPServer((parsed.hostname, parsed.port or 80), Handler)
    server.params = {}
    while not server.params:
        server.handle_request()  # ignore stray requests like /favicon.ico
    server.server_close()
    return server.params


def login(env):
    state = secrets.token_urlsafe(16)
    url = AUTHORIZE_URL + "?" + urllib.parse.urlencode({
        "response_type": "code",
        "client_id": env["OURA_CLIENT_ID"],
        "redirect_uri": env["OURA_REDIRECT_URI"],
        "scope": SCOPES,
        "state": state,
    })
    print("Åpner nettleseren for innlogging i Oura...")
    print("Hvis nettleseren ikke åpnet seg, gå til lenken:\n" + url)
    webbrowser.open(url)

    params = wait_for_code(env["OURA_REDIRECT_URI"])
    if "error" in params:
        raise SystemExit("Oura returnerte en feil: " + params["error"][0])
    if params.get("state", [None])[0] != state:
        raise SystemExit("Ugyldig state i svaret, innloggingen ble avbrutt.")

    return save_tokens(post_form(TOKEN_URL, {
        "grant_type": "authorization_code",
        "code": params["code"][0],
        "redirect_uri": env["OURA_REDIRECT_URI"],
        "client_id": env["OURA_CLIENT_ID"],
        "client_secret": env["OURA_CLIENT_SECRET"],
    }))


def refresh(env, tokens):
    return save_tokens(post_form(TOKEN_URL, {
        "grant_type": "refresh_token",
        "refresh_token": tokens["refresh_token"],
        "client_id": env["OURA_CLIENT_ID"],
        "client_secret": env["OURA_CLIENT_SECRET"],
    }))


def get_access_token(env):
    if not TOKENS_FILE.exists():
        return login(env)["access_token"]
    tokens = json.loads(TOKENS_FILE.read_text())
    if tokens.get("requested_scope") != SCOPES:
        return login(env)["access_token"]  # scopes changed, user must approve again
    if time.time() > tokens.get("expires_at", 0) - 60:
        try:
            tokens = refresh(env, tokens)
        except urllib.error.HTTPError:
            tokens = login(env)
    return tokens["access_token"]


def api_get(token, endpoint, **params):
    url = f"{API_URL}/{endpoint}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    with urllib.request.urlopen(req) as resp:
        return json.load(resp)


def main():
    env = load_env()
    token = get_access_token(env)

    print("\nPersonal info:")
    print(json.dumps(api_get(token, "personal_info"), indent=2, ensure_ascii=False))

    today = date.today()
    sleep = api_get(token, "daily_sleep",
                    start_date=(today - timedelta(days=7)).isoformat(),
                    end_date=today.isoformat())
    print("\nSøvnscore de siste 7 dagene:")
    for day in sleep.get("data", []):
        print(f"  {day['day']}: {day.get('score')}")


if __name__ == "__main__":
    main()
