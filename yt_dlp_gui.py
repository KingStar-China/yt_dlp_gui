import sys
import os
import re
import time
import traceback
import subprocess
import ctypes
import tempfile

# 导入Qt相关模块
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QLineEdit, QPushButton,
                             QProgressBar, QComboBox, QFileDialog, QMessageBox, QMenu)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
from PyQt6.QtGui import QAction, QIcon

class SniffThread(QThread):
    progress_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool, str, list)

    def __init__(self, url, parent=None):
        super().__init__(parent)
        self.url = url
        self.is_running = True
        self.available_formats = []

    def run(self):
        try:
            # 检查是否为YouTube链接，YouTube链接需要Cookies
            is_youtube = 'youtube.com' in self.url.lower() or 'youtu.be' in self.url.lower()
            
            if is_youtube and not os.path.exists(self.parent().cookie_file):
                self.finished_signal.emit(False, '未找到Cookies文件，请先更新Cookies！', [])
                return
                
            # 根据URL类型决定是否使用Cookies
            if is_youtube:
                cmd = ['yt-dlp.exe', '-F', '--cookies', self.parent().cookie_file, self.url, '--newline']
            else:
                cmd = ['yt-dlp.exe', '-F', self.url, '--newline']
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            
            while self.is_running:
                line = process.stdout.readline()
                if not line:
                    break
                self.progress_signal.emit(line.strip())
                
                # 解析H.264视频格式和音频格式
                if 'avc1' in line.lower() or 'h264' in line.lower() or 'm4a' in line.lower() or 'aac' in line.lower():
                    parts = line.split()
                    if len(parts) >= 3:
                        format_id = parts[0]
                        resolution = None
                        fps = None
                        filesize = 0
                        
                        # 解析分辨率
                        for part in parts:
                            if 'x' in part and part[0].isdigit():
                                resolution = part.split('x')[1] + 'p'
                                break
                        
                        # 解析帧率
                        for part in parts:
                            if 'fps' in part.lower():
                                try:
                                    # 提取fps值，处理多种格式
                                    fps_str = part.lower()
                                    # 移除非数字字符
                                    fps_val = ''.join([c for c in fps_str if c.isdigit() or c == '.'])
                                    if fps_val:
                                        fps = int(float(fps_val))
                                        print(f"成功解析帧率: {fps}fps")
                                except Exception as e:
                                    print(f"解析帧率错误: {e}")
                                break
                        
                        # 如果没有找到fps信息，尝试在整行中查找
                        if fps is None:
                            try:
                                # 使用正则表达式查找fps值
                                fps_match = re.search(r'(\d+(\.\d+)?)\s*fps', line.lower())
                                if fps_match:
                                    fps = int(float(fps_match.group(1)))
                                    print(f"通过正则表达式解析帧率: {fps}fps")
                            except Exception as e:
                                print(f"正则解析帧率错误: {e}")
                                
                        # 如果没有找到文件大小信息，尝试在整行中查找
                        if filesize == 0:
                            try:
                                # 查找文件大小信息
                                size_match = re.search(r'(\d+(\.\d+)?)\s*(G|M|K)iB', line, re.IGNORECASE)
                                if size_match:
                                    size = float(size_match.group(1))
                                    unit = size_match.group(3).upper()
                                    if unit == 'G':
                                        filesize = size * 1024  # 转换为MB
                                        print(f"通过正则表达式解析到GiB大小: {size}GiB = {filesize}MB")
                                    elif unit == 'M':
                                        filesize = size
                                        print(f"通过正则表达式解析到MiB大小: {size}MiB")
                                    elif unit == 'K':
                                        filesize = size / 1024
                                        print(f"通过正则表达式解析到KiB大小: {size}KiB = {filesize}MB")
                            except Exception as e:
                                print(f"正则解析文件大小错误: {e}")
                        
                        # 解析视频流大小
                        for i, part in enumerate(parts):
                            # 检查当前部分或下一部分是否包含文件大小信息
                            if ('filesize' in part.lower() or 'filesize_approx' in part.lower() or 
                                'mib' in part.lower() or 'gib' in part.lower() or 'kib' in part.lower() or
                                (i < len(parts) - 1 and ('mib' in parts[i+1].lower() or 'gib' in parts[i+1].lower() or 'kib' in parts[i+1].lower()))):
                                try:
                                    # 提取文件大小信息，处理多种格式
                                    size_str = ''
                                    
                                    # 处理形如 "76.46MiB" 的格式
                                    if 'mib' in part.lower() or 'gib' in part.lower() or 'kib' in part.lower():
                                        size_str = part
                                    # 处理形如 "~123.87MiB" 的格式
                                    elif '~' in part and (i < len(parts) - 1) and ('mib' in parts[i+1].lower() or 'gib' in parts[i+1].lower() or 'kib' in parts[i+1].lower()):
                                        size_str = part.replace('~', '') + ' ' + parts[i+1]
                                    # 处理形如 "123.87 MiB" 的格式
                                    elif part.replace('.', '', 1).isdigit() and (i < len(parts) - 1) and ('mib' in parts[i+1].lower() or 'gib' in parts[i+1].lower() or 'kib' in parts[i+1].lower()):
                                        size_str = part + ' ' + parts[i+1]
                                    # 处理其他格式
                                    elif '~' in part:
                                        size_str = part.split('~')[-1]
                                    elif '=' in part:
                                        size_str = part.split('=')[-1]
                                    elif part.lower().startswith('filesize'):
                                        size_str = part.lower().replace('filesize', '').replace('_approx', '').strip()
                                    
                                    if size_str:
                                        # 提取数字部分，处理各种格式
                                        # 先移除波浪号和空格
                                        clean_str = size_str.replace('~', '').strip()
                                        # 提取数字部分
                                        num_part = ''
                                        for c in clean_str:
                                            if c.isdigit() or c == '.':
                                                num_part += c
                                            # 遇到第一个非数字非点的字符就停止
                                            elif num_part:
                                                break
                                        
                                        if num_part:
                                            try:
                                                size = float(num_part)
                                                # 根据单位转换大小
                                                if 'gib' in size_str.lower() or 'g' in size_str.lower():
                                                    filesize = size * 1024  # 转换为MB
                                                    print(f"解析到GiB大小: {size}GiB = {filesize}MB")
                                                elif 'mib' in size_str.lower() or 'm' in size_str.lower():
                                                    filesize = size
                                                    print(f"解析到MiB大小: {size}MiB")
                                                elif 'kib' in size_str.lower() or 'k' in size_str.lower():
                                                    filesize = size / 1024
                                                    print(f"解析到KiB大小: {size}KiB = {filesize}MB")
                                            except Exception as e:
                                                print(f"转换文件大小错误: {e}, 原始字符串: {size_str}, 提取数字: {num_part}")
                                except Exception as e:
                                    print(f"解析文件大小错误: {e}")
                                break
                        
                        # 判断是否为音频格式
                        is_audio = 'm4a' in line.lower() or 'aac' in line.lower()
                        
                        if (resolution and resolution.endswith('p')) or is_audio:
                            if is_audio:
                                format_info = "音频/AAC"
                            else:
                                format_info = f"{resolution}/H.264"
                            if fps:
                                format_info += f"/{fps}fps"
                            if filesize > 0:
                                if filesize >= 1024:
                                    format_info += f"/{round(filesize/1024, 2)}GB"
                                else:
                                    format_info += f"/{round(filesize, 1)}MB"
                            else:
                                # 如果没有解析到文件大小，尝试在整行中查找
                                try:
                                    size_match = re.search(r'~?\s*(\d+(\.\d+)?)\s*(G|M|K)i?B', line, re.IGNORECASE)
                                    if size_match:
                                        size = float(size_match.group(1))
                                        unit = size_match.group(3).upper()
                                        if unit == 'G':
                                            filesize = size * 1024  # 转换为MB
                                            format_info += f"/{round(size, 2)}GB"
                                            print(f"最后尝试解析到GiB大小: {size}GiB")
                                        elif unit == 'M':
                                            filesize = size
                                            format_info += f"/{round(size, 1)}MB"
                                            print(f"最后尝试解析到MiB大小: {size}MiB")
                                        elif unit == 'K':
                                            filesize = size / 1024
                                            format_info += f"/{round(size, 1)}KB"
                                            print(f"最后尝试解析到KiB大小: {size}KiB")
                                except Exception as e:
                                    print(f"最后尝试解析文件大小错误: {e}")
                            # 打印调试信息
                            print(f"添加格式: ID={format_id}, 信息={format_info}, 分辨率={resolution}, 帧率={fps}, 大小={filesize}MB")
                            # 确保格式信息不重复添加
                            format_exists = False
                            for existing_id, existing_info in self.available_formats:
                                if existing_id == format_id:
                                    format_exists = True
                                    break
                            if not format_exists:
                                self.available_formats.append((format_id, format_info))
            
            if not self.is_running:
                process.terminate()
                self.finished_signal.emit(False, '嗅探已取消', [])
                return
                
            process.wait()
            if process.returncode == 0:
                if not self.available_formats:
                    self.finished_signal.emit(False, '未找到可用的H.264视频格式', [])
                    return
                    
                # 按分辨率从大到小排序
                resolutions = {
                    '2160p': 2160,
                    '1440p': 1440,
                    '1080p': 1080,
                    '720p': 720,
                    '480p': 480,
                    '360p': 360,
                    '240p': 240,
                    '144p': 144
                }
                
                self.available_formats.sort(key=lambda x: resolutions.get(x[1].split('/')[0], 0), reverse=True)
                self.finished_signal.emit(True, '嗅探完成', self.available_formats)
            else:
                self.finished_signal.emit(False, '嗅探失败', [])
        except Exception as e:
            self.finished_signal.emit(False, f'嗅探时发生错误：{str(e)}', [])

    def stop(self):
        self.is_running = False

