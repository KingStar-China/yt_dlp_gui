import sys
import os
import re
import time
import subprocess
from collections import deque
import tempfile
import shutil
import urllib.request
import urllib.error
import urllib.parse
import json
import gzip
import zlib
import hashlib
import random
import sqlite3
import configparser
from http.cookiejar import MozillaCookieJar
try:
    import requests
except ImportError:
    requests = None

# 导入Qt相关模块
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                             QHBoxLayout, QLabel, QLineEdit, QPushButton,
                             QComboBox, QFileDialog, QMessageBox, QMenu,
                             QPlainTextEdit)
from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QIcon


def get_runtime_dir():
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def get_settings_path():
    return os.path.join(get_runtime_dir(), 'yt_dlp_gui_settings.json')


def is_writable_directory(path):
    return bool(path and os.path.isdir(path) and os.access(path, os.W_OK))


def load_saved_output_dir():
    settings_path = get_settings_path()
    if not os.path.exists(settings_path):
        return ''
    try:
        with open(settings_path, 'r', encoding='utf-8') as settings_file:
            data = json.load(settings_file)
        output_dir = str(data.get('output_dir') or '').strip()
        if is_writable_directory(output_dir):
            return output_dir
    except Exception:
        pass
    return ''


def save_output_dir(output_dir):
    if not is_writable_directory(output_dir):
        return
    settings_path = get_settings_path()
    data = {}
    if os.path.exists(settings_path):
        try:
            with open(settings_path, 'r', encoding='utf-8') as settings_file:
                loaded_data = json.load(settings_file)
            if isinstance(loaded_data, dict):
                data = loaded_data
        except Exception:
            data = {}
    data['output_dir'] = output_dir
    with open(settings_path, 'w', encoding='utf-8') as settings_file:
        json.dump(data, settings_file, ensure_ascii=False, indent=2)


def get_default_output_dir():
    saved_output_dir = load_saved_output_dir()
    if saved_output_dir:
        return saved_output_dir

    runtime_dir = get_runtime_dir()
    user_home = os.path.expanduser('~')
    downloads_dir = os.path.join(user_home, 'Downloads')
    for candidate in (runtime_dir, downloads_dir, user_home, os.getcwd()):
        if is_writable_directory(candidate):
            return candidate
    return runtime_dir or os.getcwd()


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

RESOLUTION_SORT_ORDER = {
    '2160p': 2160,
    '1440p': 1440,
    '1080p': 1080,
    '720p': 720,
    '480p': 480,
    '360p': 360,
    '240p': 240,
    '144p': 144,
}

VIDEO_CODEC_PRIORITY = [
    ('H.264', ('avc1', 'avc3', 'h264', 'avc')),
    ('H.265', ('hev1', 'hvc1', 'hevc', 'h265')),
    ('AV1', ('av01', 'av1')),
    ('VP9', ('vp09', 'vp9')),
    ('H.266', ('vvc1', 'vvi1', 'vvc', 'h266')),
]


def extract_url_hostname(url):
    try:
        return (urllib.parse.urlparse((url or '').strip()).hostname or '').lower()
    except Exception:
        return ''


def host_matches(hostname, domain):
    normalized_host = str(hostname or '').lower().strip('.')
    normalized_domain = str(domain or '').lower().strip('.')
    if not normalized_host or not normalized_domain:
        return False
    return normalized_host == normalized_domain or normalized_host.endswith(f'.{normalized_domain}')


def normalize_cookie_domain(domain):
    return str(domain or '').lower().lstrip('.').strip()


def detect_site(url):
    hostname = extract_url_hostname(url)
    if host_matches(hostname, 'youtube.com') or host_matches(hostname, 'youtu.be'):
        return 'youtube'
    if host_matches(hostname, 'bilibili.com') or host_matches(hostname, 'b23.tv'):
        return 'bilibili'
    return 'other'


def is_youtube_playlist_url(url):
    try:
        parsed_url = urllib.parse.urlparse((url or '').strip())
        query = urllib.parse.parse_qs(parsed_url.query or '')
    except Exception:
        return False

    host = extract_url_hostname(url)
    if not host_matches(host, 'youtube.com') and not host_matches(host, 'youtu.be'):
        return False
    return bool(query.get('list')) or (parsed_url.path or '').lower() == '/playlist'


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
    reserved_names = {
        'con', 'prn', 'aux', 'nul',
        'com1', 'com2', 'com3', 'com4', 'com5', 'com6', 'com7', 'com8', 'com9',
        'lpt1', 'lpt2', 'lpt3', 'lpt4', 'lpt5', 'lpt6', 'lpt7', 'lpt8', 'lpt9',
    }
    if sanitized.lower() in reserved_names:
        sanitized = f'_{sanitized}'
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


