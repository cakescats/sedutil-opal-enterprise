<#
.SYNOPSIS
Enrols this PC with the CakesCats unlock server and turns on OPAL drive
locking with the CakesCats PBA.

.DESCRIPTION
Meant to run as SYSTEM from Intune (Win32 app) or any MDM that runs
PowerShell. A drive that already has locking on is left alone, so running it
again is safe. The drive password is made up here, sent to the unlock server
over HTTPS and never written to disk. The server returns this PC's PBA image.

Writes HKLM:\SOFTWARE\CakesCats\PBA (Enrolled, MachineId, Device) for MDM
detection rules, and logs to %ProgramData%\CakesCats\PBA\enable.log.

.EXAMPLE
Enable-CakesPBA.ps1 -Server https://unlock.corp.com -Token <enrol token>
#>
param(
    [Parameter(Mandatory = $true)] [string] $Server,
    [Parameter(Mandatory = $true)] [string] $Token,
    # e.g. \\.\PhysicalDrive0; the first OPAL 2.0 drive when left out
    [string] $Device,
    [string] $MachineId = $env:COMPUTERNAME,
    # who may unlock it, e.g. user@corp.com; the server default when left out
    [string] $Owners,
    [string] $Sedutil = (Join-Path $PSScriptRoot 'sedutil-cli.exe'),
    [switch] $DryRun
)

$ErrorActionPreference = 'Stop'
$logDir = Join-Path $env:ProgramData 'CakesCats\PBA'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$log = Join-Path $logDir 'enable.log'

function Write-Log([string] $Message) {
    "$(Get-Date -Format s) $Message" | Tee-Object -FilePath $log -Append
}

function Invoke-Sedutil([string[]] $Arguments, [string] $What) {
    # the password is an argument; never log the arguments
    $output = & $Sedutil @Arguments 2>&1
    if ($LASTEXITCODE -ne 0) {
        throw "sedutil-cli $What failed ($LASTEXITCODE): $output"
    }
    return $output
}

function Set-Marker([string] $Drive) {
    $key = 'HKLM:\SOFTWARE\CakesCats\PBA'
    New-Item -Path $key -Force | Out-Null
    Set-ItemProperty -Path $key -Name Enrolled -Value 1 -Type DWord
    Set-ItemProperty -Path $key -Name MachineId -Value $MachineId
    Set-ItemProperty -Path $key -Name Device -Value $Drive
}

try {
    $Server = $Server.TrimEnd('/')
    if (-not (Test-Path $Sedutil)) { throw "sedutil-cli.exe not found at $Sedutil" }
    if ($MachineId -notmatch '^[A-Za-z0-9._-]{1,64}$') {
        throw "machine id '$MachineId' must be letters, digits, . _ -"
    }

    if (-not $Device) {
        # first drive with OPAL 2.0: "\\.\PhysicalDrive0  2  Model ..."
        foreach ($line in (& $Sedutil --scan)) {
            if ($line -match '^(\\\\\.\\PhysicalDrive\d+)\s+\S*2') { $Device = $Matches[1]; break }
        }
        if (-not $Device) { throw 'no OPAL 2.0 drive found' }
    }

    $query = Invoke-Sedutil @('--query', $Device) 'query'
    if ($query -match 'LockingEnabled = Y') {
        Write-Log "${Device}: locking is on already, nothing to do"
        Set-Marker $Device
        exit 0
    }
    Write-Log "${Device}: enrolling $MachineId with $Server"
    if ($DryRun) {
        Write-Log "dry run: would enrol, then --initialSetup, --loadPBAimage, --enableLockingRange 0 on $Device"
        exit 0
    }

    $bytes = New-Object byte[] 18
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $password = [Convert]::ToBase64String($bytes) -replace '[+/=]', ''

    $body = @{ machine_id = $MachineId; password = $password }
    if ($Owners) { $body.owners = $Owners }
    $image = Join-Path $env:TEMP "cakes-pba-$([guid]::NewGuid()).img"
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    try {
        Invoke-WebRequest -Uri "$Server/api/enroll" -Method Post -UseBasicParsing `
            -Headers @{ Authorization = "Bearer $Token" } -ContentType 'application/json' `
            -Body ($body | ConvertTo-Json) -OutFile $image
        $head = [IO.File]::ReadAllBytes($image)[512..519]
        if ([Text.Encoding]::ASCII.GetString($head) -ne 'EFI PART') {
            throw 'the server did not return a disk image'
        }
        Invoke-Sedutil @('--initialSetup', $password, $Device) '--initialSetup (drive owned already?)' | Out-Null
        Invoke-Sedutil @('--loadPBAimage', $password, $image, $Device) '--loadPBAimage' | Out-Null
        Invoke-Sedutil @('--enableLockingRange', '0', $password, $Device) '--enableLockingRange' | Out-Null
    }
    finally {
        Remove-Item -Force -ErrorAction SilentlyContinue $image
        $password = $null
    }
    Set-Marker $Device
    Write-Log "${Device}: locking is on. It takes effect at the next full power off."
    exit 0
}
catch {
    Write-Log "error: $_"
    exit 1
}