class DownloadThread(QThread):
    progress_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, url, format_id, parent=None):
        super().__init__(parent)
        self.url = url
        self.format_id = format_id
        self.is_running = True

    def run(self):
        try:
            # 下载并合并视频和音频，选择最高码率的m4a(aac)音频
            # 检查是否为YouTube链接，只有YouTube链接才需要Cookies
            is_youtube = 'youtube.com' in self.url.lower() or 'youtu.be' in self.url.lower()
            
            if is_youtube:
                cmd = ['yt-dlp.exe', '-f', f'{self.format_id}+bestaudio[ext=m4a]', '--cookies', self.parent().cookie_file, '--merge-output-format', 'mp4', self.url, '--newline']
            else:
                cmd = ['yt-dlp.exe', '-f', f'{self.format_id}+bestaudio[ext=m4a]', '--merge-output-format', 'mp4', self.url, '--newline']
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
            
            while self.is_running:
                line = process.stdout.readline()
                if not line:
                    break
                self.progress_signal.emit(line.strip())
            
            process.wait()
            if process.returncode == 0:
                # 获取下载的文件名
                downloaded_file = None
                for line in process.stdout.readlines():
                    if '[download] Destination:' in line:
                        downloaded_file = line.split(':', 1)[1].strip()
                        break
                
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
                        # 音频文件：添加文件大小
                        new_name = f'{base_name}{file_size_str}{ext}'
                    elif ext.lower() == '.mp4':
                        # 视频文件：添加分辨率
                        format_info = next((info for id, info in self.parent().format_id_map.items() if id == self.format_id), '')
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
                
                self.finished_signal.emit(True, '下载完成')
            else:
                self.finished_signal.emit(False, '下载失败')
        except Exception as e:
            self.finished_signal.emit(False, f'发生错误：{str(e)}')

    def stop(self):
        self.is_running = False

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('yt_dlp_gui')
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
        self.cookie_file = os.path.join(tempfile.gettempdir(), 'YouTube-Cookies.txt')
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
        self.cookie_input = QLineEdit()
        self.cookie_input.setPlaceholderText('在此输入Netscape格式Cookies，报错后马上更新！')
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

        # 下载按钮
        self.download_button = QPushButton('开始嗅探')
        self.download_button.clicked.connect(self.start_download)
        layout.addWidget(self.download_button)

        # 进度显示区域
        self.progress_text = QLabel('准备就绪')
        layout.addWidget(self.progress_text)

        # 创建菜单栏
        menubar = self.menuBar()
        help_menu = menubar.addMenu('帮助')
        about_action = QAction('关于', self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

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
            self.progress_text.setText('正在嗅探能够下载的H.264视频...')
            
            # 启动嗅探线程
            if self.sniff_thread and self.sniff_thread.isRunning():
                self.sniff_thread.stop()
                self.sniff_thread.wait()
                
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
            self.download_thread.wait()

        self.download_button.setText('正在下载中')
        self.download_button.setEnabled(False)  # 设置按钮为不可用状态
        self.download_thread = DownloadThread(url, format_id, self)
        self.progress_text.setText('正在下载中...')
        self.download_thread.progress_signal.connect(self.update_progress)
        self.download_thread.finished_signal.connect(self.download_finished)
        self.download_thread.start()

    def update_progress(self, text):
        self.progress_text.setText(text)

    def sniff_finished(self, success, message, formats):
        self.is_sniffing = False
        self.download_button.setText('开始嗅探')
        self.download_button.setEnabled(True)  # 恢复按钮为可用状态
        
        if success and formats:
            self.progress_text.setText('H.264视频嗅探完成')
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
            
            if not success:
                QMessageBox.warning(self, '错误', message)
            elif not formats:
                QMessageBox.warning(self, '警告', '未找到H.264视频格式')

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
        about_box.setText('基于yt-dlp的视频下载工具\n为了兼容我只允许它下载H.264\n主要下载YouTube和bilibili视频\n\n作者：@少昊金天氏\n\n版本：v1.0.1\n\n更新时间：2025-04-17')
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
        url = self.url_input.text().strip()
        is_youtube = 'youtube.com' in url.lower() or 'youtu.be' in url.lower()
        self.cookie_container.setVisible(is_youtube)

    def save_cookie(self):
        try:
            cookie_content = self.cookie_input.text().strip()
            if not cookie_content:
                QMessageBox.warning(self, '警告', '请输入Cookies内容')
                return
            
            with open(self.cookie_file, 'w', encoding='utf-8') as f:
                f.write(cookie_content)
            
            QMessageBox.information(self, '成功', 'Cookies已更新！')
            self.cookie_input.clear()
        except Exception as e:
            QMessageBox.warning(self, '警告', f'Cookies更新失败：{str(e)}')

    def show_context_menu(self, pos):
        # 获取触发右键菜单的控件
        sender = self.sender()
        # 如果输入框有内容，先全选
        if sender.text():
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
        self.download_button.setText('开始嗅探')
        self.progress_text.setText('准备就绪')
        
        # 如果正在进行嗅探或下载，停止它们
        if self.sniff_thread and self.sniff_thread.isRunning():
            self.sniff_thread.stop()
            self.sniff_thread.wait()
        
        if self.download_thread and self.download_thread.isRunning():
            self.download_thread.stop()
            self.download_thread.wait()
        
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
            icon_path = os.path.join(base_path, '003.ico')
            app.setWindowIcon(QIcon(icon_path))
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