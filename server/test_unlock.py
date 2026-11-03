"""Tests for the unlock server: python3 -m unittest -v test_unlock (in server/)."""
import os
import re
import tempfile
import unittest

import unlock

KEY = bytes(range(32))
# the same vector LinuxPBA/PbaSso.cpp is tested against in tests/host
PBA_TOKEN = "AEBAGBCJ7V2ZPR3S"


class TokenTest(unittest.TestCase):
    def test_matches_pba(self):
        self.assertEqual(unlock.token_for(KEY, "ACME-0042", bytes([1, 2, 3, 4])), PBA_TOKEN)

    def test_parse_accepts_display_form(self):
        self.assertEqual(unlock.parse_token("aeba-gbcj-7v2z-pr3s"), unlock.parse_token(PBA_TOKEN))
        self.assertIsNone(unlock.parse_token("AEBA-GBCJ"))
        self.assertIsNone(unlock.parse_token("0000000000000000"))  # 0 is not base32

    def test_owners(self):
        self.assertTrue(unlock.allowed("alice@corp.com", "Alice@Corp.com"))
        self.assertTrue(unlock.allowed("bob@x, *@corp.com", "carol@corp.com"))
        self.assertFalse(unlock.allowed("*@corp.com", "eve@corp.com.evil"))
        self.assertFalse(unlock.allowed("", "alice@corp.com"))
        self.assertTrue(unlock.allowed("*", "anyone@anywhere"))


class UnlockTest(unittest.TestCase):
    def setUp(self):
        self.db = unlock.connect(":memory:")
        self.db.execute("insert into machines values (?, ?, ?, ?)",
                        ("ACME-0042", KEY.hex(), "drive-pass", "alice@corp.com"))

    def token(self, n):
        return unlock.token_for(KEY, "ACME-0042", n.to_bytes(4, "big"))

    def results(self):
        return [r["result"] for r in self.db.execute("select result from audit order by rowid")]

    def test_unlock_once(self):
        t = self.token(7)
        self.assertEqual(unlock.unlock(self.db, "ACME-0042", t, "alice@corp.com"), "drive-pass")
        with self.assertRaisesRegex(unlock.UnlockError, "used already"):
            unlock.unlock(self.db, "ACME-0042", t, "alice@corp.com")
        self.assertEqual(self.results(), ["unlocked", "refused: code reused"])

    def test_refusals(self):
        with self.assertRaisesRegex(unlock.UnlockError, "not known"):
            unlock.unlock(self.db, "OTHER", self.token(1), "alice@corp.com")
        with self.assertRaisesRegex(unlock.UnlockError, "may not unlock"):
            unlock.unlock(self.db, "ACME-0042", self.token(2), "mallory@corp.com")
        bad = self.token(3)
        bad = bad[:-1] + ("A" if bad[-1] != "A" else "B")
        with self.assertRaisesRegex(unlock.UnlockError, "not valid"):
            unlock.unlock(self.db, "ACME-0042", bad, "alice@corp.com")
        # a refused owner check does not burn the token
        self.assertEqual(unlock.unlock(self.db, "ACME-0042", self.token(2), "alice@corp.com"), "drive-pass")

    def test_rate_limit(self):
        for i in range(unlock.MAX_FAILURES_PER_HOUR):
            with self.assertRaises(unlock.UnlockError):
                unlock.unlock(self.db, "ACME-0042", "AAAAAAAAAAAAAAAA", "alice@corp.com")
        with self.assertRaisesRegex(unlock.UnlockError, "Too many"):
            unlock.unlock(self.db, "ACME-0042", self.token(9), "alice@corp.com")


