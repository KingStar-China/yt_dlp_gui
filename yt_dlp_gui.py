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
import urllib.parse
import json
import gzip
import zlib
import hashlib
try:
    import requests
except ImportError:
    requests = None

# 导入Qt相关模块
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QLineEdit, QPushButton,
                             QProgressBar, QComboBox, QFileDialog, QMessageBox, QMenu,
                             QPlainTextEdit)
from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
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

def get_managed_ffmpeg_path():
    return os.path.join(get_runtime_dir(), 'ffmpeg.exe')


def resolve_ffmpeg_command():
    managed_path = get_managed_ffmpeg_path()
    if os.path.exists(managed_path):
        return managed_path

    path_cmd = shutil.which('ffmpeg.exe') or shutil.which('ffmpeg')
    if path_cmd:
        return path_cmd

    return managed_path


BILIBILI_WEB_UA = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/135.0.0.0 Safari/537.36'
)


def detect_site(url):
    lower_url = (url or '').lower()
    if 'youtube.com' in lower_url or 'youtu.be' in lower_url:
        return 'youtube'
    if 'bilibili.com' in lower_url or 'b23.tv' in lower_url:
        return 'bilibili'
    return 'other'


def get_cookie_args(cookie_mode, cookie_file):
    if cookie_mode == 'file' and os.path.exists(cookie_file):
        return ['--cookies', cookie_file]
    if cookie_mode == 'firefox':
        return ['--cookies-from-browser', 'firefox']
    if cookie_mode.startswith('browser:'):
        return ['--cookies-from-browser', cookie_mode.split(':', 1)[1]]
    return []


def format_size_from_bytes(filesize):
    if not filesize:
        return ''
    if filesize >= 1024 * 1024 * 1024:
        return f'{round(filesize / (1024 * 1024 * 1024), 2)}GB'
    if filesize >= 1024 * 1024:
        return f'{round(filesize / (1024 * 1024), 1)}MB'
    if filesize >= 1024:
        return f'{round(filesize / 1024, 1)}KB'
    return f'{filesize}B'


def sanitize_filename(filename):
    sanitized = re.sub(r'[<>:"/\\|?*]', '_', (filename or '').strip())
    sanitized = sanitized.rstrip(' .')
    return sanitized or 'video'


def ensure_unique_path(file_path):
    if not os.path.exists(file_path):
        return file_path

    base_name, ext = os.path.splitext(file_path)
    index = 1
    while True:
        candidate = f'{base_name} ({index}){ext}'
        if not os.path.exists(candidate):
            return candidate
        index += 1


