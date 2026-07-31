param(
    [ValidateSet('win-x64', 'win-arm64')]
    [string]$Runtime = 'win-x64',
    [switch]$FrameworkDependent
)

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
    if (Test-Path -LiteralPath $sourcePath) {
        Copy-Item -LiteralPath $sourcePath -Destination (Join-Path $outputPath $toolName) -Force
    }
}

Write-Host "发布完成：$outputPath"
