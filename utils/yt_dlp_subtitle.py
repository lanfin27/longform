# -*- coding: utf-8 -*-
"""
yt-dlp 자막 다운로더 (v2.0)

변경사항:
1. 쿠키 없이 먼저 시도
2. 다중 브라우저 폴백 (Firefox -> Edge -> Chrome 복사본)
3. Chrome 쿠키 복사 오류 자동 처리 (GitHub Issue #7271)
"""

import os
import subprocess
import tempfile
import shutil
import re
from pathlib import Path
from typing import Optional, List, Tuple


class YtDlpSubtitleDownloader:
    """yt-dlp 자막 다운로더 (다중 쿠키 폴백 지원)"""

    # 지원 언어
    SUBTITLE_LANGS = "en,ko,ja,zh-Hans,es,de,fr"

    # 브라우저 우선순위 (Chrome 쿠키 오류 대비)
    # Chrome 실행 중일 때 쿠키 DB 잠김 → 다른 브라우저 사용
    BROWSER_PRIORITY = [
        None,           # 1. 쿠키 없이 시도 (공개 자막)
        "firefox",      # 2. Firefox (잠금 없음)
        "edge",         # 3. Edge (Windows 기본)
        "chrome_copy",  # 4. Chrome 쿠키 복사본
        "chrome",       # 5. Chrome 직접 (마지막 시도)
    ]

    def __init__(self):
        self.temp_dir = Path(tempfile.gettempdir()) / "yt_subs"
        self.temp_dir.mkdir(exist_ok=True)

        # Chrome 쿠키 복사본 경로
        self.chrome_cookie_copy = self.temp_dir / "chrome_cookies_copy"

        # yt-dlp 사용 가능 여부
        self._ytdlp_available = self._check_ytdlp()

    def _check_ytdlp(self) -> bool:
        """yt-dlp 설치 확인"""
        try:
            result = subprocess.run(
                ["yt-dlp", "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.returncode == 0
        except Exception:
            return False

    def download_subtitle(
        self,
        video_id: str,
        output_dir: str = None
    ) -> Tuple[Optional[str], str]:
        """
        자막 다운로드 (다중 폴백)

        Args:
            video_id: YouTube 영상 ID
            output_dir: 출력 디렉토리 (기본: 임시 디렉토리)

        Returns:
            (자막 파일 경로 또는 None, 상태 메시지)
        """

        if not self._ytdlp_available:
            return None, "ytdlp_not_installed"

        output_dir = output_dir or str(self.temp_dir / video_id)

        # 기존 디렉토리 정리
        if os.path.exists(output_dir):
            shutil.rmtree(output_dir, ignore_errors=True)
        os.makedirs(output_dir, exist_ok=True)

        video_url = f"https://www.youtube.com/watch?v={video_id}"

        print(f"[yt-dlp] 자막 다운로드 시작: {video_id}")

        # 각 브라우저/방식으로 시도
        for browser in self.BROWSER_PRIORITY:
            browser_name = browser or "no_cookie"
            print(f"[yt-dlp]   시도: {browser_name}")

            try:
                result = self._try_download(video_id, video_url, output_dir, browser)

                if result:
                    print(f"[yt-dlp] 성공: {browser_name}")
                    return result, f"success:{browser_name}"

            except Exception as e:
                error_msg = str(e)

                # Chrome 쿠키 오류 감지 (GitHub Issue #7271)
                if "Could not copy Chrome cookie database" in error_msg:
                    print(f"[yt-dlp]   Chrome 쿠키 잠김, 다음 방식 시도")
                    continue

                # 영상에 자막이 없는 경우
                if "no subtitles" in error_msg.lower() or "there are no subtitles" in error_msg.lower():
                    print(f"[yt-dlp]   자막 없음 (영상에 자막 없음)")
                    return None, "no_subtitle"

                print(f"[yt-dlp]   실패: {str(e)[:100]}")

        print(f"[yt-dlp] 모든 방식 실패")
        return None, "all_failed"

    def _try_download(
        self,
        video_id: str,
        video_url: str,
        output_dir: str,
        browser: Optional[str]
    ) -> Optional[str]:
        """단일 방식으로 다운로드 시도"""

        # 기본 명령어
        cmd = [
            "yt-dlp",
            "--skip-download",
            "--write-auto-sub",
            "--write-sub",
            "--sub-lang", self.SUBTITLE_LANGS,
            "--sub-format", "vtt/srt/best",
            "-o", os.path.join(output_dir, "%(id)s.%(ext)s"),
            "--no-check-certificate",
            "--no-playlist",
            "--no-warnings",
            "--socket-timeout", "30",
            "--retries", "3",
        ]

        # 브라우저별 쿠키 옵션
        if browser is None:
            # 쿠키 없이 시도
            pass
        elif browser == "chrome_copy":
            # Chrome 쿠키 복사본 사용
            cookie_file = self._copy_chrome_cookies()
            if cookie_file:
                cmd.extend(["--cookies", cookie_file])
            else:
                return None  # 복사 실패 시 스킵
        elif browser == "chrome":
            # Chrome 직접 (마지막 시도)
            cmd.extend(["--cookies-from-browser", "chrome"])
        else:
            # Firefox, Edge 등
            cmd.extend(["--cookies-from-browser", browser])

        # Node.js 런타임 (있으면 추가)
        if self._check_nodejs():
            cmd.extend(["--js-runtimes", "nodejs"])

        cmd.append(video_url)

        # 실행
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            encoding='utf-8',
            errors='replace'
        )

        # 결과 확인
        if result.returncode != 0:
            error = result.stderr or result.stdout

            # Chrome 쿠키 오류 체크
            if "Could not copy Chrome cookie database" in error:
                raise Exception("Could not copy Chrome cookie database")

            # 자막 없음 체크
            if "no subtitles" in error.lower() or "there are no subtitles" in error.lower():
                raise Exception("no subtitles available")

            return None

        # 자막 파일 찾기
        subtitle_file = self._find_subtitle_file(output_dir, video_id)
        return subtitle_file

    def _copy_chrome_cookies(self) -> Optional[str]:
        """
        Chrome 쿠키 파일 수동 복사
        (Chrome 실행 중에도 SQLite backup API로 읽기 가능)
        """

        # Chrome 쿠키 경로 (Windows)
        chrome_paths = [
            Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/User Data/Default/Network/Cookies",
            Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/User Data/Default/Cookies",
        ]

        for chrome_cookie_path in chrome_paths:
            if chrome_cookie_path.exists():
                try:
                    import sqlite3

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

    def _check_nodejs(self) -> bool:
        """Node.js 설치 확인"""
        try:
            result = subprocess.run(
                ["node", "--version"],
                capture_output=True,
                timeout=5
            )
            return result.returncode == 0
        except Exception:
            return False

    def _find_subtitle_file(self, output_dir: str, video_id: str) -> Optional[str]:
        """자막 파일 찾기"""

        output_path = Path(output_dir)

        if not output_path.exists():
            return None

        # 모든 자막 파일 찾기
        subtitle_files = []
        for ext in ['vtt', 'srt', 'json3', 'ttml']:
            subtitle_files.extend(output_path.glob(f"*.{ext}"))

        if not subtitle_files:
            return None

        print(f"[yt-dlp]   발견된 파일: {[f.name for f in subtitle_files]}")

        # 우선순위: 한국어 > 영어 > 기타
        priority_order = []

        for f in subtitle_files:
            fname = f.name.lower()
            score = 100

            # 언어 우선순위
            if ".ko." in fname or ".ko-" in fname:
                score -= 30  # 한국어 최우선
            elif ".en." in fname or ".en-" in fname:
                score -= 20  # 영어 그 다음

            # 자동생성 여부
            if ".auto." in fname or "-orig" in fname:
                score += 10  # 자동생성은 후순위

            # 포맷 우선순위
            if fname.endswith('.vtt'):
                score -= 5
            elif fname.endswith('.srt'):
                score -= 3

            priority_order.append((score, f))

        # 정렬 후 첫 번째 반환
        priority_order.sort(key=lambda x: x[0])

        if priority_order:
            return str(priority_order[0][1])

        return None


# 싱글톤
_downloader = None


def get_subtitle_downloader() -> YtDlpSubtitleDownloader:
    """YtDlpSubtitleDownloader 싱글톤"""
    global _downloader
    if _downloader is None:
        _downloader = YtDlpSubtitleDownloader()
    return _downloader


def download_subtitle(video_id: str) -> Tuple[Optional[str], str]:
    """편의 함수: 자막 다운로드"""
    downloader = get_subtitle_downloader()
    return downloader.download_subtitle(video_id)
