"""CakesCats PBA unlock server.

A phone opens the address from the PBA's QR code, the user signs in with the
company's OpenID Connect provider (Entra ID, Okta, Google, Keycloak...), and
the page shows the machine's password to type into the PBA. See docs/sso.md.

Settings come from the environment:

    OIDC_ISSUER          e.g. https://login.microsoftonline.com/<tenant>/v2.0
    OIDC_CLIENT_ID
    OIDC_CLIENT_SECRET
    OIDC_METADATA_URL    optional, when the server reaches the provider at
                         another address than the browser (docker compose)
    PUBLIC_URL           this server as users reach it, e.g. https://unlock.corp
    SECRET_KEY           random string that signs the session cookie
    UNLOCK_DB            SQLite file, default unlock.db

Enrolling machines from MDM scripts (docs/mdm.md):

    ENROLL_TOKEN         secret the rollout scripts send, enrolment is off without it
    BASE_IMAGE           released CakesCats PBA image (.img or .img.gz)
    BUILDER              cakes-builder.py from cakescats/sedutil-pba
    DEFAULT_OWNERS       who may unlock a new machine, e.g. *@corp.com
"""
import hmac
import html
import os
import re
import subprocess
import sys
import tempfile

from authlib.integrations.flask_client import OAuth
from flask import Flask, Response, abort, g, redirect, request, session, url_for

import unlock

app = Flask(__name__)
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY") or os.urandom(32),
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=os.environ.get("PUBLIC_URL", "").startswith("https://"),
)
PUBLIC_URL = os.environ.get("PUBLIC_URL", "http://localhost:8000").rstrip("/")

oauth = OAuth(app)
if os.environ.get("OIDC_ISSUER"):
    issuer = os.environ["OIDC_ISSUER"].rstrip("/")
    oauth.register(
        "idp",
        client_id=os.environ["OIDC_CLIENT_ID"],
        client_secret=os.environ["OIDC_CLIENT_SECRET"],
        server_metadata_url=os.environ.get("OIDC_METADATA_URL")
        or issuer + "/.well-known/openid-configuration",
        client_kwargs={"scope": "openid email profile"},
    )

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>CakesCats PBA unlock</title>
<style>
body{{margin:0;background:#070c2b;color:#d6d9ee;font:17px/1.5 system-ui,sans-serif}}
main{{max-width:520px;margin:0 auto;padding:32px 20px}}
h1{{color:#aa81ff;font-size:22px;margin:0 0 16px}}
.pw{{background:#10173f;border:1px solid #2d3568;border-radius:12px;padding:18px;
font:600 26px/1.3 ui-monospace,monospace;color:#f3f4fb;word-break:break-all;margin:16px 0}}
.err{{color:#ff6b8b}} .muted{{color:#a3a9cf;font-size:15px}}
input{{font:inherit;width:100%;box-sizing:border-box;padding:10px;margin:6px 0 14px;
border-radius:8px;border:1px solid #2d3568;background:#10173f;color:#f3f4fb}}
button{{font:inherit;padding:10px 18px;border-radius:8px;border:0;background:#8f6bff;color:#fff}}
a{{color:#57f3fe}}
</style></head><body><main>{body}</main></body></html>"""


def page(body, status=200):
    return PAGE.format(body=body), status


def db():
    if "db" not in g:
        g.db = unlock.connect(os.environ.get("UNLOCK_DB", "unlock.db"))
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    conn = g.pop("db", None)
    if conn is not None:
        conn.close()


@app.get("/healthz")
def healthz():
    return "ok"


@app.get("/")
def index():
    return page("""<h1>Unlock a CakesCats PBA</h1>
<p>Press F2 on the password screen of the computer and scan the QR code.
Without a camera, type what the screen shows:</p>
<form method="get" action="/go">
<label>Machine</label><input name="m" autocomplete="off" required>
<label>Code</label><input name="c" autocomplete="off" placeholder="XXXX-XXXX-XXXX-XXXX" required>
<button>Continue</button></form>""")


@app.get("/go")
def go():
    machine_id = request.args.get("m", "").strip()
    if not machine_id:
        return redirect("/")
    return redirect(url_for("machine", machine_id=machine_id, c=request.args.get("c", "").strip()))


@app.get("/m/<machine_id>")
def machine(machine_id):
    token = request.args.get("c", "")
    user = session.get("user")
    if not user:
        session["next"] = request.full_path
        return redirect(url_for("login"))
    try:
        password = unlock.unlock(db(), machine_id, token, user, request.remote_addr or "")
    except unlock.UnlockError as e:
        return page(f'<h1>Not unlocked</h1><p class="err">{html.escape(str(e))}</p>'
                    f'<p class="muted">Signed in as {html.escape(user)}. '
                    f'<a href="/logout">Sign out</a></p>', 403)
    return page(f"""<h1>Password for {html.escape(machine_id)}</h1>
<p>Type it into the password screen of the computer.</p>
<div class="pw">{html.escape(password)}</div>
<p class="muted">This unlock is recorded for {html.escape(user)}.
Close this page when you are done.</p>""")


MACHINE_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


@app.post("/api/enroll")
def enroll():
    """Register a machine and return its PBA image with the QR code set up.

    JSON body: machine_id, password (the drive's Admin1 password the script
    made up), optionally owners. Enrolling again replaces the machine.
    """
    expected = os.environ.get("ENROLL_TOKEN", "")
    given = request.headers.get("Authorization", "").removeprefix("Bearer ").strip()
    if not expected or not hmac.compare_digest(given.encode(), expected.encode()):
        abort(401)
    data = request.get_json(silent=True) or {}
    machine_id = str(data.get("machine_id", ""))
    password = str(data.get("password", ""))
    owners = str(data.get("owners") or os.environ.get("DEFAULT_OWNERS", ""))
    if not MACHINE_ID.match(machine_id) or not password or not owners:
        abort(400, "machine_id (letters, digits, . _ -), password and owners are needed")
    key = os.urandom(32).hex()
    with tempfile.TemporaryDirectory() as tmp:
        out = os.path.join(tmp, "pba.img")
        build = subprocess.run(
            [sys.executable, os.environ.get("BUILDER", "cakes-builder.py"), "build",
             "-i", os.environ.get("BASE_IMAGE", "cakes-pba.img.gz"), "-o", out,
             "--sso-url", PUBLIC_URL, "--machine-id", machine_id, "--sso-key", key],
            capture_output=True, text=True)
        if build.returncode:
            app.logger.error("image build failed: %s", build.stderr)
            abort(500, "image build failed")
        with open(out, "rb") as f:
            image = f.read()
    db().execute("insert or replace into machines (id, key, password, owners) values (?, ?, ?, ?)",
                 (machine_id, key, password, owners))
    db().commit()
    unlock.log(db(), machine_id, "enroll", "enrolled", request.remote_addr or "")
    return Response(image, mimetype="application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="{machine_id}.img"'})


@app.get("/login")
def login():
    idp = oauth.create_client("idp")
    if idp is None:
        abort(503, "OIDC_ISSUER is not set")
    return idp.authorize_redirect(PUBLIC_URL + "/auth/callback")


@app.get("/auth/callback")
def callback():
    token = oauth.idp.authorize_access_token()
    info = token.get("userinfo") or oauth.idp.userinfo()
    email = info.get("email")
    if not email or info.get("email_verified") is False:
        return page('<h1>Not signed in</h1><p class="err">The account has no verified email.</p>', 403)
    session["user"] = email.lower()
    return redirect(session.pop("next", None) or "/")


@app.get("/logout")
def logout():
    session.clear()
    return redirect("/")
