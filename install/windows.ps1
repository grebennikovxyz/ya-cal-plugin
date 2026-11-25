# Generated release installer. Runs as the current user on Windows PowerShell 5.1+.
& {
    $ErrorActionPreference = 'Stop'
    $ProgressPreference = 'SilentlyContinue'
    if (-not [Environment]::Is64BitOperatingSystem) { throw 'Ya-Ca requires 64-bit Windows.' }
    $root = Join-Path $env:LOCALAPPDATA 'Ya-Ca'
    $versions = [IO.Directory]::CreateDirectory((Join-Path $root 'versions')).FullName
    $release = Join-Path $versions 'v@VERSION@'
    $lock = [IO.File]::Open((Join-Path $root 'install.lock'), 'OpenOrCreate', 'ReadWrite', 'None')
    try {
        if (-not [IO.Directory]::Exists($release)) {
            $temp = [IO.Directory]::CreateDirectory((Join-Path $versions ([guid]::NewGuid().ToString('N')))).FullName
            try {
                $zip = Join-Path $temp 'package.zip'
                Invoke-WebRequest -UseBasicParsing -Uri '@RELEASE_URL@/ya-ca-latest-windows-x64.zip' -OutFile $zip
                $hash = [Security.Cryptography.SHA256]::Create()
                $inputFile = [IO.File]::OpenRead($zip)
                try {
                    $actual = [BitConverter]::ToString($hash.ComputeHash($inputFile)).Replace('-', '')
                } finally { $inputFile.Dispose(); $hash.Dispose() }
                if ($actual -ne '@DIGEST@') {
                    throw 'Ya-Ca download failed SHA-256 verification.'
                }
                Add-Type -AssemblyName System.IO.Compression.FileSystem
                $content = Join-Path $temp 'content'
                [IO.Compression.ZipFile]::ExtractToDirectory($zip, $content)
                [IO.Directory]::Move($content, $release)
            } finally {
                if ([IO.Path]::GetDirectoryName($temp) -eq $versions) {
                    Remove-Item -LiteralPath $temp -Recurse -Force
                }
            }
        }
        $python = Join-Path $release 'plugins\ya-ca\runtime\python.exe'
        $codexArgs = @()
        if (-not (Get-Command codex.exe,codex.cmd -ErrorAction SilentlyContinue) -and (Get-Command Get-AppxPackage -ErrorAction SilentlyContinue)) {
            $app = Get-AppxPackage -Name OpenAI.Codex -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($app) {
                $bundledCli = Join-Path $app.InstallLocation 'app\resources\codex.exe'
                if (Test-Path -LiteralPath $bundledCli) { $codexArgs = @('--codex', $bundledCli) }
            }
        }
        & $python -I -B (Join-Path $release 'activate.py') @codexArgs
        if ($LASTEXITCODE -ne 0) { throw 'Ya-Ca activation failed. See the message above.' }
    } finally { $lock.Dispose() }
}
