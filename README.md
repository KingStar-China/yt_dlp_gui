# YT-DLP-GUI

Windows 视频下载工具，底层调用 `yt-dlp.exe` 与 `ffmpeg.exe`，支持 YouTube、Bilibili 以及 yt-dlp 支持的网站。

仓库目前保留两个版本：

- `yt_dlp_gui.py`：现有 PyQt6 稳定版。
- `native/`：C# / .NET 10 / WPF Windows 原生 Beta，采用 App、Core、Infrastructure、Tests 分层结构。

原生版已支持 URL 嗅探、清晰度与编码选择、音频、字幕、YouTube 列表、B站 412 网页直连回退、下载取消、输出目录记忆、临时 Cookie 和 yt-dlp 更新。浏览器登录态默认关闭，只有用户明确勾选后才会尝试读取 Firefox、Edge、Chrome Cookie。

开发、测试和发布方式见 [native/README.md](native/README.md)。
