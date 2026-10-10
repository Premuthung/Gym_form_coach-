# Publish the page to GitHub Pages (the gh-pages branch of this repository), so it has a permanent
# address:  https://<user>.github.io/<repository>/
#
# GitHub only serves files. It cannot run the server. So the published page is a copy of frontend/
# plus two files this script writes:
#   catalog.json   the machine guides, so they open even when the server is off
#   server.json    the current address of the server (the trycloudflare link from "run.bat public")
# and GymFormCoach.apk if it has been built.
#
# Called by publish-pages.bat. With -Wait it first waits for "run.bat public" to print its link.
param([string]$Server = "", [switch]$Wait)
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$log = Join-Path $root "data\tools\tunnel.log"
$local = "http://127.0.0.1:8000"

function TunnelLink {
    if (-not (Test-Path $log)) { return "" }
    $found = Select-String -Path $log -Pattern 'https://[a-z0-9-]+\.trycloudflare\.com' | Select-Object -Last 1
    if ($found) { return $found.Matches[0].Value }
    return ""
}

if (-not $Server) {
    $Server = TunnelLink
    for ($i = 0; $Wait -and -not $Server -and $i -lt 60; $i++) { Start-Sleep -Seconds 3; $Server = TunnelLink }
}
if (-not $Server) { Write-Host " No server link yet. Start 'run.bat public' first, or pass the link: publish-pages.bat https://..." ; exit 1 }

# The guides come from the running server, in the exact form the page expects.
$catalog = $null
for ($i = 0; $i -lt 40 -and -not $catalog; $i++) {
    try { $catalog = (Invoke-WebRequest "$local/api/catalog" -UseBasicParsing -TimeoutSec 10).Content } catch { Start-Sleep -Seconds 3 }
}
if (-not $catalog) { Write-Host " The server on this computer is not answering at $local. Start run.bat first."; exit 1 }

$site = Join-Path $env:TEMP "gym-form-coach-pages"
if (Test-Path $site) { Remove-Item $site -Recurse -Force }
Copy-Item (Join-Path $root "frontend") $site -Recurse
$utf8 = New-Object System.Text.UTF8Encoding($false)
[IO.File]::WriteAllText("$site\catalog.json", $catalog, $utf8)
[IO.File]::WriteAllText("$site\server.json", (@{ server = $Server; updated = (Get-Date).ToUniversalTime().ToString("s") + "Z" } | ConvertTo-Json), $utf8)
[IO.File]::WriteAllText("$site\.nojekyll", "", $utf8)
$apk = Join-Path $root "GymFormCoach.apk"
if (Test-Path $apk) { Copy-Item $apk $site }

# The site is one commit that replaces the last one: it is built output, so it needs no history.
$origin = (git -C $root remote get-url origin)
$name = (git -C $root config user.name); $email = (git -C $root config user.email)
Push-Location $site
try {
    git init -q -b gh-pages
    git add -A
    git -c "user.name=$name" -c "user.email=$email" commit -q -m "Publish the page (server: $Server)"
    git push -q --force $origin gh-pages
    if ($LASTEXITCODE -ne 0) { throw "git push failed" }
} finally { Pop-Location }

if ($origin -match 'github\.com[:/]([^/]+)/(.+?)(\.git)?$') {
    Write-Host " Published. The page:  https://$($Matches[1].ToLower()).github.io/$($Matches[2])/"
    Write-Host " It uses the server at $Server  (GitHub needs about a minute to show a change)"
}