def terminate_process_tree(process, timeout=3):
    if not process or process.poll() is not None:
        return True

    if os.name == 'nt' and getattr(process, 'pid', None):
        try:
            subprocess.run(
                ['taskkill', '/F', '/T', '/PID', str(process.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
                timeout=timeout,
            )
            process.wait(timeout=timeout)
            return process.poll() is not None
        except Exception:
            pass

    try:
        process.terminate()
        process.wait(timeout=timeout)
        return True
    except subprocess.TimeoutExpired:
        pass
    except Exception:
        pass

    try:
        process.kill()
        process.wait(timeout=timeout)
    except Exception:
        pass
    return process.poll() is not None


def extract_process_error_message(lines, default_message):
    for raw_line in reversed(list(lines or [])):
        line = str(raw_line or '').strip()
        if not line:
            continue

        lowered = line.lower()
        if line.startswith('[download]') and 'error' not in lowered:
            continue
        if line.startswith('[info]') or line.startswith('[debug]'):
            continue

        cleaned = re.sub(r'^\s*ERROR:\s*', '', line, flags=re.IGNORECASE).strip()
        if cleaned:
            return f'{default_message}：{cleaned}'

    return default_message


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


def load_cookie_jar_from_file(cookie_file):
    if not cookie_file or not os.path.exists(cookie_file):
        return None
    cookie_jar = MozillaCookieJar()
    try:
        cookie_jar.load(cookie_file, ignore_discard=True, ignore_expires=True)
    except Exception as exc:
        raise ValueError(f'Cookies 文件格式无效：{str(exc)}')
    return cookie_jar


def get_firefox_profiles_root():
    appdata = os.getenv('APPDATA') or ''
    if not appdata:
        return None
    profiles_root = os.path.join(appdata, 'Mozilla', 'Firefox')
    return profiles_root if os.path.isdir(profiles_root) else None


def resolve_firefox_profile_path(base_dir, profile_path, is_relative):
    if not profile_path:
        return None
    full_path = os.path.join(base_dir, profile_path) if is_relative else profile_path
    return full_path if os.path.isdir(full_path) else None


def get_firefox_cookie_database_path():
    profiles_root = get_firefox_profiles_root()
    if not profiles_root:
        return None

    profiles_ini = os.path.join(profiles_root, 'profiles.ini')
    if not os.path.exists(profiles_ini):
        return None

    parser = configparser.ConfigParser()
    parser.read(profiles_ini, encoding='utf-8')
    candidates = []

    for section_name in parser.sections():
        section = parser[section_name]
        if section_name.startswith('Install') and section.get('Default'):
            profile_path = resolve_firefox_profile_path(profiles_root, section.get('Default'), True)
            if profile_path:
                candidates.append((0, profile_path))

    for section_name in parser.sections():
        if not section_name.startswith('Profile'):
            continue
        section = parser[section_name]
        profile_path = resolve_firefox_profile_path(
            profiles_root,
            section.get('Path'),
            section.getboolean('IsRelative', fallback=True),
        )
        if not profile_path:
            continue
        priority = 3
        if section.getboolean('Default', fallback=False):
            priority = 1
        elif section.get('Name', '').lower() == 'default-release':
            priority = 2
        candidates.append((priority, profile_path))

    for _, profile_path in sorted(candidates, key=lambda item: item[0]):
        cookie_db = os.path.join(profile_path, 'cookies.sqlite')
        if os.path.exists(cookie_db):
            return cookie_db
    return None


def load_firefox_cookie_records(domain_keywords=None):
    cookie_db = get_firefox_cookie_database_path()
    if not cookie_db:
        return []

    temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.sqlite')
    temp_db_path = temp_db.name
    temp_db.close()

    try:
        shutil.copy2(cookie_db, temp_db_path)
        connection = sqlite3.connect(temp_db_path)
        try:
            cursor = connection.cursor()
            cursor.execute(
                'SELECT name, value, host, path, expiry, isSecure FROM moz_cookies'
            )
            rows = cursor.fetchall()
        finally:
            connection.close()
    finally:
        try:
            os.remove(temp_db_path)
        except Exception:
            pass

    now = int(time.time())
    normalized_keywords = [
        normalize_cookie_domain(keyword)
        for keyword in (domain_keywords or [])
        if normalize_cookie_domain(keyword)
    ]
    cookie_records = {}
    for name, value, host, path, expiry, is_secure in rows:
        host_text = normalize_cookie_domain(host)
        if not name or value is None or not host_text:
            continue
        expires_at = int(expiry) if expiry else None
        if expires_at and expires_at < now:
            continue
        if normalized_keywords and not any(host_matches(host_text, keyword) for keyword in normalized_keywords):
            continue
        record_key = (str(name), host_text, path or '/')
        cookie_records[record_key] = {
            'name': name,
            'value': value,
            'domain': host_text,
            'path': path or '/',
            'expires': expires_at,
            'secure': bool(is_secure),
        }
    return list(cookie_records.values())


def cookie_records_from_cookie_jar(cookie_jar):
    records = []
    if cookie_jar is None:
        return records
    for cookie in cookie_jar:
        records.append({
            'name': cookie.name,
            'value': cookie.value,
            'domain': cookie.domain,
            'path': cookie.path or '/',
            'expires': cookie.expires,
            'secure': bool(cookie.secure),
        })
    return records


def build_cookie_header_from_records(cookie_records, url):
    parsed_url = urllib.parse.urlparse((url or '').strip())
    hostname = (parsed_url.hostname or '').lower()
    request_path = parsed_url.path or '/'
    is_https = parsed_url.scheme.lower() == 'https'
    now = int(time.time())
    cookie_pairs = []
    sorted_records = sorted(
        cookie_records or [],
        key=lambda cookie: len(str(cookie.get('path') or '/')),
        reverse=True,
    )

    for cookie in sorted_records:
        domain = normalize_cookie_domain(cookie.get('domain'))
        path = cookie.get('path') or '/'
        expires = cookie.get('expires')
        if expires and int(expires) < now:
            continue
        if cookie.get('secure') and not is_https:
            continue
        if not host_matches(hostname, domain):
            continue
        if not request_path.startswith(path):
            continue
        cookie_pairs.append(f"{cookie.get('name')}={cookie.get('value')}")

    return '; '.join(cookie_pairs)


def get_request_cookie_header(url, cookie_mode, cookie_file):
    if cookie_mode == 'file':
        return build_cookie_header_from_records(
            cookie_records_from_cookie_jar(load_cookie_jar_from_file(cookie_file)),
            url,
        )

    if cookie_mode == 'browser:firefox':
        site = detect_site(url)
        domain_keywords = []
        if site == 'bilibili':
            domain_keywords = ['bilibili.com', 'b23.tv']
        elif site == 'youtube':
            domain_keywords = ['youtube.com', 'youtu.be', 'google.com']
        return build_cookie_header_from_records(load_firefox_cookie_records(domain_keywords), url)

    return ''


def get_codec_label_and_priority(codec_name):
    normalized = str(codec_name or '').strip().lower()
    for index, (label, patterns) in enumerate(VIDEO_CODEC_PRIORITY):
        if any(pattern in normalized for pattern in patterns):
            return label, index

    if normalized in {'none', ''}:
        return '', len(VIDEO_CODEC_PRIORITY)

    fallback = normalized.split('.')[0].replace('-', '').replace('_', '').upper()
    return fallback or 'OTHER', len(VIDEO_CODEC_PRIORITY)


def build_video_sort_key(candidate):
    return (
        float(candidate.get('fps') or 0),
        float(candidate.get('bandwidth') or candidate.get('tbr') or 0),
        float(candidate.get('filesize') or 0),
        str(candidate.get('format_id') or ''),
    )


def select_best_video_candidates(video_candidates):
    grouped_candidates = {}
    for candidate in video_candidates:
        resolution = candidate.get('resolution')
        if not resolution:
            continue
        grouped_candidates.setdefault(resolution, []).append(candidate)

    selected_candidates = []
    for resolution, candidates in grouped_candidates.items():
        preferred_candidates = [
            candidate for candidate in candidates
            if candidate.get('codec_priority', len(VIDEO_CODEC_PRIORITY)) < len(VIDEO_CODEC_PRIORITY)
        ]
        if preferred_candidates:
            best_priority = min(candidate['codec_priority'] for candidate in preferred_candidates)
            best_candidates = [
                candidate for candidate in preferred_candidates
                if candidate['codec_priority'] == best_priority
            ]
            selected_candidates.append(max(best_candidates, key=build_video_sort_key))
        else:
            selected_candidates.append(random.choice(candidates))

    selected_candidates.sort(
        key=lambda candidate: RESOLUTION_SORT_ORDER.get(candidate.get('resolution'), 0),
        reverse=True,
    )
    return selected_candidates


def choose_bilibili_web_fallback_cookie_mode(cookie_modes):
    if 'file' in cookie_modes:
        return 'file'
    if 'browser:firefox' in cookie_modes:
        return 'browser:firefox'
    return 'none'


def is_valid_video_url(url):
    try:
        parsed_url = urllib.parse.urlparse((url or '').strip())
    except Exception:
        return False
    return parsed_url.scheme in {'http', 'https'} and bool(parsed_url.netloc)


def detect_known_non_video_page(url):
    try:
        parsed_url = urllib.parse.urlparse((url or '').strip())
    except Exception:
        return ''

    host = extract_url_hostname(url)
    path = (parsed_url.path or '').lower()
    query = urllib.parse.parse_qs(parsed_url.query or '')

    if host_matches(host, 'youtube.com'):
        if path == '/watch' and not query.get('v'):
            return '该链接不是具体的 YouTube 视频页面'
        if path.startswith('/post/'):
            return '该链接是 YouTube 帖子页面，不是视频页面'
        if '/community' in path:
            return '该链接是 YouTube 社区页面，不是视频页面'
        if path.startswith('/results'):
            return '该链接是 YouTube 搜索结果页面，不是视频页面'
        if path.startswith('/feed/'):
            return '该链接是 YouTube 导航页面，不是视频页面'
        if path.startswith('/hashtag/'):
            return '该链接是 YouTube 话题聚合页面，不是视频页面'

    if host_matches(host, 'space.bilibili.com'):
        return '该链接是 B站空间主页，不是视频页面'
    if host_matches(host, 'search.bilibili.com'):
        return '该链接是 B站搜索结果页面，不是视频页面'
    if host_matches(host, 't.bilibili.com'):
        return '该链接是 B站动态页面，不是视频页面'
    if host_matches(host, 'bilibili.com'):
        if path.startswith('/opus/'):
            return '该链接是 B站动态页面，不是视频页面'
        if path.startswith('/read/'):
            return '该链接是 B站专栏页面，不是视频页面'

    if host_matches(host, 'douyin.com'):
        if path.startswith('/user/'):
            return '该链接是抖音用户主页，不是具体视频页面'
        if path.startswith('/search/') or path == '/hot':
            return '该链接是抖音搜索或导航页面，不是视频页面'
        if path.startswith('/note/'):
            return '该链接是抖音图文页面，不是视频页面'

    if host_matches(host, 'xiaohongshu.com'):
        if path.startswith('/user/profile/'):
            return '该链接是小红书用户主页，不是具体视频页面'
        if path.startswith('/search_result') or path.startswith('/search'):
            return '该链接是小红书搜索结果页面，不是视频页面'

    if host_matches(host, 'weibo.com'):
        if path.startswith('/u/'):
            return '该链接是微博用户主页，不是具体视频页面'
        if path.startswith('/search'):
            return '该链接是微博搜索结果页面，不是视频页面'

    return ''


def check_site_accessibility(url, timeout=8):
    headers = {'User-Agent': BILIBILI_WEB_UA}
    site = detect_site(url)
    acceptable_status_codes = {401, 403, 405, 406, 429}

    if requests is not None:
        try:
            response = requests.get(
                url,
                headers=headers,
                timeout=timeout,
                allow_redirects=True,
                stream=True,
            )
            status_code = response.status_code
            response.close()
            if (
                200 <= status_code < 400
                or status_code in acceptable_status_codes
                or (site == 'bilibili' and status_code == 412)
            ):
                return True, ''
            return False, f'目标网站暂时无法访问（HTTP {status_code}）'
        except requests.RequestException as exc:
            return False, f'目标网站暂时无法访问：{str(exc)}'

    try:
        request = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status_code = response.getcode()
        if 200 <= status_code < 400:
            return True, ''
        return False, f'目标网站暂时无法访问（HTTP {status_code}）'
    except urllib.error.HTTPError as exc:
        if exc.code in acceptable_status_codes or (site == 'bilibili' and exc.code == 412):
            return True, ''
        return False, f'目标网站暂时无法访问（HTTP {exc.code}）'
    except Exception as exc:
        return False, f'目标网站暂时无法访问：{str(exc)}'


def check_ytdlp_url_support(ytdlp_command, url, timeout=15):
    resolved_command = str(ytdlp_command or '').strip()
    if not resolved_command:
        return False, '未找到 yt-dlp，请先点击“更新 yt-dlp”。'
    if not os.path.exists(resolved_command) and not shutil.which(resolved_command):
        return False, '未找到 yt-dlp，请先点击“更新 yt-dlp”或确认 PATH 中存在 yt-dlp。'

    try:
        result = subprocess.run(
            [
                resolved_command,
                '--simulate',
                '--skip-download',
                '--no-warnings',
                '--print',
                'extractor_key',
                url,
            ],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
            timeout=timeout,
        )
    except FileNotFoundError:
        return False, '未找到 yt-dlp，请先点击“更新 yt-dlp”或确认 PATH 中存在 yt-dlp。'
    except subprocess.TimeoutExpired:
        return False, '检测 yt-dlp 支持性超时，请稍后重试。'
    except OSError as exc:
        return False, f'调用 yt-dlp 失败：{str(exc)}'
    except Exception as exc:
        return False, f'检测 yt-dlp 支持性失败：{str(exc)}'

    if result.returncode == 0:
        return True, ''

    error_text = '\n'.join(part for part in [result.stderr, result.stdout] if part).lower()
    if (
        '[youtube:tab]' in error_text
        and (' post:' in error_text or '/post/' in url.lower() or ' does not have a ' in error_text)
    ):
        return False, '该链接是 YouTube 非视频页面，不能直接下载'
    if (
        'youtube search page' in error_text
        or 'a channel URL was given' in error_text
        or 'a feed URL was given' in error_text
    ):
        return False, '该链接是 YouTube 非视频页面，不能直接下载'
    if (
        'unsupported url' in error_text
        or 'no suitable extractor' in error_text
        or 'unsupported site' in error_text
    ):
        return False, '该链接不是 yt-dlp 支持的网站或链接类型'

    return True, ''


class OutputPathLineEdit(QLineEdit):
    choose_dir_signal = pyqtSignal()
    open_dir_signal = pyqtSignal()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.choose_dir_signal.emit()
            event.accept()
            return
        if event.button() == Qt.MouseButton.RightButton:
            self.open_dir_signal.emit()
            event.accept()
            return
        super().mousePressEvent(event)

    def contextMenuEvent(self, event):
        event.accept()

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
        self.cookie_warning_message = ''
        self.direct_download_payloads = {}
        self.format_metadata = {}

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

    def build_playlist_sniff_cmd(self, cookie_mode):
        cmd = [
            self.parent().get_ytdlp_command(),
            '--dump-single-json',
            '--flat-playlist',
            '--ignore-errors',
            '--no-warnings',
            '--yes-playlist',
        ]
        cmd.extend(get_cookie_args(cookie_mode, self.parent().cookie_file))
        cmd.append(self.url)
        return cmd

    def build_cookie_modes(self, site):
        browser_cookie_modes = ['browser:firefox', 'browser:edge', 'browser:chrome']
        has_manual_cookie = self.parent().has_manual_cookie_for_url(self.url)

        if site in {'youtube', 'bilibili'}:
            if has_manual_cookie:
                return ['file'] + browser_cookie_modes + ['none'], has_manual_cookie
            return browser_cookie_modes + ['none'], has_manual_cookie

        if has_manual_cookie:
            return ['file', 'none'] + browser_cookie_modes, has_manual_cookie
        return ['none'] + browser_cookie_modes, has_manual_cookie

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
                self.format_metadata[subtitle_id] = {'kind': 'subtitle'}

    def populate_formats_from_info(self, info):
        self.available_formats = []
        self.subtitle_entries = []
        self.format_metadata = {}
        video_candidates = []
        audio_candidates = []

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
            codec_label, codec_priority = get_codec_label_and_priority(vcodec)

            if is_audio:
                if not is_aac_audio:
                    continue
                audio_candidates.append({
                    'format_id': format_id,
                    'label': '音频/AAC',
                    'filesize': filesize,
                    'tbr': fmt.get('tbr') or 0,
                })
                continue
            if not resolution or not codec_label:
                continue

            video_candidates.append({
                'format_id': format_id,
                'resolution': resolution,
                'codec_label': codec_label,
                'codec_priority': codec_priority,
                'has_audio': acodec != 'none',
                'fps': fps or 0,
                'bandwidth': fmt.get('tbr') or 0,
                'filesize': filesize,
            })

        for candidate in select_best_video_candidates(video_candidates):
            format_info = f"{candidate['resolution']}/{candidate['codec_label']}"
            try:
                if candidate.get('fps'):
                    format_info += f"/{int(round(float(candidate['fps'])))}fps"
            except Exception:
                pass

            size_label = format_size_from_bytes(candidate.get('filesize'))
            if size_label:
                format_info += f'/{size_label}'

            self.available_formats.append((candidate['format_id'], format_info))
            self.format_metadata[candidate['format_id']] = {
                'kind': 'video',
                'has_audio': bool(candidate.get('has_audio')),
            }

        if audio_candidates:
            best_audio = max(
                audio_candidates,
                key=lambda candidate: (
                    float(candidate.get('tbr') or 0),
                    float(candidate.get('filesize') or 0),
                    str(candidate.get('format_id') or ''),
                )
            )
            audio_label = best_audio['label']
            size_label = format_size_from_bytes(best_audio.get('filesize'))
            if size_label:
                audio_label += f'/{size_label}'
            self.available_formats.append((best_audio['format_id'], audio_label))
            self.format_metadata[best_audio['format_id']] = {'kind': 'audio'}

        self.add_subtitle_group(info.get('subtitles'), 'manual')
        self.add_subtitle_group(info.get('automatic_captions'), 'auto')

    def populate_youtube_playlist_from_info(self, info):
        entries = [
            entry for entry in (info.get('entries') or [])
            if isinstance(entry, dict) and (entry.get('id') or entry.get('url'))
        ]
        playlist_count = len(entries) or info.get('playlist_count') or info.get('n_entries') or 0
        playlist_title = (
            info.get('playlist_title')
            or info.get('title')
            or 'YouTube 视频列表'
        )
        if not playlist_count:
            return False

        count_label = f'{playlist_count}个视频' if playlist_count else '多个视频'
        h264_format_id = 'youtube-playlist:h264'
        compatible_format_id = 'youtube-playlist:compatible'
        self.available_formats = [
            (h264_format_id, f'列表批量下载/H.264优先/{count_label}'),
            (compatible_format_id, f'列表批量下载/最佳兼容/{count_label}'),
        ]
        self.subtitle_entries = []
        self.format_metadata = {
            h264_format_id: {
                'kind': 'playlist',
                'site': 'youtube',
                'mode': 'h264',
                'playlist_title': playlist_title,
                'playlist_count': playlist_count,
            },
            compatible_format_id: {
                'kind': 'playlist',
                'site': 'youtube',
                'mode': 'compatible',
                'playlist_title': playlist_title,
                'playlist_count': playlist_count,
            }
        }
        return True

    def apply_requests_cookies(self, session, cookie_mode):
        if session is None:
            return

        if cookie_mode == 'file':
            cookie_jar = load_cookie_jar_from_file(self.parent().cookie_file)
            if cookie_jar is not None:
                session.cookies.update(cookie_jar)
            return

        if cookie_mode == 'browser:firefox':
            site = detect_site(self.url)
            domain_keywords = []
            if site == 'bilibili':
                domain_keywords = ['bilibili.com', 'b23.tv']
            elif site == 'youtube':
                domain_keywords = ['youtube.com', 'youtu.be', 'google.com']
            cookie_records = load_firefox_cookie_records(domain_keywords)
            for cookie in cookie_records:
                session.cookies.set(
                    cookie['name'],
                    cookie['value'],
                    domain=cookie['domain'],
                    path=cookie['path'],
                    secure=cookie['secure'],
                    expires=cookie['expires'],
                )

    def set_cookie_quality_warning(self, site, cookie_mode, playinfo_data, video_candidates):
        if cookie_mode != 'none' or site not in {'bilibili', 'youtube'}:
            return
        if not video_candidates:
            return

        actual_max_height = max(
            int(str(candidate.get('resolution', '0p')).replace('p', '') or 0)
            for candidate in video_candidates
        )
        accept_quality = playinfo_data.get('accept_quality') or []
        if site == 'bilibili' and accept_quality:
            if max(int(quality) for quality in accept_quality if str(quality).isdigit()) > 64 and actual_max_height < 720:
                self.cookie_warning_message = '更高清视频需要浏览器登录或者手动填写Cookie（推荐火狐登录成功率更高）。'
        elif site == 'youtube' and actual_max_height < 720:
            self.cookie_warning_message = '更高清视频可能需要浏览器登录或者手动填写Cookie（推荐火狐登录成功率更高）。'

    def fetch_bilibili_page_data(self, cookie_mode):
        headers = {
            'User-Agent': BILIBILI_WEB_UA,
            'Referer': 'https://www.bilibili.com/',
        }
        session = None
        if requests is not None:
            session = requests.Session()
            self.apply_requests_cookies(session, cookie_mode)
            response = session.get(self.url, headers=headers, timeout=20)
            response.raise_for_status()
            html = response.text
        else:
            cookie_header = get_request_cookie_header(self.url, cookie_mode, self.parent().cookie_file)
            if cookie_header:
                headers['Cookie'] = cookie_header
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
            if requests is None and initial_state:
                raise ValueError('当前环境缺少 requests，无法继续补拉 B站播放数据')
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
            {'bvid': bvid, 'cid': cid, 'fnval': 4048, 'qn': 127, 'fourk': 1},
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

    def run_bilibili_webpage_sniff(self, cookie_mode, reason='412'):
        self.progress_signal.emit(self.get_bilibili_web_sniff_message(reason))
        self.available_formats = []
        self.subtitle_entries = []

        playinfo, initial_state = self.fetch_bilibili_page_data(cookie_mode)
        initial_state = initial_state or {}
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
        video_candidates = []

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
            video_url = video.get('baseUrl') or video.get('base_url') or video.get('url')
            if not video_url:
                continue

            height = video.get('height')
            if not height:
                continue
            resolution = f'{int(height)}p'
            format_id = f'bili-direct-video:{index}'
            codec_label, codec_priority = get_codec_label_and_priority(video_codec)
            if not codec_label:
                continue
            payload = {
                'type': 'bilibili_direct_video',
                'title': title,
                'video_url': video_url,
                'audio_url': preferred_audio['payload']['audio_url'] if preferred_audio else None,
                'video_ext': 'mp4',
                'audio_ext': 'm4a',
                'resolution': resolution,
                'codec_label': codec_label,
                'headers': {
                    'User-Agent': BILIBILI_WEB_UA,
                    'Referer': page_url,
                },
            }
            download_payloads[format_id] = payload
            video_candidates.append({
                'format_id': format_id,
                'resolution': resolution,
                'codec_label': codec_label,
                'codec_priority': codec_priority,
                'fps': video.get('frameRate') or video.get('frame_rate') or 0,
                'bandwidth': video.get('bandwidth') or 0,
                'filesize': video.get('size') or 0,
            })

        self.set_cookie_quality_warning('bilibili', cookie_mode, playinfo_data, video_candidates)

        for candidate in select_best_video_candidates(video_candidates):
            format_info = f"{candidate['resolution']}/{candidate['codec_label']}"

            try:
                if candidate.get('fps'):
                    format_info += f"/{int(round(float(candidate['fps'])))}fps"
            except Exception:
                pass

            size_label = format_size_from_bytes(candidate.get('filesize'))
            if size_label:
                format_info += f'/{size_label}'

            self.available_formats.append((candidate['format_id'], format_info))

        if not self.available_formats:
            return False, 'B站网页已打开，但没解析到可直连的视频或 AAC 音频格式', []

        self.direct_download_payloads = download_payloads
        self.available_formats.sort(key=lambda x: RESOLUTION_SORT_ORDER.get(x[1].split('/')[0], -1), reverse=True)
        return True, 'B站网页直连嗅探完成', self.available_formats

    def normalize_error_message(self, site, error_text):
        lowered = (error_text or '').lower()
        if site == 'bilibili' and ('http error 412' in lowered or 'precondition failed' in lowered):
            return 'B站接口返回 412，已尝试常规嗅探'
        if (
            'unsupported url' in lowered
            or 'no suitable extractor' in lowered
            or 'unsupported site' in lowered
            or 'is not a valid url' in lowered
        ):
            return '该链接不是 yt-dlp 支持的网站或链接类型'
        if 'sign in' in lowered or 'login' in lowered:
            return '目标站点需要登录态或 Cookies'
        if error_text:
            return error_text.strip().splitlines()[-1]
        return '嗅探失败'

    def run_preflight_checks(self, site):
        self.progress_signal.emit('正在检测目标网站是否可访问...')
        is_accessible, accessibility_message = check_site_accessibility(self.url)
        if not self.is_running:
            return False, '嗅探已取消'
        if not is_accessible:
            self.progress_signal.emit(f'{accessibility_message}，继续尝试 yt-dlp 嗅探...')

        if site in {'youtube', 'bilibili'}:
            return True, ''

        self.progress_signal.emit('正在检测链接是否受 yt-dlp 支持...')
        is_supported, support_message = check_ytdlp_url_support(self.parent().get_ytdlp_command(), self.url)
        if not self.is_running:
            return False, '嗅探已取消'
        if not is_supported:
            return False, support_message

        return True, ''

    def get_bilibili_web_sniff_message(self, reason):
        if reason == '412':
            message = 'yt-dlp 被 B站 412 拦截，正在尝试网页直连嗅探...'
        else:
            message = '常规嗅探失败，正在尝试 B站网页直连嗅探...'

        if requests is None:
            message += '\n当前环境缺少 requests，网页/API 回退能力受限。'
        return message

    def run_sniff(self, cookie_mode, allow_bilibili_web_fallback=True):
        self.available_formats = []
        self.subtitle_entries = []
        self.cookie_warning_message = ''
        self.direct_download_payloads = {}
        self.format_metadata = {}
        site = detect_site(self.url)
        is_playlist = site == 'youtube' and is_youtube_playlist_url(self.url)
        process = subprocess.Popen(
            self.build_playlist_sniff_cmd(cookie_mode) if is_playlist else self.build_sniff_cmd(cookie_mode),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        self.process = process
        try:
            output, error_output = process.communicate()
        finally:
            self.process = None

        if not self.is_running:
            terminate_process_tree(process)
            return False, '嗅探已取消', []

        if process.returncode == 0:
            info = self.parse_info_json(output)
            if not info:
                return False, '嗅探返回了无法解析的 JSON', []

            if is_playlist:
                if not self.populate_youtube_playlist_from_info(info):
                    return False, '未找到 YouTube 列表中的可下载视频', []
            else:
                self.populate_formats_from_info(info)
            if not self.available_formats and not self.subtitle_entries:
                return False, '未找到可用的视频格式或字幕', []

            self.available_formats.sort(
                key=lambda x: RESOLUTION_SORT_ORDER.get(x[1].split('/')[0], -1),
                reverse=True,
            )
            combined_formats = self.available_formats + self.subtitle_entries
            return True, '嗅探完成', combined_formats

        combined_error = '\n'.join(part for part in [error_output, output] if part).strip()
        if allow_bilibili_web_fallback and site == 'bilibili' and ('HTTP Error 412' in combined_error or 'Precondition Failed' in combined_error):
            return self.run_bilibili_webpage_sniff(cookie_mode, reason='412')

        return False, self.normalize_error_message(site, combined_error), []

    def run(self):
        try:
            self.cookie_warning_message = ''
            site = detect_site(self.url)
            preflight_success, preflight_message = self.run_preflight_checks(site)
            if not preflight_success:
                self.finished_signal.emit(False, preflight_message, [], 'none')
                return
            cookie_modes, has_manual_cookie = self.build_cookie_modes(site)

            last_message = '嗅探失败'
            for index, cookie_mode in enumerate(cookie_modes):
                if cookie_mode.startswith('browser:'):
                    browser_name = cookie_mode.split(':', 1)[1].capitalize()
                    if index == 0:
                        self.progress_signal.emit(f'正在尝试调用 {browser_name} Cookies...')
                    else:
                        self.progress_signal.emit(f'普通嗅探失败，正在尝试调用 {browser_name} Cookies...')
                success, message, formats = self.run_sniff(
                    cookie_mode,
                    allow_bilibili_web_fallback=(site != 'bilibili'),
                )
                if success:
                    self.finished_signal.emit(True, message, formats, cookie_mode)
                    return
                last_message = message
                if not self.is_running:
                    self.finished_signal.emit(False, '嗅探已取消', [], cookie_mode)
                    return

            if site == 'bilibili':
                fallback_cookie_mode = choose_bilibili_web_fallback_cookie_mode(cookie_modes)
                success, message, formats = self.run_bilibili_webpage_sniff(fallback_cookie_mode, reason='general')
                if success:
                    self.finished_signal.emit(True, message, formats, fallback_cookie_mode)
                    return
                last_message = message

            if site == 'youtube' and not has_manual_cookie:
                self.finished_signal.emit(False, '嗅探失败，需要浏览器登录或者手动填写Cookie（推荐火狐登录成功率更高）。', [], 'show_cookie_input')
                return

            if site == 'bilibili' and not has_manual_cookie:
                self.finished_signal.emit(False, '嗅探失败，需要浏览器登录或者手动填写Cookie（推荐火狐登录成功率更高）。', [], 'show_cookie_input')
                return

            self.finished_signal.emit(False, last_message, [], 'none')
        except Exception as e:
            self.finished_signal.emit(False, f'嗅探时发生错误：{str(e)}', [], 'none')

    def stop(self):
        self.is_running = False
        terminate_process_tree(self.process)

class DownloadThread(QThread):
    progress_signal = pyqtSignal(str)
    finished_signal = pyqtSignal(bool, str)

    def __init__(self, url, format_id, parent=None):
        super().__init__(parent)
        self.url = url
        self.format_id = format_id
        self.is_running = True
        self.process = None
        self.current_response = None

    def finalize_downloaded_file(self, downloaded_file):
        if not downloaded_file or not os.path.exists(downloaded_file):
            return None

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
            format_info = self.parent().get_format_label(self.format_id)
            resolution = format_info.split('/')[0] if format_info else ''
            if resolution:
                new_name = f'{base_name}.{resolution}{ext}'
            else:
                new_name = downloaded_file
        else:
            new_name = downloaded_file

        if new_name == downloaded_file:
            return downloaded_file

        target_path = ensure_unique_path(new_name)
        try:
            os.replace(downloaded_file, target_path)
            return target_path
        except OSError as exc:
            raise RuntimeError(f'下载完成但重命名失败：{str(exc)}')

    def cleanup_ytdlp_partial_files(self, downloaded_file):
        if not downloaded_file:
            return
        for partial_path in (f'{downloaded_file}.part', f'{downloaded_file}.ytdl'):
            try:
                if os.path.exists(partial_path):
                    os.remove(partial_path)
            except Exception:
                pass

    def download_url_to_file(self, url, target_path, headers):
        request = urllib.request.Request(url, headers=headers or {})
        try:
            with urllib.request.urlopen(request, timeout=30) as response, open(target_path, 'wb') as output_file:
                self.current_response = response
                total = response.headers.get('Content-Length')
                total_bytes = int(total) if total and total.isdigit() else 0
                downloaded = 0
                last_reported_mb = -1

                while self.is_running:
                    try:
                        chunk = response.read(1024 * 256)
                    except Exception:
                        if not self.is_running:
                            raise RuntimeError('下载已取消')
                        raise
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
                if total_bytes and downloaded != total_bytes:
                    raise RuntimeError('直连下载不完整，请重试')
        finally:
            self.current_response = None

    def run_merge_process(self, cmd):
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
        self.process = process
        output_lines = deque(maxlen=80)
        try:
            while self.is_running:
                line = process.stdout.readline()
                if not line:
                    break
                line = line.strip()
                output_lines.append(line)
                if line:
                    self.progress_signal.emit(line)

            if not self.is_running and process.poll() is None:
                terminate_process_tree(process, timeout=5)
                raise RuntimeError('下载已取消')

            process.wait()
            if process.returncode != 0:
                raise RuntimeError(extract_process_error_message(output_lines, 'FFmpeg 合并失败'))
        finally:
            if process.poll() is None:
                terminate_process_tree(process, timeout=2)
            self.process = None

    def run_direct_download(self, direct_payload):
        output_dir = self.parent().get_output_dir()
        os.makedirs(output_dir, exist_ok=True)
        title = sanitize_filename(direct_payload.get('title') or 'bilibili_video')
        temp_paths = []
        final_path = None
        success = False

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
                final_path = self.finalize_downloaded_file(final_path) or final_path
                success = True
                self.finished_signal.emit(True, f'下载完成：{final_path}')
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
            self.run_merge_process(ffmpeg_cmd)

            final_path = self.finalize_downloaded_file(final_path) or final_path
            success = True
            self.finished_signal.emit(True, f'下载完成：{final_path}')
        finally:
            if not success and final_path and os.path.exists(final_path):
                try:
                    os.remove(final_path)
                except Exception:
                    pass
            for temp_path in temp_paths:
                try:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                except Exception:
                    pass

    def run_ytdlp_download(self):
        format_metadata = self.parent().get_format_metadata(self.format_id)
        is_subtitle = self.format_id.startswith('subtitle:')
        is_playlist = format_metadata.get('kind') == 'playlist'
        is_audio_only = format_metadata.get('kind') == 'audio'
        is_progressive_video = format_metadata.get('kind') == 'video' and format_metadata.get('has_audio')
        os.makedirs(self.parent().get_output_dir(), exist_ok=True)
        if is_playlist:
            playlist_title = sanitize_filename(format_metadata.get('playlist_title') or 'YouTube 视频列表')
            playlist_mode = format_metadata.get('mode') or 'h264'
            playlist_mode_label = 'H.264优先' if playlist_mode == 'h264' else '最佳兼容'
            playlist_format = (
                'bv*[ext=mp4][vcodec^=avc]+ba[ext=m4a]/b[ext=mp4][vcodec^=avc]'
                if playlist_mode == 'h264'
                else 'bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/b'
            )
            cmd = [
                self.parent().get_ytdlp_command(),
                '--yes-playlist',
                '--ignore-errors',
                '-f',
                playlist_format,
                '--merge-output-format',
                'mp4',
                '-o',
                f'{playlist_title}/%(playlist_index)03d - %(title)s.%(ext)s',
            ]
        elif is_subtitle:
            _, subtitle_lang, subtitle_mode = self.format_id.split(':', 2)
            cmd = [self.parent().get_ytdlp_command()]
            if subtitle_mode == 'auto':
                cmd.append('--write-auto-sub')
            else:
                cmd.append('--write-sub')
            cmd.extend(['--sub-lang', subtitle_lang, '--convert-subs', 'srt', '--skip-download'])
        elif is_audio_only or is_progressive_video:
            cmd = [self.parent().get_ytdlp_command(), '-f', self.format_id]
        else:
            cmd = [self.parent().get_ytdlp_command(), '-f', f'{self.format_id}+bestaudio[ext=m4a]']

        cmd.extend(get_cookie_args(self.parent().cookie_mode, self.parent().cookie_file))
        cmd.extend(['-P', self.parent().get_output_dir()])

        if is_playlist:
            cmd.extend([self.url, '--newline'])
        elif is_subtitle:
            cmd.extend([self.url, '--newline'])
        elif is_audio_only or is_progressive_video:
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
        recent_lines = deque(maxlen=40)

        try:
            while self.is_running:
                line = process.stdout.readline()
                if not line:
                    break
                line = line.strip()
                recent_lines.append(line)
                self.progress_signal.emit(line)
                if '[download] Destination:' in line:
                    downloaded_file = line.split(':', 1)[1].strip()
                elif '[Merger] Merging formats into ' in line:
                    downloaded_file = line.split('into ', 1)[1].strip().strip('"')
                elif '[ExtractAudio] Destination:' in line:
                    downloaded_file = line.split(':', 1)[1].strip()

            if not self.is_running:
                terminate_process_tree(process, timeout=5)
                self.cleanup_ytdlp_partial_files(downloaded_file)
                self.finished_signal.emit(False, '下载已取消')
                return

            process.wait()
            if process.returncode == 0:
                if is_playlist:
                    self.finished_signal.emit(True, f'列表下载完成（{playlist_mode_label}）：{os.path.join(self.parent().get_output_dir(), playlist_title)}')
                    return

                final_path = self.finalize_downloaded_file(downloaded_file) or downloaded_file
                if final_path:
                    message = '字幕下载完成' if is_subtitle else '下载完成'
                    self.finished_signal.emit(True, f'{message}：{final_path}')
                else:
                    self.finished_signal.emit(True, '字幕下载完成' if is_subtitle else '下载完成')
            else:
                self.cleanup_ytdlp_partial_files(downloaded_file)
                if is_playlist:
                    default_message = f'列表下载失败（{playlist_mode_label}）'
                else:
                    default_message = '字幕下载失败' if is_subtitle else '下载失败'
                self.finished_signal.emit(False, extract_process_error_message(recent_lines, default_message))
        finally:
            if process.poll() is None:
                terminate_process_tree(process, timeout=2)
            self.process = None

    def run(self):
        try:
            direct_payload = self.parent().get_direct_download_payload(self.format_id)
            if direct_payload:
                self.run_direct_download(direct_payload)
            else:
                self.run_ytdlp_download()
        except Exception as e:
            if '已取消' in str(e):
                self.finished_signal.emit(False, '下载已取消')
            else:
                self.finished_signal.emit(False, f'发生错误：{str(e)}')

    def stop(self):
        self.is_running = False
        if self.current_response is not None:
            try:
                self.current_response.close()
            except Exception:
                pass
        terminate_process_tree(self.process)

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

    def download_file(self, download_url, target_path, timeout=30):
        request = urllib.request.Request(download_url, headers={'User-Agent': 'yt_dlp_gui'})
        with urllib.request.urlopen(request, timeout=timeout) as response, open(target_path, 'wb') as output_file:
            total = response.headers.get('Content-Length')
            total_bytes = int(total) if total and total.isdigit() else 0
            downloaded = 0

            while True:
                chunk = response.read(1024 * 256)
                if not chunk:
                    break
                output_file.write(chunk)
                downloaded += len(chunk)

            if total_bytes and downloaded != total_bytes:
                raise RuntimeError('yt-dlp 更新下载不完整，请重试')

    def run(self):
        download_url = 'https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe'
        temp_file = None
        temp_path = None
        try:
            local_version = self.get_local_version()
            latest_version = self.get_latest_version()
            target_exists = os.path.exists(self.target_path)
            if target_exists and local_version and latest_version and local_version == latest_version:
                self.finished_signal.emit(True, f'无需更新，已经是最新版啦：{local_version}')
                return

            target_dir = os.path.dirname(self.target_path)
            os.makedirs(target_dir, exist_ok=True)
            temp_file = tempfile.NamedTemporaryFile(
                delete=False,
                dir=target_dir,
                prefix='yt-dlp-',
                suffix='.download',
            )
            temp_path = temp_file.name
            temp_file.close()
            self.download_file(download_url, temp_path)
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
        self.setWindowTitle('yt_dlp_gui v1.0.7 @少昊金天氏')
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
        cookie_fd, cookie_path = tempfile.mkstemp(prefix='yt_dlp_gui_cookie_', suffix='.txt')
        os.close(cookie_fd)
        try:
            os.remove(cookie_path)
        except OSError:
            pass
        self.cookie_file = cookie_path
        self.ytdlp_path = resolve_ytdlp_command()
        self.ffmpeg_path = resolve_ffmpeg_command()
        self.output_dir = get_default_output_dir()
        self.cookie_mode = 'none'
        self.manual_cookie_enabled = False
        self.manual_cookie_site = None
        self.manual_cookie_hostname = None
        self.format_label_map = {}
        self.format_metadata_map = {}
        self.direct_download_map = {}
        self.is_sniffing = False
        self.pending_url_change = False
        self.url_change_timer = QTimer(self)
        self.url_change_timer.setSingleShot(True)
        self.url_change_timer.timeout.connect(self.handle_url_change)

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
        self.url_input.textChanged.connect(self.on_url_text_changed)
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

        output_layout = QHBoxLayout()
        output_layout.setContentsMargins(10, 10, 10, 0)
        output_label = QLabel('输出地址：')
        output_label.setFixedWidth(60)
        self.output_path_input = OutputPathLineEdit()
        self.output_path_input.setReadOnly(True)
        self.output_path_input.setText(self.get_output_dir())
        self.output_path_input.choose_dir_signal.connect(self.choose_output_dir)
        self.output_path_input.open_dir_signal.connect(self.open_output_dir)
        output_layout.addWidget(output_label)
        output_layout.addWidget(self.output_path_input)
        layout.addLayout(output_layout)

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
        self.progress_text = QLabel(
            '准备就绪！\n'
            '使用方法：粘贴视频链接后点击“开始嗅探”，选择清晰度后再点“开始下载”。\n'
            '输出地址：左键选择输出目录，右键打开输出目录。\n'
            '若下载失败，可先火狐浏览器登录对应网站或手动填写Cookie。'
        )
        layout.addWidget(self.progress_text)

    def get_ytdlp_command(self):
        self.ytdlp_path = resolve_ytdlp_command()
        return self.ytdlp_path

    def get_ffmpeg_command(self):
        self.ffmpeg_path = resolve_ffmpeg_command()
        return self.ffmpeg_path

    def has_ffmpeg(self):
        ffmpeg_cmd = self.get_ffmpeg_command()
        return bool(ffmpeg_cmd and os.path.exists(ffmpeg_cmd)) or bool(shutil.which('ffmpeg.exe') or shutil.which('ffmpeg'))

    def get_output_dir(self):
        return self.output_dir

    def set_output_dir(self, output_dir):
        if not output_dir:
            return
        self.output_dir = output_dir
        self.output_path_input.setText(output_dir)
        try:
            save_output_dir(output_dir)
        except Exception:
            pass

    def choose_output_dir(self):
        selected_dir = QFileDialog.getExistingDirectory(
            self,
            '选择输出目录',
            self.get_output_dir(),
        )
        if selected_dir:
            self.set_output_dir(selected_dir)

    def open_output_dir(self):
        output_dir = self.get_output_dir()
        if not output_dir or not os.path.isdir(output_dir):
            QMessageBox.warning(self, '错误', '输出目录不存在，请先重新选择。')
            return
        try:
            os.startfile(output_dir)
        except Exception as e:
            QMessageBox.warning(self, '错误', f'打开输出目录失败：{str(e)}')

    def set_direct_download_payloads(self, payloads):
        self.direct_download_map = payloads or {}

    def get_direct_download_payload(self, format_id):
        return self.direct_download_map.get(format_id)

    def get_format_label(self, format_id):
        return self.format_label_map.get(format_id, '')

    def get_format_metadata(self, format_id):
        return self.format_metadata_map.get(format_id, {})

    def clear_format_state(self):
        self.format_combo.clear()
        self.format_label_map.clear()
        self.format_metadata_map.clear()
        self.set_direct_download_payloads({})

    def is_cancel_message(self, message):
        return '已取消' in str(message or '')

    def reset_url_dependent_state(self, set_ready_text=True):
        self.clear_format_state()
        self.cookie_mode = 'none'
        self.cookie_container.hide()
        self.download_button.setText('开始嗅探')
        if set_ready_text:
            self.progress_text.setText('准备就绪')

    def has_manual_cookie(self):
        has_file = bool(self.cookie_file and os.path.exists(self.cookie_file))
        if not has_file:
            self.manual_cookie_enabled = False
        return bool(self.manual_cookie_enabled and has_file)

    def has_manual_cookie_for_url(self, url):
        if not self.has_manual_cookie():
            return False
        site = detect_site(url)
        hostname = extract_url_hostname(url)
        if self.manual_cookie_site:
            return self.manual_cookie_site == site
        if self.manual_cookie_hostname:
            return host_matches(hostname, self.manual_cookie_hostname)
        return True

    def cleanup_manual_cookie_file(self):
        if self.cookie_file and os.path.exists(self.cookie_file):
            try:
                os.remove(self.cookie_file)
            except OSError:
                pass
        self.manual_cookie_enabled = False
        self.manual_cookie_site = None
        self.manual_cookie_hostname = None

    def stop_worker_thread(self, thread, timeout_ms=1000):
        if not thread or not thread.isRunning():
            return True
        stop_method = getattr(thread, 'stop', None)
        if callable(stop_method):
            stop_method()
        return thread.wait(timeout_ms)

    def has_active_transfer(self):
        return bool(
            (self.sniff_thread and self.sniff_thread.isRunning())
            or (self.download_thread and self.download_thread.isRunning())
        )

    def update_ytdlp(self):
        if self.update_thread and self.update_thread.isRunning():
            QMessageBox.warning(self, '提示', 'yt-dlp 正在更新中，请稍后再试。')
            return
        if self.has_active_transfer():
            QMessageBox.warning(self, '提示', '请等待当前嗅探或下载完成后再更新 yt-dlp。')
            return
        target_path = get_managed_ytdlp_path()
        self.update_ytdlp_button.setEnabled(False)
        self.download_button.setEnabled(False)
        self.progress_text.setText('正在更新 yt-dlp...')
        self.update_thread = UpdateYtDlpThread(target_path, self.get_ytdlp_command(), self)
        self.update_thread.finished_signal.connect(self.update_ytdlp_finished)
        self.update_thread.start()

    def update_ytdlp_finished(self, success, message):
        sender_thread = self.sender()
        if isinstance(sender_thread, UpdateYtDlpThread) and sender_thread is not self.update_thread:
            return
        self.update_thread = None
        self.update_ytdlp_button.setEnabled(True)
        self.download_button.setEnabled(True)
        self.get_ytdlp_command()
        self.progress_text.setText(message)
        if success:
            QMessageBox.information(self, '成功', message)
        else:
            QMessageBox.warning(self, '错误', message)

    def start_download(self):
        if self.update_thread and self.update_thread.isRunning():
            QMessageBox.warning(self, '提示', 'yt-dlp 正在更新中，请等待更新完成后再试。')
            return
        if self.url_change_timer.isActive():
            self.url_change_timer.stop()
            self.pending_url_change = False
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, '警告', '请输入视频URL')
            return
        if not is_valid_video_url(url):
            QMessageBox.warning(self, '警告', '请输入有效的视频URL（需包含 http:// 或 https://）')
            self.progress_text.setText('请输入有效的视频URL')
            return
        non_video_message = detect_known_non_video_page(url)
        if non_video_message:
            QMessageBox.warning(self, '错误', non_video_message)
            self.progress_text.setText('该链接不是可下载的视频页面')
            return
            
        # 如果没有可用的视频格式，需要先进行嗅探
        if not self.format_combo.count():
            if not self.stop_worker_thread(self.sniff_thread, 2000):
                QMessageBox.warning(self, '提示', '上一次嗅探仍在结束，请稍后再试。')
                return
            self.clear_format_state()
            
            # 更改按钮文本和状态
            self.download_button.setText('正在嗅探中')
            self.download_button.setEnabled(False)  # 设置按钮为不可用状态
            self.is_sniffing = True
            self.progress_text.setText('正在嗅探可下载的视频、音频和字幕...')
            
            # 启动嗅探线程
            self.sniff_thread = SniffThread(url, self)
            self.sniff_thread.progress_signal.connect(self.update_progress)
            self.sniff_thread.finished_signal.connect(self.sniff_finished)
            self.sniff_thread.start()
            return
        
        # 如果已有视频格式，执行下载操作
        if not self.format_combo.currentText():
            QMessageBox.warning(self, '警告', '请选择视频格式')
            return

        current_index = self.format_combo.currentIndex()
        format_id = self.format_combo.itemData(current_index)
        if not format_id:
            QMessageBox.warning(self, '警告', '当前格式无效，请重新嗅探')
            return

        direct_payload = self.get_direct_download_payload(format_id)
        format_metadata = self.get_format_metadata(format_id)
        needs_ffmpeg = (
            not format_id.startswith('subtitle:')
            and not (direct_payload and direct_payload.get('type') == 'bilibili_direct_audio')
            and format_metadata.get('kind') != 'audio'
            and not (format_metadata.get('kind') == 'video' and format_metadata.get('has_audio'))
        )
        if needs_ffmpeg and not self.has_ffmpeg():
            if format_metadata.get('kind') == 'playlist':
                QMessageBox.warning(self, '错误', '列表下载需要 FFmpeg 合并音视频。请把 ffmpeg.exe 放到程序根目录，或安装 FFmpeg 并加入 PATH。')
                self.progress_text.setText('缺少 FFmpeg，无法下载 YouTube 列表')
            else:
                QMessageBox.warning(self, '错误', '未找到 FFmpeg。请把 ffmpeg.exe 放到程序根目录，或安装 FFmpeg 并加入 PATH。')
                self.progress_text.setText('缺少 FFmpeg，无法合并视频和音频')
            return
        
        # 停止当前下载线程（如果有）
        if not self.stop_worker_thread(self.download_thread, 2000):
            QMessageBox.warning(self, '提示', '上一次下载仍在结束，请稍后再试。')
            return

        self.download_button.setText('正在下载中')
        self.download_button.setEnabled(False)  # 设置按钮为不可用状态
        self.download_thread = DownloadThread(url, format_id, self)
        self.progress_text.setText('正在下载中...')
        self.download_thread.progress_signal.connect(self.update_progress)
        self.download_thread.finished_signal.connect(self.download_finished)
        self.download_thread.start()

    def update_progress(self, text):
        sender_thread = self.sender()
        if isinstance(sender_thread, SniffThread) and sender_thread is not self.sniff_thread:
            return
        if isinstance(sender_thread, DownloadThread) and sender_thread is not self.download_thread:
            return
        if self.pending_url_change:
            return
        self.progress_text.setText(text)

    def sniff_finished(self, success, message, formats, cookie_mode):
        sender_thread = self.sender()
        if isinstance(sender_thread, SniffThread) and sender_thread is not self.sniff_thread:
            return
        if self.pending_url_change:
            return
        self.is_sniffing = False
        self.sniff_thread = None
        self.download_button.setText('开始嗅探')
        self.download_button.setEnabled(True)  # 恢复按钮为可用状态
        cookie_warning_message = getattr(sender_thread, 'cookie_warning_message', '')
        direct_download_payloads = getattr(sender_thread, 'direct_download_payloads', {})
        
        if success and formats:
            self.cookie_mode = cookie_mode
            self.cookie_container.hide()
            self.progress_text.setText('视频/字幕嗅探完成')
            # 清空并更新格式选择框
            self.format_combo.clear()
            self.format_label_map.clear()
            self.format_metadata_map.clear()
            self.set_direct_download_payloads(direct_download_payloads)
            self.format_metadata_map.update(getattr(sender_thread, 'format_metadata', {}))
            
            for format_id, format_label in formats:
                self.format_combo.addItem(format_label, format_id)
                self.format_label_map[format_id] = format_label
            
            # 自动选择第一个格式
            if self.format_combo.count() > 0:
                self.format_combo.setCurrentIndex(0)
                # 更改按钮文本为开始下载
                self.download_button.setText('开始下载')

            if cookie_warning_message:
                self.cookie_container.show()
                QMessageBox.warning(self, '提示', cookie_warning_message)
        else:
            # 嗅探失败时重置状态
            self.download_button.setText('开始嗅探')
            self.progress_text.setText(message if self.is_cancel_message(message) else '准备就绪')
            self.clear_format_state()
            
            if cookie_mode == 'show_cookie_input':
                self.cookie_container.show()
                self.cookie_mode = 'none'
                QMessageBox.warning(self, '错误', message)
            elif self.is_cancel_message(message):
                return
            elif not success:
                retry_box = QMessageBox(self)
                retry_box.setWindowTitle('错误')
                retry_box.setText(message)
                retry_box.setIcon(QMessageBox.Icon.Warning)
                retry_button = retry_box.addButton('再试一次', QMessageBox.ButtonRole.AcceptRole)
                retry_box.addButton('取消', QMessageBox.ButtonRole.RejectRole)
                retry_box.exec()
                if retry_box.clickedButton() is retry_button:
                    QTimer.singleShot(0, self.start_download)
            elif not formats:
                QMessageBox.warning(self, '警告', '未找到可下载的视频格式或字幕')

    def download_finished(self, success, message):
        sender_thread = self.sender()
        if isinstance(sender_thread, DownloadThread) and sender_thread is not self.download_thread:
            return
        if self.pending_url_change:
            return
        self.download_thread = None
        self.download_button.setEnabled(True)  # 恢复按钮为可用状态
        self.is_sniffing = False
        self.progress_text.setText(message)
        self.download_button.setText('开始下载')  # 无论成功失败都显示"开始下载"
        if success:
            QMessageBox.information(self, '成功', message)
        elif self.is_cancel_message(message):
            return
        else:
            retry_box = QMessageBox(self)
            retry_box.setWindowTitle('错误')
            retry_box.setText(message)
            retry_box.setIcon(QMessageBox.Icon.Warning)
            retry_button = retry_box.addButton('再试一次', QMessageBox.ButtonRole.AcceptRole)
            retry_box.addButton('取消', QMessageBox.ButtonRole.RejectRole)
            retry_box.exec()
            if retry_box.clickedButton() is retry_button:
                QTimer.singleShot(0, self.start_download)

    def on_url_text_changed(self):
        self.cookie_container.hide()
        self.pending_url_change = True
        self.reset_url_dependent_state(set_ready_text=not self.has_active_transfer())
        if self.has_active_transfer():
            self.progress_text.setText('链接已变更，正在停止当前任务...')
        self.download_button.setEnabled(True)
        self.is_sniffing = False
        self.url_change_timer.start(250)

    def save_cookie(self):
        try:
            cookie_content = self.cookie_input.toPlainText().strip()
            if not cookie_content:
                QMessageBox.warning(self, '警告', '请输入Cookies内容')
                return
            
            with open(self.cookie_file, 'w', encoding='utf-8') as f:
                f.write(cookie_content)
            load_cookie_jar_from_file(self.cookie_file)
            
            self.manual_cookie_enabled = True
            current_url = self.url_input.text().strip()
            site = detect_site(current_url)
            hostname = extract_url_hostname(current_url)
            self.manual_cookie_site = site if site in {'youtube', 'bilibili'} else None
            self.manual_cookie_hostname = None if self.manual_cookie_site else (hostname or None)
            self.cookie_mode = 'file'
            self.cookie_container.hide()
            QMessageBox.information(self, '成功', 'Cookies已更新，请重新点击开始嗅探。')
            self.cookie_input.clear()
        except Exception as e:
            self.cleanup_manual_cookie_file()
            QMessageBox.warning(self, '警告', f'Cookies更新失败：{str(e)}')

    def show_context_menu(self, pos):
        sender = self.sender()

        if sender is self.url_input:
            if self.url_change_timer.isActive():
                self.url_change_timer.stop()
                self.pending_url_change = False
            sender.clear()
            sender.paste()
            sender.update()
            QApplication.processEvents()
            QTimer.singleShot(120, self.start_download)
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
        if self.update_thread and self.update_thread.isRunning():
            QMessageBox.warning(self, '提示', 'yt-dlp 正在更新中，请等待更新完成后再退出。')
            event.ignore()
            return
        if (self.download_thread and self.download_thread.isRunning()) or (self.sniff_thread and self.sniff_thread.isRunning()):
            operation = '嗅探' if self.is_sniffing else '下载'
            reply = QMessageBox.question(self, '确认', f'{operation}正在进行中，确定要退出吗？',
                                       QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            if reply == QMessageBox.StandardButton.Yes:
                # 设置最大等待时间（毫秒）
                max_wait_time = 3000
                
                # 终止下载线程
                download_stopped = self.stop_worker_thread(self.download_thread, max_wait_time)
                
                # 终止嗅探线程
                sniff_stopped = self.stop_worker_thread(self.sniff_thread, max_wait_time)

                if not download_stopped or not sniff_stopped:
                    QMessageBox.warning(self, '提示', '当前任务仍在结束，请稍后再试退出。')
                    event.ignore()
                    return

                event.accept()
                self.cleanup_manual_cookie_file()
            else:
                event.ignore()
                return
        else:
            event.accept()
            self.cleanup_manual_cookie_file()

    def handle_url_change(self):
        if not self.pending_url_change:
            return
        self.pending_url_change = False

        sniff_thread = self.sniff_thread
        download_thread = self.download_thread
        self.sniff_thread = None
        self.download_thread = None

        if sniff_thread and sniff_thread.isRunning():
            self.stop_worker_thread(sniff_thread, 1000)

        if download_thread and download_thread.isRunning():
            self.stop_worker_thread(download_thread, 1000)

        self.reset_url_dependent_state(set_ready_text=True)
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
                padding: 5px 0px;
            }
            QMenu::item {
                padding: 5px 20px;
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
        """)
        
        runtime_dir = get_runtime_dir()
        path_entries = [runtime_dir]
        dll_dir = os.path.join(runtime_dir, 'dll')
        try:
            os.makedirs(dll_dir, exist_ok=True)
            path_entries.append(dll_dir)
        except OSError:
            pass

        # 优先让程序根目录和 dll 目录参与 PATH，便于找到 ffmpeg.exe / 相关 DLL
        os.environ['PATH'] = os.pathsep.join(path_entries + [os.environ.get('PATH', '')])

        window = MainWindow()
        window.show()
        sys.exit(app.exec())
    except Exception as e:
        error_msg = f'程序启动失败：{str(e)}'
        QMessageBox.critical(None, '错误', error_msg)
        return

if __name__ == '__main__':
    main()
