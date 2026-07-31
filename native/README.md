# YtDlpGui.Native

`YtDlpGui.Native` 是现有 PyQt6 版本的 Windows 原生旁路重构。当前为 `2.0.0-beta.1`，不会覆盖根目录中的 Python 稳定版。

## 工程结构

```text
src/
  YtDlpGui.App/             WPF 界面与交互状态
  YtDlpGui.Core/            URL、格式模型、解析器、命令构造、状态机
  YtDlpGui.Infrastructure/  进程、HTTP、设置、更新与 B站直连回退
tests/
  YtDlpGui.Core.Tests/      Core 行为回归测试
```

## 当前能力

- 匿名优先的 yt-dlp 嗅探，浏览器登录态必须由用户明确勾选。
- 视频、AAC 音频、人工字幕和自动字幕下载。
- YouTube 列表批量下载，提供 H.264 优先和最佳兼容模式。
- B站常规嗅探失败后的网页/API 直连回退与 FFmpeg 合并。
- 完整进程树取消，不在后台遗留 yt-dlp 或 FFmpeg。
- `%LOCALAPPDATA%\YtDlpGui\settings.json` 用户级输出目录设置。
- 手动 Cookie 仅写入临时文件，按当前网站隔离，退出时删除。
- 从 GitHub 官方 latest 地址下载并校验 yt-dlp 更新。

## 开发

要求 Windows 与 .NET 10 SDK。调试时工具定位器会从应用目录逐级查找仓库根目录中的 `yt-dlp.exe` 和 `ffmpeg.exe`。

```powershell
dotnet restore .\native\YtDlpGui.Native.slnx
dotnet build .\native\YtDlpGui.Native.slnx --configuration Debug
dotnet test .\native\YtDlpGui.Native.slnx --configuration Debug
dotnet run --project .\native\src\YtDlpGui.App\YtDlpGui.App.csproj
```

## 发布

默认生成自包含 `win-x64` 目录，并复制仓库根目录现有的 `yt-dlp.exe` 与 `ffmpeg.exe`：

```powershell
.\native\publish.ps1
```

输出目录为 `native\artifacts\win-x64`。若目标机器已经安装 .NET 10 Desktop Runtime，可使用框架依赖发布减小 GUI 文件体积：

```powershell
.\native\publish.ps1 -FrameworkDependent
```

FFmpeg 仍然是发布包体积的主要部分；原生重构的主要收益是 Windows 集成、启动体验、状态可靠性和可维护性，而不是下载速度。
