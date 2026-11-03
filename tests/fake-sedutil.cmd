@echo off
rem Stand-in for sedutil-cli.exe in the PowerShell dry run test: one OPAL drive.
if "%1"=="--scan" (
  echo Scanning for Opal compliant disks
  echo \\.\PhysicalDrive0  No  USB Stick 1.0
  echo \\.\PhysicalDrive1   2  FAKE OPAL SSD 1.0
  exit /b 0
)
if "%1"=="--query" (
  echo     Locked = N, LockingEnabled = N, LockingSupported = Y, MBRDone = N, MBREnabled = N, MediaEncrypt = Y
  exit /b 0
)
exit /b 0