def build_bilibili_mixin_key(img_url, sub_url):
    lookup = (
        str(img_url or '').rpartition('/')[2].partition('.')[0]
        + str(sub_url or '').rpartition('/')[2].partition('.')[0]
    )
    mixin_key_enc_tab = [
        46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
        27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
        37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
        22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52,
    ]
    if len(lookup) < 64:
        return ''
    return ''.join(lookup[index] for index in mixin_key_enc_tab)[:32]

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
        self.subtitle_process = None

    def build_sniff_cmd(self, cookie_mode):
        cmd = [
            self.parent().get_ytdlp_command(),
            '--dump-single-json',
            '--no-warnings',
            '--no-playlist',
        ]
        cmd.extend(get_cookie_args(cookie_mode, self.parent().cookie_file))
        cmd.append(self.url)
        return cmd

    def parse_info_json(self, output):
        text = (output or '').strip()
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            for line in reversed(text.splitlines()):
                line = line.strip()
                if not line.startswith('{'):
                    continue
                try:
                    return json.loads(line)
                except json.JSONDecodeError:
                    continue
        return None

    def get_resolution_label(self, fmt):
        height = fmt.get('height')
        if isinstance(height, (int, float)) and height:
            return f'{int(height)}p'

        resolution = str(fmt.get('resolution') or '')
        if resolution:
            match = re.search(r'(\d{3,4})p', resolution, re.IGNORECASE)
            if match:
                return f'{match.group(1)}p'
            match = re.search(r'(\d{3,4})x(\d{3,4})', resolution)
            if match:
                return f'{match.group(2)}p'
        return None

    def add_subtitle_group(self, subtitle_map, mode):
        for subtitle_lang, entries in (subtitle_map or {}).items():
            if not entries:
                continue

            exts = []
            for entry in entries:
                ext = str(entry.get('ext') or '').strip()
                if ext and ext not in exts:
                    exts.append(ext)

            subtitle_id = f'subtitle:{subtitle_lang}:{mode}'
            subtitle_kind = '自动字幕' if mode == 'auto' else '字幕'
            subtitle_info = f'{subtitle_kind}/{subtitle_lang}'
            if exts:
                subtitle_info += f"/{','.join(exts)}"
            if not any(existing_id == subtitle_id for existing_id, _ in self.subtitle_entries):
                self.subtitle_entries.append((subtitle_id, subtitle_info))

    def populate_formats_from_info(self, info):
        self.available_formats = []
        self.subtitle_entries = []

        for fmt in info.get('formats') or []:
            format_id = str(fmt.get('format_id') or '').strip()
            if not format_id:
                continue

            vcodec = str(fmt.get('vcodec') or '').lower()
            acodec = str(fmt.get('acodec') or '').lower()
            ext = str(fmt.get('ext') or '').lower()
            resolution = self.get_resolution_label(fmt)
            fps = fmt.get('fps')
            filesize = fmt.get('filesize') or fmt.get('filesize_approx') or 0

            is_audio = vcodec == 'none' and acodec != 'none'
            is_aac_audio = any(token in acodec for token in ('aac', 'mp4a')) or ext in {'m4a', 'aac'}
            is_h264_video = vcodec != 'none' and any(token in vcodec for token in ('avc1', 'h264'))

            if is_audio:
                if not is_aac_audio:
                    continue
                format_info = '音频/AAC'
            elif is_h264_video and resolution:
                format_info = f'{resolution}/H.264'
            else:
                continue

            try:
                if fps:
                    format_info += f'/{int(round(float(fps)))}fps'
            except Exception:
                pass

            size_label = format_size_from_bytes(filesize)
            if size_label:
                format_info += f'/{size_label}'

            if not any(existing_id == format_id for existing_id, _ in self.available_formats):
                self.available_formats.append((format_id, format_info))

        self.add_subtitle_group(info.get('subtitles'), 'manual')
        self.add_subtitle_group(info.get('automatic_captions'), 'auto')

    def fetch_bilibili_page_data(self):
        headers = {
            'User-Agent': BILIBILI_WEB_UA,
            'Referer': 'https://www.bilibili.com/',
        }
        session = None
        if requests is not None:
            session = requests.Session()
            response = session.get(self.url, headers=headers, timeout=20)
            response.raise_for_status()
            html = response.text
        else:
            request = urllib.request.Request(self.url, headers=headers)
            with urllib.request.urlopen(request, timeout=20) as response:
                raw_data = response.read()
                content_encoding = str(response.headers.get('Content-Encoding') or '').lower()
                if content_encoding == 'gzip':
                    raw_data = gzip.decompress(raw_data)
                elif content_encoding == 'deflate':
                    raw_data = zlib.decompress(raw_data)
                html = raw_data.decode('utf-8', errors='ignore')

        playinfo = self.extract_embedded_json(html, r'window\.__playinfo__\s*=')
        initial_state = self.extract_embedded_json(html, r'window\.__INITIAL_STATE__\s*=')
        if not playinfo:
            if initial_state:
                playinfo = self.fetch_bilibili_playinfo_from_api(session, initial_state)
            if playinfo:
                return playinfo, initial_state
            if any(keyword in html for keyword in ['验证码', '安全验证', '风控', '请完成验证', 'geetest']):
                raise ValueError('B站返回了风控/验证页面，请稍后重试或提供 Cookies')
            page_title_match = re.search(r'<title[^>]*>(.*?)</title>', html, re.IGNORECASE | re.DOTALL)
            page_title = ''
            if page_title_match:
                page_title = re.sub(r'\s+', ' ', page_title_match.group(1)).strip()
            if page_title:
                raise ValueError(f'B站返回的不是标准视频页：{page_title}')
            raise ValueError('B站页面里没找到播放器数据')
        return playinfo, initial_state

    def get_bilibili_page_number(self):
        try:
            parsed_url = urllib.parse.urlparse(self.url)
            query = urllib.parse.parse_qs(parsed_url.query)
            page_no = int(query.get('p', ['1'])[0])
            return max(page_no, 1)
        except Exception:
            return 1

    def get_bilibili_video_identifiers(self, initial_state):
        video_data = (initial_state or {}).get('videoData') or {}
        pages = video_data.get('pages') or []
        page_no = self.get_bilibili_page_number()
        page_index = min(max(page_no - 1, 0), len(pages) - 1) if pages else 0
        current_page = pages[page_index] if pages else {}
        return {
            'bvid': video_data.get('bvid') or (initial_state or {}).get('bvid'),
            'aid': video_data.get('aid') or (initial_state or {}).get('aid'),
            'cid': current_page.get('cid') or video_data.get('cid'),
        }

    def get_bilibili_wbi_key(self, session, initial_state):
        default_key = build_bilibili_mixin_key(
            ((initial_state or {}).get('defaultWbiKey') or {}).get('wbiImgKey'),
            ((initial_state or {}).get('defaultWbiKey') or {}).get('wbiSubKey'),
        )
        if default_key:
            return default_key

        if session is None:
            raise ValueError('当前环境缺少 requests，无法补拉 B站播放数据')

        response = session.get(
            'https://api.bilibili.com/x/web-interface/nav',
            headers={'User-Agent': BILIBILI_WEB_UA, 'Referer': self.url},
            timeout=20,
        )
        response.raise_for_status()
        data = response.json().get('data') or {}
        wbi_img = data.get('wbi_img') or {}
        mixin_key = build_bilibili_mixin_key(wbi_img.get('img_url'), wbi_img.get('sub_url'))
        if not mixin_key:
            raise ValueError('获取 B站 WBI 签名失败')
        return mixin_key

    def sign_bilibili_wbi_params(self, params, mixin_key):
        signed_params = {'wts': round(time.time())}
        signed_params.update(params)
        signed_params = {
            key: ''.join(char for char in str(value) if char not in "!'()*")
            for key, value in sorted(signed_params.items())
        }
        query = urllib.parse.urlencode(signed_params)
        signed_params['w_rid'] = hashlib.md5(f'{query}{mixin_key}'.encode('utf-8')).hexdigest()
        return signed_params

    def fetch_bilibili_playinfo_from_api(self, session, initial_state):
        if session is None:
            return None

        identifiers = self.get_bilibili_video_identifiers(initial_state)
        bvid = identifiers.get('bvid')
        cid = identifiers.get('cid')
        if not bvid or not cid:
            return None

        mixin_key = self.get_bilibili_wbi_key(session, initial_state)
        params = self.sign_bilibili_wbi_params(
            {'bvid': bvid, 'cid': cid, 'fnval': 4048},
            mixin_key,
        )
        response = session.get(
            'https://api.bilibili.com/x/player/wbi/playurl',
            params=params,
            headers={
                'User-Agent': BILIBILI_WEB_UA,
                'Referer': self.url,
                'Origin': 'https://www.bilibili.com',
            },
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get('code') != 0:
            raise ValueError(f'B站播放接口返回异常：{payload.get("message") or payload.get("code")}')
        return payload

    def extract_embedded_json(self, html, marker_pattern):
        marker_match = re.search(marker_pattern, html)
        if not marker_match:
            return None

        start = html.find('{', marker_match.end())
        if start < 0:
            return None

        depth = 0
        in_string = False
        escape = False

        for index in range(start, len(html)):
            char = html[index]

            if in_string:
                if escape:
                    escape = False
                elif char == '\\':
                    escape = True
                elif char == '"':
                    in_string = False
                continue

            if char == '"':
                in_string = True
            elif char == '{':
                depth += 1
            elif char == '}':
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(html[start:index + 1])
                    except json.JSONDecodeError:
                        return None
        return None

    def run_bilibili_webpage_sniff(self):
        self.progress_signal.emit('yt-dlp 被 B站 412 拦截，正在尝试网页直连嗅探...')
        self.available_formats = []
        self.subtitle_entries = []

        playinfo, initial_state = self.fetch_bilibili_page_data()
        playinfo_data = playinfo.get('data') or {}
        dash = playinfo_data.get('dash') or {}
        videos = dash.get('video') or []
        audios = dash.get('audio') or []

        title = (
            ((initial_state.get('videoData') or {}).get('title'))
            or (initial_state.get('h1Title'))
            or 'bilibili_video'
        )
        page_url = self.url
        download_payloads = {}

        preferred_audio = None
        for index, audio in enumerate(audios):
            audio_codec = str(audio.get('codecs') or '').lower()
            if 'mp4a' not in audio_codec and 'aac' not in audio_codec:
                continue
            audio_url = audio.get('baseUrl') or audio.get('base_url') or audio.get('url')
            if not audio_url:
                continue
            audio_entry = {
                'type': 'bilibili_direct_audio',
                'title': title,
                'audio_url': audio_url,
                'audio_ext': 'm4a',
                'audio_codec': audio.get('codecs'),
                'filesize': audio.get('size') or 0,
                'headers': {
                    'User-Agent': BILIBILI_WEB_UA,
                    'Referer': page_url,
                },
            }
            if preferred_audio is None or (audio.get('bandwidth') or 0) > (preferred_audio.get('bandwidth') or 0):
                preferred_audio = {
                    'index': index,
                    'bandwidth': audio.get('bandwidth') or 0,
                    'payload': audio_entry,
                }

        if preferred_audio:
            audio_format_id = f'bili-direct-audio:{preferred_audio["index"]}'
            format_info = '音频/AAC'
            size_label = format_size_from_bytes(preferred_audio['payload'].get('filesize'))
            if size_label:
                format_info += f'/{size_label}'
            self.available_formats.append((audio_format_id, format_info))
            download_payloads[audio_format_id] = preferred_audio['payload']

        for index, video in enumerate(videos):
            video_codec = str(video.get('codecs') or '').lower()
            if not any(token in video_codec for token in ('avc1', 'h264')):
                continue

            video_url = video.get('baseUrl') or video.get('base_url') or video.get('url')
            if not video_url:
                continue

            height = video.get('height')
            if not height:
                continue
            resolution = f'{int(height)}p'
            format_id = f'bili-direct-video:{index}'
            format_info = f'{resolution}/H.264'

            try:
                fps = float(video.get('frameRate') or video.get('frame_rate') or 0)
                if fps:
                    format_info += f'/{int(round(fps))}fps'
            except Exception:
                pass

            size_label = format_size_from_bytes(video.get('size') or 0)
            if size_label:
                format_info += f'/{size_label}'

            self.available_formats.append((format_id, format_info))
            download_payloads[format_id] = {
                'type': 'bilibili_direct_video',
                'title': title,
                'video_url': video_url,
                'audio_url': preferred_audio['payload']['audio_url'] if preferred_audio else None,
                'video_ext': 'mp4',
                'audio_ext': 'm4a',
                'resolution': resolution,
                'headers': {
                    'User-Agent': BILIBILI_WEB_UA,
                    'Referer': page_url,
                },
            }

        if not self.available_formats:
            return False, 'B站网页已打开，但没解析到可直连的 H.264/AAC 格式', []

        self.parent().set_direct_download_payloads(download_payloads)
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
        return True, 'B站网页直连嗅探完成', self.available_formats

    def normalize_error_message(self, site, error_text):
        lowered = (error_text or '').lower()
        if site == 'bilibili' and ('http error 412' in lowered or 'precondition failed' in lowered):
            return 'B站接口返回 412，已尝试常规嗅探'
        if 'sign in' in lowered or 'login' in lowered:
            return '目标站点需要登录态或 Cookies'
        if error_text:
            return error_text.strip().splitlines()[-1]
        return '嗅探失败'

    def run_sniff(self, cookie_mode):
        self.available_formats = []
        self.subtitle_entries = []
        self.parent().set_direct_download_payloads({})
        site = detect_site(self.url)
        process = subprocess.Popen(
            self.build_sniff_cmd(cookie_mode),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        self.process = process
        output, error_output = process.communicate()
        self.process = None

        if not self.is_running:
            if process.poll() is None:
                process.terminate()
            return False, '嗅探已取消', []

        if process.returncode == 0:
            info = self.parse_info_json(output)
            if not info:
                return False, '嗅探返回了无法解析的 JSON', []

            self.populate_formats_from_info(info)
            if not self.available_formats and not self.subtitle_entries:
                return False, '未找到可用的 H.264 视频格式或字幕', []

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

        combined_error = '\n'.join(part for part in [error_output, output] if part).strip()
        if site == 'bilibili' and ('HTTP Error 412' in combined_error or 'Precondition Failed' in combined_error):
            return self.run_bilibili_webpage_sniff()

        return False, self.normalize_error_message(site, combined_error), []

    def run(self):
        try:
            site = detect_site(self.url)
            cookie_modes = ['none']
            if site == 'youtube':
                if self.parent().manual_cookie_enabled and os.path.exists(self.parent().cookie_file):
                    cookie_modes = ['file']
                else:
                    cookie_modes = ['none', 'browser:firefox']
            elif site == 'bilibili':
                if self.parent().manual_cookie_enabled and os.path.exists(self.parent().cookie_file):
                    cookie_modes = ['file']
                else:
                    cookie_modes = ['none', 'browser:firefox', 'browser:edge', 'browser:chrome']

            last_message = '嗅探失败'
            for cookie_mode in cookie_modes:
                if cookie_mode.startswith('browser:'):
                    browser_name = cookie_mode.split(':', 1)[1].capitalize()
                    self.progress_signal.emit(f'普通嗅探失败，正在尝试调用 {browser_name} Cookies...')
                success, message, formats = self.run_sniff(cookie_mode)
                if success:
                    self.finished_signal.emit(True, message, formats, cookie_mode)
                    return
                last_message = message
                if not self.is_running:
                    self.finished_signal.emit(False, '嗅探已取消', [], cookie_mode)
                    return

            if site == 'youtube' and not self.parent().manual_cookie_enabled:
                self.finished_signal.emit(False, 'Firefox Cookies 调用失败，请手动输入 Cookies 后重试。', [], 'show_cookie_input')
                return

            if site == 'bilibili' and not self.parent().manual_cookie_enabled:
                self.finished_signal.emit(False, 'B站常规接口失败时，程序会先尝试网页直连；若你需要更高画质或登录态资源，请手动输入 Cookies 后重试。', [], 'show_cookie_input')
                return

            self.finished_signal.emit(False, last_message, [], 'none')
        except Exception as e:
            self.finished_signal.emit(False, f'嗅探时发生错误：{str(e)}', [], 'none')

    def stop(self):
        self.is_running = False
        if self.process and self.process.poll() is None:
            self.process.terminate()
        if self.subtitle_process and self.subtitle_process.poll() is None:
            self.subtitle_process.terminate()

class DownloadThread(QThread):
    progress_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, url, format_id, parent=None):
        super().__init__(parent)
        self.url = url
        self.format_id = format_id
        self.is_running = True
        self.process = None

    def finalize_downloaded_file(self, downloaded_file):
        if not downloaded_file or not os.path.exists(downloaded_file):
            return

        file_size = os.path.getsize(downloaded_file)
        file_size_str = ''
        if file_size >= 1024 * 1024 * 1024:
            file_size_str = f'.{round(file_size / (1024 * 1024 * 1024), 2)}G'
        elif file_size >= 1024 * 1024:
            file_size_str = f'.{round(file_size / (1024 * 1024), 1)}M'
        elif file_size >= 1024:
            file_size_str = f'.{round(file_size / 1024, 1)}K'

        base_name, ext = os.path.splitext(downloaded_file)
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

    def download_url_to_file(self, url, target_path, headers):
        request = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(request, timeout=30) as response, open(target_path, 'wb') as output_file:
            total = response.headers.get('Content-Length')
            total_bytes = int(total) if total and total.isdigit() else 0
            downloaded = 0
            last_reported_mb = -1

            while self.is_running:
                chunk = response.read(1024 * 256)
                if not chunk:
                    break
                output_file.write(chunk)
                downloaded += len(chunk)

                current_mb = downloaded // (1024 * 1024)
                if current_mb != last_reported_mb:
                    last_reported_mb = current_mb
                    if total_bytes:
                        percent = int(downloaded * 100 / total_bytes)
                        self.progress_signal.emit(f'正在下载直连流... {percent}%')
                    else:
                        self.progress_signal.emit(f'正在下载直连流... {round(downloaded / (1024 * 1024), 1)}MB')

            if not self.is_running:
                raise RuntimeError('下载已取消')

    def run_direct_download(self, direct_payload):
        output_dir = os.getcwd()
        title = sanitize_filename(direct_payload.get('title') or 'bilibili_video')
        temp_paths = []

        try:
            if direct_payload.get('type') == 'bilibili_direct_audio':
                final_path = ensure_unique_path(os.path.join(output_dir, f'{title}.m4a'))
                temp_path = final_path + '.part'
                temp_paths.append(temp_path)
                self.progress_signal.emit('正在下载 B站音频直链...')
                self.download_url_to_file(
                    direct_payload['audio_url'],
                    temp_path,
                    direct_payload.get('headers'),
                )
                os.replace(temp_path, final_path)
                self.finalize_downloaded_file(final_path)
                self.finished_signal.emit(True, '下载完成')
                return

            final_path = ensure_unique_path(os.path.join(output_dir, f'{title}.mp4'))
            temp_video_path = final_path + '.video.m4s'
            temp_audio_path = final_path + '.audio.m4a'
            temp_paths.extend([temp_video_path, temp_audio_path])

            self.progress_signal.emit('正在下载 B站视频直链...')
            self.download_url_to_file(
                direct_payload['video_url'],
                temp_video_path,
                direct_payload.get('headers'),
            )

            audio_url = direct_payload.get('audio_url')
            if audio_url:
                self.progress_signal.emit('正在下载 B站音频直链...')
                self.download_url_to_file(audio_url, temp_audio_path, direct_payload.get('headers'))

            ffmpeg_cmd = [self.parent().get_ffmpeg_command(), '-y', '-i', temp_video_path]
            if audio_url:
                ffmpeg_cmd.extend(['-i', temp_audio_path, '-c', 'copy', final_path])
            else:
                ffmpeg_cmd.extend(['-c', 'copy', final_path])

            self.progress_signal.emit('正在用 FFmpeg 合并 B站音视频...')
            result = subprocess.run(
                ffmpeg_cmd,
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW,
                timeout=120,
            )
            if result.returncode != 0:
                raise RuntimeError((result.stderr or result.stdout or 'FFmpeg 合并失败').strip())

            self.finalize_downloaded_file(final_path)
            self.finished_signal.emit(True, '下载完成')
        finally:
            for temp_path in temp_paths:
                try:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                except Exception:
                    pass

    def run_ytdlp_download(self):
        site = detect_site(self.url)
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

        if site in {'youtube', 'bilibili'}:
            cmd.extend(get_cookie_args(self.parent().cookie_mode, self.parent().cookie_file))

        if is_subtitle:
            cmd.extend([self.url, '--newline'])
        else:
            cmd.extend(['--merge-output-format', 'mp4', self.url, '--newline'])

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
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
            self.finalize_downloaded_file(downloaded_file)
            self.finished_signal.emit(True, '下载完成' if not is_subtitle else '字幕下载完成')
        else:
            self.finished_signal.emit(False, '下载失败')

    def run(self):
        try:
            direct_payload = self.parent().get_direct_download_payload(self.format_id)
            if direct_payload:
                self.run_direct_download(direct_payload)
            else:
                self.run_ytdlp_download()
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
            target_exists = os.path.exists(self.target_path)
            if target_exists and local_version and latest_version and local_version == latest_version:
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
        self.setWindowTitle('yt_dlp_gui v1.0.6 @少昊金天氏')
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
        self.ffmpeg_path = resolve_ffmpeg_command()
        self.cookie_mode = 'none'
        self.manual_cookie_enabled = False
        self.format_id_map = {}
        self.direct_download_map = {}
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

    def get_ffmpeg_command(self):
        self.ffmpeg_path = resolve_ffmpeg_command()
        return self.ffmpeg_path

    def has_ffmpeg(self):
        ffmpeg_cmd = self.get_ffmpeg_command()
        return bool(ffmpeg_cmd and os.path.exists(ffmpeg_cmd)) or bool(shutil.which('ffmpeg.exe') or shutil.which('ffmpeg'))

    def set_direct_download_payloads(self, payloads):
        self.direct_download_map = payloads or {}

    def get_direct_download_payload(self, format_id):
        return self.direct_download_map.get(format_id)

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
            self.set_direct_download_payloads({})
            
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

        if not format_id.startswith('subtitle:') and not self.has_ffmpeg():
            QMessageBox.warning(self, '错误', '未找到 FFmpeg。请把 ffmpeg.exe 放到程序根目录，或安装 FFmpeg 并加入 PATH。')
            self.progress_text.setText('缺少 FFmpeg，无法合并视频和音频')
            return
        
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
            self.set_direct_download_payloads({})
            
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
            self.set_direct_download_payloads({})
            
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
        about_box.setText('基于yt-dlp的视频下载工具\n为了兼容我只允许它下载H.264\n主要下载YouTube和bilibili视频\n\n作者：@少昊金天氏\n\n更新时间：2026-03-30')
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
            QTimer.singleShot(0, self.start_download)
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
        self.set_direct_download_payloads({})
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
    
        
        
        # 优先让程序根目录和 dll 目录参与 PATH，便于找到 ffmpeg.exe / 相关 DLL
        runtime_dir = get_runtime_dir()
        os.environ['PATH'] = runtime_dir + os.pathsep + dll_dir + os.pathsep + os.environ.get('PATH', '')

        window = MainWindow()
        window.show()
        sys.exit(app.exec())
    except Exception as e:
        error_msg = f'程序启动失败：{str(e)}'
        QMessageBox.critical(None, '错误', error_msg)
        return

if __name__ == '__main__':
    main()
