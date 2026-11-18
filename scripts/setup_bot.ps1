# Copy one Sanity role into a Hermes profile and install Python deps.
# Tokens stay out of this script. HERMES_PROFILE_DIR is a placeholder path.
#
#   $env:HERMES_PROFILE_DIR = "$env:USERPROFILE\.hermes\profiles\sanity-reader"
#   .\scripts\setup_bot.ps1 reader
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("reader", "verifier", "writer")]
    [string]$Role
)

$ErrorActionPreference = "Stop"

if (-not $env:HERMES_PROFILE_DIR) {
    $env:HERMES_PROFILE_DIR = Join-Path $env:USERPROFILE ".hermes\profiles\sanity-$Role"
}
$ProfileDir = $env:HERMES_PROFILE_DIR

$Root = Split-Path -Parent $PSScriptRoot

if ($env:SANITY_WORKDIR) {
    if (-not (Test-Path (Join-Path $env:SANITY_WORKDIR ".git"))) {
        if (-not $env:SANITY_REPO_URL) {
            Write-Error "Set SANITY_REPO_URL to clone into $($env:SANITY_WORKDIR)"
        }
        git clone $env:SANITY_REPO_URL $env:SANITY_WORKDIR
    }
    $Root = (Resolve-Path $env:SANITY_WORKDIR).Path
}

Set-Location $Root
if (Test-Path (Join-Path $Root ".git")) {
    git pull --ff-only
    if ($LASTEXITCODE -ne 0) {
        Write-Host "git pull did not fast-forward. Continuing with this checkout."
    }
}

$Python = Get-Command python -ErrorAction SilentlyContinue
if (-not $Python) {
    $Python = Get-Command py -ErrorAction SilentlyContinue
}
if (-not $Python) {
    Write-Error "Python 3 is not on PATH."
}

& $Python.Source -m venv .venv
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
& $VenvPython -m pip install -r (Join-Path $Root "agents\verifier\requirements.txt")

New-Item -ItemType Directory -Force -Path $ProfileDir | Out-Null
Copy-Item -Path (Join-Path $Root "hermes\$Role\*") -Destination $ProfileDir -Recurse -Force
Copy-Item -Path (Join-Path $Root "agents\$Role\AGENT.md") -Destination (Join-Path $ProfileDir "SOUL.md") -Force

$TokenName = "$($Role.ToUpper())_TELEGRAM_TOKEN"

Write-Host ""
Write-Host "Profile copied to: $ProfileDir"
Write-Host "Role prompt: agents\$Role\AGENT.md -> $ProfileDir\SOUL.md"
Write-Host "Skill: skills\verify-math (see skills.external_dirs and skills.auto_load in config.yaml)"
Write-Host "Python: $Root\.venv"
Write-Host ""
Write-Host "Still manual:"
Write-Host ""
Write-Host "1. In @BotFather, send /setprivacy, choose this bot, and choose Disable."
Write-Host "2. Remove the bot from the group and add it again. Privacy does not update until you do."
Write-Host "3. If the bot still shows 'has no access to messages', privacy is still on. Repeat steps 1 and 2."
Write-Host "4. Set the team's numeric Telegram user IDs. Replace the placeholders in"
Write-Host "   $ProfileDir\config.yaml and in the profile .env:"
Write-Host "   TELEGRAM_ALLOWED_USERS=id1,id2,id3"
Write-Host "   A starter list of names is hermes\$Role\env.example. Do not commit the filled-in file."
Write-Host "5. Set the BotFather token as an environment variable. Do not write it into the repo."
Write-Host "   Hermes reads TELEGRAM_BOT_TOKEN. On this machine you can keep it as $TokenName"
Write-Host "   and copy that value into TELEGRAM_BOT_TOKEN for this profile only."
Write-Host "6. Replace `${SANITY_REPO}, `${MODEL_PROVIDER}, `${MODEL_NAME}, and the user-id"
Write-Host "   placeholders in $ProfileDir\config.yaml."
Write-Host "7. Start the Hermes gateway for this profile."
Write-Host ""