class AppTest(unittest.TestCase):
    """Web flow with the session set directly instead of a real sign-in."""

    def setUp(self):
        fd, self.path = tempfile.mkstemp()
        os.close(fd)
        os.environ["UNLOCK_DB"] = self.path
        import app as app_module
        self.app = app_module.app
        self.app.config["TESTING"] = True
        db = unlock.connect(self.path)
        db.execute("insert into machines values (?, ?, ?, ?)",
                   ("ACME-0042", KEY.hex(), "drive-pass", "*@corp.com"))
        db.commit()
        db.close()
        self.client = self.app.test_client()

    def tearDown(self):
        os.unlink(self.path)

    def test_needs_sign_in_and_remembers_the_code(self):
        r = self.client.get("/m/ACME-0042?c=" + PBA_TOKEN)
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r.headers["Location"].endswith("/login"))
        with self.client.session_transaction() as s:
            self.assertEqual(s["next"], "/m/ACME-0042?c=" + PBA_TOKEN)

    def test_shows_password_to_owner(self):
        with self.client.session_transaction() as s:
            s["user"] = "carol@corp.com"
        token = unlock.token_for(KEY, "ACME-0042", b"\x00\x00\x00\x05")
        r = self.client.get("/m/ACME-0042?c=" + token)
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"drive-pass", r.data)
        r = self.client.get("/m/ACME-0042?c=" + token)
        self.assertEqual(r.status_code, 403)
        self.assertNotIn(b"drive-pass", r.data)

    def test_manual_form(self):
        r = self.client.get("/go?m=ACME-0042&c=AEBA-GBCJ-7V2Z-PR3S")
        self.assertEqual(r.status_code, 302)
        self.assertTrue(re.search(r"/m/ACME-0042\?c=AEBA-GBCJ-7V2Z-PR3S$", r.headers["Location"]))


STUB_BUILDER = """import sys
args = sys.argv[1:]
out = args[args.index("-o") + 1]
with open(out, "w") as f:
    f.write(" ".join(args))
"""


class EnrollTest(unittest.TestCase):
    """Enrolment with a stand-in for cakes-builder.py that records its arguments."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        stub = os.path.join(self.tmp.name, "builder.py")
        with open(stub, "w") as f:
            f.write(STUB_BUILDER)
        os.environ.update(UNLOCK_DB=os.path.join(self.tmp.name, "u.db"), BUILDER=stub,
                          BASE_IMAGE="base.img.gz", ENROLL_TOKEN="t0ken", DEFAULT_OWNERS="*@corp.com")
        import app as app_module
        self.client = app_module.app.test_client()

    def tearDown(self):
        for k in ("BUILDER", "BASE_IMAGE", "ENROLL_TOKEN", "DEFAULT_OWNERS"):
            os.environ.pop(k, None)
        self.tmp.cleanup()

    def post(self, body, token="t0ken"):
        return self.client.post("/api/enroll", json=body, headers={"Authorization": "Bearer " + token})

    def test_needs_token(self):
        self.assertEqual(self.post({"machine_id": "PC-1", "password": "p"}, token="wrong").status_code, 401)
        os.environ["ENROLL_TOKEN"] = ""
        self.assertEqual(self.post({"machine_id": "PC-1", "password": "p"}, token="").status_code, 401)

    def test_checks_input(self):
        self.assertEqual(self.post({"machine_id": "PC 1", "password": "p"}).status_code, 400)
        self.assertEqual(self.post({"machine_id": "PC-1"}).status_code, 400)

    def test_enrolls_and_builds(self):
        r = self.post({"machine_id": "PC-1", "password": "drive-pw"})
        self.assertEqual(r.status_code, 200)
        args = r.data.decode().split()
        self.assertEqual(args[args.index("--machine-id") + 1], "PC-1")
        self.assertEqual(args[args.index("-i") + 1], "base.img.gz")
        key = args[args.index("--sso-key") + 1]
        db = unlock.connect(os.environ["UNLOCK_DB"])
        row = db.execute("select * from machines where id = 'PC-1'").fetchone()
        self.assertEqual((row["key"], row["password"], row["owners"]), (key, "drive-pw", "*@corp.com"))
        # the image's key unlocks the machine for an owner
        token = unlock.token_for(bytes.fromhex(key), "PC-1", b"\x00\x00\x00\x01")
        self.assertEqual(unlock.unlock(db, "PC-1", token, "dana@corp.com"), "drive-pw")


if __name__ == "__main__":
    unittest.main()
