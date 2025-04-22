# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['E:\\01、下载\\.YouTube\\yt-dlp\\yt_dlp_gui.py'],
    pathex=[],
    binaries=[],
    datas=[('E:\\01、下载\\.YouTube\\yt-dlp\\ffmpeg.exe', '.'), ('E:\\01、下载\\.YouTube\\yt-dlp\\yt-dlp.exe', '.'), ('E:\\01、下载\\.YouTube\\yt-dlp\\dll\\avcodec-61.dll', '.'), ('E:\\01、下载\\.YouTube\\yt-dlp\\dll\\avdevice-61.dll', '.'), ('E:\\01、下载\\.YouTube\\yt-dlp\\dll\\avfilter-10.dll', '.'), ('E:\\01、下载\\.YouTube\\yt-dlp\\dll\\avformat-61.dll', '.'), ('E:\\01、下载\\.YouTube\\yt-dlp\\dll\\avutil-59.dll', '.'), ('E:\\01、下载\\.YouTube\\yt-dlp\\dll\\postproc-58.dll', '.'), ('E:\\01、下载\\.YouTube\\yt-dlp\\dll\\swresample-5.dll', '.'), ('E:\\01、下载\\.YouTube\\yt-dlp\\dll\\swscale-8.dll', '.')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='yt_dlp_gui',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['E:\\01、下载\\.YouTube\\yt-dlp\\dist\\icons\\favicon.ico'],
)
