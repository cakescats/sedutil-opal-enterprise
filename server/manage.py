#!/usr/bin/env python3
"""Manage machines of the CakesCats PBA unlock server.

    manage.py add <machine.json> --password <pw> --owners alice@corp,*@corp
    manage.py add --id ACME-0042 --key <hex> --password <pw> --owners alice@corp
    manage.py owners <machine id> <owners>
    manage.py password <machine id> <pw>
    manage.py list
    manage.py audit [--limit N]

The database is UNLOCK_DB (default unlock.db). machine.json comes from
cakes-builder.py build --sso-url ... --machine-id ...
"""
import argparse
import json
import os
import sys
import time

import unlock


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add", help="add or replace a machine")
    a.add_argument("json", nargs="?", help="machine.json from cakes-builder")
    a.add_argument("--id")
    a.add_argument("--key")
    a.add_argument("--password", required=True, help="the drive password (Admin1) to show")
    a.add_argument("--owners", required=True, help="who may unlock: user@corp, *@corp or *")
    o = sub.add_parser("owners", help="change who may unlock a machine")
    o.add_argument("id")
    o.add_argument("owners")
    p = sub.add_parser("password", help="change the password shown for a machine")
    p.add_argument("id")
    p.add_argument("password")
    sub.add_parser("list", help="list machines")
    au = sub.add_parser("audit", help="show the audit log")
    au.add_argument("--limit", type=int, default=50)
    args = ap.parse_args()

    db = unlock.connect(os.environ.get("UNLOCK_DB", "unlock.db"))
    if args.cmd == "add":
        machine_id, key = args.id, args.key
        if args.json:
            with open(args.json) as f:
                data = json.load(f)
            machine_id, key = machine_id or data["machine_id"], key or data["key"]
        if not machine_id or not key:
            sys.exit("need machine.json or --id and --key")
        bytes.fromhex(key)
        db.execute("insert or replace into machines (id, key, password, owners) values (?, ?, ?, ?)",
                   (machine_id, key, args.password, args.owners))
        print(f"added {machine_id}")
    elif args.cmd in ("owners", "password"):
        column = "owners" if args.cmd == "owners" else "password"
        cur = db.execute(f"update machines set {column} = ? where id = ?", (getattr(args, column), args.id))
        if not cur.rowcount:
            sys.exit(f"no machine {args.id}")
    elif args.cmd == "list":
        for row in db.execute("select id, owners from machines order by id"):
            print(f"{row['id']}\t{row['owners']}")
    elif args.cmd == "audit":
        for row in db.execute("select * from audit order by at desc limit ?", (args.limit,)):
            when = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(row["at"]))
            print(f"{when}\t{row['machine_id']}\t{row['user']}\t{row['result']}\t{row['ip']}")
    db.commit()


if __name__ == "__main__":
    main()
