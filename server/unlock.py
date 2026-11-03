"""Unlock server core: machines, QR code tokens, access rules and the audit log.

No web framework in here, so app.py, manage.py and the tests share it.
The token format must match LinuxPBA/PbaSso.cpp.
"""
import base64
import binascii
import hashlib
import hmac
import sqlite3
import time

CONTEXT = b"cakes-pba-sso-v1"
CHALLENGE_BYTES = 4
MAC_BYTES = 6
# failed token checks per machine and hour before the server stops answering
MAX_FAILURES_PER_HOUR = 20

SCHEMA = """
create table if not exists machines (
    id text primary key,
    key text not null,            -- hex, from cakes-builder's .machine.json
    password text not null,       -- shown after a successful check
    owners text not null default '' -- comma separated: user@corp, *@corp, *
);
create table if not exists used_tokens (
    machine_id text not null,
    challenge text not null,
    at integer not null,
    primary key (machine_id, challenge)
);
create table if not exists audit (
    at integer not null,
    machine_id text not null,
    user text not null,
    result text not null,
    ip text not null default ''
);
"""


class UnlockError(Exception):
    """A refused unlock; str() is safe to show to the user."""

    def __init__(self, message, reason):
        super().__init__(message)
        self.reason = reason  # for the audit log only


def connect(path):
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.executescript(SCHEMA)
    return db


def token_for(key, machine_id, challenge):
    """The token the PBA shows for a challenge: base32 of challenge + MAC."""
    msg = CONTEXT + b"\0" + machine_id.encode() + b"\0" + challenge
    mac = hmac.new(key, msg, hashlib.sha512).digest()[:MAC_BYTES]
    return base64.b32encode(challenge + mac).decode()


def parse_token(text):
    """Challenge and MAC from a token as shown or scanned, or None."""
    clean = "".join(c for c in text.upper() if c.isalnum())
    if len(clean) != 16:
        return None
    try:
        raw = base64.b32decode(clean)
    except (binascii.Error, ValueError):
        return None
    return raw[:CHALLENGE_BYTES], raw[CHALLENGE_BYTES:]


def allowed(owners, email):
    email = email.lower()
    for rule in (r.strip().lower() for r in owners.split(",")):
        if rule == "*" or rule == email:
            return True
        if rule.startswith("*@") and email.endswith(rule[1:]):
            return True
    return False


def log(db, machine_id, user, result, ip=""):
    db.execute("insert into audit (at, machine_id, user, result, ip) values (?, ?, ?, ?, ?)",
               (int(time.time()), machine_id, user, result, ip))
    db.commit()


def unlock(db, machine_id, token, email, ip=""):
    """Check a token for a signed-in user and return the machine password.

    Raises UnlockError. Every attempt goes into the audit log, and a token
    works once: the PBA makes a new one each time F2 is pressed.
    """
    try:
        row = db.execute("select * from machines where id = ?", (machine_id,)).fetchone()
        if row is None:
            raise UnlockError("This machine is not known to the unlock server.", "unknown machine")
        since = int(time.time()) - 3600
        failures = db.execute("select count(*) from audit where machine_id = ? and at > ? "
                              "and result like 'refused: bad code%'", (machine_id, since)).fetchone()[0]
        if failures >= MAX_FAILURES_PER_HOUR:
            raise UnlockError("Too many wrong codes for this machine. Try again in an hour.", "rate limit")
        parsed = parse_token(token)
        if parsed is None:
            raise UnlockError("The code is not valid. Press F2 on the machine for a new one.", "bad code format")
        challenge, mac = parsed
        expected = token_for(bytes.fromhex(row["key"]), machine_id, challenge)
        if not hmac.compare_digest(parse_token(expected)[1], mac):
            raise UnlockError("The code is not valid. Press F2 on the machine for a new one.", "bad code mac")
        if not allowed(row["owners"], email):
            raise UnlockError("Your account may not unlock this machine.", "not an owner")
        try:
            db.execute("insert into used_tokens (machine_id, challenge, at) values (?, ?, ?)",
                       (machine_id, challenge.hex(), int(time.time())))
        except sqlite3.IntegrityError:
            raise UnlockError("This code was used already. Press F2 on the machine for a new one.",
                              "code reused")
        log(db, machine_id, email, "unlocked", ip)
        return row["password"]
    except UnlockError as e:
        log(db, machine_id, email, "refused: " + e.reason, ip)
        raise
