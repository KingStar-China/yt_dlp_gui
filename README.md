# YT-DLP-GUI

这是一个基于yt-dlp的图形界面下载工具，可以方便地下载YouTube、bilibili视频。

## 功能特点

- 支持输入视频URL进行下载
- 提供多种视频质量选项（1080p、720p、480p）
- 自动使用YouTube-Cookies.txt进行授权
- 实时显示下载进度

## 安装步骤

1. 确保已安装Python 3.8或更高版本
2. 安装依赖包：
   ```bash
   pip install -r requirements.txt
   ```

## 使用方法

### 直接运行Python脚本

```bash
python yt_dlp_gui.py
```

### 打包成独立exe文件

```bash
pyinstaller yt_dlp_gui.spec
```

打包后的可执行文件将在`dist/yt_dlp_gui`目录中。

## 注意事项

- 确保yt-dlp.exe和ffmpeg.exe在同一目录下
- 如需下载需要登录的视频，请确保YouTube-Cookies.txt文件存在且有效
- 下载高质量视频时会自动合并视频和音频流
