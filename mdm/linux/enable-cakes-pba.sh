#!/bin/sh
# Enrol this machine with the CakesCats unlock server and turn on OPAL drive
# locking with the CakesCats PBA. Run as root, from MDM, Ansible or by hand.
# A drive that already has locking on is left alone, so running it again is safe.
#
#   enable-cakes-pba.sh --server https://unlock.corp.com --token <enrol token>
#       [--device /dev/nvme0] [--machine-id <id>] [--owners user@corp.com]
#       [--sedutil /path/to/sedutil-cli] [--dry-run]
#
# The drive password is made up here, sent to the unlock server over HTTPS
# and never written to disk. The server returns this machine's PBA image.
set -eu

SERVER=""
TOKEN=""
DEVICE=""
MACHINE_ID=$(hostname -s 2>/dev/null || hostname)
OWNERS=""
SEDUTIL=sedutil-cli
DRY_RUN=""

die() { echo "enable-cakes-pba: $*" >&2; exit 1; }

while [ $# -gt 0 ]; do
	case "$1" in
	--server) SERVER=${2%/}; shift 2 ;;
	--token) TOKEN=$2; shift 2 ;;
	--device) DEVICE=$2; shift 2 ;;
	--machine-id) MACHINE_ID=$2; shift 2 ;;
	--owners) OWNERS=$2; shift 2 ;;
	--sedutil) SEDUTIL=$2; shift 2 ;;
	--dry-run) DRY_RUN=1; shift ;;
	-h|--help) sed -n '2,13p' "$0"; exit 0 ;;
	*) die "unknown option $1" ;;
	esac
done
if [ -z "$SERVER" ] || [ -z "$TOKEN" ]; then die "--server and --token are needed"; fi
# tests run the script against a stand-in sedutil-cli without root
[ -n "$DRY_RUN" ] || [ -n "${CAKES_PBA_TEST:-}" ] || [ "$(id -u)" = 0 ] || die "run as root"
command -v curl >/dev/null || die "curl is needed"
command -v "$SEDUTIL" >/dev/null || die "sedutil-cli not found, use --sedutil"
echo "$MACHINE_ID" | grep -Eq '^[A-Za-z0-9._-]{1,64}$' || die "machine id '$MACHINE_ID' must be letters, digits, . _ -"
[ -z "$OWNERS" ] || echo "$OWNERS" | grep -Eq '^[A-Za-z0-9.@*_+, -]+$' || die "bad --owners"

if [ -z "$DEVICE" ]; then
	# first drive with OPAL 2.0: "/dev/nvme0   2  Model ..."
	DEVICE=$("$SEDUTIL" --scan | awk '$1 ~ /^\/dev\// && $2 ~ /2/ { print $1; exit }')
	[ -n "$DEVICE" ] || die "no OPAL 2.0 drive found"
fi
if "$SEDUTIL" --query "$DEVICE" | grep -q 'LockingEnabled = Y'; then
	echo "$DEVICE: locking is on already, nothing to do"
	exit 0
fi
echo "$DEVICE: enrolling $MACHINE_ID with $SERVER"
if [ -n "$DRY_RUN" ]; then
	echo "dry run: would enrol, then --initialSetup, --loadPBAimage, --enableLockingRange 0 on $DEVICE"
	exit 0
fi

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
umask 077
PASSWORD=$(head -c 18 /dev/urandom | base64 | tr -d '/+=\n')
# token and password go through files, not the command line
printf 'Authorization: Bearer %s\n' "$TOKEN" > "$tmp/header"
printf '{"machine_id":"%s","password":"%s"%s}' "$MACHINE_ID" "$PASSWORD" \
	"${OWNERS:+,\"owners\":\"$OWNERS\"}" > "$tmp/body"
curl -fsS -H @"$tmp/header" -H 'Content-Type: application/json' --data-binary @"$tmp/body" \
	-o "$tmp/pba.img" "$SERVER/api/enroll" || die "enrolment failed"
rm -f "$tmp/body"
[ "$(dd if="$tmp/pba.img" bs=1 skip=512 count=8 2>/dev/null)" = "EFI PART" ] ||
	die "the server did not return a disk image"

# sedutil-cli only takes the password as an argument; it is visible to
# other root processes for the seconds these commands run
"$SEDUTIL" --initialSetup "$PASSWORD" "$DEVICE" || die "--initialSetup failed (drive owned already?)"
"$SEDUTIL" --loadPBAimage "$PASSWORD" "$tmp/pba.img" "$DEVICE" || die "--loadPBAimage failed"
"$SEDUTIL" --enableLockingRange 0 "$PASSWORD" "$DEVICE" || die "--enableLockingRange failed"
PASSWORD=""
echo "$DEVICE: locking is on. It takes effect at the next full power off."
