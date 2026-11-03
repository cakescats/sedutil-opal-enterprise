#!/usr/bin/env python3
"""End-to-end test against docker compose: enrolment and a real Keycloak sign-in.

    docker compose up -d --build
    BUILDER_PY=path/to/cakes-builder.py python3 e2e_test.py

1. enrols machine E2E-1 the way the rollout scripts do and gets its image;
2. reads the machine key from that image, as the PBA would use it;
3. alice opens a fresh QR code link, signs in and sees the password;
4. bob signs in and is refused.
"""
import html
import importlib.util
import os
import re
import sys
import tempfile
import time

import requests

import unlock

APP = "http://localhost:8000"
KC = "http://localhost:8080"


def wait(url, seconds=180):
    for _ in range(seconds):
        try:
            if requests.get(url, timeout=3).status_code == 200:
                return
        except requests.RequestException:
            pass
        time.sleep(1)
    sys.exit(f"{url} did not come up")


def machine_key(image_path):
    """sso_key from the overlay of a builder image."""
    spec = importlib.util.spec_from_file_location("builder", os.environ["BUILDER_PY"])
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    img = builder.read_image(image_path)
    offset, size = builder.esp_partition(img)
    fs = builder.FatImage(bytes(img[offset:offset + size]))
    conf = builder.cpio_read(fs.files[fs.find(builder.OVERLAY)])[builder.CONF_PATH].decode()
    return builder.effective(conf)["sso_key"]


def unlock_as(key, user, password):
    """Open a fresh QR code link, sign in through the Keycloak form, return the final page."""
    s = requests.Session()
    token = unlock.token_for(bytes.fromhex(key), "E2E-1", os.urandom(4))
    r = s.get(f"{APP}/m/E2E-1?c={token}", timeout=30)
    m = re.search(r'<form[^>]*id="kc-form-login"[^>]*action="([^"]+)"', r.text)
    if not m:
        sys.exit(f"no Keycloak login form at {r.url}:\n{r.text[:2000]}")
    return s.post(html.unescape(m.group(1)), data={"username": user, "password": password,
                                                   "credentialId": ""}, timeout=30)


def main():
    wait(f"{KC}/realms/cakes/.well-known/openid-configuration")
    wait(f"{APP}/healthz")

    r = requests.post(f"{APP}/api/enroll", json={"machine_id": "E2E-1", "password": "e2e-pass"},
                      headers={"Authorization": "Bearer demo-enroll-token"}, timeout=120)
    if r.status_code != 200 or r.content[512:520] != b"EFI PART":
        sys.exit(f"enrol: expected a disk image, got {r.status_code}: {r.text[:500]}")
    with tempfile.NamedTemporaryFile(suffix=".img") as f:
        f.write(r.content)
        f.flush()
        key = machine_key(f.name)
    print(f"enrolled E2E-1, image {len(r.content) // 1048576} MiB")

    r = unlock_as(key, "alice", "alice")
    if r.status_code != 200 or "e2e-pass" not in r.text:
        sys.exit(f"alice: expected the password, got {r.status_code} at {r.url}:\n{r.text[:2000]}")
    print("alice sees the password")
    r = unlock_as(key, "bob", "bob")
    if r.status_code != 403 or "e2e-pass" in r.text:
        sys.exit(f"bob: expected a refusal, got {r.status_code}:\n{r.text[:2000]}")
    print("bob is refused")


if __name__ == "__main__":
    main()
