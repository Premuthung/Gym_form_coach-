# Build GymFormCoach.apk without Gradle or Android Studio: only the Android SDK tools and a JDK.
# Called by build-apk.bat in the project folder. Steps: resources -> Java -> dex -> align -> sign.
param([string]$Server = "")
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$out = Join-Path (Split-Path -Parent $here) "GymFormCoach.apk"
$build = Join-Path $here "build"
$keystore = Join-Path $here "gym-form-coach.keystore"
$MIN_SDK = 26      # Android 8.0
$TARGET_SDK = 34

function Run($exe) {
    & $exe @args
    if ($LASTEXITCODE -ne 0) { throw "$(Split-Path -Leaf $exe) failed (exit code $LASTEXITCODE)" }
}

# ---- find the tools -------------------------------------------------------------------------
$sdk = @($env:ANDROID_HOME, $env:ANDROID_SDK_ROOT, "$env:LOCALAPPDATA\Android\Sdk") |
    Where-Object { $_ -and (Test-Path "$_\build-tools") } | Select-Object -First 1
if (-not $sdk) {
    throw "The Android SDK was not found. Install Android Studio, or the command-line tools with 'platforms;android-34' and 'build-tools;34.0.0', into $env:LOCALAPPDATA\Android\Sdk"
}
$tools = Get-ChildItem "$sdk\build-tools" -Directory | Sort-Object { [version]($_.Name -replace '[^\d.]', '') } | Select-Object -Last 1 -ExpandProperty FullName
$androidJar = Get-ChildItem "$sdk\platforms\android-*\android.jar" | Sort-Object { [int]($_.Directory.Name -replace '\D', '') } | Select-Object -Last 1 -ExpandProperty FullName
if (-not $androidJar) { throw "No Android platform is installed in $sdk\platforms" }

# The dex tool needs Java 11 or newer; JAVA_HOME on this computer may point at Java 8.
$jdk = @($env:JAVA_HOME) + @(Get-ChildItem "C:\Program Files\Microsoft\jdk-*", "C:\Program Files\Eclipse Adoptium\jdk-*", "C:\Program Files\Java\jdk-*", "C:\Program Files\Android\Android Studio\jbr" -Directory -ErrorAction SilentlyContinue | ForEach-Object FullName) |
    Where-Object { $_ -and (Test-Path "$_\bin\javac.exe") -and ((Get-Item "$_\bin\javac.exe").VersionInfo.FileMajorPart -ge 11) } | Select-Object -First 1
if (-not $jdk) { throw "Java 11 or newer (a JDK, with javac) was not found." }

# ---- build ----------------------------------------------------------------------------------
if (Test-Path $build) { Remove-Item $build -Recurse -Force }
New-Item -ItemType Directory -Force "$build\assets", "$build\gen", "$build\classes" | Out-Null
[IO.File]::WriteAllText("$build\assets\server.txt", $Server.Trim())

# Newer builds must have a higher number, or the phone refuses to install over the old one.
$versionCode = [int](((Get-Date).ToUniversalTime() - [datetime]"2026-01-01").TotalMinutes)

Write-Host " Packing resources..."
Run "$tools\aapt2.exe" compile --dir "$here\res" -o "$build\res.zip"
Run "$tools\aapt2.exe" link -o "$build\unaligned.apk" -I $androidJar --manifest "$here\AndroidManifest.xml" `
    -A "$build\assets" --java "$build\gen" --min-sdk-version $MIN_SDK --target-sdk-version $TARGET_SDK `
    --version-code $versionCode --version-name "0.1" "$build\res.zip"

Write-Host " Compiling..."
$sources = Get-ChildItem "$here\src", "$build\gen" -Recurse -Filter *.java | ForEach-Object FullName
Run "$jdk\bin\javac.exe" -nowarn -source 11 -target 11 -encoding UTF-8 -classpath $androidJar -d "$build\classes" @sources
$classes = Get-ChildItem "$build\classes" -Recurse -Filter *.class | ForEach-Object FullName
Run "$jdk\bin\java.exe" -cp "$tools\lib\d8.jar" com.android.tools.r8.D8 --min-api $MIN_SDK --lib $androidJar --output $build @classes

Push-Location $build
try { Run "$tools\aapt.exe" add unaligned.apk classes.dex | Out-Null } finally { Pop-Location }
Run "$tools\zipalign.exe" -f -p 4 "$build\unaligned.apk" "$build\aligned.apk"

Write-Host " Signing..."
if (-not (Test-Path $keystore)) {
    # Keep this file. A phone only installs an update that is signed with the same key as before.
    Run "$jdk\bin\keytool.exe" -genkeypair -keystore $keystore -alias app -keyalg RSA -keysize 2048 -validity 10000 `
        -storepass gymformcoach -keypass gymformcoach -dname "CN=Gym Form Coach prototype"
}
Run "$jdk\bin\java.exe" -jar "$tools\lib\apksigner.jar" sign --ks $keystore --ks-pass pass:gymformcoach --out $out "$build\aligned.apk"
Run "$jdk\bin\java.exe" -jar "$tools\lib\apksigner.jar" verify $out
Remove-Item "$out.idsig" -ErrorAction SilentlyContinue

Write-Host ""
Write-Host (" Built {0}  ({1:N0} KB)" -f $out, ((Get-Item $out).Length / 1KB))
if ($Server) { Write-Host " It opens $Server" } else { Write-Host " No server address inside: the app asks for the link when it is first opened." }
