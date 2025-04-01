import sys
import os
import re
import time
import traceback
import subprocess
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QLineEdit, QPushButton,
                             QProgressBar, QComboBox, QFileDialog, QMessageBox, QMenu)
from PyQt6.QtGui import QAction
from PyQt6.QtCore import Qt, QThread, pyqtSignal

class SniffThread(QThread):
    progress_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool, str, list)

    def __init__(self, url):
        super().__init__()
        self.url = url
        self.is_running = True
        self.available_formats = []

    def run(self):
        try:
            # 检查是否为YouTube链接，只有YouTube链接才需要Cookie
            is_youtube = 'youtube.com' in self.url.lower() or 'youtu.be' in self.url.lower()
            
            if is_youtube and not os.path.exists('YouTube-Cookies.txt'):
                self.finished_signal.emit(False, '未找到Cookies文件，请先更新Cookies！', [])
                return
                
            # 根据URL类型决定是否使用Cookie
            if is_youtube:
                cmd = ['yt-dlp.exe', '-F', '--cookies', 'YouTube-Cookies.txt', self.url, '--newline']
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
                        for part in parts:
                            if 'x' in part and part[0].isdigit():
                                resolution = part.split('x')[1] + 'p'
                                break
                        
                        if resolution and resolution.endswith('p'):
                            self.available_formats.append((format_id, resolution + '/H.264'))
            
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

    def __init__(self, url, format_id):
        super().__init__()
        self.url = url
        self.format_id = format_id
        self.is_running = True

    def run(self):
        try:
            # 下载并合并视频和音频，选择最高码率的m4a(aac)音频
            # 检查是否为YouTube链接，只有YouTube链接才需要Cookies
            is_youtube = 'youtube.com' in self.url.lower() or 'youtu.be' in self.url.lower()
            
            if is_youtube:
                cmd = ['yt-dlp.exe', '-f', f'{self.format_id}+bestaudio[ext=m4a]', '--cookies', 'YouTube-Cookies.txt', '--merge-output-format', 'mp4', self.url, '--newline']
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

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('yt_dlp_gui')
        self.setMinimumSize(533, 400)
        self.download_thread = None
        self.sniff_thread = None
        self.cookie_file = 'YouTube-Cookies.txt'
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

        # Cookie设置区域
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
                
            self.sniff_thread = SniffThread(url)
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
        self.download_thread = DownloadThread(url, format_id)
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
        QMessageBox.about(self, '关于', '基于yt-dlp的视频下载工具\n为了兼容我只允许它下载H.264\n主要下载YouTube和bilibili视频\n\n作者：@少昊金天氏\n\n版本：0.0.1\n\n更新时间：2025-03-31')

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
    # 创建日志目录
    log_dir = 'logs'
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f'app_{time.strftime("%Y%m%d_%H%M%S")}.log')
    
    def log_message(level, msg, exc_info=None):
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
        try:
            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(f"[{timestamp}] {level}: {msg}\n")
                if exc_info:
                    f.write(f"[{timestamp}] TRACEBACK:\n{exc_info}\n")
        except Exception as e:
            print(f"写入日志失败：{e}")
    
    try:
        # 记录程序启动信息
        log_message('INFO', '程序启动')
        
        # 首先初始化QApplication，确保在使用任何Qt组件前完成初始化
        app = QApplication(sys.argv)
        
        # 检查必要文件是否存在
        required_files = ['yt-dlp.exe', 'ffmpeg.exe']
        missing_files = [f for f in required_files if not os.path.exists(f)]
        if missing_files:
            error_msg = f'缺少必要文件：{", ".join(missing_files)}\n请确保程序目录下包含这些文件。'
            log_message('ERROR', error_msg)
            QMessageBox.critical(None, '错误', error_msg)
            return
            
        # 检查FFmpeg所需的DLL文件
        ffmpeg_dlls = [
            'avcodec-61.dll', 'avformat-61.dll', 'avutil-59.dll',
            'swresample-5.dll', 'swscale-8.dll', 'avfilter-10.dll',
            'avdevice-61.dll', 'postproc-58.dll'
        ]
        
        # 创建DLL目录
        dll_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dll')
        os.makedirs(dll_dir, exist_ok=True)
        
        # 检查DLL文件是否存在
        missing_dlls = []
        for dll in ffmpeg_dlls:
            if not (os.path.exists(dll) or os.path.exists(os.path.join(dll_dir, dll))):
                missing_dlls.append(dll)
        
        if missing_dlls:
            warning_msg = f'缺少FFmpeg所需的DLL文件：{", ".join(missing_dlls)}\n音视频合并功能可能无法正常工作。'
            log_message('WARNING', warning_msg)
            QMessageBox.warning(None, '警告', warning_msg)
            
        # 设置环境变量，确保FFmpeg能找到DLL文件
        os.environ['PATH'] = os.path.dirname(os.path.abspath(__file__)) + os.pathsep + \
                            dll_dir + os.pathsep + os.environ.get('PATH', '')

        window = MainWindow()
        window.show()
        log_message('INFO', '主窗口已显示')
        sys.exit(app.exec())
    except Exception as e:
        error_msg = f'程序启动失败：{str(e)}'
        log_message('ERROR', error_msg, traceback.format_exc())
        QMessageBox.critical(None, '错误', error_msg)
        return

if __name__ == '__main__':
    main()