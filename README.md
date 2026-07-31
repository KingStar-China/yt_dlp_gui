# YT-DLP-GUI

Windows 视频下载工具，底层调用 `yt-dlp.exe` 与 `ffmpeg.exe`，支持 YouTube、Bilibili 以及 yt-dlp 支持的网站。

仓库目前保留两个版本：

- `native/`：C# / .NET 10 / WPF Windows 原生正式版，采用 App、Core、Infrastructure、Tests 分层结构。
- `yt_dlp_gui.py`：保留的 PyQt6 旧版。

原生版已支持 URL 嗅探、清晰度与编码选择、音频、字幕、YouTube 列表、B站 412 网页直连回退、下载取消、输出目录记忆、深浅色主题、临时 Cookie 和 yt-dlp 更新。浏览器登录态默认关闭，只有用户明确勾选后才会尝试读取 Firefox、Edge、Chrome Cookie。

Windows 10/11 x64 用户可从 [v2.0.0 Release](https://github.com/KingStar-China/yt_dlp_gui/releases/tag/v2.0.0) 下载自包含正式包。开发、测试和发布方式见 [native/README.md](native/README.md)。

本项目按 [MIT License](LICENSE) 发布；随包第三方程序的许可证与源码信息见 [THIRD-PARTY-NOTICES.md](THIRD-PARTY-NOTICES.md)。
