# Rolling out with MDM

The rollout scripts turn on OPAL hardware encryption with the CakesCats PBA
on each machine. They need no Python and no image builder on the machines,
only `sedutil-cli`:

1. The script finds the first OPAL 2.0 drive. If locking is on already, it
   stops: running it again is safe.
2. It makes up a random drive password and enrols the machine with the
   unlock server: `POST /api/enroll` with the enrolment token.
3. The server stores the password, builds this machine's PBA image with
   the QR code set up, and returns it.
4. The script runs `--initialSetup`, `--loadPBAimage` and
   `--enableLockingRange 0`. Locking takes effect at the next full power
   off.

The password never touches the machine's disk. Users never need it: they
get it from the QR code after signing in. IT can see it with `manage.py` on
the server.

Before rolling out:

- Run the unlock server, see [server.md](server.md). Set `ENROLL_TOKEN`,
  `DEFAULT_OWNERS` and a `BASE_IMAGE` from a release that shows the QR code
  (v1.20.0-cakes.2 or later).
- Try one machine by hand, with the drive's PSID written down.
- Check the machines' storage mode. OPAL works with NVMe and AHCI. With
  Intel RST/VMD in RAID mode, Windows sees no OPAL drive.
- BitLocker can stay on. It is a separate, software layer on top.

| Platform | Script | Tool |
|---|---|---|
| Windows | `mdm/windows/Enable-CakesPBA.ps1` | `sedutil-cli-windows-x64.exe` from a [sedutil-pba release](https://github.com/cakescats/sedutil-pba/releases), renamed to `sedutil-cli.exe` |
| Linux | `mdm/linux/enable-cakes-pba.sh` | `sedutil-cli-linux-x86_64` from the same release |

## Microsoft Intune (Windows)

Package the script and the tool as a Win32 app:

1. Put `Enable-CakesPBA.ps1` and `sedutil-cli.exe` into one folder.
2. `IntuneWinAppUtil.exe -c <folder> -s Enable-CakesPBA.ps1 -o <out>`
3. In Intune: Apps → Windows → Add → Windows app (Win32), and upload the `.intunewin`.
4. Program:
   - Install command:
     ```
     %SystemRoot%\sysnative\WindowsPowerShell\v1.0\powershell.exe -ExecutionPolicy Bypass -NoProfile -File Enable-CakesPBA.ps1 -Server https://unlock.corp.com -Token <enrol token>
     ```
     `sysnative` makes it run as 64-bit PowerShell: Intune starts Win32
     apps as 32-bit.
   - Uninstall command: `cmd /c exit 0`. Turning locking off is a manual
     step, see the PBA manual.
   - Install behaviour: System. Device restart behaviour: no specific action.
5. Detection rule: registry `HKEY_LOCAL_MACHINE\SOFTWARE\CakesCats\PBA`,
   value `Enrolled`, integer, equals 1.
6. Assign the app to a device group. Start with a pilot group.

Return code 0 means locking is on, 1 means it failed. The log is at
`%ProgramData%\CakesCats\PBA\enable.log`.

Intune admins can see the enrolment token in the install command. It only
allows enrolling machines, not reading passwords. Rotate it when people
leave by changing `ENROLL_TOKEN` and the command.

## Ansible (Linux)

```
cp sedutil-cli-linux-x86_64 mdm/ansible/
ansible-playbook -i inventory mdm/ansible/cakes-pba.yml \
    -e unlock_server=https://unlock.corp.com -e enroll_token=<token>
```

The playbook installs `sedutil-cli` and the script, then runs the script.
Machines with locking on already are reported as unchanged. The machine id
is the short host name. Add `-e owners=user@corp.com` to set who may unlock.

## Google Workspace (Windows device management)

Google's Windows device management installs MSI packages through a custom
setting with the OMA-URI
`./Device/Vendor/MSFT/EnterpriseDesktopAppManagement/MSI/{ProductID}/DownloadInstall`.
It doesn't run scripts. So the rollout needs an MSI that carries
`sedutil-cli.exe` and runs `Enable-CakesPBA.ps1` on install. That MSI is
the next step on the roadmap. Until then, use another tool that runs
PowerShell as SYSTEM.

## Other tools

Any tool that can run a script as SYSTEM or root works the same way, for
example Workspace ONE, ManageEngine, NinjaOne, Tactical RMM, SCCM, or a
Group Policy startup script:

```
Enable-CakesPBA.ps1 -Server https://unlock.corp.com -Token <token> [-Owners user@corp.com] [-MachineId PC-0042]
enable-cakes-pba.sh --server https://unlock.corp.com --token <token> [--owners user@corp.com] [--machine-id pc-0042]
```

Both scripts take `-DryRun` / `--dry-run` to show what they would do, and a
device (`\\.\PhysicalDrive1`, `/dev/nvme1`) when the first OPAL drive is not
the one.

## After the rollout

- Each machine locks at its next full power off. The PBA then asks for the
  password, and F2 shows the QR code.
- Set who may unlock each machine: `manage.py owners PC-0042 alice@corp.com`.
- Watch `manage.py audit` for enrolments and unlocks.
- Updating the PBA later is `sedutil-cli --loadPBAimage <password> <new image> <device>`.
  An update script is on the roadmap.
