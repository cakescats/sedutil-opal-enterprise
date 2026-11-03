#!/bin/sh
# Stand-in for sedutil-cli in the rollout script tests: one OPAL drive,
# /dev/nvme0, locking off until --enableLockingRange. Calls go to $FAKE_LOG.
log=${FAKE_LOG:-/tmp/fake-sedutil.log}
echo "$*" >> "$log"
case "$1" in
--scan)
	echo "Scanning for Opal compliant disks"
	echo "/dev/sda    No  USB Stick 1.0"
	echo "/dev/nvme0   2  FAKE OPAL SSD 1.0"
	;;
--query)
	if grep -q '^--enableLockingRange' "$log"; then
		echo "    Locked = N, LockingEnabled = Y, LockingSupported = Y, MBRDone = Y, MBREnabled = Y, MediaEncrypt = Y"
	else
		echo "    Locked = N, LockingEnabled = N, LockingSupported = Y, MBRDone = N, MBREnabled = N, MediaEncrypt = Y"
	fi
	;;
--loadPBAimage)
	[ "$(dd if="$3" bs=1 skip=512 count=8 2>/dev/null)" = "EFI PART" ] || { echo "not an image" >&2; exit 1; }
	;;
esac
exit 0
