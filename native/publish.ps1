param(
    [ValidateSet('win-x64', 'win-arm64')]
    [string]$Runtime = 'win-x64',
    [switch]$FrameworkDependent
)

function Get-YtDlpVersion {
    param([string]$Path)

    try {
        $versionText = (& $Path --version 2>$null | Select-Object -First 1).Trim()
        $parsedVersion = [version]'0.0'
        if ([version]::TryParse($versionText, [ref]$parsedVersion)) {
            return $parsedVersion
        }
    }
    catch {
        # An unreadable candidate is treated as older and replaced below.
    }

    return [version]'0.0'
}

$nativeRoot = Split-Path -Parent $PSCommandPath
$repositoryRoot = Split-Path -Parent $nativeRoot
$projectPath = Join-Path $nativeRoot 'src\YtDlpGui.App\YtDlpGui.App.csproj'
$outputPath = Join-Path $nativeRoot "artifacts\$Runtime"
$selfContained = -not $FrameworkDependent

New-Item -ItemType Directory -Force -Path $outputPath | Out-Null

dotnet publish $projectPath `
    --configuration Release `
    --runtime $Runtime `
    --self-contained $selfContained `
    -p:PublishSingleFile=true `
    -p:DebugType=None `
    -p:DebugSymbols=false `
    --output $outputPath

if ($LASTEXITCODE -ne 0) {
    throw "dotnet publish 失败，退出码：$LASTEXITCODE"
}

foreach ($toolName in @('yt-dlp.exe', 'ffmpeg.exe')) {
    $sourcePath = Join-Path $repositoryRoot $toolName
    $destinationPath = Join-Path $outputPath $toolName
    if (Test-Path -LiteralPath $sourcePath) {
        if ($toolName -eq 'yt-dlp.exe' -and (Test-Path -LiteralPath $destinationPath)) {
            $sourceVersion = Get-YtDlpVersion $sourcePath
            $destinationVersion = Get-YtDlpVersion $destinationPath
            if ($destinationVersion -gt $sourceVersion) {
                Write-Host "保留已更新的 yt-dlp：$destinationVersion"
                continue
            }
        }

        Copy-Item -LiteralPath $sourcePath -Destination $destinationPath -Force
    }
}

$licenseOutputPath = Join-Path $outputPath 'licenses'
New-Item -ItemType Directory -Force -Path $licenseOutputPath | Out-Null

Copy-Item -LiteralPath (Join-Path $repositoryRoot 'LICENSE') `
    -Destination (Join-Path $outputPath 'LICENSE') -Force
Copy-Item -LiteralPath (Join-Path $repositoryRoot 'THIRD-PARTY-NOTICES.md') `
    -Destination (Join-Path $outputPath 'THIRD-PARTY-NOTICES.md') -Force
Copy-Item -LiteralPath (Join-Path $nativeRoot 'README.md') `
    -Destination (Join-Path $outputPath 'README.md') -Force
Copy-Item -LiteralPath (Join-Path $nativeRoot 'FFMPEG_SOURCE_INFO.md') `
    -Destination (Join-Path $outputPath 'FFMPEG_SOURCE_INFO.md') -Force
Copy-Item -Path (Join-Path $nativeRoot 'licenses\*') `
    -Destination $licenseOutputPath -Force

Write-Host "发布完成：$outputPath"
