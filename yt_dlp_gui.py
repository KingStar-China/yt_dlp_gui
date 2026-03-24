import sys
import os
import re
import time
import traceback
import subprocess
import ctypes
import tempfile
import shutil
import urllib.request
import json

# 导入Qt相关模块
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QLineEdit, QPushButton,
                             QProgressBar, QComboBox, QFileDialog, QMessageBox, QMenu,
                             QPlainTextEdit)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QAction, QIcon


def get_runtime_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def get_managed_ytdlp_path():
    return os.path.join(get_runtime_dir(), 'yt-dlp.exe')


def resolve_ytdlp_command():
    managed_path = get_managed_ytdlp_path()
    if os.path.exists(managed_path):
        return managed_path

    path_cmd = shutil.which('yt-dlp.exe') or shutil.which('yt-dlp')
    if path_cmd:
        return path_cmd

    return managed_path

class SniffThread(QThread):
    progress_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool, str, list, str)

    def __init__(self, url, parent=None):
        super().__init__(parent)
        self.url = url
        self.is_running = True
        self.available_formats = []
        self.subtitle_entries = []
        self.process = None

    def build_sniff_cmd(self, cookie_mode):
        cmd = [self.parent().get_ytdlp_command(), '-F']
        if cookie_mode == 'firefox':
            cmd.extend(['--cookies-from-browser', 'firefox'])
        elif cookie_mode == 'file':
            cmd.extend(['--cookies', self.parent().cookie_file])
        cmd.extend([self.url, '--newline'])
        return cmd

    def build_subtitle_cmd(self, cookie_mode):
        cmd = [self.parent().get_ytdlp_command(), '--list-subs']
        if cookie_mode == 'firefox':
            cmd.extend(['--cookies-from-browser', 'firefox'])
        elif cookie_mode == 'file':
            cmd.extend(['--cookies', self.parent().cookie_file])
        cmd.append(self.url)
        return cmd

    def collect_subtitles(self, cookie_mode):
        process = subprocess.Popen(
            self.build_subtitle_cmd(cookie_mode),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        output, _ = process.communicate()
        if process.returncode != 0:
            return

        for raw_line in output.splitlines():
            line = raw_line.strip()
            subtitle_match = re.match(r'^([a-zA-Z0-9_-]+)\s+(.*)$', line)
            if not subtitle_match:
                continue
            subtitle_lang = subtitle_match.group(1)
            subtitle_note = subtitle_match.group(2).strip()
            if subtitle_lang.lower() in {'language', 'code', 'name'}:
                continue
            if not re.search(r'(vtt|ttml|srv\d|json3|srt|ass)', subtitle_note, re.IGNORECASE):
                continue

            subtitle_kind = '自动字幕' if 'auto' in subtitle_note.lower() else '字幕'
            subtitle_id = f'subtitle:{subtitle_lang}:{"auto" if "auto" in subtitle_note.lower() else "manual"}'
            subtitle_info = f'{subtitle_kind}/{subtitle_lang}'
            if subtitle_note:
                subtitle_info += f'/{subtitle_note}'
            if not any(existing_id == subtitle_id for existing_id, _ in self.subtitle_entries):
                self.subtitle_entries.append((subtitle_id, subtitle_info))

    def run_sniff(self, cookie_mode):
        self.available_formats = []
        self.subtitle_entries = []
        process = subprocess.Popen(
            self.build_sniff_cmd(cookie_mode),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        self.process = process

        while self.is_running:
            line = process.stdout.readline()
            if not line:
                break
            self.progress_signal.emit(line.strip())

            if 'avc1' in line.lower() or 'h264' in line.lower() or 'm4a' in line.lower() or 'aac' in line.lower():
                parts = line.split()
                if len(parts) >= 3:
                    format_id = parts[0]
                    resolution = None
                    fps = None
                    filesize = 0

                    for part in parts:
                        if 'x' in part and part[0].isdigit():
                            resolution = part.split('x')[1] + 'p'
                            break

                    for part in parts:
                        if 'fps' in part.lower():
                            try:
                                fps_str = part.lower()
                                fps_val = ''.join([c for c in fps_str if c.isdigit() or c == '.'])
                                if fps_val:
                                    fps = int(float(fps_val))
                                    print(f"成功解析帧率: {fps}fps")
                            except Exception as e:
                                print(f"解析帧率错误: {e}")
                            break

                    if fps is None:
                        try:
                            fps_match = re.search(r'(\d+(\.\d+)?)\s*fps', line.lower())
                            if fps_match:
                                fps = int(float(fps_match.group(1)))
                                print(f"通过正则表达式解析帧率: {fps}fps")
                        except Exception as e:
                            print(f"正则解析帧率错误: {e}")

                    if filesize == 0:
                        try:
                            size_match = re.search(r'(\d+(\.\d+)?)\s*(G|M|K)iB', line, re.IGNORECASE)
                            if size_match:
                                size = float(size_match.group(1))
                                unit = size_match.group(3).upper()
                                if unit == 'G':
                                    filesize = size * 1024
                                elif unit == 'M':
                                    filesize = size
                                elif unit == 'K':
                                    filesize = size / 1024
                        except Exception as e:
                            print(f"正则解析文件大小错误: {e}")

                    for i, part in enumerate(parts):
                        if ('filesize' in part.lower() or 'filesize_approx' in part.lower() or
                            'mib' in part.lower() or 'gib' in part.lower() or 'kib' in part.lower() or
                            (i < len(parts) - 1 and ('mib' in parts[i+1].lower() or 'gib' in parts[i+1].lower() or 'kib' in parts[i+1].lower()))):
                            try:
                                size_str = ''
                                if 'mib' in part.lower() or 'gib' in part.lower() or 'kib' in part.lower():
                                    size_str = part
                                elif '~' in part and (i < len(parts) - 1) and ('mib' in parts[i+1].lower() or 'gib' in parts[i+1].lower() or 'kib' in parts[i+1].lower()):
                                    size_str = part.replace('~', '') + ' ' + parts[i+1]
                                elif part.replace('.', '', 1).isdigit() and (i < len(parts) - 1) and ('mib' in parts[i+1].lower() or 'gib' in parts[i+1].lower() or 'kib' in parts[i+1].lower()):
                                    size_str = part + ' ' + parts[i+1]
                                elif '~' in part:
                                    size_str = part.split('~')[-1]
                                elif '=' in part:
                                    size_str = part.split('=')[-1]
                                elif part.lower().startswith('filesize'):
                                    size_str = part.lower().replace('filesize', '').replace('_approx', '').strip()

                                if size_str:
                                    clean_str = size_str.replace('~', '').strip()
                                    num_part = ''
                                    for c in clean_str:
                                        if c.isdigit() or c == '.':
                                            num_part += c
                                        elif num_part:
                                            break

                                    if num_part:
                                        size = float(num_part)
                                        if 'gib' in size_str.lower() or 'g' in size_str.lower():
                                            filesize = size * 1024
                                        elif 'mib' in size_str.lower() or 'm' in size_str.lower():
                                            filesize = size
                                        elif 'kib' in size_str.lower() or 'k' in size_str.lower():
                                            filesize = size / 1024
                            except Exception as e:
                                print(f"解析文件大小错误: {e}")
                            break

                    is_audio = 'm4a' in line.lower() or 'aac' in line.lower()
                    if (resolution and resolution.endswith('p')) or is_audio:
                        format_info = '音频/AAC' if is_audio else f'{resolution}/H.264'
                        if fps:
                            format_info += f'/{fps}fps'
                        if filesize > 0:
                            if filesize >= 1024:
                                format_info += f'/{round(filesize/1024, 2)}GB'
                            else:
                                format_info += f'/{round(filesize, 1)}MB'
                        else:
                            try:
                                size_match = re.search(r'~?\s*(\d+(\.\d+)?)\s*(G|M|K)i?B', line, re.IGNORECASE)
                                if size_match:
                                    size = float(size_match.group(1))
                                    unit = size_match.group(3).upper()
                                    if unit == 'G':
                                        format_info += f'/{round(size, 2)}GB'
                                    elif unit == 'M':
                                        format_info += f'/{round(size, 1)}MB'
                                    elif unit == 'K':
                                        format_info += f'/{round(size, 1)}KB'
                            except Exception as e:
                                print(f"最后尝试解析文件大小错误: {e}")

                        if not any(existing_id == format_id for existing_id, _ in self.available_formats):
                            self.available_formats.append((format_id, format_info))


        if not self.is_running:
            if process.poll() is None:
                process.terminate()
            return False, '嗅探已取消', []

        process.wait()
        if process.returncode == 0:
            self.collect_subtitles(cookie_mode)
            if not self.available_formats and not self.subtitle_entries:
                return False, '未找到可用的H.264视频格式或字幕', []

            resolutions = {
                '2160p': 2160,
                '1440p': 1440,
                '1080p': 1080,
                '720p': 720,
                '480p': 480,
                '360p': 360,
                '240p': 240,
                '144p': 144,
            }
            self.available_formats.sort(key=lambda x: resolutions.get(x[1].split('/')[0], 0), reverse=True)
            combined_formats = self.available_formats + self.subtitle_entries
            return True, '嗅探完成', combined_formats

        return False, '嗅探失败', []

    def run(self):
        try:
            is_youtube = 'youtube.com' in self.url.lower() or 'youtu.be' in self.url.lower()
            cookie_modes = ['none']
            if is_youtube:
                if self.parent().manual_cookie_enabled and os.path.exists(self.parent().cookie_file):
                    cookie_modes = ['file']
                else:
                    cookie_modes = ['none', 'firefox']

            last_message = '嗅探失败'
            for cookie_mode in cookie_modes:
                if is_youtube and cookie_mode == 'firefox':
                    self.progress_signal.emit('普通嗅探失败，正在尝试调用 Firefox Cookies...')
                success, message, formats = self.run_sniff(cookie_mode)
                if success:
                    self.finished_signal.emit(True, message, formats, cookie_mode)
                    return
                last_message = message
                if not self.is_running:
                    self.finished_signal.emit(False, '嗅探已取消', [], cookie_mode)
                    return

            if is_youtube and not self.parent().manual_cookie_enabled:
                self.finished_signal.emit(False, 'Firefox Cookies 调用失败，请手动输入 Cookies 后重试。', [], 'show_cookie_input')
                return

            self.finished_signal.emit(False, last_message, [], 'none')
        except Exception as e:
            self.finished_signal.emit(False, f'嗅探时发生错误：{str(e)}', [], 'none')

    def stop(self):
        self.is_running = False
        if self.process and self.process.poll() is None:
            self.process.terminate()

class DownloadThread(QThread):
    progress_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, url, format_id, parent=None):
        super().__init__(parent)
        self.url = url
        self.format_id = format_id
        self.is_running = True
        self.process = None

    def run(self):
        try:
            # 下载并合并视频和音频，选择最高码率的m4a(aac)音频
            # 检查是否为YouTube链接，只有YouTube链接才需要Cookies
            is_youtube = 'youtube.com' in self.url.lower() or 'youtu.be' in self.url.lower()
            
            is_subtitle = self.format_id.startswith('subtitle:')
            if is_subtitle:
                _, subtitle_lang, subtitle_mode = self.format_id.split(':', 2)
                cmd = [self.parent().get_ytdlp_command()]
                if subtitle_mode == 'auto':
                    cmd.append('--write-auto-sub')
                else:
                    cmd.append('--write-sub')
                cmd.extend(['--sub-lang', subtitle_lang, '--convert-subs', 'srt', '--skip-download'])
            else:
                cmd = [self.parent().get_ytdlp_command(), '-f', f'{self.format_id}+bestaudio[ext=m4a]']
            if is_youtube and self.parent().cookie_mode == 'firefox':
                cmd.extend(['--cookies-from-browser', 'firefox'])
            elif is_youtube and self.parent().cookie_mode == 'file' and os.path.exists(self.parent().cookie_file):
                cmd.extend(['--cookies', self.parent().cookie_file])
            if is_subtitle:
                cmd.extend([self.url, '--newline'])
            else:
                cmd.extend(['--merge-output-format', 'mp4', self.url, '--newline'])
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            self.process = process
            downloaded_file = None
            
            while self.is_running:
                line = process.stdout.readline()
                if not line:
                    break
                line = line.strip()
                self.progress_signal.emit(line)
                if '[download] Destination:' in line:
                    downloaded_file = line.split(':', 1)[1].strip()
                elif '[Merger] Merging formats into ' in line:
                    downloaded_file = line.split('into ', 1)[1].strip().strip('"')
            
            process.wait()
            if process.returncode == 0:
                if downloaded_file and os.path.exists(downloaded_file):
                    # 获取文件大小
                    file_size = os.path.getsize(downloaded_file)
                    file_size_str = ''
                    if file_size >= 1024 * 1024 * 1024:  # GB
                        file_size_str = f'.{round(file_size / (1024 * 1024 * 1024), 2)}G'
                    elif file_size >= 1024 * 1024:  # MB
                        file_size_str = f'.{round(file_size / (1024 * 1024), 1)}M'
                    elif file_size >= 1024:  # KB
                        file_size_str = f'.{round(file_size / 1024, 1)}K'
                    
                    # 获取文件扩展名和基本名称
                    base_name, ext = os.path.splitext(downloaded_file)
                    
                    # 根据文件类型添加不同的后缀
                    if ext.lower() in ['.m4a', '.aac']:
                        new_name = f'{base_name}{file_size_str}{ext}'
                    elif ext.lower() == '.mp4':
                        format_info = next((label for label, fmt_id in self.parent().format_id_map.items() if fmt_id == self.format_id), '')
                        resolution = format_info.split('/')[0] if format_info else ''
                        if resolution:
                            new_name = f'{base_name}.{resolution}{ext}'
                        else:
                            new_name = downloaded_file
                    else:
                        new_name = downloaded_file
                    
                    try:
                        if new_name != downloaded_file:
                            os.rename(downloaded_file, new_name)
                    except Exception as e:
                        print(f'重命名文件失败：{str(e)}')
                
                self.finished_signal.emit(True, '下载完成' if not is_subtitle else '字幕下载完成')
            else:
                self.finished_signal.emit(False, '下载失败')
        except Exception as e:
            self.finished_signal.emit(False, f'发生错误：{str(e)}')

    def stop(self):
        self.is_running = False
        if self.process and self.process.poll() is None:
            self.process.terminate()

class UpdateYtDlpThread(QThread):
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, target_path, current_command, parent=None):
        super().__init__(parent)
        self.target_path = target_path
        self.current_command = current_command

    def get_local_version(self):
        try:
            if not self.current_command or not os.path.exists(self.current_command):
                return None
            result = subprocess.run(
                [self.current_command, '--version'],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
                timeout=15,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return None

    def get_latest_version(self):
        request = urllib.request.Request(
            'https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest',
            headers={'User-Agent': 'yt_dlp_gui'}
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode('utf-8'))
        return str(data.get('tag_name', '')).strip() or None

    def run(self):
        temp_path = self.target_path + '.download'
        download_url = 'https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe'
        try:
            local_version = self.get_local_version()
            latest_version = self.get_latest_version()
            if local_version and latest_version and local_version == latest_version:
                self.finished_signal.emit(True, f'无需更新，已经是最新版啦：{local_version}')
                return

            os.makedirs(os.path.dirname(self.target_path), exist_ok=True)
            urllib.request.urlretrieve(download_url, temp_path)
            if os.path.exists(self.target_path):
                os.remove(self.target_path)
            os.replace(temp_path, self.target_path)

            final_version = latest_version or self.get_local_version() or '未知版本'
            self.finished_signal.emit(True, f'yt-dlp 更新完成：{final_version}')
        except Exception as e:
            try:
                if os.path.exists(temp_path):
                    os.remove(temp_path)
            except Exception:
                pass
            self.finished_signal.emit(False, f'yt-dlp 更新失败：{str(e)}')


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('yt_dlp_gui v1.0.4 @少昊金天氏')
        self.setMinimumSize(533, 400)
        # 在Windows 10/11上设置深色标题栏
        # 导入必要的模块
        import ctypes
        from ctypes import windll, c_int, byref, sizeof
        
        # 设置窗口属性
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        
        # 使用Windows 11的深色标题栏API
        try:
            # DWMWA_USE_IMMERSIVE_DARK_MODE = 20 用于Windows 10/11
            # DWMWA_CAPTION_COLOR = 35 用于Windows 11 22H2及以上版本
            DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            DWMWA_CAPTION_COLOR = 35
            
            # 获取窗口句柄
            hwnd = int(self.winId())
            
            # 设置深色模式
            dark_mode_value = c_int(2)  # 2表示启用深色模式
            windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 
                DWMWA_USE_IMMERSIVE_DARK_MODE, 
                byref(dark_mode_value), 
                sizeof(dark_mode_value)
            )
            
            # 尝试设置标题栏颜色（仅适用于Windows 11 22H2及以上版本）
            try:
                # 设置标题栏颜色为深灰色 (#2b2b2b)
                # 颜色格式为ABGR，其中A为透明度
                caption_color = c_int(0xFF2B2B2B)  # 完全不透明的深灰色
                windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, 
                    DWMWA_CAPTION_COLOR, 
                    byref(caption_color), 
                    sizeof(caption_color)
                )
            except Exception:
                # 如果设置标题栏颜色失败，可能是因为系统版本不支持
                pass
        except Exception as e:
            # 如果设置深色标题栏失败，记录错误但不影响程序运行
            pass
        self.download_thread = None
        self.sniff_thread = None
        self.update_thread = None
        self.cookie_file = os.path.join(tempfile.gettempdir(), 'YouTube-Cookies.txt')
        self.ytdlp_path = resolve_ytdlp_command()
        self.cookie_mode = 'none'
        self.manual_cookie_enabled = False
        self.format_id_map = {}
        self.is_sniffing = False

        # 创建主窗口部件和布局
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setSpacing(10)  # 设置垂直布局的间距

        # URL输入区域
        url_layout = QHBoxLayout()
        url_layout.setContentsMargins(10, 10, 10, 0)
        url_label = QLabel('视频URL：')
        url_label.setFixedWidth(60)  # 固定标签宽度
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText('目录链接批量下载失败别怕，再次点击会继续下载未完成视频。')
        self.url_input.textChanged.connect(self.check_youtube_url)
        self.url_input.textChanged.connect(self.handle_url_change)
        self.url_input.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.url_input.customContextMenuRequested.connect(self.show_context_menu)
        url_layout.addWidget(url_label)
        url_layout.addWidget(self.url_input)
        layout.addLayout(url_layout)

        # 格式选择区域
        format_layout = QHBoxLayout()
        format_layout.setContentsMargins(10, 10, 10, 0)  # 与URL输入区域保持一致的边距
        format_label = QLabel('嗅探结果：')
        format_label.setFixedWidth(60)  # 与URL标签保持相同宽度
        self.format_combo = QComboBox()
        format_layout.addWidget(format_label)
        format_layout.addWidget(self.format_combo)
        layout.addLayout(format_layout)

        # Cookies设置区域
        self.cookie_container = QWidget()
        cookie_layout = QVBoxLayout(self.cookie_container)
        cookie_layout.setContentsMargins(10, 10, 10, 0)  # 与其他区域保持一致的边距
        
        cookie_input_layout = QHBoxLayout()
        cookie_input_layout.setContentsMargins(0, 0, 0, 0)
        cookie_label = QLabel('Cookies：')
        cookie_label.setFixedWidth(60)  # 与其他标签保持相同宽度
        self.cookie_input = QPlainTextEdit()
        self.cookie_input.setPlaceholderText('在此粘贴 Netscape 格式 Cookies，多行原样保存。')
        self.cookie_input.setFixedHeight(96)
        self.cookie_input.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.cookie_input.customContextMenuRequested.connect(self.show_context_menu)
        save_cookie_button = QPushButton('更新')
        save_cookie_button.clicked.connect(self.save_cookie)
        cookie_input_layout.addWidget(cookie_label)
        cookie_input_layout.addWidget(self.cookie_input)
        cookie_input_layout.addWidget(save_cookie_button)
        
        cookie_layout.addLayout(cookie_input_layout)
        layout.addWidget(self.cookie_container)
        self.cookie_container.hide()

        # 操作按钮
        action_layout = QHBoxLayout()
        action_layout.setContentsMargins(0, 0, 0, 0)
        self.download_button = QPushButton('开始嗅探')
        self.download_button.clicked.connect(self.start_download)
        self.update_ytdlp_button = QPushButton('更新 yt-dlp')
        self.update_ytdlp_button.clicked.connect(self.update_ytdlp)
        action_layout.addWidget(self.download_button)
        action_layout.addWidget(self.update_ytdlp_button)
        layout.addLayout(action_layout)

        # 进度显示区域
        self.progress_text = QLabel('准备就绪！（若下载失败请安装火狐浏览器并登录相应网站，比如油管以获得cookie。）')
        layout.addWidget(self.progress_text)

        # 创建菜单栏
        menubar = self.menuBar()
        help_menu = menubar.addMenu('帮助')
        about_action = QAction('关于', self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def get_ytdlp_command(self):
        self.ytdlp_path = resolve_ytdlp_command()
        return self.ytdlp_path

    def update_ytdlp(self):
        target_path = get_managed_ytdlp_path()
        self.update_ytdlp_button.setEnabled(False)
        self.progress_text.setText('正在更新 yt-dlp...')
        self.update_thread = UpdateYtDlpThread(target_path, self.get_ytdlp_command(), self)
        self.update_thread.finished_signal.connect(self.update_ytdlp_finished)
        self.update_thread.start()

    def update_ytdlp_finished(self, success, message):
        self.update_ytdlp_button.setEnabled(True)
        self.get_ytdlp_command()
        self.progress_text.setText(message)
        if success:
            QMessageBox.information(self, '成功', message)
        else:
            QMessageBox.warning(self, '错误', message)

    def start_download(self):
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, '警告', '请输入视频URL')
            return
            
        # 如果没有可用的视频格式，需要先进行嗅探
        if not self.format_combo.count():
            # 清空格式选择框
            self.format_combo.clear()
            self.format_id_map.clear()
            
            # 更改按钮文本和状态
            self.download_button.setText('正在嗅探中')
            self.download_button.setEnabled(False)  # 设置按钮为不可用状态
            self.is_sniffing = True
            self.progress_text.setText('正在嗅探可下载的视频、音频和字幕...')
            
            # 启动嗅探线程
            if self.sniff_thread and self.sniff_thread.isRunning():
                self.sniff_thread.stop()
                self.sniff_thread.wait(1000)
                
            self.sniff_thread = SniffThread(url, self)
            self.sniff_thread.progress_signal.connect(self.update_progress)
            self.sniff_thread.finished_signal.connect(self.sniff_finished)
            self.sniff_thread.start()
            return
        
        # 如果已有视频格式，执行下载操作
        if not self.format_combo.currentText():
            QMessageBox.warning(self, '警告', '请选择视频格式')
            return
            
        format_id = self.format_id_map[self.format_combo.currentText()]
        
        # 停止当前下载线程（如果有）
        if self.download_thread and self.download_thread.isRunning():
            self.download_thread.stop()
            self.download_thread.wait(1000)

        self.download_button.setText('正在下载中')
        self.download_button.setEnabled(False)  # 设置按钮为不可用状态
        self.download_thread = DownloadThread(url, format_id, self)
        self.progress_text.setText('正在下载中...')
        self.download_thread.progress_signal.connect(self.update_progress)
        self.download_thread.finished_signal.connect(self.download_finished)
        self.download_thread.start()

    def update_progress(self, text):
        self.progress_text.setText(text)

    def sniff_finished(self, success, message, formats, cookie_mode):
        self.is_sniffing = False
        self.download_button.setText('开始嗅探')
        self.download_button.setEnabled(True)  # 恢复按钮为可用状态
        
        if success and formats:
            self.cookie_mode = cookie_mode
            self.cookie_container.hide()
            self.progress_text.setText('视频/字幕嗅探完成')
            # 清空并更新格式选择框
            self.format_combo.clear()
            self.format_id_map.clear()
            
            for format_id, resolution in formats:
                self.format_combo.addItem(resolution)
                self.format_id_map[resolution] = format_id
            
            # 自动选择第一个格式
            if self.format_combo.count() > 0:
                self.format_combo.setCurrentIndex(0)
                # 更改按钮文本为开始下载
                self.download_button.setText('开始下载')
        else:
            # 嗅探失败时重置状态
            self.download_button.setText('开始嗅探')
            self.progress_text.setText('准备就绪')
            self.format_combo.clear()
            self.format_id_map.clear()
            
            if cookie_mode == 'show_cookie_input':
                self.cookie_container.show()
                self.cookie_mode = 'none'
                QMessageBox.warning(self, '错误', message)
            elif not success:
                QMessageBox.warning(self, '错误', message)
            elif not formats:
                QMessageBox.warning(self, '警告', '未找到可下载的视频格式或字幕')

    def download_finished(self, success, message):
        self.download_button.setEnabled(True)  # 恢复按钮为可用状态
        self.is_sniffing = False
        self.progress_text.setText(message)
        self.download_button.setText('开始下载')  # 无论成功失败都显示"开始下载"
        if success:
            QMessageBox.information(self, '成功', '下载完成！')
        else:
            QMessageBox.warning(self, '错误', message)

    def show_about(self):
        # 创建自定义的关于对话框
        about_box = QMessageBox(self)
        about_box.setWindowTitle('关于')
        about_box.setText('基于yt-dlp的视频下载工具\n为了兼容我只允许它下载H.264\n主要下载YouTube和bilibili视频\n\n作者：@少昊金天氏\n\n版本：v1.0.3\n\n更新时间：2026-03-24')
        about_box.setIcon(QMessageBox.Icon.Information)
        
        # 设置对话框的深色标题栏
        try:
            # 导入必要的模块
            from ctypes import windll, c_int, byref, sizeof
            
            # 设置窗口属性
            about_box.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            
            # 等待对话框创建完成并获取窗口句柄
            about_box.show()
            hwnd = int(about_box.winId())
            
            # 设置深色模式
            DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            dark_mode_value = c_int(2)  # 2表示启用深色模式
            windll.dwmapi.DwmSetWindowAttribute(
                hwnd, 
                DWMWA_USE_IMMERSIVE_DARK_MODE, 
                byref(dark_mode_value), 
                sizeof(dark_mode_value)
            )
            
            # 尝试设置标题栏颜色（仅适用于Windows 11 22H2及以上版本）
            try:
                # 设置标题栏颜色为深灰色 (#2b2b2b)
                DWMWA_CAPTION_COLOR = 35
                caption_color = c_int(0xFF2B2B2B)  # 完全不透明的深灰色
                windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, 
                    DWMWA_CAPTION_COLOR, 
                    byref(caption_color), 
                    sizeof(caption_color)
                )
            except Exception:
                # 如果设置标题栏颜色失败，可能是因为系统版本不支持
                pass
                
            # 隐藏对话框，稍后再显示（这样可以确保样式应用）
            about_box.hide()
        except Exception as e:
            # 如果设置深色标题栏失败，记录错误但不影响程序运行
            print(f"设置关于对话框深色标题栏失败: {e}")
        
        # 设置对话框的样式表，使其与主窗口风格一致
        about_box.setStyleSheet("""
            QMessageBox {
                background-color: #2D2D2D;
                color: white;
            }
            QLabel {
                color: white;
            }
            QPushButton {
                background-color: #3D3D3D;
                color: white;
                border: 1px solid #555555;
                padding: 5px;
                border-radius: 2px;
            }
            QPushButton:hover {
                background-color: #4D4D4D;
            }
            QPushButton:pressed {
                background-color: #5D5D5D;
            }
        """)
        
        # 显示对话框并等待用户关闭
        about_box.exec()

    def check_youtube_url(self):
        self.cookie_container.hide()

    def save_cookie(self):
        try:
            cookie_content = self.cookie_input.toPlainText().strip()
            if not cookie_content:
                QMessageBox.warning(self, '警告', '请输入Cookies内容')
                return
            
            with open(self.cookie_file, 'w', encoding='utf-8') as f:
                f.write(cookie_content)
            
            self.manual_cookie_enabled = True
            self.cookie_mode = 'file'
            self.cookie_container.hide()
            QMessageBox.information(self, '成功', 'Cookies已更新，请重新点击开始嗅探。')
            self.cookie_input.clear()
        except Exception as e:
            QMessageBox.warning(self, '警告', f'Cookies更新失败：{str(e)}')

    def show_context_menu(self, pos):
        sender = self.sender()

        if sender is self.url_input:
            sender.clear()
            sender.paste()
            if sender.text().strip():
                self.start_download()
            return

        if hasattr(sender, 'toPlainText'):
            if sender.toPlainText():
                sender.selectAll()
        elif sender.text():
            sender.selectAll()

        menu = QMenu(self)
        cut_action = menu.addAction('剪切')
        copy_action = menu.addAction('复制')
        paste_action = menu.addAction('粘贴')
        delete_action = menu.addAction('删除')

        cut_action.triggered.connect(sender.cut)
        copy_action.triggered.connect(sender.copy)
        paste_action.triggered.connect(sender.paste)
        delete_action.triggered.connect(sender.clear)

        menu.exec(sender.mapToGlobal(pos))

    def closeEvent(self, event):
        if (self.download_thread and self.download_thread.isRunning()) or (self.sniff_thread and self.sniff_thread.isRunning()):
            operation = '嗅探' if self.is_sniffing else '下载'
            reply = QMessageBox.question(self, '确认', f'{operation}正在进行中，确定要退出吗？',
                                       QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                # 设置最大等待时间（毫秒）
                max_wait_time = 3000
                
                # 终止下载线程
                if self.download_thread and self.download_thread.isRunning():
                    self.download_thread.stop()
                    if not self.download_thread.wait(max_wait_time):
                        self.download_thread.terminate()
                        self.download_thread.wait(1000)  # 再给一秒确保完全终止
                
                # 终止嗅探线程
                if self.sniff_thread and self.sniff_thread.isRunning():
                    self.sniff_thread.stop()
                    if not self.sniff_thread.wait(max_wait_time):
                        self.sniff_thread.terminate()
                        self.sniff_thread.wait(1000)  # 再给一秒确保完全终止
                
                # 终止所有相关的子进程
                try:
                    current_pid = os.getpid()
                    subprocess.run(['taskkill', '/F', '/T', '/PID', str(current_pid)], 
                                 creationflags=subprocess.CREATE_NO_WINDOW,
                                 capture_output=True)
                except Exception as e:
                    print(f'终止进程时出错：{str(e)}')
                
                event.accept()
            else:
                event.ignore()

    def handle_url_change(self):
        # 清空格式选择框和相关状态
        self.format_combo.clear()
        self.format_id_map.clear()
        self.cookie_mode = 'none'
        self.cookie_container.hide()
        self.download_button.setText('开始嗅探')
        self.progress_text.setText('准备就绪')
        
        # 如果正在进行嗅探或下载，停止它们
        if self.sniff_thread and self.sniff_thread.isRunning():
            self.sniff_thread.stop()
            self.sniff_thread.wait(1000)
        
        if self.download_thread and self.download_thread.isRunning():
            self.download_thread.stop()
            self.download_thread.wait(1000)
        
        self.download_button.setEnabled(True)
        self.is_sniffing = False

def main():
    try:
        # 首先初始化QApplication，确保在使用任何Qt组件前完成初始化
        app = QApplication(sys.argv)
        # 修改应用程序图标
        try:
            if getattr(sys, 'frozen', False):
                # PyInstaller打包后的路径
                base_path = sys._MEIPASS
            else:
                # 开发环境路径
                base_path = os.path.dirname(os.path.abspath(__file__))
            icon_candidates = [
                os.path.join(base_path, 'logo', 'app.ico'),
                os.path.join(base_path, 'logo', 'Q糖logo.png'),
                os.path.join(base_path, '003.ico'),
            ]
            for icon_path in icon_candidates:
                if os.path.exists(icon_path):
                    app.setWindowIcon(QIcon(icon_path))
                    break
        except Exception as e:
            print(f"设置应用程序图标失败: {e}")
        
        # 设置深色主题样式
        from PyQt6.QtGui import QPalette
        app.setStyle('Fusion')
        dark_palette = QPalette()
        dark_palette.setColor(QPalette.ColorRole.Window, Qt.GlobalColor.darkGray)
        dark_palette.setColor(QPalette.ColorRole.WindowText, Qt.GlobalColor.white)
        dark_palette.setColor(QPalette.ColorRole.Base, Qt.GlobalColor.darkGray)
        dark_palette.setColor(QPalette.ColorRole.AlternateBase, Qt.GlobalColor.darkGray)
        dark_palette.setColor(QPalette.ColorRole.ToolTipBase, Qt.GlobalColor.darkGray)
        dark_palette.setColor(QPalette.ColorRole.ToolTipText, Qt.GlobalColor.white)
        dark_palette.setColor(QPalette.ColorRole.Text, Qt.GlobalColor.white)
        dark_palette.setColor(QPalette.ColorRole.Button, Qt.GlobalColor.darkGray)
        dark_palette.setColor(QPalette.ColorRole.ButtonText, Qt.GlobalColor.white)
        dark_palette.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
        dark_palette.setColor(QPalette.ColorRole.Link, Qt.GlobalColor.cyan)
        dark_palette.setColor(QPalette.ColorRole.Highlight, Qt.GlobalColor.cyan)
        dark_palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.black)
        app.setPalette(dark_palette)
        
        # 设置深色主题样式表
        app.setStyleSheet("""
            QMainWindow, QWidget { 
                background-color: #2b2b2b; 
                color: #ffffff; 
            }
            /* 标题栏样式 */
            QMainWindow::title {
                background-color: #2b2b2b;
                color: #ffffff;
            }
            QMainWindow::titleBar {
                background-color: #2b2b2b;
                color: #ffffff;
            }
            QTitleBar {
                background-color: #2b2b2b;
                color: #ffffff;
            }
            QMenuBar { 
                background-color: #2b2b2b; 
                color: #ffffff; 
                border-bottom: 1px solid #555555;
            }
            QMenuBar::item {
                background-color: transparent;
                padding: 4px 8px;
            }
            QMenuBar::item:selected {
                background-color: #3b3b3b;
                border-radius: 3px;
            }
            QMenuBar::item:pressed {
                background-color: #4b4b4b;
            }
            QMenu {
                background-color: #2b2b2b;
                border: 1px solid #555555;
            }
            QMenu::item {
                padding: 5px 30px 5px 20px;
                border: 1px solid transparent;
            }
            QMenu::item:selected {
                background-color: #3b3b3b;
            }
            QLineEdit, QComboBox { 
                background-color: #3b3b3b; 
                border: 1px solid #555555; 
                padding: 5px; 
                border-radius: 3px; 
            }
            QPushButton { 
                background-color: #3b3b3b; 
                border: 1px solid #555555; 
                padding: 5px 10px; 
                border-radius: 3px; 
            }
            QPushButton:hover { 
                background-color: #4b4b4b; 
                border-color: #666666; 
            }
            QPushButton:pressed { 
                background-color: #2b2b2b; 
                border-color: #777777; 
            }
            QPushButton:disabled { 
                background-color: #2b2b2b; 
                color: #666666; 
                border-color: #444444; 
            }
            QComboBox:drop-down { 
                border: none; 
                width: 20px; 
            }
            QComboBox:down-arrow { 
                image: none; 
            }
            QComboBox QAbstractItemView { 
                background-color: #3b3b3b; 
                selection-background-color: #4b4b4b; 
                border: 1px solid #555555; 
            }
            QMenuBar { 
                background-color: #2b2b2b; 
                color: #ffffff; 
                border-bottom: 1px solid #555555; 
            }
            QMenuBar::item:selected, QMenu::item:selected { 
                background-color: #3b3b3b; 
            }
            QMenu { 
                background-color: #2b2b2b; 
                border: 1px solid #555555; 
                padding: 5px 0px; 
            }
            QMenu::item { 
                padding: 5px 20px; 
            }
        """)
        
        # 创建DLL目录
        dll_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dll')
        os.makedirs(dll_dir, exist_ok=True)
    
        
        
        # 设置环境变量，确保FFmpeg能找到DLL文件
        os.environ['PATH'] = os.path.dirname(os.path.abspath(__file__)) + os.pathsep + \
                            dll_dir + os.pathsep + os.environ.get('PATH', '')

        window = MainWindow()
        window.show()
        sys.exit(app.exec())
    except Exception as e:
        error_msg = f'程序启动失败：{str(e)}'
        QMessageBox.critical(None, '错误', error_msg)
        return

if __name__ == '__main__':
    main()
