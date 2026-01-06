# -*- coding: utf-8 -*-
"""
YouTube 트랜스크립트 다운로더 (v4.4 - 한국어 우선 + SRT 지원)

방식:
1. API: youtube-transcript-api 사용 (빠름, Rate Limit 취약)
2. yt-dlp: yt-dlp 사용 (느림, 안정적)
3. 자동: 성공한 방식 우선, 실패 시 다른 방식 시도

v4.4 변경사항:
- ⭐ 한국어 자막 최우선 선택 (독일어 등 타 언어보다 우선)
- ⭐ TranscriptFormatter 클래스 추가 (SRT/VTT/TXT 형식 지원)
- ⭐ _select_best_subtitle_file() 메서드 추가
- ⭐ yt-dlp sub_lang 한국어 최우선으로 변경

v4.3 변경사항 (속도 최적화):
- ⭐ 성공한 방식 기억 및 우선 사용
- ⭐ 연속 3회 실패한 방식 자동 비활성화
- ⭐ 딜레이 시간 대폭 감소 (5-10초 → 1-3초)
- ⭐ Rate Limit 시 즉시 스킵 (긴 대기 없음)
- 영상 1개 평균 20초 → 3초로 단축
"""

import os
import json
import time
import subprocess
import tempfile
import re
import csv
import zipfile
import random
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Callable, Tuple
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict

# youtube-transcript-api
try:
    from youtube_transcript_api import YouTubeTranscriptApi
    from youtube_transcript_api._errors import (
        TranscriptsDisabled,
        NoTranscriptFound,
        VideoUnavailable,
        NoTranscriptAvailable
    )
    API_AVAILABLE = True
except ImportError:
    API_AVAILABLE = False
    print("[Transcript] youtube-transcript-api가 설치되지 않았습니다.")


# ═══════════════════════════════════════════════════════════════════
# yt-dlp 버전 관리자
# ═══════════════════════════════════════════════════════════════════

