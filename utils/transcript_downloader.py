# -*- coding: utf-8 -*-
"""
YouTube 트랜스크립트 다운로더 (하이브리드 버전)

방식:
1. API: youtube-transcript-api 사용 (빠름, Rate Limit 취약)
2. yt-dlp: yt-dlp 사용 (느림, 안정적)
3. 자동: API 먼저 시도, 429 에러시 yt-dlp 자동 전환
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


class DownloadMethod(Enum):
    """다운로드 방식"""
    API = "api"           # youtube-transcript-api
    YTDLP = "yt-dlp"      # yt-dlp
    AUTO = "auto"         # 자동 (API 실패시 yt-dlp)


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
    """YouTube 트랜스크립트 다운로더 (하이브리드)"""

    # 언어 우선순위
    DEFAULT_LANGUAGE_PRIORITY = ["en", "ko", "ja", "zh-Hans", "zh-Hant", "es", "de", "fr", "pt", "ru"]

    # 설정
    API_DEFAULT_DELAY = 2.0      # API 요청 간격
    YTDLP_DEFAULT_DELAY = 1.0    # yt-dlp 요청 간격
    BATCH_SIZE = 10
    BATCH_DELAY = 15.0
    MAX_RETRIES = 2
    RATE_LIMIT_THRESHOLD = 3     # 연속 429 에러 N회 발생 시 yt-dlp 전환

    def __init__(self, output_dir: str = "data/transcripts"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir = Path(tempfile.gettempdir()) / "yt_transcripts"
        self.temp_dir.mkdir(exist_ok=True)

        # 상태 추적
        self._consecutive_rate_limits = 0
        self._switched_to_ytdlp = False
        self._current_method = DownloadMethod.API
        self._total_retries = 0

        # yt-dlp 사용 가능 여부 확인
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
            if result.returncode == 0:
                print(f"[Transcript] yt-dlp 버전: {result.stdout.strip()}")
                return True
        except FileNotFoundError:
            print("[Transcript] yt-dlp가 설치되지 않았습니다. (pip install yt-dlp)")
        except Exception as e:
            print(f"[Transcript] yt-dlp 확인 오류: {e}")
        return False

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
        단일 영상 트랜스크립트 다운로드

        Args:
            video_id: YouTube 영상 ID
            video_title: 영상 제목
            language: 자막 언어 ("auto", "en", "ko" 등)
            include_auto_generated: 자동생성 자막 포함
            method: 다운로드 방식 (API, yt-dlp, 자동)
            retry_count: 재시도 횟수
        """

        # 방식 결정
        if method == DownloadMethod.AUTO:
            # 자동 모드: 이미 yt-dlp로 전환되었으면 계속 yt-dlp 사용
            if self._switched_to_ytdlp:
                actual_method = DownloadMethod.YTDLP
            else:
                actual_method = DownloadMethod.API
        else:
            actual_method = method

        # API 사용 불가 시 yt-dlp로
        if actual_method == DownloadMethod.API and not API_AVAILABLE:
            print("[Transcript] API 사용 불가, yt-dlp로 전환")
            actual_method = DownloadMethod.YTDLP

        # yt-dlp 사용 불가 시 API로
        if actual_method == DownloadMethod.YTDLP and not self._ytdlp_available:
            print("[Transcript] yt-dlp 사용 불가, API로 전환")
            actual_method = DownloadMethod.API

        # 다운로드 실행
        if actual_method == DownloadMethod.API:
            result = self._download_via_api(
                video_id, video_title, language,
                include_auto_generated, retry_count
            )

            # API에서 429 에러 발생 시 자동 전환 (AUTO 모드일 때)
            if (method == DownloadMethod.AUTO and
                result.error_type == "rate_limit" and
                self._ytdlp_available):

                self._consecutive_rate_limits += 1
                print(f"[Transcript] 연속 Rate Limit: {self._consecutive_rate_limits}회")

                if self._consecutive_rate_limits >= self.RATE_LIMIT_THRESHOLD:
                    print(f"[Transcript] yt-dlp로 자동 전환!")
                    self._switched_to_ytdlp = True

                    # yt-dlp로 재시도
                    return self._download_via_ytdlp(
                        video_id, video_title, language,
                        include_auto_generated, 0
                    )

            elif result.success:
                self._consecutive_rate_limits = 0  # 성공 시 카운터 리셋

            return result

        else:  # yt-dlp
            return self._download_via_ytdlp(
                video_id, video_title, language,
                include_auto_generated, retry_count
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
                    method_used="api"
                )

            elif "NoTranscript" in error_msg or "no transcript" in error_msg.lower():
                return TranscriptResult(
                    success=False,
                    video_id=video_id,
                    video_title=video_title,
                    error="자막 없음",
                    error_type="no_caption",
                    method_used="api"
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
        yt-dlp를 사용한 자막 다운로드 (Windows 호환 완전 수정 버전)

        수정 사항:
        1. Windows 경로 호환성 보장 (os.path.join 사용)
        2. cwd 제거하고 절대 경로 사용
        3. 디버그 출력 추가
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
            sub_lang = "en,ko,ja,zh-Hans,es,de,fr"
        else:
            sub_lang = f"{language},en"

        # ⭐ Windows 호환 경로 설정 (os.path 사용)
        import shutil
        output_dir = os.path.join(tempfile.gettempdir(), "yt_subs", video_id)

        # 디렉토리 생성 (기존 삭제 후 재생성)
        if os.path.exists(output_dir):
            shutil.rmtree(output_dir, ignore_errors=True)
        os.makedirs(output_dir, exist_ok=True)

        # ⭐ Windows 경로 템플릿 (절대 경로 사용)
        output_template = os.path.join(output_dir, "%(id)s.%(ext)s")

        try:
            # ⭐ 수정된 yt-dlp 명령어
            cmd = [
                "yt-dlp",
                "--skip-download",
                "--write-auto-sub",          # 자동 자막
                "--write-sub",               # 수동 자막
                "--sub-lang", sub_lang,
                "--sub-format", "vtt/srt/best",
                "-o", output_template,       # ⭐ 절대 경로 템플릿
                "--no-check-certificate",
                "--no-playlist",
                video_url
            ]

            print(f"[yt-dlp] 실행: {video_id}")
            print(f"[yt-dlp] 출력 디렉토리: {output_dir}")
            print(f"[yt-dlp] 명령어: {' '.join(cmd)}")

            # ⭐ subprocess 실행 (cwd 제거!)
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
                encoding='utf-8',
                errors='replace'
                # cwd 제거 - 절대 경로 사용
            )

            # 실행 결과 출력
            print(f"[yt-dlp] return code: {result.returncode}")
            if result.stdout:
                print(f"[yt-dlp] stdout: {result.stdout[:300]}")
            if result.stderr:
                print(f"[yt-dlp] stderr: {result.stderr[:300]}")

            # ⭐ 생성된 파일 확인
            output_path = Path(output_dir)
            all_files = list(output_path.glob("*")) if output_path.exists() else []
            print(f"[yt-dlp] 생성된 파일들: {[f.name for f in all_files]}")

            # 자막 파일 찾기
            subtitle_file = None
            for ext in ['vtt', 'srt', 'json3', 'ttml']:
                candidates = list(output_path.glob(f"*.{ext}"))
                if candidates:
                    subtitle_file = candidates[0]
                    break

            if subtitle_file:
                print(f"[yt-dlp] 자막 파일 발견: {subtitle_file.name}")
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
                else:
                    print(f"[yt-dlp] 자막 파싱 실패: {subtitle_file.name}")
            else:
                print(f"[yt-dlp] 자막 파일을 찾을 수 없음")

            # 정리
            self._cleanup_directory(output_path)

            # 에러 메시지 상세화
            error_detail = "자막을 찾을 수 없습니다."
            if result.stderr:
                stderr_lower = result.stderr.lower()
                if "no subtitles" in stderr_lower:
                    error_detail = "이 영상에 자막이 없습니다."
                elif "unavailable" in stderr_lower:
                    error_detail = "영상을 사용할 수 없습니다."
                elif "private" in stderr_lower:
                    error_detail = "비공개 영상입니다."
                elif "429" in result.stderr or "too many" in stderr_lower:
                    error_detail = "Rate Limit (429)"
                else:
                    error_detail = f"yt-dlp: {result.stderr[:80]}"

            return TranscriptResult(
                success=False,
                video_id=video_id,
                video_title=video_title,
                error=error_detail,
                error_type="no_caption",
                method_used="yt-dlp"
            )

        except subprocess.TimeoutExpired:
            self._cleanup_directory(Path(output_dir))
            return TranscriptResult(
                success=False,
                video_id=video_id,
                video_title=video_title,
                error="다운로드 시간 초과 (120초)",
                error_type="timeout",
                method_used="yt-dlp"
            )

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
            print(f"[yt-dlp] 예외: {error_msg}")

            # 재시도
            if retry_count < self.MAX_RETRIES:
                print(f"[yt-dlp] 재시도 {retry_count + 1}/{self.MAX_RETRIES}")
                time.sleep(3)
                return self._download_via_ytdlp(
                    video_id, video_title, language,
                    include_auto_generated, retry_count + 1
                )

            return TranscriptResult(
                success=False,
                video_id=video_id,
                video_title=video_title,
                error=f"오류: {error_msg[:100]}",
                error_type="other",
                method_used="yt-dlp"
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
        """VTT 파싱 (개선)"""
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        transcript = []

        # VTT 헤더 제거
        if content.startswith("WEBVTT"):
            # 첫 번째 빈 줄 이후부터 파싱
            parts = content.split("\n\n", 1)
            content = parts[1] if len(parts) > 1 else content

        # 블록 단위로 분리
        blocks = re.split(r'\n\s*\n', content)

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
                elif timestamp_line and line.strip():
                    text_lines.append(line)

            if timestamp_line and text_lines:
                # 타임스탬프 파싱
                match = re.match(
                    r'(\d{1,2}:)?(\d{2}):(\d{2})[.,](\d{3})\s*-->\s*(\d{1,2}:)?(\d{2}):(\d{2})[.,](\d{3})',
                    timestamp_line
                )

                if match:
                    groups = match.groups()

                    # 시작 시간
                    start_h = int(groups[0].replace(":", "")) if groups[0] else 0
                    start_m = int(groups[1])
                    start_s = int(groups[2])
                    start_ms = int(groups[3])
                    start = start_h * 3600 + start_m * 60 + start_s + start_ms / 1000

                    # 종료 시간
                    end_h = int(groups[4].replace(":", "")) if groups[4] else 0
                    end_m = int(groups[5])
                    end_s = int(groups[6])
                    end_ms = int(groups[7])
                    end = end_h * 3600 + end_m * 60 + end_s + end_ms / 1000

                    # 텍스트 정리 (HTML 태그 제거)
                    text = " ".join(text_lines)
                    text = re.sub(r'<[^>]+>', '', text)  # HTML 태그 제거
                    text = re.sub(r'\{[^}]+\}', '', text)  # {...} 제거
                    text = text.strip()

                    if text:
                        transcript.append({
                            "start": start,
                            "duration": end - start,
                            "text": text
                        })

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

        # 요청 간격 설정
        if delay is None:
            delay = self.API_DEFAULT_DELAY if method != DownloadMethod.YTDLP else self.YTDLP_DEFAULT_DELAY

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

        progress = DownloadProgress(
            total=total,
            completed=0,
            success=0,
            no_captions=0,
            failed=0,
            current_video="",
            current_status="대기",
            current_delay=delay
        )

        method_str = {
            DownloadMethod.API: "API",
            DownloadMethod.YTDLP: "yt-dlp",
            DownloadMethod.AUTO: "자동 (API -> yt-dlp)"
        }[method]

        print(f"[Transcript] 다운로드 시작: {total}개 영상")
        print(f"[Transcript] 방식: {method_str}, 요청 간격: {delay}초")

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

            # 요청 간격
            if i < total - 1:
                # yt-dlp 전환 후에는 간격 줄임
                actual_delay = self.YTDLP_DEFAULT_DELAY if self._switched_to_ytdlp else delay
                # 랜덤 지터 추가
                jitter = random.uniform(0.1, 0.5)
                time.sleep(actual_delay + jitter)

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


def get_transcript_downloader(output_dir: str = "data/transcripts") -> YouTubeTranscriptDownloader:
    """트랜스크립트 다운로더 인스턴스 생성"""
    return YouTubeTranscriptDownloader(output_dir)
