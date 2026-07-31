# FFmpeg 二进制与对应源码

YtDlpGui.Native 2.0.0 正式包中的 `ffmpeg.exe` 是独立程序，应用通过子进程调用它。

## 二进制识别

- 文件版本输出：`N-121066-g189d0b83b2-20250915`
- SHA-256：`72470BCF8A66669FF5E66E585417B0565E8FF77F66818D8C5AFFFD9321D8A1CD`
- FFmpeg 提交：`189d0b83b20bd701bf7f8e171d3bb8e9c6077dd7`
- 提交日期：`2025-09-15 12:30:00 UTC`
- 构建配置包含：`--enable-gpl --enable-version3`
- 适用许可证：GNU General Public License version 3 or later

可用以下命令核对当前文件：

```powershell
.\ffmpeg.exe -version
Get-FileHash .\ffmpeg.exe -Algorithm SHA256
```

## 对应源码

GitHub Release 同时提供 `YtDlpGui.Native-2.0.0-ffmpeg-source.zip`，其中包含：

- `FFmpeg-189d0b83b20bd701bf7f8e171d3bb8e9c6077dd7.tar.gz`
  - 原始地址：<https://github.com/FFmpeg/FFmpeg/archive/189d0b83b20bd701bf7f8e171d3bb8e9c6077dd7.tar.gz>
  - 源码树：<https://github.com/FFmpeg/FFmpeg/tree/189d0b83b20bd701bf7f8e171d3bb8e9c6077dd7>
- `BtbN-FFmpeg-Builds-fd4fbc0391a26afb30e9e36be94f0dc89ffe23bb.tar.gz`
  - 原始地址：<https://github.com/BtbN/FFmpeg-Builds/archive/fd4fbc0391a26afb30e9e36be94f0dc89ffe23bb.tar.gz>
  - 构建脚本树：<https://github.com/BtbN/FFmpeg-Builds/tree/fd4fbc0391a26afb30e9e36be94f0dc89ffe23bb>

二进制内嵌的 `/ffbuild/prefix` 路径与配置特征指向 BtbN/FFmpeg-Builds。由于该项目的旧日构建资产已按保留策略过期，无法再从原 Release 反查原始 ZIP；这里选择 FFmpeg 提交时间之后、当日下一次构建脚本变更之前的 `fd4fbc0391a26afb30e9e36be94f0dc89ffe23bb` 作为对应构建流程快照，并明确记录这一识别依据。

FFmpeg 源码归档包含上游许可证文件；BtbN/FFmpeg-Builds 构建脚本的 MIT License 也保存在正式包的 `licenses/BTBN_FFMPEG_BUILDS_MIT.txt`。