class YtdlpManager:
    """yt-dlp 버전 관리, 자동 업데이트 및 JS 런타임 관리"""

    # 최소 필요 버전 (nsig 수정 포함)
    MIN_VERSION = "2025.12.01"

    # 🔴 v2.5: JS 런타임 캐시
    _js_runtime: Optional[str] = None
    _js_runtime_checked: bool = False

    @classmethod
    def get_js_runtime(cls) -> Optional[str]:
        """
        사용 가능한 JavaScript 런타임 확인

        yt-dlp 2025.12+ 버전은 JS 런타임이 필요함.
        우선순위: deno > nodejs

        Returns:
            "deno", "nodejs", 또는 None
        """
        if cls._js_runtime_checked:
            return cls._js_runtime

        cls._js_runtime_checked = True

        # Deno 확인 (우선)
        try:
            result = subprocess.run(
                ["deno", "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                version = result.stdout.split('\n')[0].strip()
                print(f"[yt-dlp] ✅ Deno 런타임 발견: {version}")
                cls._js_runtime = "deno"
                return cls._js_runtime
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        # Node.js 확인 (대안)
        try:
            result = subprocess.run(
                ["node", "--version"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                version = result.stdout.strip()
                print(f"[yt-dlp] ✅ Node.js 런타임 발견: {version}")
                cls._js_runtime = "nodejs"
                return cls._js_runtime
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

        # 런타임 없음
        print("[yt-dlp] ⚠️ JavaScript 런타임(deno/nodejs)이 설치되지 않음")
        print("[yt-dlp]   일부 YouTube 기능이 제한될 수 있습니다.")
        print("[yt-dlp]   설치 권장: https://deno.land/ (PowerShell: irm https://deno.land/install.ps1 | iex)")
        cls._js_runtime = None
        return None

    @classmethod
    def has_js_runtime(cls) -> bool:
        """JS 런타임 설치 여부 확인"""
        return cls.get_js_runtime() is not None

    @classmethod
    def get_version(cls) -> Optional[str]:
        """현재 yt-dlp 버전 확인"""
        try:
            result = subprocess.run(
                ["yt-dlp", "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.stdout.strip() if result.returncode == 0 else None
        except Exception as e:
            print(f"[yt-dlp] 버전 확인 실패: {e}")
            return None

    @classmethod
    def is_outdated(cls) -> bool:
        """버전이 오래되었는지 확인"""
        current = cls.get_version()
        if not current:
            return True

        try:
            # 버전 비교 (YYYY.MM.DD 형식)
            current_date = datetime.strptime(current, "%Y.%m.%d")
            min_date = datetime.strptime(cls.MIN_VERSION, "%Y.%m.%d")
            return current_date < min_date
        except ValueError:
            # 파싱 실패 시 업데이트 권장
            return True

    @classmethod
    def update(cls) -> bool:
        """yt-dlp 업데이트"""
        import sys

        print("[yt-dlp] 업데이트 시작...")

        methods = [
            # 방법 1: pip upgrade
            [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"],
            # 방법 2: yt-dlp 자체 업데이트
            ["yt-dlp", "-U"],
        ]

        for cmd in methods:
            try:
                print(f"[yt-dlp] 시도: {' '.join(cmd[:4])}...")
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=120
                )

                if result.returncode == 0:
                    new_version = cls.get_version()
                    print(f"[yt-dlp] ✅ 업데이트 성공: {new_version}")
                    return True

            except Exception as e:
                print(f"[yt-dlp] 방법 실패: {e}")
                continue

        print("[yt-dlp] ❌ 모든 업데이트 방법 실패")
        return False

    @classmethod
    def ensure_updated(cls) -> bool:
        """업데이트 필요 시 자동 업데이트"""
        current = cls.get_version()
        print(f"[yt-dlp] 현재 버전: {current}")

        if cls.is_outdated():
            print(f"[yt-dlp] ⚠️ 버전이 오래됨 (최소 필요: {cls.MIN_VERSION})")
            return cls.update()

        print(f"[yt-dlp] ✅ 버전 OK")
        return True


class DownloadMethod(Enum):
    """다운로드 방식"""
    API = "api"           # youtube-transcript-api
    YTDLP = "yt-dlp"      # yt-dlp
    AUTO = "auto"         # 자동 (성공한 방식 우선)


@dataclass
class MethodStats:
    """⭐ v4.3: 다운로드 방식별 통계 추적"""
    success_count: int = 0
    fail_count: int = 0
    consecutive_fails: int = 0
    last_success_time: float = 0.0
    disabled: bool = False

    def record_success(self):
        """성공 기록"""
        self.success_count += 1
        self.consecutive_fails = 0
        self.last_success_time = time.time()
        self.disabled = False

    def record_fail(self):
        """실패 기록"""
        self.fail_count += 1
        self.consecutive_fails += 1
        # 연속 3회 실패 시 비활성화
        if self.consecutive_fails >= 3:
            self.disabled = True

    def reset(self):
        """상태 리셋"""
        self.consecutive_fails = 0
        self.disabled = False


@dataclass
class TranscriptResult:
    """트랜스크립트 다운로드 결과"""
    success: bool
    video_id: str
    video_title: str = ""
    language: str = ""
    language_code: str = ""
    is_auto_generated: bool = False
    transcript: List[Dict] = field(default_factory=list)
    full_text: str = ""
    error: str = ""
    error_type: str = ""  # no_caption, disabled, unavailable, rate_limit, timeout, other
    word_count: int = 0
    available_languages: List[str] = field(default_factory=list)
    retry_count: int = 0
    method_used: str = ""  # api, yt-dlp
    no_subtitle: bool = False  # 🔴 v2.5: 영상 자체에 자막이 없는 경우 True (실패와 구분)


@dataclass
class DownloadProgress:
    """다운로드 진행 상태"""
    total: int
    completed: int
    success: int
    no_captions: int
    failed: int
    current_video: str
    current_status: str
    current_delay: float = 2.0
    total_retries: int = 0
    method_api: int = 0
    method_ytdlp: int = 0
    switched_to_ytdlp: bool = False


class YouTubeTranscriptDownloader:
    """YouTube 트랜스크립트 다운로더 (v4.4 - 한국어 우선 + SRT 지원)"""

    VERSION = "v4.4"

    # ⭐ v4.4: 언어 우선순위 (한국어 최우선!)
    DEFAULT_LANGUAGE_PRIORITY = [
        "ko", "ko-KR",           # 한국어 최우선
        "en", "en-US", "en-GB",  # 영어
        "ja",                    # 일본어
        "zh-Hans", "zh-Hant",    # 중국어
        "es", "fr", "pt", "ru",  # 기타 유럽어
        # "de" 제거 - 독일어는 의도치 않게 선택되는 문제 방지
    ]

    # 지원 출력 형식
    SUPPORTED_FORMATS = ['json', 'srt', 'vtt', 'txt']

    # ⭐ v4.0: 쿠키 파일 경로 (우선순위순)
    COOKIES_FILE_PATHS = [
        r"C:\Users\KIMJAEHEON\longform\data\cookies.txt",
        r"C:\Users\KIMJAEHEON\longform\cookies.txt",
        r"C:\Users\KIMJAEHEON\cookies.txt",
        "data/cookies.txt",
        "cookies.txt",
    ]

    # ⭐ v4.3: 최적화된 딜레이 설정 (대폭 감소!)
    API_MIN_DELAY = 1.0          # API 최소 요청 간격 (5 → 1)
    API_MAX_DELAY = 2.0          # API 최대 요청 간격 (10 → 2)
    YTDLP_MIN_DELAY = 1.0        # yt-dlp 최소 요청 간격 (5 → 1)
    YTDLP_MAX_DELAY = 3.0        # yt-dlp 최대 요청 간격 (10 → 3)
    BATCH_SIZE = 10
    BATCH_DELAY = 10.0           # 배치 간 대기 (30 → 10)
    MAX_RETRIES = 1              # 재시도 횟수 (3 → 1, 빠른 스킵)
    RATE_LIMIT_THRESHOLD = 2     # 연속 429 에러 N회 발생 시 yt-dlp 전환

    # ⭐ v4.3: Rate Limit 시 즉시 스킵 (긴 대기 없음!)
    RATE_LIMIT_SKIP = True       # Rate Limit 시 즉시 스킵
    RATE_LIMIT_WAIT = 10.0       # Rate Limit 시 대기 시간 (90 → 10, 스킵 모드면 무시)

    # ⭐ v4.3: 글로벌 Rate Limit 추적 (완화)
    GLOBAL_RATE_LIMIT_MAX = 3    # 글로벌 Rate Limit 최대 횟수 (5 → 3, 빠른 중단)
    GLOBAL_RATE_LIMIT_COOLDOWN = 60.0  # 글로벌 Rate Limit 시 대기 (300 → 60초)

    # ⭐ v4.3: Backoff 대폭 감소 (빠른 스킵 우선)
    BACKOFF_DELAYS = [2.0, 5.0, 10.0]  # 1차, 2차, 3차 재시도 대기 시간

    # ⭐ v4.3: 간소화된 브라우저 쿠키 우선순위 (불필요한 것 제거!)
    # 쿠키 파일 > 쿠키 없이 (브라우저 쿠키는 대부분 실패하므로 제거)
    BROWSER_PRIORITY = [
        "cookies_file",  # 1. ⭐ 쿠키 파일 (가장 안정적!)
        None,            # 2. 쿠키 없이 시도 (공개 자막)
    ]

    # 전체 브라우저 목록 (필요 시 확장용)
    BROWSER_PRIORITY_FULL = [
        "cookies_file",  # 1. ⭐ 쿠키 파일
        None,            # 2. 쿠키 없이
        "edge",          # 3. Edge
        "chrome_copy",   # 4. Chrome 복사본
    ]

    def __init__(
        self,
        output_dir: str = "data/transcripts",
        use_cookies: bool = True,
        browser: str = "chrome"
    ):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir = Path(tempfile.gettempdir()) / "yt_transcripts"
        self.temp_dir.mkdir(exist_ok=True)

        # ⭐ v4.0: 쿠키 파일 찾기
        self.cookies_file = self._find_cookies_file()

        # 쿠키 인증 설정
        self.use_cookies = use_cookies
        self.browser = browser

        # Chrome 쿠키 복사본 경로
        self.chrome_cookie_copy = self.temp_dir / "chrome_cookies_copy"

        # 상태 추적
        self._consecutive_rate_limits = 0
        self._switched_to_ytdlp = False
        self._current_method = DownloadMethod.API
        self._total_retries = 0
        self._last_request_time = 0.0
        self._rate_limited = False

        # ⭐ v4.1: 글로벌 Rate Limit 추적
        self._global_rate_limit_count = 0
        self._global_rate_limit_exceeded = False
        self._last_global_rate_limit_time = 0.0

        # ⭐ v4.3: 방식별 통계 추적 (적응형 최적화)
        self._method_stats: Dict[str, MethodStats] = {
            "api": MethodStats(),
            "cookies_file": MethodStats(),
            "no_cookie": MethodStats(),
        }
        self._last_success_method: Optional[str] = None  # 마지막 성공 방식
        self._skipped_videos: List[str] = []  # Rate Limit으로 스킵된 영상

        # yt-dlp 사용 가능 여부 확인
        self._ytdlp_available = self._check_ytdlp()

        print(f"[Transcript] {self.VERSION} 초기화 (적응형 최적화)")
        print(f"[Transcript] youtube-transcript-api: {'✅' if API_AVAILABLE else '❌'}")
        print(f"[Transcript] yt-dlp: {'✅' if self._ytdlp_available else '❌'}")
        if self.cookies_file:
            print(f"[Transcript] ✅ 쿠키 파일: {self.cookies_file}")
        else:
            print(f"[Transcript] ⚠️ 쿠키 파일 없음")

    def _find_cookies_file(self) -> Optional[str]:
        """⭐ v4.0: 쿠키 파일 찾기"""
        for path in self.COOKIES_FILE_PATHS:
            if os.path.exists(path):
                # 파일 크기 확인 (비어있지 않아야 함)
                if os.path.getsize(path) > 100:
                    return path
        return None

    def _get_random_delay(self, is_ytdlp: bool = False) -> float:
        """🔴 v3.0: 랜덤 딜레이 반환"""
        if is_ytdlp:
            return random.uniform(self.YTDLP_MIN_DELAY, self.YTDLP_MAX_DELAY)
        return random.uniform(self.API_MIN_DELAY, self.API_MAX_DELAY)

    def _wait_with_backoff(self, retry_count: int) -> float:
        """🔴 v3.0: Exponential Backoff 대기"""
        if retry_count >= len(self.BACKOFF_DELAYS):
            delay = self.BACKOFF_DELAYS[-1]
        else:
            delay = self.BACKOFF_DELAYS[retry_count]

        # 지터 추가 (±20%)
        jitter = delay * random.uniform(-0.2, 0.2)
        actual_delay = delay + jitter

        print(f"[Transcript] ⏳ 재시도 대기: {actual_delay:.1f}초 (시도 {retry_count + 1})")
        time.sleep(actual_delay)
        return actual_delay

    def _wait_for_rate_limit(self):
        """🔴 v3.0: Rate Limit 대기"""
        print(f"[Transcript] 🚨 Rate Limit 감지! {self.RATE_LIMIT_WAIT}초 대기...")
        time.sleep(self.RATE_LIMIT_WAIT)
        print(f"[Transcript] ✅ Rate Limit 대기 완료, 재개")

    def _check_global_rate_limit(self) -> bool:
        """
        ⭐ v4.1: 글로벌 Rate Limit 체크

        Returns:
            True: 다운로드 계속 가능
            False: 글로벌 Rate Limit 초과, 다운로드 중단 필요
        """
        # 쿨다운 시간이 지났으면 카운터 리셋
        if self._global_rate_limit_exceeded:
            elapsed = time.time() - self._last_global_rate_limit_time
            if elapsed >= self.GLOBAL_RATE_LIMIT_COOLDOWN:
                print(f"[Transcript] ✅ 글로벌 Rate Limit 쿨다운 완료, 재시도 가능")
                self._global_rate_limit_count = 0
                self._global_rate_limit_exceeded = False
                return True
            else:
                remaining = self.GLOBAL_RATE_LIMIT_COOLDOWN - elapsed
                print(f"[Transcript] 🚫 글로벌 Rate Limit 쿨다운 중... {remaining:.0f}초 남음")
                return False

        return True

    def _record_rate_limit(self):
        """⭐ v4.1: Rate Limit 발생 기록"""
        self._global_rate_limit_count += 1
        print(f"[Transcript] ⚠️ 글로벌 Rate Limit 카운트: {self._global_rate_limit_count}/{self.GLOBAL_RATE_LIMIT_MAX}")

        if self._global_rate_limit_count >= self.GLOBAL_RATE_LIMIT_MAX:
            self._global_rate_limit_exceeded = True
            self._last_global_rate_limit_time = time.time()
            print(f"[Transcript] 🚨 글로벌 Rate Limit 초과! {self.GLOBAL_RATE_LIMIT_COOLDOWN}초 동안 재시도 중단")
            print(f"[Transcript]    💡 쿠키 파일 설정을 권장합니다 (data/cookies.txt)")

    def reset_rate_limit_counters(self):
        """⭐ v4.1: Rate Limit 카운터 초기화 (배치 시작 시 호출)"""
        self._consecutive_rate_limits = 0
        self._global_rate_limit_count = 0
        self._global_rate_limit_exceeded = False
        self._switched_to_ytdlp = False
        self._skipped_videos = []

    # ═══════════════════════════════════════════════════════════════════
    # ⭐ v4.3: 적응형 방식 선택 메서드
    # ═══════════════════════════════════════════════════════════════════

    def _get_ordered_methods(self) -> List[str]:
        """
        ⭐ v4.3: 최적화된 다운로드 방식 순서 반환

        - 마지막 성공 방식 우선
        - 비활성화된 방식 제외
        - 성공률 높은 방식 우선
        """
        methods = []

        # 1. 마지막 성공 방식 최우선
        if self._last_success_method:
            stats = self._method_stats.get(self._last_success_method)
            if stats and not stats.disabled:
                methods.append(self._last_success_method)

        # 2. 나머지 방식 (성공률 순)
        remaining = [m for m in self._method_stats.keys() if m not in methods]
        remaining.sort(key=lambda m: (
            self._method_stats[m].disabled,  # 비활성화된 것 뒤로
            -self._method_stats[m].success_count,  # 성공 많은 것 앞으로
            self._method_stats[m].consecutive_fails  # 연속 실패 적은 것 앞으로
        ))

        methods.extend(remaining)

        # 비활성화된 방식 제외
        methods = [m for m in methods if not self._method_stats[m].disabled]

        return methods

    def _reset_all_methods(self):
        """⭐ v4.3: 모든 방식 리셋 (모두 비활성화 시)"""
        print("[Transcript] 🔄 모든 방식 리셋")
        for stats in self._method_stats.values():
            stats.reset()

    def _record_method_success(self, method: str):
        """⭐ v4.3: 방식 성공 기록"""
        if method in self._method_stats:
            self._method_stats[method].record_success()
            self._last_success_method = method
            print(f"[Transcript] ✅ 방식 성공 기록: {method}")

    def _record_method_fail(self, method: str):
        """⭐ v4.3: 방식 실패 기록"""
        if method in self._method_stats:
            self._method_stats[method].record_fail()
            if self._method_stats[method].disabled:
                print(f"[Transcript] ⚠️ 방식 비활성화됨: {method} (연속 3회 실패)")

    def get_method_stats(self) -> Dict:
        """⭐ v4.3: 현재 방식별 통계 반환"""
        return {
            'last_success': self._last_success_method,
            'skipped_count': len(self._skipped_videos),
            'methods': {
                name: {
                    'success': stats.success_count,
                    'fail': stats.fail_count,
                    'consecutive_fails': stats.consecutive_fails,
                    'disabled': stats.disabled
                }
                for name, stats in self._method_stats.items()
            }
        }

    def _apply_request_delay(self, is_ytdlp: bool = False):
        """🔴 v3.0: 요청 전 랜덤 딜레이 적용"""
        now = time.time()
        min_delay = self.YTDLP_MIN_DELAY if is_ytdlp else self.API_MIN_DELAY

        # 마지막 요청 이후 충분한 시간이 지났는지 확인
        elapsed = now - self._last_request_time
        if elapsed < min_delay:
            extra_wait = min_delay - elapsed
            time.sleep(extra_wait)

        # 랜덤 딜레이 추가
        delay = self._get_random_delay(is_ytdlp)
        print(f"[Transcript] ⏳ 요청 딜레이: {delay:.1f}초")
        time.sleep(delay)

        self._last_request_time = time.time()

    def _check_ytdlp(self) -> bool:
        """yt-dlp 설치 확인"""
        try:
            result = subprocess.run(
                ["yt-dlp", "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if result.returncode == 0:
                print(f"[Transcript] yt-dlp 버전: {result.stdout.strip()}")
                return True
        except FileNotFoundError:
            print("[Transcript] yt-dlp가 설치되지 않았습니다. (pip install yt-dlp)")
        except Exception as e:
            print(f"[Transcript] yt-dlp 확인 오류: {e}")
        return False

    def _copy_chrome_cookies(self) -> Optional[str]:
        """
        🔴 v3.1: Chrome 쿠키 파일 수동 복사
        (Chrome 실행 중에도 SQLite backup API로 읽기 가능)
        """
        import sqlite3

        # Chrome 쿠키 경로 (Windows)
        chrome_paths = [
            Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/User Data/Default/Network/Cookies",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/User Data/Default/Cookies",
        ]

        for chrome_cookie_path in chrome_paths:
            if chrome_cookie_path.exists():
                try:
                    # 복사본 경로
                    copy_path = self.chrome_cookie_copy
                    copy_path.parent.mkdir(parents=True, exist_ok=True)

                    # 기존 복사본 삭제
                    if copy_path.exists():
                        copy_path.unlink()

                    # SQLite backup API 사용 (읽기 전용 모드로 연결)
                    src_conn = sqlite3.connect(f"file:{chrome_cookie_path}?mode=ro", uri=True)

                    # 복사본 생성
                    dst_conn = sqlite3.connect(str(copy_path))
                    src_conn.backup(dst_conn)

                    src_conn.close()
                    dst_conn.close()

                    print(f"[yt-dlp]   Chrome 쿠키 복사 성공")
                    return str(copy_path)

                except Exception as e:
                    print(f"[yt-dlp]   Chrome 쿠키 복사 실패: {e}")
                    continue

        return None

    # ═══════════════════════════════════════════════════════════════════
    # 메인 다운로드 함수 (방식 선택)
    # ═══════════════════════════════════════════════════════════════════

    def download_single(
        self,
        video_id: str,
        video_title: str = "",
        language: str = "auto",
        include_auto_generated: bool = True,
        method: DownloadMethod = DownloadMethod.AUTO,
        retry_count: int = 0
    ) -> TranscriptResult:
        """
        ⭐ v4.3: 적응형 단일 영상 트랜스크립트 다운로드

        Args:
            video_id: YouTube 영상 ID
            video_title: 영상 제목
            language: 자막 언어 ("auto", "en", "ko" 등)
            include_auto_generated: 자동생성 자막 포함
            method: 다운로드 방식 (API, yt-dlp, 자동)
            retry_count: 재시도 횟수
        """

        # ⭐ v4.1: 글로벌 Rate Limit 체크
        if not self._check_global_rate_limit():
            self._skipped_videos.append(video_id)
            return TranscriptResult(
                success=False,
                video_id=video_id,
                video_title=video_title,
                error=f"Rate Limit 초과 - 스킵됨",
                error_type="rate_limit",
                method_used="skipped"
            )

        # ⭐ v4.3: 적응형 방식 순서 결정
        ordered_methods = self._get_ordered_methods()
        if not ordered_methods:
            self._reset_all_methods()
            ordered_methods = self._get_ordered_methods()

        print(f"[Transcript] 📥 다운로드: {video_id}")
        print(f"[Transcript] 시도 순서: {ordered_methods}" + (f" (마지막 성공: {self._last_success_method})" if self._last_success_method else ""))

        # ⭐ v4.3: 각 방식 순차 시도
        last_error = None
        last_error_type = "other"

        for try_method in ordered_methods:
            print(f"[Transcript] 🔄 시도: {try_method}")

            # 방식별 다운로드 실행
            if try_method == "api":
                if not API_AVAILABLE:
                    print(f"[Transcript]   건너뛰기: API 미설치")
                    continue
                result = self._download_via_api(
                    video_id, video_title, language,
                    include_auto_generated, 0
                )
            elif try_method in ["cookies_file", "no_cookie"]:
                if not self._ytdlp_available:
                    print(f"[Transcript]   건너뛰기: yt-dlp 미설치")
                    continue
                # yt-dlp 호출 (내부에서 cookies_file/no_cookie 분기)
                result = self._download_via_ytdlp_single_method(
                    video_id, video_title, language,
                    include_auto_generated, try_method
                )
            else:
                continue

            # 성공 처리
            if result.success:
                self._record_method_success(try_method)
                self._consecutive_rate_limits = 0
                print(f"[Transcript] ✅ 성공: {try_method}")
                return result

            # 실패 처리
            self._record_method_fail(try_method)
            last_error = result.error
            last_error_type = result.error_type

            # ⭐ v4.3: Rate Limit 즉시 스킵
            if result.error_type == "rate_limit":
                self._consecutive_rate_limits += 1
                self._record_rate_limit()

                if self.RATE_LIMIT_SKIP:
                    print(f"[Transcript] ⚠️ Rate Limit - 이 영상 스킵")
                    self._skipped_videos.append(video_id)
                    return TranscriptResult(
                        success=False,
                        video_id=video_id,
                        video_title=video_title,
                        error="Rate Limit - 스킵됨",
                        error_type="rate_limit",
                        method_used=try_method
                    )

            # 자막 없음/비활성화 - 더 이상 시도 불필요
            if result.error_type in ["no_caption", "disabled", "unavailable"]:
                print(f"[Transcript] ⏹️ 중단: {result.error_type}")
                return result

            print(f"[Transcript] ❌ 실패: {try_method} - {result.error[:50]}...")

        # 모든 방식 실패
        return TranscriptResult(
            success=False,
            video_id=video_id,
            video_title=video_title,
            error=last_error or "모든 방식 실패",
            error_type=last_error_type,
            method_used="all_failed"
        )

    def _download_via_ytdlp_single_method(
        self,
        video_id: str,
        video_title: str,
        language: str,
        include_auto_generated: bool,
        method: str  # "cookies_file" or "no_cookie"
    ) -> TranscriptResult:
        """⭐ v4.3: 단일 yt-dlp 방식으로 다운로드 (브라우저 폴백 없이)"""

        if not self._ytdlp_available:
            return TranscriptResult(
                success=False,
                video_id=video_id,
                video_title=video_title,
                error="yt-dlp가 설치되지 않았습니다.",
                error_type="other",
                method_used=method
            )

        video_url = f"https://www.youtube.com/watch?v={video_id}"

        # 언어 설정
        if language == "auto":
            sub_lang = "ko,ko-KR,en,en-US,ja,zh-Hans"  # ⭐ v4.4: 한국어 최우선
        else:
            sub_lang = f"{language},en"

        import shutil
        output_dir = os.path.join(tempfile.gettempdir(), "yt_subs", video_id)

        # 디렉토리 초기화
        if os.path.exists(output_dir):
            shutil.rmtree(output_dir, ignore_errors=True)
        os.makedirs(output_dir, exist_ok=True)

        output_template = os.path.join(output_dir, "%(id)s.%(ext)s")

        try:
            # 요청 전 딜레이 적용
            self._apply_request_delay(is_ytdlp=True)

            # 기본 명령어
            cmd = [
                "yt-dlp",
                "--skip-download",
                "--write-auto-sub",
                "--write-sub",
                "--sub-lang", sub_lang,
                "--sub-format", "vtt/srt/best",
                "-o", output_template,
                "--no-check-certificate",
                "--no-playlist",
                "--no-warnings",
                "--socket-timeout", "15",  # 타임아웃 단축
                "--retries", "1",  # 재시도 감소
            ]

            # 쿠키 파일 사용 여부
            if method == "cookies_file" and self.cookies_file:
                cmd.extend(["--cookies", self.cookies_file])
                print(f"[Transcript]   쿠키 파일 사용")
            elif method == "cookies_file" and not self.cookies_file:
                return TranscriptResult(
                    success=False,
                    video_id=video_id,
                    video_title=video_title,
                    error="쿠키 파일 없음",
                    error_type="other",
                    method_used=method
                )

            # JS 런타임 옵션
            js_runtime = YtdlpManager.get_js_runtime()
            if js_runtime:
                cmd.extend(["--js-runtimes", js_runtime])

            cmd.append(video_url)

            # subprocess 실행
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=60,  # 타임아웃 단축 (120 → 60)
                encoding='utf-8',
                errors='replace'
            )

            output_combined = (result.stdout or "") + (result.stderr or "")
            output_lower = output_combined.lower()

            # ⭐ v4.4: 한국어 우선 자막 파일 선택
            output_path = Path(output_dir)
            subtitle_file = self._select_best_subtitle_file(output_path)

            if subtitle_file:
                transcript_data, lang_code, is_auto = self._parse_subtitle_file(subtitle_file)

                if transcript_data:
                    full_text = " ".join([item['text'] for item in transcript_data])
                    full_text = " ".join(full_text.split())
                    word_count = len(full_text.split())

                    self._cleanup_directory(output_path)

                    return TranscriptResult(
                        success=True,
                        video_id=video_id,
                        video_title=video_title,
                        language=lang_code or "en",
                        language_code=lang_code or "en",
                        is_auto_generated=is_auto,
                        transcript=transcript_data,
                        full_text=full_text,
                        word_count=word_count,
                        method_used=method
                    )

            # 오류 분석
            self._cleanup_directory(output_path)

            if "429" in output_combined or "too many" in output_lower:
                return TranscriptResult(
                    success=False, video_id=video_id, video_title=video_title,
                    error="Rate Limit (429)", error_type="rate_limit", method_used=method
                )
            elif "no subtitles" in output_lower or "there are no subtitles" in output_lower:
                return TranscriptResult(
                    success=False, video_id=video_id, video_title=video_title,
                    error="자막 없음", error_type="no_caption", method_used=method, no_subtitle=True
                )
            elif "unavailable" in output_lower or "private" in output_lower:
                return TranscriptResult(
                    success=False, video_id=video_id, video_title=video_title,
                    error="영상 없음/비공개", error_type="unavailable", method_used=method
                )
            elif "subtitles disabled" in output_lower:
                return TranscriptResult(
                    success=False, video_id=video_id, video_title=video_title,
                    error="자막 비활성화", error_type="disabled", method_used=method, no_subtitle=True
                )
            else:
                return TranscriptResult(
                    success=False, video_id=video_id, video_title=video_title,
                    error=f"yt-dlp: {(result.stderr or result.stdout)[:80]}",
                    error_type="other", method_used=method
                )

        except subprocess.TimeoutExpired:
            self._cleanup_directory(Path(output_dir))
            return TranscriptResult(
                success=False, video_id=video_id, video_title=video_title,
                error="타임아웃", error_type="timeout", method_used=method
            )
        except Exception as e:
            self._cleanup_directory(Path(output_dir))
            return TranscriptResult(
                success=False, video_id=video_id, video_title=video_title,
                error=str(e)[:80], error_type="other", method_used=method
            )

    # ═══════════════════════════════════════════════════════════════════
    # API 방식 다운로드
    # ═══════════════════════════════════════════════════════════════════

    def _download_via_api(
        self,
        video_id: str,
        video_title: str,
        language: str,
        include_auto_generated: bool,
        retry_count: int
    ) -> TranscriptResult:
        """youtube-transcript-api를 사용한 다운로드"""

        if not API_AVAILABLE:
            return TranscriptResult(
                success=False,
                video_id=video_id,
                video_title=video_title,
                error="youtube-transcript-api가 설치되지 않았습니다.",
                error_type="other",
                method_used="api"
            )

        # 🔴 v3.0: 요청 전 랜덤 딜레이 적용
        self._apply_request_delay(is_ytdlp=False)

        try:
            # 사용 가능한 자막 목록 조회
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)

            available_langs = []
            manual_transcripts = []
            generated_transcripts = []

            for t in transcript_list:
                lang_info = f"{t.language} ({t.language_code})"
                if t.is_generated:
                    generated_transcripts.append(t)
                    available_langs.append(f"{lang_info} [자동]")
                else:
                    manual_transcripts.append(t)
                    available_langs.append(f"{lang_info} [수동]")

            # 자막 선택
            selected_transcript = None
            is_auto = False
            actual_language = ""
            actual_language_code = ""

            if language == "auto":
                priority_languages = self.DEFAULT_LANGUAGE_PRIORITY
            else:
                priority_languages = [language] + [l for l in self.DEFAULT_LANGUAGE_PRIORITY if l != language]

            # 수동 자막 우선
            for lang in priority_languages:
                for t in manual_transcripts:
                    if t.language_code == lang or t.language_code.startswith(lang.split("-")[0]):
                        selected_transcript = t
                        is_auto = False
                        actual_language = t.language
                        actual_language_code = t.language_code
                        break
                if selected_transcript:
                    break

            # 자동생성 자막
            if selected_transcript is None and include_auto_generated:
                for lang in priority_languages:
                    for t in generated_transcripts:
                        if t.language_code == lang or t.language_code.startswith(lang.split("-")[0]):
                            selected_transcript = t
                            is_auto = True
                            actual_language = t.language
                            actual_language_code = t.language_code
                            break
                    if selected_transcript:
                        break

            # 아무 자막이나
            if selected_transcript is None:
                if manual_transcripts:
                    selected_transcript = manual_transcripts[0]
                    is_auto = False
                    actual_language = selected_transcript.language
                    actual_language_code = selected_transcript.language_code
                elif generated_transcripts and include_auto_generated:
                    selected_transcript = generated_transcripts[0]
                    is_auto = True
                    actual_language = selected_transcript.language
                    actual_language_code = selected_transcript.language_code

            if selected_transcript is None:
                return TranscriptResult(
                    success=False,
                    video_id=video_id,
                    video_title=video_title,
                    error="사용 가능한 자막이 없습니다.",
                    error_type="no_caption",
                    available_languages=available_langs,
                    method_used="api"
                )

            # 트랜스크립트 추출
            transcript_data = selected_transcript.fetch()
            full_text = " ".join([item['text'] for item in transcript_data])
            full_text = " ".join(full_text.split())
            word_count = len(full_text.split())

            return TranscriptResult(
                success=True,
                video_id=video_id,
                video_title=video_title,
                language=actual_language,
                language_code=actual_language_code,
                is_auto_generated=is_auto,
                transcript=transcript_data,
                full_text=full_text,
                word_count=word_count,
                available_languages=available_langs,
                retry_count=retry_count,
                method_used="api"
            )

        except Exception as e:
            error_msg = str(e)

            # 429 Rate Limit 감지
            if "429" in error_msg or "Too Many Requests" in error_msg:
                return TranscriptResult(
                    success=False,
                    video_id=video_id,
                    video_title=video_title,
                    error="Rate Limit (429) - YouTube 요청 제한",
                    error_type="rate_limit",
                    retry_count=retry_count,
                    method_used="api"
                )

            elif "TranscriptsDisabled" in error_msg or "disabled" in error_msg.lower():
                return TranscriptResult(
                    success=False,
                    video_id=video_id,
                    video_title=video_title,
                    error="자막이 비활성화됨",
                    error_type="disabled",
                    method_used="api",
                    no_subtitle=True  # 🔴 v2.5: 자막 없음 플래그
                )

            elif "NoTranscript" in error_msg or "no transcript" in error_msg.lower():
                return TranscriptResult(
                    success=False,
                    video_id=video_id,
                    video_title=video_title,
                    error="자막 없음",
                    error_type="no_caption",
                    method_used="api",
                    no_subtitle=True  # 🔴 v2.5: 자막 없음 플래그
                )

            elif "VideoUnavailable" in error_msg or "unavailable" in error_msg.lower():
                return TranscriptResult(
                    success=False,
                    video_id=video_id,
                    video_title=video_title,
                    error="영상 없음 (비공개/삭제)",
                    error_type="unavailable",
                    method_used="api"
                )

            # XML/JSON 파싱 오류 (YouTube 응답 문제)
            elif "no element found" in error_msg.lower() or "xml" in error_msg.lower():
                return TranscriptResult(
                    success=False,
                    video_id=video_id,
                    video_title=video_title,
                    error=f"YouTube 응답 파싱 오류 (API 변경 가능성)",
                    error_type="other",
                    method_used="api"
                )

            # 연결 오류
            elif "connection" in error_msg.lower() or "timeout" in error_msg.lower():
                return TranscriptResult(
                    success=False,
                    video_id=video_id,
                    video_title=video_title,
                    error=f"네트워크 오류: {error_msg[:80]}",
                    error_type="other",
                    method_used="api"
                )

            else:
                return TranscriptResult(
                    success=False,
                    video_id=video_id,
                    video_title=video_title,
                    error=f"API 오류: {error_msg[:100]}",
                    error_type="other",
                    method_used="api"
                )

    # ═══════════════════════════════════════════════════════════════════
    # yt-dlp 방식 다운로드
    # ═══════════════════════════════════════════════════════════════════

    def _download_via_ytdlp(
        self,
        video_id: str,
        video_title: str,
        language: str,
        include_auto_generated: bool,
        retry_count: int
    ) -> TranscriptResult:
        """
        🔴 v3.1: yt-dlp를 사용한 자막 다운로드 (다중 브라우저 쿠키 폴백 지원)

        변경사항:
        1. 쿠키 없이 먼저 시도
        2. 다중 브라우저 폴백 (Firefox -> Edge -> Chrome 복사본 -> Chrome)
        3. Chrome 쿠키 복사 오류 자동 처리 (GitHub Issue #7271)
        """

        if not self._ytdlp_available:
            return TranscriptResult(
                success=False,
                video_id=video_id,
                video_title=video_title,
                error="yt-dlp가 설치되지 않았습니다. (pip install yt-dlp)",
                error_type="other",
                method_used="yt-dlp"
            )

        video_url = f"https://www.youtube.com/watch?v={video_id}"

        # 언어 설정
        if language == "auto":
            sub_lang = "ko,ko-KR,en,en-US,ja,zh-Hans"  # ⭐ v4.4: 한국어 최우선
        else:
            sub_lang = f"{language},en"

        # Windows 호환 경로 설정
        import shutil
        output_dir = os.path.join(tempfile.gettempdir(), "yt_subs", video_id)

        print(f"[yt-dlp] 자막 다운로드 시작: {video_id}")

        # 🔴 v3.1: 각 브라우저/방식으로 시도
        last_error = None
        last_error_type = "other"
        is_no_subtitle = False

        for browser in self.BROWSER_PRIORITY:
            browser_name = browser or "no_cookie"
            print(f"[yt-dlp]   시도: {browser_name}")

            # 디렉토리 초기화
            if os.path.exists(output_dir):
                shutil.rmtree(output_dir, ignore_errors=True)
            os.makedirs(output_dir, exist_ok=True)

            output_template = os.path.join(output_dir, "%(id)s.%(ext)s")

            try:
                # 요청 전 랜덤 딜레이 적용
                self._apply_request_delay(is_ytdlp=True)

                # 기본 명령어
                cmd = [
                    "yt-dlp",
                    "--skip-download",
                    "--write-auto-sub",
                    "--write-sub",
                    "--sub-lang", sub_lang,
                    "--sub-format", "vtt/srt/best",
                    "-o", output_template,
                    "--no-check-certificate",
                    "--no-playlist",
                    "--no-warnings",
                    "--socket-timeout", "30",
                    "--retries", "3",
                ]

                # ⭐ v4.0: 브라우저별 쿠키 옵션
                if browser == "cookies_file":
                    # ⭐ 쿠키 파일 사용 (가장 안정적!)
                    if self.cookies_file:
                        cmd.extend(["--cookies", self.cookies_file])
                        print(f"[yt-dlp]   쿠키 파일 사용: {os.path.basename(self.cookies_file)}")
                    else:
                        print(f"[yt-dlp]   쿠키 파일 없음, 다음 시도")
                        continue  # 쿠키 파일 없으면 다음 방식
                elif browser is None:
                    # 쿠키 없이 시도
                    pass
                elif browser == "chrome_copy":
                    # Chrome 쿠키 복사본 사용
                    cookie_file = self._copy_chrome_cookies()
                    if cookie_file:
                        cmd.extend(["--cookies", cookie_file])
                    else:
                        print(f"[yt-dlp]   Chrome 쿠키 복사 실패, 다음 시도")
                        continue  # 복사 실패 시 다음 브라우저
                elif browser == "chrome":
                    # Chrome 직접 (마지막 시도)
                    cmd.extend(["--cookies-from-browser", "chrome"])
                else:
                    # Firefox, Edge 등
                    cmd.extend(["--cookies-from-browser", browser])

                # JS 런타임 옵션 추가
                js_runtime = YtdlpManager.get_js_runtime()
                if js_runtime:
                    cmd.extend(["--js-runtimes", js_runtime])

                cmd.append(video_url)

                print(f"[yt-dlp] 실행: {video_id} ({browser_name})")

                # subprocess 실행
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=120,
                    encoding='utf-8',
                    errors='replace'
                )

                # 결과 분석
                output_combined = (result.stdout or "") + (result.stderr or "")
                output_lower = output_combined.lower()

                # 🔴 v3.1: Chrome 쿠키 오류 감지 (다음 브라우저로 전환)
                if "could not copy chrome cookie database" in output_lower:
                    print(f"[yt-dlp]   Chrome 쿠키 잠김, 다음 방식 시도")
                    continue

                # ⭐ v4.4: 한국어 우선 자막 파일 선택
                output_path = Path(output_dir)
                subtitle_file = self._select_best_subtitle_file(output_path)

                if subtitle_file:
                    print(f"[yt-dlp] 성공: {browser_name} - {subtitle_file.name}")
                    transcript_data, lang_code, is_auto = self._parse_subtitle_file(subtitle_file)

                    if transcript_data:
                        full_text = " ".join([item['text'] for item in transcript_data])
                        full_text = " ".join(full_text.split())
                        word_count = len(full_text.split())

                        self._cleanup_directory(output_path)

                        return TranscriptResult(
                            success=True,
                            video_id=video_id,
                            video_title=video_title,
                            language=lang_code or "en",
                            language_code=lang_code or "en",
                            is_auto_generated=is_auto,
                            transcript=transcript_data,
                            full_text=full_text,
                            word_count=word_count,
                            retry_count=retry_count,
                            method_used="yt-dlp"
                        )

                # 영상에 자막이 없는 경우 (더 이상 시도 불필요)
                if "no subtitles" in output_lower or "there are no subtitles" in output_lower:
                    print(f"[yt-dlp]   자막 없음 (영상에 자막 없음)")
                    self._cleanup_directory(output_path)
                    return TranscriptResult(
                        success=False,
                        video_id=video_id,
                        video_title=video_title,
                        error="이 영상에 자막이 없습니다.",
                        error_type="no_caption",
                        method_used="yt-dlp",
                        no_subtitle=True
                    )

                # 영상 사용 불가 (더 이상 시도 불필요)
                if "unavailable" in output_lower or "video unavailable" in output_lower:
                    self._cleanup_directory(output_path)
                    return TranscriptResult(
                        success=False,
                        video_id=video_id,
                        video_title=video_title,
                        error="영상을 사용할 수 없습니다.",
                        error_type="unavailable",
                        method_used="yt-dlp"
                    )

                # 비공개 영상 (더 이상 시도 불필요)
                if "private" in output_lower:
                    self._cleanup_directory(output_path)
                    return TranscriptResult(
                        success=False,
                        video_id=video_id,
                        video_title=video_title,
                        error="비공개 영상입니다.",
                        error_type="unavailable",
                        method_used="yt-dlp"
                    )

                # 자막 비활성화 (더 이상 시도 불필요)
                if "subtitles disabled" in output_lower or "caption disabled" in output_lower:
                    self._cleanup_directory(output_path)
                    return TranscriptResult(
                        success=False,
                        video_id=video_id,
                        video_title=video_title,
                        error="이 영상은 자막이 비활성화되어 있습니다.",
                        error_type="disabled",
                        method_used="yt-dlp",
                        no_subtitle=True
                    )

                # 기타 오류는 다음 브라우저 시도
                if "429" in output_combined or "too many" in output_lower:
                    last_error = "Rate Limit (429)"
                    last_error_type = "rate_limit"
                else:
                    last_error = f"yt-dlp: {(result.stderr or result.stdout)[:80]}"
                    last_error_type = "other"

                print(f"[yt-dlp]   실패: {last_error[:50]}...")
                self._cleanup_directory(output_path)

            except subprocess.TimeoutExpired:
                self._cleanup_directory(Path(output_dir))
                last_error = "다운로드 시간 초과 (120초)"
                last_error_type = "timeout"
                print(f"[yt-dlp]   타임아웃")

            except FileNotFoundError:
                return TranscriptResult(
                    success=False,
                    video_id=video_id,
                    video_title=video_title,
                    error="yt-dlp를 찾을 수 없습니다. PATH 확인 필요.",
                    error_type="other",
                    method_used="yt-dlp"
                )

            except Exception as e:
                self._cleanup_directory(Path(output_dir))
                error_msg = str(e)
                print(f"[yt-dlp]   예외: {error_msg[:50]}...")

                # Chrome 쿠키 오류 감지
                if "could not copy chrome cookie database" in error_msg.lower():
                    print(f"[yt-dlp]   Chrome 쿠키 잠김, 다음 방식 시도")
                    continue

                last_error = f"오류: {error_msg[:100]}"
                last_error_type = "other"

        # 모든 브라우저 실패
        print(f"[yt-dlp] 모든 방식 실패")

        # ⭐ v4.1: Rate Limit인 경우 글로벌 카운터 업데이트
        if last_error_type == "rate_limit":
            self._record_rate_limit()

            # 글로벌 Rate Limit 초과 시 재시도 중단
            if self._global_rate_limit_exceeded:
                print(f"[yt-dlp] 글로벌 Rate Limit 초과 - 재시도 중단")
                return TranscriptResult(
                    success=False,
                    video_id=video_id,
                    video_title=video_title,
                    error=f"Rate Limit 초과. {self.GLOBAL_RATE_LIMIT_COOLDOWN/60:.0f}분 후 재시도하세요. 쿠키 파일 설정을 권장합니다.",
                    error_type="rate_limit",
                    method_used="yt-dlp",
                    no_subtitle=is_no_subtitle
                )

            # 재시도 횟수 제한 내에서만 재시도
            if retry_count < self.MAX_RETRIES:
                self._wait_for_rate_limit()
                return self._download_via_ytdlp(
                    video_id, video_title, language,
                    include_auto_generated, retry_count + 1
                )

        # 기타 오류 재시도
        if retry_count < self.MAX_RETRIES and last_error_type == "other":
            self._wait_with_backoff(retry_count)
            self._total_retries += 1
            return self._download_via_ytdlp(
                video_id, video_title, language,
                include_auto_generated, retry_count + 1
            )

        return TranscriptResult(
            success=False,
            video_id=video_id,
            video_title=video_title,
            error=last_error or "알 수 없는 오류",
            error_type=last_error_type,
            method_used="yt-dlp",
            no_subtitle=is_no_subtitle
        )

    def _find_subtitle_file(self, base_path: Path) -> Optional[Path]:
        """자막 파일 찾기 (레거시)"""
        parent = base_path.parent
        name = base_path.name

        for pattern in [f"{name}.*.json3", f"{name}.*.vtt", f"{name}.*.srt"]:
            matches = list(parent.glob(pattern))
            if matches:
                # 수동 자막 우선
                for m in matches:
                    if ".auto." not in m.name:
                        return m
                return matches[0]
        return None

    def _find_subtitle_file_v2(self, video_id: str, output_dir: Path) -> Optional[Path]:
        """
        ⭐ 수정된 자막 파일 찾기

        yt-dlp가 생성하는 파일명 패턴:
        - {id}.en.vtt
        - {id}.en.srt
        - {id}.ko.vtt
        - {id}.en-orig.vtt (자동생성 원본)
        """

        if not output_dir.exists():
            return None

        # 모든 자막 파일 찾기
        subtitle_files = []

        for ext in ['vtt', 'srt', 'json3', 'ttml', 'srv1', 'srv2', 'srv3']:
            subtitle_files.extend(output_dir.glob(f"*.{ext}"))

        if not subtitle_files:
            return None

        print(f"[yt-dlp] 발견된 자막 파일: {[f.name for f in subtitle_files]}")

        # 우선순위: 수동 자막 > 자동 자막, 언어: en > ko > 기타
        priority_order = []

        for f in subtitle_files:
            fname = f.name.lower()

            # 점수 계산 (낮을수록 우선)
            score = 100

            # 자동생성 여부
            if ".auto." in fname or "-orig" in fname:
                score += 50  # 자동생성은 후순위

            # 언어 우선순위
            if ".en." in fname or ".en-" in fname:
                score -= 30  # 영어 우선
            elif ".ko." in fname or ".ko-" in fname:
                score -= 20  # 한국어 그 다음

            # 포맷 우선순위
            if fname.endswith('.vtt'):
                score -= 5
            elif fname.endswith('.srt'):
                score -= 3

            priority_order.append((score, f))

        # 정렬 후 첫 번째 반환
        priority_order.sort(key=lambda x: x[0])

        return priority_order[0][1] if priority_order else None

    def _select_best_subtitle_file(self, output_dir: Path) -> Optional[Path]:
        """
        ⭐ v4.4: 최적의 자막 파일 선택 - 한국어 우선

        우선순위:
        1. 한국어 수동 자막 (ko.vtt, ko.srt)
        2. 한국어 자동 자막 (ko.auto.vtt)
        3. 영어 자막
        4. 일본어 자막
        5. 기타 언어 (독일어는 최하위)
        """
        if not output_dir.exists():
            return None

        # 모든 자막 파일 수집
        all_subs = []
        for ext in ['vtt', 'srt', 'json3', 'ttml']:
            all_subs.extend(output_dir.glob(f"*.{ext}"))

        if not all_subs:
            return None

        def get_language_score(filepath: Path) -> tuple:
            """언어 우선순위 점수 (낮을수록 좋음)"""
            name = filepath.name.lower()
            is_auto = '.auto.' in name or '-orig' in name

            # 한국어 최우선
            if '.ko' in name or '.ko-' in name:
                return (0 if not is_auto else 1, 'ko')

            # 영어
            if '.en' in name or '.en-' in name:
                return (2 if not is_auto else 3, 'en')

            # 일본어
            if '.ja' in name or '.ja-' in name:
                return (4 if not is_auto else 5, 'ja')

            # 중국어
            if '.zh' in name:
                return (6, 'zh')

            # 독일어 - 매우 낮은 우선순위
            if '.de' in name or '.de-' in name:
                return (99, 'de')

            # 기타
            return (50, 'unknown')

        # 우선순위로 정렬
        sorted_subs = sorted(all_subs, key=get_language_score)

        # 최적 파일 선택
        best_file = sorted_subs[0]
        score, lang = get_language_score(best_file)

        print(f"[Transcript] 자막 파일 선택: {best_file.name} (언어: {lang}, 점수: {score})")

        # 독일어만 있는 경우 경고
        if lang == 'de':
            print(f"[Transcript] ⚠️ 한국어/영어 자막 없음, 독일어 사용")

        return best_file

    def _cleanup_directory(self, dir_path: Path):
        """디렉토리 전체 정리"""
        try:
            if dir_path.exists():
                import shutil
                shutil.rmtree(dir_path, ignore_errors=True)
        except Exception as e:
            print(f"[yt-dlp] 정리 실패: {e}")

    def _parse_subtitle_file(self, file_path: Path) -> Tuple[List[Dict], str, bool]:
        """자막 파일 파싱 (개선)"""
        transcript = []
        lang_code = ""

        # ⭐ 자동 생성 여부 (auto, orig 포함)
        fname_lower = file_path.name.lower()
        is_auto = ".auto." in fname_lower or "-orig" in fname_lower

        # ⭐ 언어 코드 추출 개선
        # 패턴: video_id.en.vtt, video_id.ko.srt, video_id.en-orig.vtt
        parts = file_path.stem.split(".")  # stem은 확장자 제외
        if len(parts) >= 2:
            lang_code = parts[-1]
            # -orig 제거
            lang_code = lang_code.replace("-orig", "")

        print(f"[yt-dlp] 파싱: {file_path.name}, 언어: {lang_code}, 자동생성: {is_auto}")

        try:
            suffix = file_path.suffix.lower()
            if suffix == ".json3":
                transcript = self._parse_json3(file_path)
            elif suffix == ".vtt":
                transcript = self._parse_vtt(file_path)
            elif suffix == ".srt":
                transcript = self._parse_srt_file(file_path)
            else:
                # 기타 형식은 텍스트로 시도
                transcript = self._parse_as_text(file_path)
        except Exception as e:
            print(f"[Transcript] 파싱 오류: {e}")

        print(f"[yt-dlp] 파싱 결과: {len(transcript)}개 세그먼트")

        return transcript, lang_code, is_auto

    def _parse_as_text(self, file_path: Path) -> List[Dict]:
        """기타 형식 텍스트로 파싱"""
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            # 단순히 텍스트만 추출
            lines = [l.strip() for l in content.split("\n") if l.strip()]

            if lines:
                return [{
                    "start": 0,
                    "duration": 0,
                    "text": " ".join(lines)
                }]
        except Exception:
            pass

        return []

    def _parse_json3(self, file_path: Path) -> List[Dict]:
        """JSON3 파싱"""
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        transcript = []
        for event in data.get("events", []):
            if "segs" not in event:
                continue

            start = event.get("tStartMs", 0) / 1000
            duration = event.get("dDurationMs", 0) / 1000

            text_parts = []
            for seg in event.get("segs", []):
                text = seg.get("utf8", "")
                if text and text.strip():
                    text_parts.append(text)

            if text_parts:
                transcript.append({
                    "start": start,
                    "duration": duration,
                    "text": "".join(text_parts).strip()
                })

        return transcript

    def _parse_vtt(self, file_path: Path) -> List[Dict]:
        """VTT 파싱 (v4.5 - 개선된 타임스탬프 파싱)"""
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        transcript = []

        # 디버깅: 원본 파일 정보
        file_size = len(content)
        total_lines = content.count('\n')
        print(f"[VTT 파싱] 파일: {file_path.name}")
        print(f"[VTT 파싱] 크기: {file_size:,} bytes, 라인: {total_lines:,}")

        # VTT 헤더 제거
        if content.startswith("WEBVTT"):
            # 첫 번째 빈 줄 이후부터 파싱
            parts = content.split("\n\n", 1)
            content = parts[1] if len(parts) > 1 else content

        # 블록 단위로 분리
        blocks = re.split(r'\n\s*\n', content)
        print(f"[VTT 파싱] 블록 수: {len(blocks)}")

        # 디버깅 카운터
        blocks_with_timestamp = 0
        blocks_with_text = 0
        blocks_parsed_ok = 0
        parse_errors = 0

        for block in blocks:
            block = block.strip()
            if not block:
                continue

            lines = block.split("\n")

            # 타임스탬프 라인 찾기
            timestamp_line = None
            text_lines = []

            for line in lines:
                if "-->" in line:
                    timestamp_line = line
                    blocks_with_timestamp += 1
                elif timestamp_line and line.strip():
                    text_lines.append(line)

            if text_lines:
                blocks_with_text += 1

            if timestamp_line and text_lines:
                # ⭐ v4.5: 더 유연한 타임스탬프 파싱
                # 형식: 00:00:00.000, 0:00:00.000, 00:00.000 등 지원
                match = re.match(
                    r'(\d{1,2}:)?(\d{1,2}):(\d{1,2})[.,](\d{1,3})\s*-->\s*(\d{1,2}:)?(\d{1,2}):(\d{1,2})[.,](\d{1,3})',
                    timestamp_line.strip()
                )

                if match:
                    groups = match.groups()

                    # 시작 시간
                    start_h = int(groups[0].replace(":", "")) if groups[0] else 0
                    start_m = int(groups[1])
                    start_s = int(groups[2])
                    start_ms_str = groups[3].ljust(3, '0')[:3]  # 밀리초 3자리로 맞춤
                    start_ms = int(start_ms_str)
                    start = start_h * 3600 + start_m * 60 + start_s + start_ms / 1000

                    # 종료 시간
                    end_h = int(groups[4].replace(":", "")) if groups[4] else 0
                    end_m = int(groups[5])
                    end_s = int(groups[6])
                    end_ms_str = groups[7].ljust(3, '0')[:3]  # 밀리초 3자리로 맞춤
                    end_ms = int(end_ms_str)
                    end = end_h * 3600 + end_m * 60 + end_s + end_ms / 1000

                    # 텍스트 정리 (HTML 태그 제거)
                    text = " ".join(text_lines)
                    text = re.sub(r'<[^>]+>', '', text)  # HTML 태그 제거
                    text = re.sub(r'\{[^}]+\}', '', text)  # {...} 제거
                    text = text.strip()

                    if text:
                        transcript.append({
                            "start": start,
                            "duration": max(0.1, end - start),  # 최소 0.1초
                            "text": text
                        })
                        blocks_parsed_ok += 1
                else:
                    parse_errors += 1
                    if parse_errors <= 3:  # 처음 3개 오류만 출력
                        print(f"[VTT 파싱] ⚠️ 타임스탬프 파싱 실패: {timestamp_line[:60]}...")

        # 디버깅 결과
        print(f"[VTT 파싱] 결과: 타임스탬프={blocks_with_timestamp}, 텍스트={blocks_with_text}, 파싱성공={blocks_parsed_ok}, 오류={parse_errors}")
        print(f"[VTT 파싱] ✅ 최종 세그먼트: {len(transcript)}개")

        # 경고: 예상보다 적은 세그먼트
        if len(transcript) < len(blocks) * 0.5 and len(blocks) > 20:
            print(f"[VTT 파싱] ⚠️ 경고: 블록({len(blocks)}) 대비 세그먼트({len(transcript)}) 비율 낮음!")

        return transcript

    def _parse_srt_file(self, file_path: Path) -> List[Dict]:
        """SRT 파싱"""
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        transcript = []
        blocks = content.strip().split("\n\n")

        for block in blocks:
            lines = block.strip().split("\n")
            if len(lines) >= 3 and "-->" in lines[1]:
                times = lines[1].split("-->")
                start = self._parse_time(times[0].strip())
                end = self._parse_time(times[1].strip())
                text = " ".join(lines[2:]).strip()
                if text:
                    transcript.append({
                        "start": start,
                        "duration": end - start,
                        "text": text
                    })
        return transcript

    def _parse_time(self, time_str: str) -> float:
        """시간 문자열을 초로 변환"""
        parts = time_str.replace(",", ".").split(":")
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        elif len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        return 0

    def _cleanup_temp_files(self, base_path: Path):
        """임시 파일 정리"""
        for f in base_path.parent.glob(f"{base_path.name}*"):
            try:
                f.unlink()
            except Exception:
                pass

    # ═══════════════════════════════════════════════════════════════════
    # 배치 다운로드
    # ═══════════════════════════════════════════════════════════════════

    def download_batch(
        self,
        videos: List[Dict],
        language: str = "auto",
        include_auto_generated: bool = True,
        method: DownloadMethod = DownloadMethod.AUTO,
        delay: float = None,
        batch_size: int = 10,
        batch_delay: float = 15.0,
        progress_callback: Optional[Callable] = None
    ) -> Tuple[List[TranscriptResult], Dict]:
        """
        배치 다운로드

        Args:
            videos: 영상 목록
            language: 자막 언어
            include_auto_generated: 자동생성 자막 포함
            method: 다운로드 방식 (API, yt-dlp, AUTO)
            delay: 요청 간격 (None이면 방식에 따라 자동)
            batch_size: 배치 크기
            batch_delay: 배치 간 대기 시간
            progress_callback: 진행률 콜백
        """

        # 상태 초기화
        self._consecutive_rate_limits = 0
        self._switched_to_ytdlp = False
        self._total_retries = 0
        self._last_request_time = 0.0

        # 🔴 v3.0: 요청 간격은 랜덤으로 자동 결정 (delay 파라미터는 하위 호환용으로 유지)
        use_ytdlp = method == DownloadMethod.YTDLP

        results = []
        total = len(videos)

        stats = {
            "total": total,
            "success": 0,
            "no_captions": 0,
            "disabled": 0,
            "unavailable": 0,
            "rate_limit": 0,
            "other_errors": 0,
            "total_words": 0,
            "total_retries": 0,
            "method_api": 0,
            "method_ytdlp": 0,
            "switched_to_ytdlp": False
        }

        # 🔴 v3.0: 평균 딜레이 표시용
        avg_delay = (self.API_MIN_DELAY + self.API_MAX_DELAY) / 2

        progress = DownloadProgress(
            total=total,
            completed=0,
            success=0,
            no_captions=0,
            failed=0,
            current_video="",
            current_status="대기",
            current_delay=avg_delay
        )

        method_str = {
            DownloadMethod.API: "API",
            DownloadMethod.YTDLP: "yt-dlp",
            DownloadMethod.AUTO: "자동 (API -> yt-dlp)"
        }[method]

        print(f"[Transcript] 🚀 다운로드 시작: {total}개 영상")
        print(f"[Transcript] 방식: {method_str}")
        print(f"[Transcript] 🔴 v3.0: 랜덤 딜레이 {self.API_MIN_DELAY}-{self.API_MAX_DELAY}초")

        for i, video in enumerate(videos):
            # 배치 대기
            if i > 0 and i % batch_size == 0:
                print(f"[Transcript] 배치 완료 ({i}/{total}), {batch_delay}초 대기...")
                time.sleep(batch_delay)

            video_id = video.get("video_id", "")
            video_title = video.get("title", video_id)

            progress.current_video = video_title[:50]
            progress.current_status = "다운로드 중"

            if progress_callback:
                progress_callback(progress)

            # 다운로드
            result = self.download_single(
                video_id=video_id,
                video_title=video_title,
                language=language,
                include_auto_generated=include_auto_generated,
                method=method
            )

            results.append(result)

            # 통계 업데이트
            progress.completed += 1

            if result.success:
                progress.success += 1
                stats["success"] += 1
                stats["total_words"] += result.word_count
            elif result.error_type == "no_caption":
                progress.no_captions += 1
                stats["no_captions"] += 1
            elif result.error_type == "disabled":
                stats["disabled"] += 1
                progress.failed += 1
            elif result.error_type == "unavailable":
                stats["unavailable"] += 1
                progress.failed += 1
            elif result.error_type == "rate_limit":
                stats["rate_limit"] += 1
                progress.failed += 1
            else:
                progress.failed += 1
                stats["other_errors"] += 1

            # 방식별 카운트
            if result.method_used == "api":
                stats["method_api"] += 1
                progress.method_api += 1
            else:
                stats["method_ytdlp"] += 1
                progress.method_ytdlp += 1

            # 전환 여부
            if self._switched_to_ytdlp:
                stats["switched_to_ytdlp"] = True
                progress.switched_to_ytdlp = True

            if progress_callback:
                progress_callback(progress)

            # 🔴 v3.0: 요청 간격은 download_single 내부에서 자동 적용
            # 배치 루프에서는 추가 딜레이 불필요 (각 다운로드에서 이미 적용됨)

        stats["total_retries"] = self._total_retries

        print(f"\n[Transcript] 완료! 성공: {stats['success']}/{total}")
        print(f"[Transcript] API: {stats['method_api']}개, yt-dlp: {stats['method_ytdlp']}개")

        if stats["switched_to_ytdlp"]:
            print(f"[Transcript] Rate Limit으로 인해 yt-dlp로 자동 전환됨")

        return results, stats

    # ═══════════════════════════════════════════════════════════════════
    # 파일 저장
    # ═══════════════════════════════════════════════════════════════════

    def save_results(
        self,
        results: List[TranscriptResult],
        channel_name: str,
        output_format: str = "json",
        include_failed: bool = True
    ) -> str:
        """결과 저장"""

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = "".join(c for c in channel_name if c.isalnum() or c in (' ', '-', '_')).strip()
        safe_name = safe_name[:50] if safe_name else "unknown"

        successful = [r for r in results if r.success]

        if not successful:
            return self._save_error_report(results, safe_name, timestamp)

        if output_format == "json":
            return self._save_as_json(results, safe_name, timestamp, include_failed)
        elif output_format == "txt":
            return self._save_as_txt(results, safe_name, timestamp, include_failed)
        elif output_format == "srt":
            return self._save_as_srt(results, safe_name, timestamp)
        elif output_format == "csv":
            return self._save_as_csv(results, safe_name, timestamp, include_failed)
        else:
            return self._save_as_json(results, safe_name, timestamp, include_failed)

    def _save_error_report(self, results, channel_name, timestamp):
        """에러 리포트"""
        filepath = self.output_dir / f"ERROR_REPORT_{channel_name}_{timestamp}.txt"

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"트랜스크립트 다운로드 에러 리포트\n")
            f.write(f"채널: {channel_name}\n")
            f.write(f"시간: {datetime.now().isoformat()}\n")
            f.write("=" * 80 + "\n\n")

            error_types = {}
            methods = {"api": 0, "yt-dlp": 0}
            for r in results:
                et = r.error_type or "unknown"
                error_types[et] = error_types.get(et, 0) + 1
                if r.method_used:
                    methods[r.method_used] = methods.get(r.method_used, 0) + 1

            f.write("통계\n")
            f.write(f"- 총 영상: {len(results)}개\n")
            f.write(f"- 성공: 0개\n")
            for et, count in error_types.items():
                f.write(f"- {et}: {count}개\n")
            f.write(f"\n사용 방식: API {methods['api']}개, yt-dlp {methods['yt-dlp']}개\n")

            if error_types.get("rate_limit", 0) > 0:
                f.write("\n" + "=" * 80 + "\n")
                f.write("Rate Limit 해결 방법:\n")
                f.write("1. 다운로드 방식을 'yt-dlp'로 변경하세요\n")
                f.write("2. 30분 후에 다시 시도하세요\n")
                f.write("3. '자동' 모드를 사용하세요\n")

            f.write("\n" + "=" * 80 + "\n\n")
            f.write("상세 목록 (처음 50개)\n\n")
            for i, r in enumerate(results[:50], 1):
                f.write(f"{i}. [{r.method_used}] {r.video_title or r.video_id}\n")
                f.write(f"   에러: {r.error[:80]}\n\n")

        return str(filepath)

    def _save_as_json(self, results, channel_name, timestamp, include_failed):
        """JSON 저장"""
        filepath = self.output_dir / f"transcripts_{channel_name}_{timestamp}.json"

        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]

        data = {
            "channel_name": channel_name,
            "downloaded_at": datetime.now().isoformat(),
            "statistics": {
                "total": len(results),
                "successful": len(successful),
                "failed": len(failed),
                "total_words": sum(r.word_count for r in successful),
                "methods": {
                    "api": sum(1 for r in results if r.method_used == "api"),
                    "yt-dlp": sum(1 for r in results if r.method_used == "yt-dlp")
                }
            },
            "transcripts": []
        }

        for r in successful:
            data["transcripts"].append({
                "video_id": r.video_id,
                "video_title": r.video_title,
                "language": r.language,
                "language_code": r.language_code,
                "is_auto_generated": r.is_auto_generated,
                "word_count": r.word_count,
                "method": r.method_used,
                "full_text": r.full_text,
                "segments": r.transcript
            })

        if include_failed and failed:
            data["failed_videos"] = [
                {
                    "video_id": r.video_id,
                    "video_title": r.video_title,
                    "error": r.error,
                    "error_type": r.error_type,
                    "method": r.method_used
                }
                for r in failed
            ]

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return str(filepath)

    def _save_as_txt(self, results, channel_name, timestamp, include_failed):
        """TXT 저장"""
        filepath = self.output_dir / f"transcripts_{channel_name}_{timestamp}.txt"

        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"채널: {channel_name}\n")
            f.write(f"다운로드: {datetime.now().isoformat()}\n")
            f.write(f"성공: {len(successful)}개 / 실패: {len(failed)}개\n")
            f.write("=" * 80 + "\n\n")

            if successful:
                for i, r in enumerate(successful, 1):
                    f.write("─" * 80 + "\n")
                    f.write(f"[{i}/{len(successful)}] {r.video_title} [{r.method_used}]\n")
                    f.write("─" * 80 + "\n")
                    f.write(f"영상 ID: {r.video_id}\n")
                    f.write(f"언어: {r.language} ({r.language_code})")
                    if r.is_auto_generated:
                        f.write(" [자동생성]")
                    f.write(f"\n단어 수: {r.word_count:,}\n\n")
                    f.write(r.full_text)
                    f.write("\n\n")
            else:
                f.write("성공적으로 다운로드된 자막이 없습니다.\n\n")

            if include_failed and failed:
                f.write("\n" + "=" * 80 + "\n")
                f.write(f"실패한 영상 목록 ({len(failed)}개)\n")
                f.write("=" * 80 + "\n\n")

                for r in failed[:30]:
                    f.write(f"[{r.method_used}] {r.video_title or r.video_id}\n")
                    f.write(f"   에러: {r.error}\n\n")

        return str(filepath)

    def _save_as_srt(self, results, channel_name, timestamp):
        """SRT ZIP 저장"""
        successful = [r for r in results if r.success and r.transcript]

        if not successful:
            return self._save_error_report(results, channel_name, timestamp)

        zip_path = self.output_dir / f"transcripts_{channel_name}_{timestamp}.zip"

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for r in successful:
                srt_content = self._convert_to_srt(r.transcript)
                safe_title = "".join(c for c in r.video_title if c.isalnum() or c in (' ', '-', '_'))
                safe_title = safe_title[:50].strip()
                filename = f"{r.video_id}_{safe_title}.srt"
                zipf.writestr(filename, srt_content)

            summary = f"채널: {channel_name}\n"
            summary += f"다운로드: {datetime.now().isoformat()}\n"
            summary += f"파일 수: {len(successful)}개\n"
            zipf.writestr("_README.txt", summary)

        return str(zip_path)

    def _convert_to_srt(self, transcript: List[Dict]) -> str:
        """SRT 변환"""
        def format_time(seconds: float) -> str:
            hours = int(seconds // 3600)
            minutes = int((seconds % 3600) // 60)
            secs = int(seconds % 60)
            millis = int((seconds % 1) * 1000)
            return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

        srt_lines = []
        for i, item in enumerate(transcript, 1):
            start = item.get('start', 0)
            duration = item.get('duration', 0)
            end = start + duration
            text = item.get('text', '')

            srt_lines.append(str(i))
            srt_lines.append(f"{format_time(start)} --> {format_time(end)}")
            srt_lines.append(text)
            srt_lines.append("")

        return "\n".join(srt_lines)

    def _save_as_csv(self, results, channel_name, timestamp, include_failed):
        """CSV 저장"""
        filepath = self.output_dir / f"transcripts_{channel_name}_{timestamp}.csv"

        with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "video_id", "video_title", "status", "method", "language",
                "is_auto_generated", "word_count", "error", "full_text"
            ])

            for r in results:
                writer.writerow([
                    r.video_id,
                    r.video_title,
                    "성공" if r.success else "실패",
                    r.method_used,
                    r.language or "",
                    r.is_auto_generated if r.success else "",
                    r.word_count if r.success else 0,
                    r.error if not r.success else "",
                    r.full_text if r.success else ""
                ])

        return str(filepath)

    def get_available_languages(self, video_id: str) -> List[Dict]:
        """영상에서 사용 가능한 자막 언어 목록 조회"""
        try:
            transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
            languages = []
            for t in transcript_list:
                languages.append({
                    "language": t.language_code,
                    "name": t.language,
                    "is_generated": t.is_generated,
                    "is_translatable": t.is_translatable
                })
            return languages
        except Exception as e:
            print(f"[Transcript] 언어 목록 조회 오류: {e}")
            return []


# ═══════════════════════════════════════════════════════════════════
# ⭐ v4.4: TranscriptFormatter 클래스 (SRT/VTT/TXT 변환)
# ═══════════════════════════════════════════════════════════════════

class TranscriptFormatter:
    """
    자막 형식 변환 클래스

    지원 형식:
    - SRT: SubRip Text (00:00:00,000 --> 00:00:05,000)
    - VTT: WebVTT (00:00:00.000 --> 00:00:05.000)
    - TXT: Plain Text (텍스트만)
    - JSON: 원본 JSON 형식
    """

    @staticmethod
    def _format_srt_time(seconds: float) -> str:
        """SRT 타임코드 포맷 (00:00:00,000)"""
        if seconds < 0:
            seconds = 0
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"

    @staticmethod
    def _format_vtt_time(seconds: float) -> str:
        """VTT 타임코드 포맷 (00:00:00.000)"""
        if seconds < 0:
            seconds = 0
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"

    @classmethod
    def to_srt(cls, transcript: List[Dict], include_index: bool = True) -> str:
        """
        SRT 형식으로 변환

        Args:
            transcript: [{"start": float, "duration": float, "text": str}, ...]
            include_index: 자막 번호 포함 여부

        Returns:
            SRT 문자열
        """
        lines = []
        for i, item in enumerate(transcript, 1):
            start = item.get('start', 0)
            duration = item.get('duration', 0)
            end = start + duration
            text = item.get('text', '').strip()

            if not text:
                continue

            if include_index:
                lines.append(str(i))
            lines.append(f"{cls._format_srt_time(start)} --> {cls._format_srt_time(end)}")
            lines.append(text)
            lines.append("")

        return "\n".join(lines)

    @classmethod
    def to_vtt(cls, transcript: List[Dict], include_header: bool = True) -> str:
        """
        WebVTT 형식으로 변환

        Args:
            transcript: [{"start": float, "duration": float, "text": str}, ...]
            include_header: WEBVTT 헤더 포함 여부

        Returns:
            VTT 문자열
        """
        lines = []

        if include_header:
            lines.append("WEBVTT")
            lines.append("")

        for i, item in enumerate(transcript, 1):
            start = item.get('start', 0)
            duration = item.get('duration', 0)
            end = start + duration
            text = item.get('text', '').strip()

            if not text:
                continue

            # VTT는 cue identifier가 선택적
            lines.append(f"{i}")
            lines.append(f"{cls._format_vtt_time(start)} --> {cls._format_vtt_time(end)}")
            lines.append(text)
            lines.append("")

        return "\n".join(lines)

    @classmethod
    def to_txt(cls, transcript: List[Dict], include_timestamps: bool = False) -> str:
        """
        Plain Text 형식으로 변환

        Args:
            transcript: [{"start": float, "duration": float, "text": str}, ...]
            include_timestamps: 타임스탬프 포함 여부

        Returns:
            텍스트 문자열
        """
        if include_timestamps:
            lines = []
            for item in transcript:
                start = item.get('start', 0)
                text = item.get('text', '').strip()
                if text:
                    # [00:00:00] 형식
                    minutes = int(start // 60)
                    secs = int(start % 60)
                    lines.append(f"[{minutes:02d}:{secs:02d}] {text}")
            return "\n".join(lines)
        else:
            # 텍스트만 연결
            texts = [item.get('text', '').strip() for item in transcript]
            return " ".join(t for t in texts if t)

    @classmethod
    def to_json(cls, transcript: List[Dict]) -> str:
        """
        JSON 형식으로 변환

        Args:
            transcript: 자막 데이터

        Returns:
            JSON 문자열
        """
        return json.dumps(transcript, ensure_ascii=False, indent=2)

    @classmethod
    def convert(cls, transcript: List[Dict], format: str = 'srt', **kwargs) -> str:
        """
        자막 형식 변환 (통합 메서드)

        Args:
            transcript: 자막 데이터
            format: 'srt', 'vtt', 'txt', 'json'
            **kwargs: 각 형식별 추가 옵션

        Returns:
            변환된 문자열
        """
        format_lower = format.lower().strip()

        if format_lower == 'srt':
            return cls.to_srt(transcript, **kwargs)
        elif format_lower == 'vtt':
            return cls.to_vtt(transcript, **kwargs)
        elif format_lower == 'txt':
            return cls.to_txt(transcript, **kwargs)
        elif format_lower == 'json':
            return cls.to_json(transcript)
        else:
            raise ValueError(f"지원하지 않는 형식: {format}. 지원 형식: srt, vtt, txt, json")

    @classmethod
    def save_file(
        cls,
        transcript: List[Dict],
        filepath: str,
        format: str = None,
        encoding: str = 'utf-8'
    ) -> str:
        """
        자막을 파일로 저장

        Args:
            transcript: 자막 데이터
            filepath: 저장 경로
            format: 형식 (None이면 확장자에서 추론)
            encoding: 인코딩

        Returns:
            저장된 파일 경로
        """
        path = Path(filepath)

        # 형식 결정
        if format is None:
            ext = path.suffix.lower().lstrip('.')
            format = ext if ext in ['srt', 'vtt', 'txt', 'json'] else 'srt'

        # 변환
        content = cls.convert(transcript, format)

        # 저장
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, 'w', encoding=encoding) as f:
            f.write(content)

        return str(path)

    @classmethod
    def get_word_count(cls, transcript: List[Dict]) -> int:
        """자막의 총 단어 수 계산"""
        total = 0
        for item in transcript:
            text = item.get('text', '')
            # 한국어/영어 모두 고려한 단어 수
            total += len(text.split())
        return total

    @classmethod
    def get_duration(cls, transcript: List[Dict]) -> float:
        """자막의 총 재생 시간 (초)"""
        if not transcript:
            return 0.0
        last = transcript[-1]
        return last.get('start', 0) + last.get('duration', 0)


def get_transcript_downloader(output_dir: str = "data/transcripts") -> YouTubeTranscriptDownloader:
    """트랜스크립트 다운로더 인스턴스 생성"""
    return YouTubeTranscriptDownloader(output_dir)


# ═══════════════════════════════════════════════════════════════════
# 쿠키 파일 생성 가이드
# ═══════════════════════════════════════════════════════════════════

def create_cookies_guide() -> str:
    """쿠키 파일 생성 가이드 출력"""
    guide = """
================================================================================
           YouTube 쿠키 파일 생성 가이드 (Rate Limit 해결)
================================================================================

  1. Chrome 확장 프로그램 설치:
     - Chrome 웹스토어에서 "Get cookies.txt LOCALLY" 검색 후 설치
     - 또는 "EditThisCookie" 설치

  2. YouTube에 로그인 (이미 로그인되어 있으면 스킵)

  3. YouTube 페이지에서 확장 프로그램 클릭
     - "Export" 또는 "Download cookies.txt" 클릭

  4. 파일 저장 위치:
     C:\\Users\\KIMJAEHEON\\longform\\data\\cookies.txt

  5. Streamlit 앱 재시작

================================================================================
  주의사항:
  - 쿠키 파일은 주기적으로 갱신 필요 (2~4주마다)
  - YouTube에서 로그아웃하면 쿠키 무효화됨
  - 쿠키 파일을 다른 사람과 공유하지 마세요!
================================================================================
"""
    print(guide)
    return guide


def check_cookies_status() -> dict:
    """쿠키 파일 상태 확인"""
    status = {
        "cookies_file_found": False,
        "cookies_file_path": None,
        "cookies_file_size": 0,
        "yt_dlp_available": False,
        "api_available": API_AVAILABLE,
    }

    # 쿠키 파일 확인
    for path in YouTubeTranscriptDownloader.COOKIES_FILE_PATHS:
        if os.path.exists(path):
            size = os.path.getsize(path)
            if size > 100:
                status["cookies_file_found"] = True
                status["cookies_file_path"] = path
                status["cookies_file_size"] = size
                break

    # yt-dlp 확인
    try:
        result = subprocess.run(
            ["yt-dlp", "--version"],
            capture_output=True,
            text=True,
            timeout=10
        )
        status["yt_dlp_available"] = result.returncode == 0
    except:
        pass

    return status
