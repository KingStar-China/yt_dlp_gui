# 第三方软件声明

YtDlpGui.Native 本身按仓库根目录 `LICENSE` 中的 MIT License 发布。正式包还包含以下独立可执行程序；它们各自适用其上游许可证，不因本项目的 MIT License 而改变。

## yt-dlp

- 版本：`2026.07.04`
- 文件：`yt-dlp.exe`
- SHA-256：`52FE3C26DCF71FBDC85B528589020BB0B8E383155CFA81B64DD447BBE35E24B8`
- 许可证：The Unlicense
- 上游项目：<https://github.com/yt-dlp/yt-dlp>
- 对应发布与源码：<https://github.com/yt-dlp/yt-dlp/releases/tag/2026.07.04>

许可证全文随正式包保存为 `licenses/YT_DLP_UNLICENSE.txt`。

## FFmpeg

- 文件：`ffmpeg.exe`
- 内嵌版本：`N-121066-g189d0b83b2-20250915`
- 对应 FFmpeg 提交：`189d0b83b20bd701bf7f8e171d3bb8e9c6077dd7`
- SHA-256：`72470BCF8A66669FF5E66E585417B0565E8FF77F66818D8C5AFFFD9321D8A1CD`
- 构建配置包含：`--enable-gpl --enable-version3`
- 适用许可证：GNU General Public License version 3 or later
- 上游项目：<https://ffmpeg.org/>
- 对应源码：<https://github.com/FFmpeg/FFmpeg/tree/189d0b83b20bd701bf7f8e171d3bb8e9c6077dd7>

该二进制的构建路径和配置特征与 BtbN/FFmpeg-Builds 构建相符。用于复现构建流程的脚本快照、对应 FFmpeg 源码归档及详细识别依据，随 GitHub Release 的 `YtDlpGui.Native-2.0.0-ffmpeg-source.zip` 一并提供。详见正式包中的 `FFMPEG_SOURCE_INFO.md`。

BtbN/FFmpeg-Builds 构建脚本按 MIT License 发布，许可证全文随正式包保存为 `licenses/BTBN_FFMPEG_BUILDS_MIT.txt`。

YtDlpGui.Native 通过子进程调用上述独立程序，不把它们链接进应用程序集。
