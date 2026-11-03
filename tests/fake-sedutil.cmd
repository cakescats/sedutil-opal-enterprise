@echo off
rem Stand-in for sedutil-cli.exe in the PowerShell dry run test: one OPAL drive.
if "%1"=="--scan" (
  echo Scanning for Opal compliant disks
  echo \\.\PhysicalDrive0  No  USB Stick 1.0
  echo \\.\PhysicalDrive1   2  FAKE OPAL SSD 1.0
  exit /b 0
)
rem FAKE_DRIVE=noopal: the drive has no OPAL; FAKE_DRIVE=owned: SID changed, locking off
if "%1"=="--query" (
  if "%FAKE_DRIVE%"=="noopal" (
    echo Invalid or unsupported disk %2
    exit /b 0
  )
  echo     Locked = N, LockingEnabled = N, LockingSupported = Y, MBRDone = N, MBREnabled = N, MediaEncrypt = Y
  if "%FAKE_DRIVE%"=="owned" echo     SID equals MSID = N, SID blocked = N, HW Reset can clear  = N
  exit /b 0
)
exit /b 0
