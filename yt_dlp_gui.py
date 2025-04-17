import sys
import os
import re
import time
import traceback
import subprocess
import ctypes
<<<<<<< HEAD
import tempfile
=======
>>>>>>> 40052f5497c696c139a83b1c9406571b279ebd46

# 导入Qt相关模块
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QLineEdit, QPushButton,
                             QProgressBar, QComboBox, QFileDialog, QMessageBox, QMenu)
<<<<<<< HEAD
=======
from PyQt6.QtGui import QAction, QIcon
>>>>>>> 40052f5497c696c139a83b1c9406571b279ebd46
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
                
                # 解析H.264视频格式
                if 'avc1' in line.lower() or 'h264' in line.lower():
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
                                    fps = int(float(part.lower().replace('fps', '')))
                                except:
                                    pass
                                break
                        
                        # 解析文件大小
                        for part in parts:
                            if 'mib' in part.lower() or 'gib' in part.lower():
                                try:
                                    size = float(part[:-3])
                                    if 'gib' in part.lower():
                                        filesize = round(size * 1024, 1)
                                    else:
                                        filesize = round(size, 1)
                                except:
                                    pass
                                break
                        
                        if resolution and resolution.endswith('p'):
                            format_info = f"{resolution}/H.264"
                            if fps:
                                format_info += f"/{fps}fps"
                            if filesize > 0:
                                if filesize >= 1024:
                                    format_info += f"/{round(filesize/1024, 1)}GB"
                                else:
                                    format_info += f"/{filesize}MB"
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
                self.finished_signal.emit(True, '视频格式嗅探完成', self.available_formats)
            else:
                self.finished_signal.emit(False, '视频格式嗅探失败', [])
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
                self.finished_signal.emit(True, '下载完成')
            else:
                self.finished_signal.emit(False, '下载失败')
        except Exception as e:
            self.finished_signal.emit(False, f'发生错误：{str(e)}')

    def stop(self):
        self.is_running = False

# 在顶部导入部分添加 QIcon
from PyQt6.QtGui import QAction, QIcon

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('yt_dlp_gui')
        self.setWindowIcon(QIcon('icons/favicon.ico'))  # 修改图标路径
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
        self.url_input.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.url_input.customContextMenuRequested.connect(self.show_context_menu)
        url_layout.addWidget(url_label)
        url_layout.addWidget(self.url_input)
        layout.addLayout(url_layout)

        # 格式选择区域
        format_layout = QHBoxLayout()
        format_layout.setContentsMargins(10, 10, 10, 0)  # 与URL输入区域保持一致的边距
        format_label = QLabel('视频格式：')
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
        if success:
            self.download_button.setText('开始嗅探')
            QMessageBox.information(self, '成功', '下载完成！')
            # 清空格式列表，为下一次下载做准备
            self.format_combo.clear()
            self.format_id_map.clear()
        else:
            self.download_button.setText('开始下载')  # 下载失败时保持'开始下载'状态
            QMessageBox.warning(self, '错误', message)

    def show_about(self):
        # 创建自定义的关于对话框
        about_box = QMessageBox(self)
        about_box.setWindowTitle('关于')
<<<<<<< HEAD
        about_box.setText('基于yt-dlp的视频下载工具\n为了兼容我只允许它下载H.264\n主要下载YouTube和bilibili视频\n\n作者：@少昊金天氏\n\n版本：v1.0.1\n\n更新时间：2025-04-17')
=======
        about_box.setText('基于yt-dlp的视频下载工具\n为了兼容我只允许它下载H.264\n主要下载YouTube和bilibili视频\n\n作者：@少昊金天氏\n\n版本：v1.0.0\n\n更新时间：2025-03-31')
>>>>>>> 40052f5497c696c139a83b1c9406571b279ebd46
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
        menu = QMenu(self)
        cut_action = menu.addAction('剪切')
        copy_action = menu.addAction('复制')
        paste_action = menu.addAction('粘贴')
        delete_action = menu.addAction('删除')
        menu.addSeparator()
        select_all_action = menu.addAction('全选')

        cut_action.triggered.connect(sender.cut)
        copy_action.triggered.connect(sender.copy)
        paste_action.triggered.connect(sender.paste)
        delete_action.triggered.connect(sender.clear)
        select_all_action.triggered.connect(sender.selectAll)

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

def main():
    try:
<<<<<<< HEAD
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
=======
        
        # 首先初始化QApplication，确保在使用任何Qt组件前完成初始化
        app = QApplication(sys.argv)
        app.setWindowIcon(QIcon('icons/favicon.ico'))  # 修改应用程序图标路径
        
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
        
        # 检查必要文件是否存在
        required_files = ['yt-dlp.exe', 'ffmpeg.exe']
        missing_files = [f for f in required_files if not os.path.exists(f)]
        if missing_files:
            error_msg = f'缺少必要文件：{", ".join(missing_files)}\n请确保程序目录下包含这些文件。'
            log_message('ERROR', error_msg)
            QMessageBox.critical(None, '错误', error_msg)
            return
            
        
>>>>>>> 40052f5497c696c139a83b1c9406571b279ebd46
        
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
