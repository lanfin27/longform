# -*- coding: utf-8 -*-
"""
Claude Code CLI 래퍼 (v13.18)

변경사항:
- ⭐ v13.18: 프롬프트 템플릿 축약 문제 해결
  [핵심 변경]
  - "Template too long" 축약 로직 제거!
  - 템플릿을 별도 파일로 저장 후 Claude Code가 직접 Read()
  - 템플릿 100% 적용 보장 (캐릭터 추출 규칙 등 누락 방지)
  [이전 문제]
  - 16,635 토큰 템플릿이 5,000자로 축약됨
  - 캐릭터 추출 규칙 등 핵심 내용 누락
  [해결 방법]
  - 템플릿 파일 경로만 프롬프트에 포함
  - Claude Code에게 파일 전체 읽기 지시
  - 토큰 절약 + 완전한 템플릿 적용
- ⭐ v13.17: 프롬프트 토큰 제한 + 캐릭터 추출 + PowerShell 오류 수정
  [토큰 제한]
  - MAX_PROMPT_TOKENS = 20,000 (Claude Code 25,000 한계의 80%)
  - estimate_tokens(): 한글/영어 혼합 토큰 추정 함수
  - check_prompt_token_limit(): 프롬프트 토큰 검증 함수
  [캐릭터 추출 규칙]
  - 캐릭터(characters) 필드 생성 규칙을 프롬프트 최상단에 배치
  - 인물 있는 씬 vs 없는 씬 판단 기준 명시
  - 빈 characters 배열 방지 규칙 강조
  [Python 스크립트 금지]
  - .py 파일 생성/저장 금지 규칙 추가
  - scenes.json 직접 수정 지시
- ⭐ v13.14: PowerShell 한글 인코딩 + script_ko 보존 수정
  [인코딩 수정]
  - 프롬프트 파일(.md) UTF-8 BOM으로 저장 (utf-8-sig)
  - PowerShell 스크립트에 완전한 인코딩 설정 추가
  - 프롬프트 미리보기 한글 정상 표시
  [script_ko 보존]
  - Bundle 병합 시 script_ko, script_en 복사 제외 (각 씬 고유 데이터)
  - _load_original_scripts(): 원본 스크립트 로드 (scenes_original.json, 백업, SRT)
  - backup_original_scenes_before_analysis(): 분석 전 원본 백업
  - 모든 씬에 원본 script_ko 보존 보장
- ⭐ v13.13: Bundle 병합 기능 추가
  - save_bundle_info_for_claude_code(): 분석 전 Bundle 정보 저장
  - apply_bundle_merge_after_claude_code(): 분석 후 Bundle 병합
  - sync_claude_code_results_with_bundle_merge(): UI용 연동 함수
  - 대표 씬 분석 결과를 묶음 내 다른 씬에 자동 복사
- ⭐ v13.12: UTF-8 BOM 인코딩 오류 수정
  - 모든 JSON 파일 읽기에 'utf-8-sig' 인코딩 사용 (BOM 자동 처리)
  - load_json_safe() 헬퍼 함수 추가 (여러 인코딩 순차 시도)
  - _progress.json, scenes.json 읽기 오류 해결
- ⭐ v13.11: 배치 씬 ID 계산 수정, 완료 상태 감지 개선
- ⭐ v13.10: PowerShell 한글 인코딩 오류 수정
  - PowerShell 스크립트(.ps1)를 UTF-8 BOM으로 저장 (encoding='utf-8-sig')
  - 모든 스크립트 메시지를 영어로 변경 (인코딩 문제 완전 방지)
  - 배치 파일(.bat)도 영어로 변경
- ⭐ v13.9: CMD 창 즉시 닫힘 문제 해결
  - 배치 파일에서 exit → pause로 변경하여 창 유지
  - PowerShell에서 -p 옵션 대신 @파일 참조 방식 사용 (긴 프롬프트 지원)
  - 사용자가 아무 키나 누를 때까지 창 유지
- ⭐ v13.8: Raw Mode Not Supported 에러 완전 해결
  - stdin 리다이렉션 (<) 대신 --print -p 옵션 사용
  - PowerShell 스크립트로 프롬프트 파일 읽어서 -p 옵션에 전달
  - Ink raw mode 에러 근본적 해결
- ⭐ v13.7: 씬 범위 선택 버그 완전 수정
  - run_scene_analysis_agent()에 selected_scene_ids 파라미터 추가
  - build_scene_analysis_prompt() 호출 시 selected_scene_ids 전달
  - 프롬프트에 선택된 씬 ID 목록이 정확히 포함됨
- ⭐ v13.6: 실시간 진행률 표시 수정
  - Python에서 배치 실행 전에 진행률 파일 미리 생성
  - Streamlit 폴링이 즉시 시작 가능하도록 개선
- ⭐ v13.5: 씬 범위 선택 문제 수정
  - selected_scene_ids 파라미터 추가
  - 프롬프트 맨 앞에 분석 대상 씬 ID 목록 명시
  - 다른 씬 수정 금지 지시 강화
  - 올바른 필터링 코드 예시 포함
- ⭐ v13.4: 진행률 추적 + 자동 완료 + 데이터 동기화
  - 진행률 파일 (_progress.json) 생성 및 모니터링
  - get_claude_code_progress(), wait_for_claude_code_with_progress() 함수
  - sync_scenes_to_session_state() 함수로 세션 상태 동기화
- ⭐ v13.3: 완전 자동화 (강제 덮어쓰기 + 완료 감지)
- ⭐ v13.2: 프롬프트 자동 입력
- ⭐ v13.1: API 키 선택 프롬프트 건너뛰기
- ⭐ v13.0: 대화형 모드로 전환
- ⭐ v12.2: PowerShell ^ 캐럿 문법 오류 수정 (폐기)
- ⭐ v12.0: Ink raw mode 에러 수정 (폐기)
- ⭐ v11.0: 새 CMD 창에서 자동 실행
- ⭐ Max Plan 전용 (API 크레딧 사용 안 함)

✅ v13.0 대화형 모드 (가장 간단하고 안정적):
1. 프롬프트 파일 생성 (.md)
2. @ 명령어 클립보드 복사 (예: @logs/claude_code/prompt.md)
3. CMD 창에서 대화형 Claude Code 실행:
   claude --dangerously-skip-permissions
4. 사용자가 Ctrl+V + Enter로 프롬프트 전달
5. Max Plan 적용 - API 크레딧 소모 없음
"""

import os
import subprocess
import shutil
import json
import re
import time
import tempfile
from pathlib import Path
from typing import Optional, Dict, Any, List
from dataclasses import dataclass


# ============================================================
# ⭐ v13.12: UTF-8 BOM 안전 처리 유틸리티
# ============================================================

def load_json_safe(file_path: str) -> Optional[Dict[str, Any]]:
    """
    JSON 파일 안전하게 로드 (BOM 처리 포함) - v13.12

    PowerShell/Bash에서 생성한 JSON 파일에는 UTF-8 BOM이 포함될 수 있음.
    이 함수는 여러 인코딩을 순차 시도하여 안정적으로 로드함.

    Args:
        file_path: JSON 파일 경로 (str 또는 Path)

    Returns:
        파싱된 딕셔너리 (실패 시 None)
    """
    file_path = Path(file_path) if isinstance(file_path, str) else file_path

    if not file_path.exists():
        print(f"[load_json_safe] 파일 없음: {file_path}")
        return None

    # 여러 인코딩 시도 (BOM 처리용 utf-8-sig 우선)
    encodings = ['utf-8-sig', 'utf-8', 'cp949', 'euc-kr']

    for encoding in encodings:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                content = f.read()

            # BOM 수동 제거 (혹시 모를 경우 대비)
            if content.startswith('\ufeff'):
                content = content[1:]

            data = json.loads(content)
            print(f"[load_json_safe] ✅ 로드 성공 ({encoding}): {file_path.name}")
            return data

        except UnicodeDecodeError:
            continue
        except json.JSONDecodeError as e:
            print(f"[load_json_safe] JSON 파싱 오류 ({encoding}): {e}")
            continue
        except Exception as e:
            print(f"[load_json_safe] 로드 오류 ({encoding}): {e}")
            continue

    print(f"[load_json_safe] ❌ 모든 인코딩 시도 실패: {file_path}")
    return None


def read_text_safe(file_path: str) -> Optional[str]:
    """
    텍스트 파일 안전하게 읽기 (BOM 처리 포함) - v13.12

    Args:
        file_path: 파일 경로

    Returns:
        파일 내용 문자열 (실패 시 None)
    """
    file_path = Path(file_path) if isinstance(file_path, str) else file_path

    if not file_path.exists():
        return None

    encodings = ['utf-8-sig', 'utf-8', 'cp949', 'euc-kr']

    for encoding in encodings:
        try:
            with open(file_path, 'r', encoding=encoding) as f:
                content = f.read()

            # BOM 수동 제거
            if content.startswith('\ufeff'):
                content = content[1:]

            return content

        except UnicodeDecodeError:
            continue
        except Exception:
            continue

    return None


# ============================================================
# ⭐ v13.17: 토큰 카운팅 유틸리티 (프롬프트 크기 제한용)
# ============================================================

MAX_PROMPT_TOKENS = 20000  # Claude Code 파일 읽기 제한 25,000의 80% (여유 확보)

def estimate_tokens(text: str) -> int:
    """
    텍스트의 토큰 수 추정 (v13.17)

    간단한 휴리스틱 방식:
    - 영어: 평균 4자당 1토큰
    - 한글: 평균 2자당 1토큰 (한글 1자는 보통 1~2토큰)
    - 공백/구두점: 별도 처리

    Args:
        text: 토큰 수를 추정할 텍스트

    Returns:
        추정 토큰 수
    """
    if not text:
        return 0

    # 한글 문자 수 세기
    korean_chars = len(re.findall(r'[\uAC00-\uD7AF]', text))

    # 한글 외 문자 수 (영어, 숫자, 공백, 구두점 등)
    other_chars = len(text) - korean_chars

    # 토큰 추정: 한글은 2자당 1토큰, 기타는 4자당 1토큰
    korean_tokens = korean_chars / 1.5  # 한글은 더 보수적으로 계산
    other_tokens = other_chars / 4

    # 10% 여유 추가 (안전 마진)
    estimated = int((korean_tokens + other_tokens) * 1.1)

    return max(1, estimated)


def check_prompt_token_limit(prompt: str, limit: int = MAX_PROMPT_TOKENS) -> tuple:
    """
    프롬프트가 토큰 제한 내에 있는지 확인 (v13.17)

    Args:
        prompt: 확인할 프롬프트
        limit: 토큰 제한 (기본값: MAX_PROMPT_TOKENS)

    Returns:
        (is_within_limit: bool, token_count: int, over_by: int)
    """
    token_count = estimate_tokens(prompt)
    is_within_limit = token_count <= limit
    over_by = max(0, token_count - limit)

    if not is_within_limit:
        print(f"[Token Check] WARNING: Prompt exceeds limit! {token_count:,} / {limit:,} tokens (over: {over_by:,})")
    else:
        print(f"[Token Check] OK: Prompt tokens: {token_count:,} / {limit:,} tokens")

    return is_within_limit, token_count, over_by


# ============================================================
# ⭐ v11.0: 새 CMD 창에서 자동 실행 (subprocess 대신)
# ============================================================
# subprocess.run(['claude', ...]) 방식은 API 크레딧을 소모합니다!
#
# ✅ 해결책: 새 CMD 창에서 자동 실행
# - 새 CMD 창에서 `type prompt.md | claude` 실행
# - Max Plan이 적용되어 API 크레딧 소모 없음
# - 사용자가 실행 과정을 볼 수 있음
# ============================================================
CLAUDE_CLI_DISABLED = True  # True면 새 CMD 창 자동 실행, False면 subprocess 사용

# 자동 실행 모드 활성화 (CLAUDE_CLI_DISABLED=True일 때 새 CMD 창에서 실행)
CLAUDE_AGENT_MODE_ENABLED = True

# 자동 실행 안내 메시지
SUBPROCESS_DISABLED_REASON = """
✅ Claude Code 자동 실행 모드 (v11.0)

새 CMD 창에서 Claude Code가 자동으로 실행됩니다.
Max Plan이 적용되어 API 크레딧을 소모하지 않습니다.

📋 실행 과정:
1. 프롬프트 파일 생성 (.md)
2. 배치 파일 생성 (.bat)
3. 새 CMD 창에서 자동 실행
4. 완료 후 "결과 확인" 버튼 클릭
"""


@dataclass
class ClaudeCodeResult:
    """Claude Code 실행 결과"""
    success: bool
    output: str
    error: str = ""
    return_code: int = 0
    model_used: str = ""
    is_rate_limited: bool = False  # Rate limit 여부
    should_fallback: bool = False  # 폴백 필요 여부


class ClaudeCodeRunner:
    """Claude Code CLI 실행기 (v9.0 - Max Plan 전용)"""

    HARDCODED_CLAUDE_PATH = r"C:\Users\KIMJAEHEON\AppData\Roaming\npm\claude.cmd"
    DEFAULT_MODEL = "claude-sonnet-4-20250514"
    DEFAULT_TIMEOUT = 300
    DEBUG_OUTPUT = True
    USE_STDIN = True

    # 배치 간 딜레이 (Rate limit 방지)
    BATCH_DELAY = 2.0  # 초

    # 재시도 설정
    MAX_RETRIES = 2
    RETRY_DELAY = 5.0  # 초

    # Rate limit / 오류 패턴
    RATE_LIMIT_PATTERNS = [
        "rate limit",
        "rate_limit",
        "too many requests",
        "quota exceeded",
        "throttle",
        "429"
    ]

    SHOULD_FALLBACK_PATTERNS = [
        "credit balance is too low",
        "rate limit",
        "rate_limit",
        "too many requests",
        "quota exceeded",
        "throttle",
        "overloaded",
        "503",
        "529"
    ]

    def __init__(self, model: str = None):
        print(f"[ClaudeCodeRunner] 초기화 중...")

        # 비활성화 플래그 확인
        global CLAUDE_CLI_DISABLED
        if CLAUDE_CLI_DISABLED:
            print(f"[ClaudeCodeRunner] [DISABLED] Claude CLI 비활성화됨 (CLAUDE_CLI_DISABLED=True)")
            print(f"[ClaudeCodeRunner]   -> Gemini가 기본 AI로 사용됩니다")
            self.claude_path = None
            self.available = False
            self.model = model or self.DEFAULT_MODEL
            self._consecutive_errors = 0
            self._last_request_time = 0
            return

        self.claude_path = self._find_claude_path()
        self.available = self.claude_path is not None
        self.model = model or self.DEFAULT_MODEL
        self._consecutive_errors = 0
        self._last_request_time = 0

        if self.available:
            print(f"[ClaudeCodeRunner] ✅ Claude CLI 발견: {self.claude_path}")
            print(f"[ClaudeCodeRunner]   모델: {self.model}")
            print(f"[ClaudeCodeRunner]   배치 딜레이: {self.BATCH_DELAY}초")
        else:
            print(f"[ClaudeCodeRunner] ❌ Claude CLI를 찾을 수 없습니다")

    def _find_claude_path(self) -> Optional[str]:
        """Claude CLI 경로 찾기"""
        if self.HARDCODED_CLAUDE_PATH:
            hardcoded = Path(self.HARDCODED_CLAUDE_PATH)
            if hardcoded.exists():
                print(f"[ClaudeCodeRunner] 하드코딩 경로에서 발견: {hardcoded}")
                return str(hardcoded)

        claude_path = shutil.which("claude")
        if claude_path:
            return claude_path

        if os.name == 'nt':
            paths = [
                Path(os.environ.get("APPDATA", "")) / "npm" / "claude.cmd",
                Path.home() / "AppData" / "Roaming" / "npm" / "claude.cmd",
            ]
            for p in paths:
                if p.exists():
                    return str(p)

        return None

    def _get_env(self) -> dict:
        """실행 환경 변수"""
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        if os.name == 'nt':
            env["CHCP"] = "65001"
        env["CLAUDE_NO_CONFIRM"] = "1"
        env["NO_COLOR"] = "1"
        return env

    def _is_rate_limited(self, output: str, error: str = "") -> bool:
        """Rate limit 오류인지 확인"""
        combined = (output + " " + error).lower()
        return any(p in combined for p in self.RATE_LIMIT_PATTERNS)

    def _should_fallback(self, output: str, error: str = "") -> bool:
        """폴백이 필요한 오류인지 확인"""
        combined = (output + " " + error).lower()
        return any(p in combined for p in self.SHOULD_FALLBACK_PATTERNS)

    def _wait_for_rate_limit(self):
        """Rate limit 방지를 위한 딜레이"""
        now = time.time()
        elapsed = now - self._last_request_time

        if elapsed < self.BATCH_DELAY:
            wait_time = self.BATCH_DELAY - elapsed
            print(f"[ClaudeCodeRunner] ⏳ Rate limit 방지 대기: {wait_time:.1f}초")
            time.sleep(wait_time)

        self._last_request_time = time.time()

    def run(
        self,
        prompt: str,
        timeout: int = None,
        working_dir: str = None,
        model: str = None,
        retry: bool = True
    ) -> ClaudeCodeResult:
        """
        Claude Code CLI 실행

        v9.0: Rate limit 방지 딜레이 + 재시도
        """

        if not self.available:
            return ClaudeCodeResult(
                success=False,
                output="",
                error="Claude CLI를 찾을 수 없습니다",
                should_fallback=True
            )

        timeout = timeout or self.DEFAULT_TIMEOUT
        use_model = model or self.model

        # Rate limit 방지 딜레이
        self._wait_for_rate_limit()

        print(f"[ClaudeCodeRunner] 🔵 Claude CLI 실행 중...")
        print(f"[ClaudeCodeRunner]   경로: {self.claude_path}")
        print(f"[ClaudeCodeRunner]   모델: {use_model}")
        print(f"[ClaudeCodeRunner]   프롬프트 길이: {len(prompt)}자")
        print(f"[ClaudeCodeRunner]   타임아웃: {timeout}초")

        # 재시도 로직
        last_error = None
        for attempt in range(self.MAX_RETRIES + 1):
            if attempt > 0:
                print(f"[ClaudeCodeRunner] 🔄 재시도 {attempt}/{self.MAX_RETRIES} ({self.RETRY_DELAY}초 후)")
                time.sleep(self.RETRY_DELAY)

            try:
                result = self._run_with_stdin(prompt, timeout, working_dir, use_model)

                # Rate limit 체크
                if self._is_rate_limited(result.output, result.error):
                    print(f"[ClaudeCodeRunner] ⚠️ Rate limit 감지")
                    result.is_rate_limited = True

                    if retry and attempt < self.MAX_RETRIES:
                        last_error = "Rate limit"
                        continue
                    else:
                        result.should_fallback = True
                        return result

                # 폴백 필요 체크
                if self._should_fallback(result.output, result.error):
                    print(f"[ClaudeCodeRunner] ⚠️ 폴백 필요한 오류 감지")
                    result.should_fallback = True

                # 성공
                if result.success:
                    self._consecutive_errors = 0
                    result.model_used = use_model
                    return result

                # 실패했지만 재시도 가능
                if retry and attempt < self.MAX_RETRIES:
                    last_error = result.error
                    continue

                result.model_used = use_model
                return result

            except subprocess.TimeoutExpired:
                print(f"[ClaudeCodeRunner] ❌ 타임아웃 ({timeout}초)")
                if retry and attempt < self.MAX_RETRIES:
                    last_error = f"타임아웃 ({timeout}초)"
                    continue
                return ClaudeCodeResult(
                    success=False,
                    output="",
                    error=f"타임아웃 ({timeout}초)",
                    model_used=use_model,
                    should_fallback=True
                )
            except Exception as e:
                print(f"[ClaudeCodeRunner] ❌ 예외: {e}")
                if retry and attempt < self.MAX_RETRIES:
                    last_error = str(e)
                    continue
                return ClaudeCodeResult(
                    success=False,
                    output="",
                    error=str(e),
                    model_used=use_model,
                    should_fallback=True
                )

        # 모든 재시도 실패
        return ClaudeCodeResult(
            success=False,
            output="",
            error=f"모든 재시도 실패: {last_error}",
            model_used=use_model,
            should_fallback=True
        )

    def _run_with_stdin(
        self,
        prompt: str,
        timeout: int,
        working_dir: str = None,
        model: str = None
    ) -> ClaudeCodeResult:
        """
        v12.0: --print -p 플래그로 프롬프트 전달 (Ink 호환)

        stdin 파이프 대신 -p 플래그를 사용하여 Ink raw mode 에러 방지
        """

        print(f"[ClaudeCodeRunner]   방식: --print -p (Ink 호환)")

        # v12.0: --print -p 방식으로 변경 (stdin 대신)
        cmd = [
            self.claude_path,
            "--print",
            "--dangerously-skip-permissions",
            "--output-format", "text",
            "-p", prompt  # stdin 대신 -p 플래그로 프롬프트 전달
        ]

        if model:
            cmd.extend(["--model", model])

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=timeout,
            cwd=working_dir,
            env=self._get_env(),
            shell=True
        )

        return self._process_result(result)

    def _run_with_file(
        self,
        prompt: str,
        timeout: int,
        working_dir: str = None,
        model: str = None
    ) -> ClaudeCodeResult:
        """
        v12.0: 임시 파일 + --print -p 방식 (Ink 호환)

        긴 프롬프트의 경우 임시 파일에 저장 후 -p 플래그로 전달
        """

        print(f"[ClaudeCodeRunner]   방식: 임시 파일 + --print -p (Ink 호환)")

        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.txt',
            delete=False,
            encoding='utf-8'
        ) as f:
            f.write(prompt)
            prompt_file = f.name

        try:
            # v12.0: --print -p 방식으로 변경
            cmd = [
                self.claude_path,
                "--print",
                "--dangerously-skip-permissions",
                "--output-format", "text",
                "-p", prompt  # stdin 대신 -p 플래그로 프롬프트 전달
            ]

            if model:
                cmd.extend(["--model", model])

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=timeout,
                cwd=working_dir,
                env=self._get_env(),
                shell=True
            )

            return self._process_result(result)

        finally:
            try:
                os.unlink(prompt_file)
            except:
                pass

    def _process_result(self, result) -> ClaudeCodeResult:
        """subprocess 결과 처리"""

        print(f"[ClaudeCodeRunner] 반환 코드: {result.returncode}")

        stdout = result.stdout or ""
        stderr = result.stderr or ""

        if self.DEBUG_OUTPUT and stdout:
            preview = stdout[:500].replace('\n', '\\n')
            print(f"[ClaudeCodeRunner] 출력 미리보기: {preview}...")

        if result.returncode == 0:
            return ClaudeCodeResult(
                success=True,
                output=stdout,
                return_code=0
            )
        else:
            return ClaudeCodeResult(
                success=False,
                output=stdout,
                error=stderr or f"실행 실패 (코드: {result.returncode})",
                return_code=result.returncode
            )

    def extract_json(self, output: str) -> Optional[dict]:
        """출력에서 JSON 추출 (강화된 버전)"""

        if not output:
            print(f"[ClaudeCodeRunner] extract_json: 출력이 비어있음")
            return None

        print(f"[ClaudeCodeRunner] extract_json: 출력 길이 {len(output)}자")

        # 프롬프트 미전달 감지
        if "도와드릴까요" in output or "어떤 작업" in output or "무엇을 도와" in output:
            print(f"[ClaudeCodeRunner] ⚠️ 프롬프트가 전달되지 않은 것 같음 (일반 응답 감지)")

        # 방법 1: ```json ... ``` 블록
        try:
            match = re.search(r'```json\s*([\s\S]*?)\s*```', output, re.IGNORECASE)
            if match:
                json_str = match.group(1).strip()
                print(f"[ClaudeCodeRunner] JSON 블록 발견 (```json)")
                return json.loads(json_str)
        except json.JSONDecodeError as e:
            print(f"[ClaudeCodeRunner] JSON 블록 파싱 실패: {e}")

        # 방법 2: ``` ... ``` 블록
        try:
            match = re.search(r'```\s*([\s\S]*?)\s*```', output)
            if match:
                json_str = match.group(1).strip()
                if json_str.startswith('{'):
                    print(f"[ClaudeCodeRunner] 코드 블록에서 JSON 발견")
                    return json.loads(json_str)
        except json.JSONDecodeError:
            pass

        # 방법 3: {"scenes": ...} 패턴
        try:
            match = re.search(r'\{\s*"scenes"\s*:\s*\[[\s\S]*?\]\s*\}', output)
            if match:
                json_str = match.group()
                print(f"[ClaudeCodeRunner] scenes 패턴 발견")
                return json.loads(json_str)
        except json.JSONDecodeError:
            pass

        # 방법 4: 첫 번째 { ~ 마지막 }
        try:
            start = output.find('{')
            end = output.rfind('}')
            if start != -1 and end != -1 and end > start:
                json_str = output[start:end+1]
                print(f"[ClaudeCodeRunner] 중괄호 범위에서 JSON 추출 시도")

                open_brackets = json_str.count('[') - json_str.count(']')
                open_braces = json_str.count('{') - json_str.count('}')
                json_str += ']' * max(0, open_brackets)
                json_str += '}' * max(0, open_braces)

                return json.loads(json_str)
        except json.JSONDecodeError as e:
            print(f"[ClaudeCodeRunner] 중괄호 범위 파싱 실패: {e}")

        # 방법 5: 줄 단위
        try:
            for line in output.split('\n'):
                line = line.strip()
                if line.startswith('{') and line.endswith('}'):
                    print(f"[ClaudeCodeRunner] 단일 줄 JSON 발견")
                    return json.loads(line)
        except json.JSONDecodeError:
            pass

        print(f"[ClaudeCodeRunner] JSON 추출 실패")
        print(f"[ClaudeCodeRunner] 출력 처음 200자: {output[:200]}")
        return None


# 싱글톤
_runner: Optional[ClaudeCodeRunner] = None

def get_claude_code_runner(model: str = None) -> ClaudeCodeRunner:
    global _runner
    if _runner is None:
        _runner = ClaudeCodeRunner(model=model)
    return _runner

def reset_claude_code_runner():
    global _runner
    _runner = None

def run_claude_code(prompt: str, timeout: int = 300, model: str = None) -> ClaudeCodeResult:
    return get_claude_code_runner().run(prompt, timeout=timeout, model=model)

def is_claude_code_available() -> bool:
    """Claude CLI 사용 가능 여부 확인"""
    global CLAUDE_CLI_DISABLED
    if CLAUDE_CLI_DISABLED:
        return False  # 비활성화 시 항상 False -> Gemini 폴백 유도
    return get_claude_code_runner().available

def get_claude_code_model() -> str:
    """현재 설정된 모델명 반환"""
    return get_claude_code_runner().model


# ============================================================
# 씬 분석 에이전트 함수 (v10.0 추가)
# ============================================================

def run_scene_analysis_with_claude_code(
    script_path: str,
    output_path: str,
    language: str = "ko",
    timeout: int = 300,
    progress_callback = None
) -> tuple:
    """
    Claude Code로 씬 분석 실행

    ⚠️ v10.0: subprocess 방식 비활성화됨
    CLAUDE_CLI_DISABLED=True일 경우 즉시 False 반환 (에이전트 모드 사용 권장)

    Args:
        script_path: 스크립트 파일 경로
        output_path: scenes.json 출력 경로
        language: 언어 코드
        timeout: 타임아웃 (초)
        progress_callback: 진행 콜백 (선택)

    Returns:
        (성공 여부, 메시지, scenes 데이터 또는 None)
    """
    from pathlib import Path

    # ═══════════════════════════════════════════════════════════════════
    # ⭐ v11.0: 새 CMD 창에서 자동 실행
    # ═══════════════════════════════════════════════════════════════════
    if CLAUDE_CLI_DISABLED:
        print(f"\n{'='*70}")
        print(f"[SceneAnalysis] 🚀 새 CMD 창에서 자동 실행 모드")
        print(f"[SceneAnalysis] Max Plan 적용 - API 크레딧 소모 없음")
        print(f"{'='*70}\n")

        if progress_callback:
            progress_callback("새 CMD 창에서 Claude Code 실행 중...")

        # 프롬프트 생성
        prompt = f"""# 씬 분석 작업

## 입력 파일
- 스크립트: {script_path}

## 출력 파일
- JSON: {output_path}

## 작업 내용
스크립트 파일을 읽고 씬 데이터를 생성해주세요.
"""
        # 자동 실행
        auto_result = execute_claude_code_in_new_window(
            prompt_text=prompt,
            project_path=str(Path(output_path).parent.parent),
            scenes_json_path=output_path
        )

        if auto_result.success:
            return True, "새 CMD 창에서 Claude Code 실행 시작됨. 완료 후 결과를 확인하세요.", None
        else:
            return False, f"자동 실행 실패: {auto_result.error}", None

    PROJECT_ROOT = Path(__file__).parent.parent

    # 에이전트 프롬프트 파일
    agent_file = PROJECT_ROOT / "agents" / "scene_analysis_agent.md"
    template_file = PROJECT_ROOT / "agents" / "templates" / "scene_analysis_prompt.md"

    # 에이전트 프롬프트 로드
    system_prompt = ""
    if agent_file.exists():
        system_prompt = agent_file.read_text(encoding='utf-8')

    # 태스크 프롬프트 구성
    if template_file.exists():
        template = template_file.read_text(encoding='utf-8')
        task_prompt = template.format(
            script_path=script_path,
            output_path=output_path,
            language=language
        )
    else:
        task_prompt = f"""
다음 스크립트 파일을 분석하여 씬 데이터를 생성해주세요.

스크립트 파일: {script_path}
출력 파일: {output_path}
언어: {language}

1. 스크립트 파일을 읽고 씬 단위로 분할
2. 각 씬에 대해 다음 정보 추출:
   - scene_id, script_text, char_count, duration_estimate
   - characters, visual_elements, mood
   - direction_guide, camera_suggestion
   - image_prompt_ko, image_prompt_en
   - character_prompt_ko, character_prompt_en
   - video_prompt_character, video_prompt_full

3. 결과를 JSON 배열로 {output_path}에 저장해주세요.
"""

    # 전체 프롬프트
    if system_prompt:
        full_prompt = f"{system_prompt}\n\n---\n\n{task_prompt}"
    else:
        full_prompt = task_prompt

    print(f"[SceneAnalysis] Claude Code로 씬 분석 시작")
    print(f"[SceneAnalysis]   스크립트: {script_path}")
    print(f"[SceneAnalysis]   출력: {output_path}")
    print(f"[SceneAnalysis]   프롬프트 길이: {len(full_prompt)}자")

    if progress_callback:
        progress_callback("Claude Code 실행 중...")

    # Claude Code 실행
    runner = get_claude_code_runner()
    result = runner.run(full_prompt, timeout=timeout)

    if result.success:
        # 출력 파일 확인
        output_file = Path(output_path)
        if output_file.exists():
            try:
                data = json.loads(output_file.read_text(encoding='utf-8'))
                print(f"[SceneAnalysis] 출력 파일 로드 성공: {len(data)}개 씬")
                if progress_callback:
                    progress_callback("분석 완료")
                return True, f"분석 완료 ({len(data)}개 씬)", data
            except json.JSONDecodeError as e:
                print(f"[SceneAnalysis] 출력 파일 JSON 파싱 실패: {e}")
                return False, f"결과 파일 파싱 실패: {e}", None
        else:
            # 출력에서 JSON 추출 시도
            json_data = runner.extract_json(result.output)
            if json_data:
                # scenes 키가 있으면 추출
                if isinstance(json_data, dict) and 'scenes' in json_data:
                    scenes = json_data['scenes']
                elif isinstance(json_data, list):
                    scenes = json_data
                else:
                    return False, "올바른 씬 데이터 형식이 아닙니다", None

                # 파일에 저장
                output_file.parent.mkdir(parents=True, exist_ok=True)
                output_file.write_text(json.dumps(scenes, ensure_ascii=False, indent=2), encoding='utf-8')
                print(f"[SceneAnalysis] 출력에서 JSON 추출 후 저장: {len(scenes)}개 씬")
                if progress_callback:
                    progress_callback("분석 완료")
                return True, f"분석 완료 ({len(scenes)}개 씬)", scenes
            else:
                print(f"[SceneAnalysis] 출력에서 JSON 추출 실패")
                return False, "결과 파일이 생성되지 않았습니다", None
    else:
        error_msg = result.error or "알 수 없는 오류"
        print(f"[SceneAnalysis] Claude Code 실행 실패: {error_msg}")
        if progress_callback:
            progress_callback(f"실패: {error_msg}")

        # 폴백 필요 여부 반환
        if result.should_fallback:
            return False, f"Claude Code 오류 (Gemini 폴백 권장): {error_msg}", None
        return False, error_msg, None


def enable_claude_cli():
    """
    Claude CLI 활성화

    ⚠️ 경고: subprocess 방식은 API 크레딧을 소모합니다!
    Max Plan 구독과 별개로 비용이 발생합니다.

    대신 에이전트 모드(프롬프트 복사 + 수동 실행)를 권장합니다.
    """
    global CLAUDE_CLI_DISABLED
    print(f"\n{'='*70}")
    print(f"[ClaudeCodeRunner] ⚠️ 경고: subprocess 방식은 API 크레딧을 소모합니다!")
    print(f"[ClaudeCodeRunner] Max Plan 구독과 별개로 비용이 발생합니다.")
    print(f"[ClaudeCodeRunner] 에이전트 모드(프롬프트 복사 + 수동 실행)를 권장합니다.")
    print(f"{'='*70}\n")
    # subprocess 방식은 권장하지 않으므로 비활성화 유지
    # CLAUDE_CLI_DISABLED = False
    # reset_claude_code_runner()
    print("[ClaudeCodeRunner] subprocess 방식은 비활성화 상태를 유지합니다.")
    print("[ClaudeCodeRunner] 에이전트 모드를 사용하세요.")


def disable_claude_cli():
    """Claude CLI 비활성화"""
    global CLAUDE_CLI_DISABLED
    CLAUDE_CLI_DISABLED = True
    reset_claude_code_runner()
    print("[ClaudeCodeRunner] Claude CLI 비활성화됨")


# ============================================================
# 씬 분석 에이전트 (v11.0 - Claude Code Max Plan 전용)
# ============================================================

@dataclass
class SceneAnalysisResult:
    """씬 분석 결과"""
    success: bool
    output: str
    error: str = ""
    elapsed_time: float = 0
    scenes_analyzed: int = 0
    scenes_failed: int = 0
    fields_generated: dict = None

    def __post_init__(self):
        if self.fields_generated is None:
            self.fields_generated = {}


def check_claude_code_installation() -> dict:
    """
    Claude Code CLI 설치 상태 확인

    Returns:
        설치 상태 정보 딕셔너리
    """
    status = {
        'installed': False,
        'version': None,
        'path': None,
        'error': None
    }

    try:
        # 하드코딩 경로 먼저 확인
        hardcoded_path = r"C:\Users\KIMJAEHEON\AppData\Roaming\npm\claude.cmd"
        if os.path.exists(hardcoded_path):
            status['path'] = hardcoded_path
        else:
            # which로 찾기
            claude_path = shutil.which("claude")
            if claude_path:
                status['path'] = claude_path

        if status['path']:
            # 버전 확인
            result = subprocess.run(
                [status['path'], '--version'],
                capture_output=True,
                text=True,
                timeout=10,
                shell=True
            )

            if result.returncode == 0:
                status['installed'] = True
                status['version'] = result.stdout.strip()
            else:
                status['error'] = result.stderr or "버전 확인 실패"
        else:
            status['error'] = "Claude Code CLI를 찾을 수 없습니다"

    except subprocess.TimeoutExpired:
        status['error'] = "응답 시간 초과"

    except Exception as e:
        status['error'] = str(e)

    return status


def _get_actual_scene_ids_from_file(scenes_json_path: str) -> list:
    """
    scenes.json 파일에서 실제 씬 ID 목록 읽기 (v13.12: BOM 처리)

    Args:
        scenes_json_path: scenes.json 파일 경로

    Returns:
        씬 ID 리스트 (정렬됨) 또는 빈 리스트
    """
    try:
        scenes_path = Path(scenes_json_path)
        if not scenes_path.exists():
            print(f"[_get_actual_scene_ids] scenes.json 파일 없음: {scenes_json_path}")
            return []

        # v13.12: load_json_safe 사용 (BOM 자동 처리)
        scenes = load_json_safe(str(scenes_path))

        if not scenes:
            return []

        # scene_id 필드 추출 (없으면 인덱스+1 사용)
        scene_ids = []
        for i, scene in enumerate(scenes):
            sid = scene.get('scene_id') or scene.get('scene_num') or (i + 1)
            scene_ids.append(sid)

        scene_ids = sorted(set(scene_ids))  # 중복 제거 및 정렬
        print(f"[_get_actual_scene_ids] 읽은 씬 ID: {len(scene_ids)}개 (범위: {min(scene_ids)}-{max(scene_ids)})")
        return scene_ids

    except Exception as e:
        print(f"[_get_actual_scene_ids] 파일 읽기 실패: {e}")
        return []


def build_scene_analysis_prompt(
    scenes_json_path: str,
    project_path: str,
    scene_range: tuple = None,
    bundle_mode: bool = True,
    custom_instructions: str = "",
    completion_flag_path: str = None,
    progress_file_path: str = None,
    total_scenes: int = 0,
    selected_scene_ids: list = None,
    prompt_id: str = None  # v3.95: 프롬프트 템플릿 ID 추가
) -> str:
    """
    씬 분석용 프롬프트 생성 (v13.18: 템플릿 파일 직접 읽기로 변경)

    v13.18 핵심 변경:
    - 템플릿 축약 제거! 전체 내용을 Claude Code가 직접 읽음
    - 템플릿을 별도 파일로 저장 후 Read 지시
    - "Template too long" 문제 완전 해결
    - 캐릭터 추출 규칙 등 핵심 내용 100% 적용

    v13.17 핵심 변경:
    - 프롬프트 토큰 제한 (20,000 토큰 이하) - Claude Code 25,000 한계의 80%
    - 캐릭터 추출 규칙을 최상단에 배치
    - Python 스크립트 생성 금지 규칙 추가
    - 중복 내용 제거로 프롬프트 압축

    Args:
        scenes_json_path: scenes.json 파일 경로
        project_path: 프로젝트 루트 경로
        scene_range: 분석할 씬 범위 (start, end) 또는 None (전체)
        bundle_mode: 묶음 모드 사용 여부
        custom_instructions: 추가 지시사항
        completion_flag_path: 완료 신호 파일 경로 (None이면 자동 생성)
        progress_file_path: 진행률 파일 경로 (None이면 자동 생성)
        total_scenes: 전체 씬 수 (0이면 자동 계산)
        selected_scene_ids: 분석할 씬 ID 목록 (None이면 전체 또는 scene_range 사용)
        prompt_id: 프롬프트 템플릿 ID (None이면 기본 템플릿 사용)

    Returns:
        Claude Code에 전달할 프롬프트 문자열
    """

    # 파일 경로 설정
    logs_dir = Path(project_path) / "logs" / "claude_code"
    if completion_flag_path is None:
        completion_flag_path = str(logs_dir / "_analysis_complete.flag")
    if progress_file_path is None:
        progress_file_path = str(logs_dir / "_progress.json")

    # ═══════════════════════════════════════════════════════════════════════════
    # ⭐ v13.17: 캐릭터 추출 + Python 금지 규칙을 최상단에 배치!
    # Claude Code 파일 읽기 제한(25,000 토큰)으로 인해 핵심 규칙이 잘릴 수 있음
    # ═══════════════════════════════════════════════════════════════════════════
    # ═══════════════════════════════════════════════════════════════════════════
    # ⭐ v13.20: 최적화된 프롬프트 - 토큰 초과 방지
    # ═══════════════════════════════════════════════════════════════════════════

    # bundle_info 경로 계산
    analysis_dir = Path(scenes_json_path).parent
    bundle_info_path = analysis_dir / "bundle_info_claude_code.json"

    critical_rules_header = f"""# 🚨🚨🚨 [최우선] 핵심 규칙 - 반드시 먼저 읽으세요! 🚨🚨🚨

## 🔴 [절대 금지] 다음 사항은 절대 금지입니다!
1. ❌ **scenes.json 전체 읽기 금지** → 토큰 초과로 분석 실패!
2. ❌ **Python 스크립트(.py) 파일 생성 금지**
3. ❌ **Task() 또는 백그라운드 에이전트 사용 금지**
4. ❌ **추가 질문 금지** → 즉시 실행하세요!

---

## ✅ [필수 규칙] 반드시 따라야 할 처리 방식

### 1. 파일 읽기 방식 (토큰 절약!)
- **bundle_info 파일 먼저 읽기**: `{bundle_info_path}`
- scenes.json은 **Read tool의 offset/limit** 사용 (한 번에 100줄 이하)
- 또는 **Grep tool**로 특정 scene_id만 검색

### 2. 처리 단위
- **5개 묶음(Bundle)씩 처리** 후 **즉시 scenes.json Update**
- 전체 완료 후 한 번에 저장하지 말 것!
- 진행 상황을 자주 보고 (예: "묶음 1-5 완료, 6-10 처리 중...")

### 3. Update 방식
- **Edit tool** 사용하여 scenes.json 직접 수정
- 한 씬당 필요한 필드만 추가/수정
- 전체 파일 재작성 금지!

---

## 🔴🔴🔴 [절대 규칙] 캐릭터(characters) 필드 생성 규칙 🔴🔴🔴

### 1. 인물이 있는 씬:
```json
{{
  "characters": [
    {{"name": "이재용", "visual_prompt": "Lee Jae-yong in formal business suit, confident expression"}}
  ],
  "character_prompt": "이재용 회장",
  "character_prompt_en": "Lee Jae-yong in formal business suit, confident expression"
}}
```

### 2. 인물이 없는 씬:
```json
{{
  "characters": [],
  "character_prompt": "",
  "character_prompt_en": "",
  "image_prompt_en": "(background_prompt_en과 동일한 값)"
}}
```

### 📋 캐릭터 판단 기준:
- **있음**: 이재용, 박사님, 김대리 등 이름/특정 인물
- **없음**: "이게 중요합니다", "~가 된다" 등 개념 설명

---

"""

    # ⭐ v13.18: 프롬프트 템플릿 원본 파일 경로 전달 방식으로 변경
    # 선택된 프롬프트가 바뀌면 해당 프롬프트의 원본 파일 경로가 자동으로 전달됨!
    # 템플릿 내용을 프롬프트에 포함하지 않고, Claude Code가 직접 원본 파일을 읽음
    prompt_template_file_path = None
    template_name = "기본"

    # v13.19: 프롬프트 선택 확인 로깅 강화
    print(f"\n{'='*60}")
    print(f"[Claude Code] PROMPT SELECTION CHECK")
    print(f"{'='*60}")
    print(f"[Claude Code] Received prompt_id: '{prompt_id}'")

    if prompt_id:
        try:
            from core.prompt.prompt_template_manager import get_template_manager
            template_manager = get_template_manager()
            template = template_manager.get_template(prompt_id)

            if template:
                template_name = template.name
                template_tokens = estimate_tokens(template.prompt)

                # v13.19: 상세 로깅 - 선택된 프롬프트 정보
                print(f"[Claude Code] ✅ Template found!")
                print(f"[Claude Code]    - ID: {prompt_id}")
                print(f"[Claude Code]    - Name: {template_name}")
                print(f"[Claude Code]    - Category: {template.category}")
                print(f"[Claude Code]    - Tokens: {template_tokens:,}")

                # 프롬프트 첫 줄 출력 (버전 확인용)
                first_line = template.prompt.strip().split('\n')[0][:100]
                print(f"[Claude Code]    - First line: {first_line}...")

                # ⭐ v13.18: 원본 템플릿 파일 경로 가져오기 (복사 대신!)
                # get_template_file_path()가 원본 파일 경로를 반환하거나,
                # 없으면 data/prompts/templates/ 디렉토리에 파일 생성 (내용 자동 동기화!)
                prompt_template_file_path = template_manager.get_template_file_path(prompt_id)

                if prompt_template_file_path:
                    print(f"[Claude Code] ✅ Template file: {prompt_template_file_path}")
                else:
                    print(f"[Claude Code] ⚠️ Could not get template file path")
            else:
                print(f"[Claude Code] ❌ Template '{prompt_id}' NOT FOUND in template_manager!")
                print(f"[Claude Code]    Available templates: {list(template_manager.templates.keys())[:5]}...")
        except Exception as e:
            print(f"[Claude Code] ❌ Template load error: {e}")
            import traceback
            traceback.print_exc()
    else:
        print(f"[Claude Code] ⚠️ No prompt_id provided - using default behavior")

    print(f"{'='*60}\n")

    # ⭐ v13.11: 분석 대상 씬 ID 목록 생성
    if selected_scene_ids:
        target_ids = selected_scene_ids
    elif scene_range:
        actual_scene_ids = _get_actual_scene_ids_from_file(scenes_json_path)
        if actual_scene_ids:
            target_ids = [sid for sid in actual_scene_ids if scene_range[0] <= sid <= scene_range[1]]
            if not target_ids:
                target_ids = actual_scene_ids
        else:
            target_ids = list(range(scene_range[0], scene_range[1] + 1))
    else:
        target_ids = None

    # 분석 대상 씬 지시
    if target_ids:
        ids_str = ', '.join(map(str, target_ids[:50]))  # v13.17: 너무 길면 50개만
        if len(target_ids) > 50:
            ids_str += f", ... (총 {len(target_ids)}개)"
        min_id = min(target_ids)
        max_id = max(target_ids)
        count = len(target_ids)

        target_instruction = f"""## 📋 분석 대상 씬
- 씬 ID: [{ids_str}]
- 범위: {min_id} ~ {max_id} ({count}개)
- ⚠️ 다른 씬 수정 금지!
"""
    else:
        target_instruction = "## 📋 분석 대상: 전체 씬\n"

    # 파일 경로 정보 (v13.20: bundle_info 경로 추가)
    paths_info = f"""## 📁 파일 경로
- **bundle_info (먼저 읽기!)**: `{bundle_info_path}`
- scenes.json: `{scenes_json_path}`
- 진행률 파일: `{progress_file_path}`
- 완료 신호: `{completion_flag_path}`
"""

    # 16개 필수 필드 (압축 버전)
    required_fields = """## 📋 필수 생성 필드 (16개)

| 필드명 | 타입 | 언어 | 설명 |
|--------|------|------|------|
| image_prompt | str | 한글 | 이미지 프롬프트 |
| image_prompt_en | str | 영어 | 영문 이미지 프롬프트 (+ no text 문구) |
| background_prompt | str | 한글 | 배경 설명 |
| background_prompt_en | str | 영어 | 영문 배경 (사람 제외!) |
| character_prompt | str | 한글 | 캐릭터 설명 |
| character_prompt_en | str | 영어 | 영문 캐릭터 |
| image_prompt_korean_text | str | 영어 | 한글 텍스트 오버레이 |
| korean_text | str | 영어 | (위와 동일) |
| visual_elements | arr | 한글 | 시각 요소 배열 |
| direction_guide | str | 한글 | 연출 가이드 |
| camera_suggestion | str | 영어 | 카메라 제안 |
| video_prompt_character | str | 영어 | 캐릭터 비디오 |
| video_prompt_full | str | 영어 | 전체 비디오 |
| characters | arr | 혼합 | [{name, visual_prompt}] |
| location | str | 한글 | 장소 |
| mood | str | 한글 | 분위기 |

### 영어 프롬프트 끝에 필수 추가:
`no text, no letters, no words, no writing, no numbers, no speech bubbles, no readable text, brand logos are acceptable`
"""

    # 묶음 모드 (압축)
    bundle_instruction = ""
    if bundle_mode:
        bundle_instruction = """## 📦 묶음(Bundle) 규칙
- 동일 bundle_id 씬들은 하나의 묶음
- 스크립트를 합쳐서 분석
- 결과를 모든 씬에 동일 적용
"""

    # 완료 처리 (압축)
    completion_instruction = f"""## 🏁 완료 처리
1. scenes.json 저장 후
2. 진행률 파일 업데이트: `{progress_file_path}`
3. 완료 신호 생성: `{completion_flag_path}`
"""

    # 실행 지시 (v13.20: 최적화된 실행 단계)
    execution_instruction = f"""## ▶️ 실행 단계 (순서대로!)

### Step 1: Bundle Info 파일 읽기
```
Read: {bundle_info_path}
```
이 파일에 묶음별 scene_id 목록이 있습니다.

### Step 2: 5개 묶음씩 처리
각 묶음에 대해:
1. Grep으로 해당 scene_id의 스크립트 찾기
2. 16개 필드 분석/생성
3. **5개 묶음 처리 후 즉시** scenes.json Update (Edit tool 사용)

### Step 3: 반복
- 다음 5개 묶음 처리
- Update 반복
- 모든 묶음 완료까지

### Step 4: 완료 신호
- 완료 신호 파일 생성

**🚀 질문 없이 즉시 시작하세요!**
"""

    # ═══════════════════════════════════════════════════════════════════════════
    # 프롬프트 조립 (핵심 규칙 최상단!)
    # ═══════════════════════════════════════════════════════════════════════════
    prompt_parts = [
        critical_rules_header,  # ⭐ 캐릭터 추출 + Python 금지 규칙 (최상단!)
        target_instruction,
        paths_info,
        required_fields,
        bundle_instruction,
    ]

    # 커스텀 지시사항 (있으면)
    if custom_instructions:
        prompt_parts.append(f"## 추가 지시사항\n{custom_instructions}\n")

    # ⭐ v13.18: 프롬프트 템플릿 원본 파일 읽기 지시
    if prompt_template_file_path:
        template_read_instruction = f"""
## 🔴🔴🔴 [1단계 - 필수!] 프롬프트 템플릿 전체 읽기 🔴🔴🔴

**선택된 프롬프트**: `{template_name}` (ID: `{prompt_id}`)

**⚠️ 분석 시작 전에 반드시 다음 파일을 처음부터 끝까지 전체 읽으세요!**

```
{prompt_template_file_path}
```

이 파일에 씬 분석의 **모든 규칙**이 포함되어 있습니다:
- ✅ 캐릭터 추출 규칙 (characters 배열 생성법)
- ✅ 16개 필드 생성 규칙 및 예시
- ✅ 인물 없는 씬 처리 규칙 (image_prompt_en = background_prompt_en)
- ✅ 브랜드 로고 허용 규칙
- ✅ 영어 프롬프트 끝 문구 규칙 (no text, no letters...)
- ✅ 한글 텍스트 처리 규칙

**❌ 이 파일을 읽지 않으면 분석이 불완전합니다!**
**❌ 파일이 길어도 전체를 읽어야 합니다!**

**🚀 지금 바로 Read 도구로 위 파일을 읽으세요!**

---
"""
        prompt_parts.append(template_read_instruction)

    prompt_parts.extend([
        completion_instruction,
        execution_instruction,
    ])

    # 최종 프롬프트 생성
    final_prompt = "\n".join(prompt_parts)

    # ⭐ v13.17: 토큰 수 검증
    is_within_limit, token_count, over_by = check_prompt_token_limit(final_prompt)
    print(f"[Claude Code] Prompt generated: {token_count:,} tokens")

    if not is_within_limit:
        print(f"[Claude Code] WARNING: Token limit exceeded! Need to reduce {over_by:,} tokens")
        # 에이전트 프롬프트 생략하여 크기 줄이기
        # (이미 핵심 규칙은 포함되어 있음)

    return final_prompt


def run_scene_analysis_agent(
    scenes_json_path: str,
    project_path: str = None,
    scene_range: tuple = None,
    bundle_mode: bool = True,
    custom_instructions: str = "",
    timeout: int = 600,
    progress_callback = None,
    selected_scene_ids: list = None,  # v13.7: 선택된 씬 ID 목록 추가
    prompt_id: str = None  # v3.95: 프롬프트 템플릿 ID 추가
) -> SceneAnalysisResult:
    """
    Claude Code 씬 분석 에이전트 실행

    ⚠️ v10.0: subprocess 방식 비활성화됨
    CLAUDE_CLI_DISABLED=True일 경우 에이전트 모드 결과 반환
    (프롬프트 복사 + 수동 실행 방식)

    Args:
        scenes_json_path: scenes.json 파일 경로
        project_path: 프로젝트 루트 경로 (None이면 자동 감지)
        scene_range: 분석할 씬 범위 (start, end)
        bundle_mode: 묶음 모드
        custom_instructions: 추가 지시사항
        timeout: 타임아웃 (초)
        progress_callback: 진행 상황 콜백
        selected_scene_ids: 분석할 씬 ID 목록 (v13.7 추가)

    Returns:
        SceneAnalysisResult 객체
    """
    import time as time_module
    from datetime import datetime

    start_time = time_module.time()

    # 프로젝트 경로 자동 감지
    if project_path is None:
        project_path = str(Path(__file__).parent.parent)

    # ═══════════════════════════════════════════════════════════════════
    # ⭐ v11.0: 새 CMD 창에서 자동 실행 (subprocess API 크레딧 문제 해결)
    # ═══════════════════════════════════════════════════════════════════
    if CLAUDE_CLI_DISABLED:
        print(f"\n{'='*70}")
        print(f"[Claude Code] 🚀 새 CMD 창에서 자동 실행 모드")
        print(f"[Claude Code] Max Plan 적용 - API 크레딧 소모 없음")
        print(f"{'='*70}\n")

        if progress_callback:
            progress_callback("새 CMD 창에서 Claude Code 실행 중...")

        # 프롬프트 생성 (v13.7: selected_scene_ids 전달, v3.95: prompt_id 전달)
        prompt = build_scene_analysis_prompt(
            scenes_json_path=scenes_json_path,
            project_path=project_path,
            scene_range=scene_range,
            bundle_mode=bundle_mode,
            custom_instructions=custom_instructions,
            selected_scene_ids=selected_scene_ids,  # v13.7: 선택된 씬 ID 목록 전달
            prompt_id=prompt_id  # v3.95: 프롬프트 템플릿 ID 전달!
        )

        # ⭐ v13.13: Bundle 정보 저장 (분석 후 병합에 사용)
        try:
            scenes_for_bundle = load_json_safe(scenes_json_path)
            if scenes_for_bundle and bundle_mode:
                video_path = str(Path(scenes_json_path).parent.parent)  # analysis 폴더의 부모
                save_bundle_info_for_claude_code(
                    scenes=scenes_for_bundle,
                    video_path=video_path,
                    selected_scene_ids=selected_scene_ids
                )
        except Exception as e:
            print(f"[Claude Code] ⚠️ Bundle 정보 저장 실패 (계속 진행): {e}")

        # ⭐ 새 CMD 창에서 자동 실행
        auto_result = execute_claude_code_in_new_window(
            prompt_text=prompt,
            project_path=project_path,
            scenes_json_path=scenes_json_path
        )

        if auto_result.success:
            print(f"[Claude Code] ✅ 새 CMD 창에서 실행 시작됨!")
            print(f"[Claude Code] 프롬프트 파일: {auto_result.prompt_file}")
            print(f"[Claude Code] 배치 파일: {auto_result.batch_file}")

            # 성공 결과 반환 - 실행 중 상태
            return SceneAnalysisResult(
                success=True,  # 실행 시작 성공
                output=prompt,
                error="",
                elapsed_time=time_module.time() - start_time,
                scenes_analyzed=0,  # 아직 분석 중
                scenes_failed=0,
                fields_generated={
                    'auto_execution': True,
                    'status': 'running',
                    'prompt_file': auto_result.prompt_file,
                    'batch_file': auto_result.batch_file,
                    'scenes_json_path': scenes_json_path,
                    'message': '새 CMD 창에서 Claude Code가 실행되고 있습니다. 완료 후 "결과 확인" 버튼을 클릭하세요.'
                }
            )
        else:
            print(f"[Claude Code] ❌ 자동 실행 실패: {auto_result.error}")

            # 실패 시 프롬프트 파일은 저장되어 있음
            return SceneAnalysisResult(
                success=False,
                output=prompt,
                error=f"자동 실행 실패: {auto_result.error}",
                elapsed_time=time_module.time() - start_time,
                scenes_analyzed=0,
                scenes_failed=0,
                fields_generated={
                    'auto_execution': False,
                    'prompt_file': auto_result.prompt_file,
                    'scenes_json_path': scenes_json_path,
                    'message': f'자동 실행 실패. 프롬프트 파일: {auto_result.prompt_file}'
                }
            )

    # ─────────────────────────────────────────────────────────────────────
    # 이하 기존 subprocess 실행 코드 (CLAUDE_CLI_DISABLED=False일 때만 실행)
    # ─────────────────────────────────────────────────────────────────────

    # 로그 디렉토리
    log_dir = Path(project_path) / 'logs' / 'claude_code'
    log_dir.mkdir(parents=True, exist_ok=True)

    # Claude Code 설치 확인
    status = check_claude_code_installation()
    if not status['installed']:
        return SceneAnalysisResult(
            success=False,
            output="",
            error=status['error'] or "Claude Code CLI를 사용할 수 없습니다.",
            elapsed_time=0
        )

    claude_path = status['path']

    # 프롬프트 생성 (v13.7: selected_scene_ids 전달)
    prompt = build_scene_analysis_prompt(
        scenes_json_path=scenes_json_path,
        project_path=project_path,
        scene_range=scene_range,
        bundle_mode=bundle_mode,
        custom_instructions=custom_instructions,
        selected_scene_ids=selected_scene_ids  # v13.7: 선택된 씬 ID 목록 전달
    )

    # 프롬프트 파일로 저장 (디버깅용)
    # v13.14: UTF-8 BOM으로 저장 (PowerShell 한글 호환성)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    prompt_file = log_dir / f"prompt_{timestamp}.md"
    prompt_file.write_text(prompt, encoding='utf-8-sig')

    print(f"\n{'='*70}")
    print(f"[ClaudeCode] 씬 분석 시작")
    print(f"[ClaudeCode] 프롬프트 파일 (UTF-8 BOM): {prompt_file}")
    print(f"[ClaudeCode] 씬 파일: {scenes_json_path}")
    print(f"{'='*70}\n")

    if progress_callback:
        progress_callback("Claude Code 실행 중...")

    try:
        # Claude Code 실행
        # --print: 결과를 stdout으로 출력
        # --dangerously-skip-permissions: 파일 수정 권한 자동 승인
        cmd = [
            claude_path,
            '--print',
            '--dangerously-skip-permissions',
            '-p', prompt
        ]

        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUTF8"] = "1"
        env["CLAUDE_NO_CONFIRM"] = "1"
        env["NO_COLOR"] = "1"

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=project_path,
            encoding='utf-8',
            errors='replace',
            env=env,
            shell=True
        )

        elapsed_time = time_module.time() - start_time

        # 결과 로그 저장
        log_file = log_dir / f"result_{timestamp}.txt"
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write(f"Exit Code: {result.returncode}\n")
            f.write(f"Elapsed: {elapsed_time:.2f}s\n")
            f.write(f"\n{'='*50}\nSTDOUT:\n{'='*50}\n")
            f.write(result.stdout or "")
            f.write(f"\n{'='*50}\nSTDERR:\n{'='*50}\n")
            f.write(result.stderr or "")

        print(f"\n[ClaudeCode] 실행 완료 ({elapsed_time:.1f}초)")
        print(f"[ClaudeCode] 로그 파일: {log_file}")

        # 결과 파싱
        output = result.stdout or ""
        error = result.stderr or ""

        analysis_result = _parse_scene_analysis_output(output)

        if progress_callback:
            progress_callback("분석 완료")

        return SceneAnalysisResult(
            success=result.returncode == 0,
            output=output,
            error=error if result.returncode != 0 else "",
            elapsed_time=elapsed_time,
            scenes_analyzed=analysis_result.get('analyzed', 0),
            scenes_failed=analysis_result.get('failed', 0),
            fields_generated=analysis_result.get('fields', {})
        )

    except subprocess.TimeoutExpired:
        elapsed_time = time_module.time() - start_time

        if progress_callback:
            progress_callback(f"타임아웃 ({timeout}초)")

        return SceneAnalysisResult(
            success=False,
            output="",
            error=f"타임아웃 ({timeout}초 초과)",
            elapsed_time=elapsed_time
        )

    except Exception as e:
        elapsed_time = time_module.time() - start_time

        if progress_callback:
            progress_callback(f"오류: {str(e)}")

        return SceneAnalysisResult(
            success=False,
            output="",
            error=str(e),
            elapsed_time=elapsed_time
        )


def _parse_scene_analysis_output(output: str) -> dict:
    """
    분석 결과 출력 파싱

    Args:
        output: Claude Code stdout

    Returns:
        파싱된 결과 딕셔너리
    """
    result = {
        'analyzed': 0,
        'failed': 0,
        'fields': {}
    }

    if not output:
        return result

    try:
        # "분석 성공: X" 패턴 찾기
        success_match = re.search(r'분석 성공[:\s]+(\d+)', output)
        if success_match:
            result['analyzed'] = int(success_match.group(1))

        # "총 씬 수: X" 패턴에서 추출 (분석 성공 없을 때)
        if result['analyzed'] == 0:
            total_match = re.search(r'총 씬[:\s]+(\d+)|(\d+)개\s*씬', output)
            if total_match:
                result['analyzed'] = int(total_match.group(1) or total_match.group(2))

        failed_match = re.search(r'분석 실패[:\s]+(\d+)', output)
        if failed_match:
            result['failed'] = int(failed_match.group(1))

        # 필드별 생성 현황 파싱
        field_pattern = r'-\s*(\w+)[:\s]+(\d+)/(\d+)'
        for match in re.finditer(field_pattern, output):
            field_name = match.group(1)
            count = int(match.group(2))
            result['fields'][field_name] = count

        # 다른 형식도 지원
        field_pattern2 = r'(\w+_prompt_en|characters|visual_elements|scene_mood)[:\s]+(\d+)'
        for match in re.finditer(field_pattern2, output):
            field_name = match.group(1)
            count = int(match.group(2))
            if field_name not in result['fields']:
                result['fields'][field_name] = count

    except Exception as e:
        print(f"[ClaudeCode] 출력 파싱 실패: {e}")

    return result


# ============================================================
# ⭐ v11.0: Claude Code 자동 실행 (새 CMD 창에서)
# ============================================================
# 이 방식은 새 CMD 창에서 Claude Code를 실행합니다.
# 사용자의 Claude Code Max Plan이 적용되어 무료입니다.
# subprocess로 백그라운드 실행하는 것과 다릅니다.
# ============================================================

@dataclass
class AutoExecutionResult:
    """자동 실행 결과"""
    success: bool
    status: str  # 'running', 'completed', 'failed', 'timeout'
    prompt_file: str = ""
    batch_file: str = ""
    ps1_file: str = ""  # v12.2: PowerShell 스크립트 파일 경로
    message: str = ""
    error: str = ""


def execute_claude_code_in_new_window(
    prompt_text: str,
    project_path: str,
    scenes_json_path: str = None
) -> AutoExecutionResult:
    """
    Claude Code를 새 CMD 창에서 실행 (v13.14 - script_ko 보존)

    ⭐ v13.14: script_ko 보존을 위한 원본 백업 추가
    - 분석 시작 전 scenes_original.json 백업

    ⭐ v13.10: PowerShell 한글 인코딩 오류 수정
    - PowerShell 스크립트를 UTF-8 BOM으로 저장 (encoding='utf-8-sig')
    - 모든 스크립트 메시지를 영어로 변경 (인코딩 문제 완전 방지)

    ⭐ v13.9: CMD 창 즉시 닫힘 문제 해결
    - 배치 파일에서 exit → pause로 변경하여 창 유지
    - @파일 참조 방식으로 긴 프롬프트 지원
    - 사용자가 아무 키나 누를 때까지 창 유지

    Args:
        prompt_text: 실행할 프롬프트 텍스트
        project_path: 프로젝트 경로
        scenes_json_path: scenes.json 경로 (선택)

    Returns:
        AutoExecutionResult
    """
    from datetime import datetime

    project_path = Path(project_path)
    logs_dir = project_path / 'logs' / 'claude_code'
    logs_dir.mkdir(parents=True, exist_ok=True)

    # ⭐ v13.14: 분석 전 원본 백업 (script_ko 보존)
    backup_original_scenes_before_analysis(str(project_path))

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    # 1. 프롬프트 파일 생성
    # v13.14: UTF-8 BOM으로 저장 (Windows PowerShell 한글 호환성)
    prompt_file = logs_dir / f'prompt_auto_{timestamp}.md'
    prompt_file.write_text(prompt_text, encoding='utf-8-sig')

    print(f"\n{'='*70}")
    print(f"[Claude Code] 프롬프트 파일 생성됨 (UTF-8 BOM): {prompt_file}")
    print(f"{'='*70}\n")

    # 1.5 초기 진행률 파일 생성 (Streamlit 폴링 전에 미리 생성)
    progress_file_early = logs_dir / '_progress.json'
    initial_progress = {
        "status": "starting",
        "current": 0,
        "total": 0,
        "message": "Claude Code 시작 준비 중..."
    }
    progress_file_early.write_text(json.dumps(initial_progress, ensure_ascii=False), encoding='utf-8')
    print(f"[Claude Code] 초기 진행률 파일 생성됨: {progress_file_early}")

    # 2. @ 명령어 생성 (상대 경로)
    try:
        prompt_relative = prompt_file.relative_to(project_path)
        prompt_ref = f"@{prompt_relative}".replace('\\', '/')
    except ValueError:
        prompt_ref = f"@{prompt_file}"

    # 3. 클립보드에 @ 명령어 복사 (Windows clip 명령어 사용)
    clipboard_copied = False
    try:
        # Windows 내장 clip 명령어 사용 (pyperclip 불필요)
        process = subprocess.Popen(
            'clip',
            stdin=subprocess.PIPE,
            shell=True
        )
        process.communicate(input=prompt_ref.encode('utf-8'))
        clipboard_copied = True
        print(f"[Claude Code] 클립보드에 복사됨: {prompt_ref}")
    except Exception as e:
        print(f"[Claude Code] 클립보드 복사 실패: {e}")
        print(f"[Claude Code] 수동으로 입력하세요: {prompt_ref}")

    # 4. 배치 파일 생성 (v13.4: 진행률 + 완료 신호 + 자동 종료)
    batch_file = logs_dir / f'run_auto_{timestamp}.bat'
    completion_flag = logs_dir / '_analysis_complete.flag'
    progress_file = logs_dir / '_progress.json'
    completion_flag_str = str(completion_flag).replace('/', '\\')
    progress_file_str = str(progress_file).replace('/', '\\')
    logs_dir_str = str(logs_dir).replace('/', '\\')

    # 프롬프트 파일 절대 경로 (Windows 형식)
    prompt_file_abs = str(prompt_file).replace('/', '\\')

    # v13.8: PowerShell 스크립트로 raw mode 에러 해결
    # stdin 리다이렉션 대신 --print -p 옵션 사용
    ps1_file = logs_dir / f'run_auto_{timestamp}.ps1'

    # v13.9: @파일 참조 방식으로 변경 (긴 프롬프트 지원 + 창 유지)
    # 프롬프트 파일 상대 경로 계산
    try:
        prompt_relative = prompt_file.relative_to(project_path)
        prompt_ref = str(prompt_relative).replace('\\', '/')
    except ValueError:
        prompt_ref = str(prompt_file).replace('\\', '/')

    # v13.12: PowerShell script content - Complete encoding fix for Korean
    ps1_content = f'''# Claude Code Auto Execution (v13.12 - Complete Korean encoding fix)
# @file reference method for long prompts

# ================================================================
# v13.12: Complete encoding settings for Korean support
# ================================================================

# 1. Set console code page to UTF-8
chcp 65001 | Out-Null

# 2. Set PowerShell encoding
$ErrorActionPreference = 'Continue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::InputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

# 3. Set environment variables
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"
$env:ANTHROPIC_API_KEY = ""

Write-Host ""
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "  Claude Code Auto Execution (Max Plan)"
Write-Host "  v13.12 - Complete Korean encoding fix"
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "[INFO] Start time: $(Get-Date)" -ForegroundColor Yellow
Write-Host "[INFO] Project: {project_path}" -ForegroundColor Yellow
Write-Host "[INFO] Prompt file: {prompt_file_abs}" -ForegroundColor Yellow
Write-Host "[INFO] Scenes file: {scenes_json_path or 'N/A'}" -ForegroundColor Yellow
Write-Host ""

# Change working directory
Set-Location -Path "{project_path}"
Write-Host "[OK] Working directory: $(Get-Location)" -ForegroundColor Green
Write-Host ""

# Clean up existing files
if (Test-Path "{completion_flag_str}") {{
    Remove-Item "{completion_flag_str}" -Force
    Write-Host "[INFO] Removed existing completion flag"
}}
if (Test-Path "{progress_file_str}") {{
    Remove-Item "{progress_file_str}" -Force
    Write-Host "[INFO] Removed existing progress file"
}}

# Create initial progress file
$initProgress = @{{status="starting"; current=0; total=0; message="Starting Claude Code..."}} | ConvertTo-Json -Compress
$initProgress | Out-File -FilePath "{progress_file_str}" -Encoding UTF8
Write-Host "[INFO] Initial progress file created"

# Check if prompt file exists
if (-not (Test-Path "{prompt_file_abs}")) {{
    Write-Host "[ERROR] Prompt file not found!" -ForegroundColor Red
    Write-Host "[ERROR] Path: {prompt_file_abs}" -ForegroundColor Red
    Write-Host ""
    Write-Host "Press any key to close this window..." -ForegroundColor Gray
    $null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
    exit 1
}}

Write-Host "[OK] Prompt file verified" -ForegroundColor Green
Write-Host ""

# v13.12: Preview prompt file with UTF-8 encoding
Write-Host "[DEBUG] Prompt preview (UTF-8):" -ForegroundColor Magenta
Write-Host "----------------------------------------"
Get-Content "{prompt_file_abs}" -Encoding UTF8 -TotalCount 5 | ForEach-Object {{ Write-Host $_ }}
Write-Host "----------------------------------------"
Write-Host ""

Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "[RUNNING] Claude Code Analysis Starting" -ForegroundColor Green
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host ""

# v13.12: @file reference method (supports long prompts + Korean)
Write-Host "[INFO] Command: claude --dangerously-skip-permissions @{prompt_ref}" -ForegroundColor Yellow
Write-Host ""

$exitCode = 0

try {{
    # Execute Claude Code (@file reference - interactive mode)
    # --dangerously-skip-permissions: auto-approve file modifications
    claude --dangerously-skip-permissions "@{prompt_ref}"
    $exitCode = $LASTEXITCODE
}} catch {{
    Write-Host "[ERROR] Execution error: $_" -ForegroundColor Red
    $exitCode = 1
}}

Write-Host ""
Write-Host "================================================================" -ForegroundColor Cyan
if ($exitCode -eq 0) {{
    Write-Host "[SUCCESS] Claude Code completed (exit code: $exitCode)" -ForegroundColor Green
}} else {{
    Write-Host "[WARNING] Claude Code exit code: $exitCode" -ForegroundColor Yellow
}}
Write-Host "[INFO] End time: $(Get-Date)" -ForegroundColor Yellow
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host ""

# Update progress to complete status
$completeProgress = @{{status="complete"; current=100; total=100; message="Analysis complete!"; exit_code=$exitCode}} | ConvertTo-Json -Compress
$completeProgress | Out-File -FilePath "{progress_file_str}" -Encoding UTF8
Write-Host "[INFO] Progress updated to complete status"

# Create completion signal file
"COMPLETE" | Out-File -FilePath "{completion_flag_str}" -Encoding UTF8
Write-Host "[INFO] Completion signal file created: {completion_flag_str}"

Write-Host ""
Write-Host "[INFO] Results: {scenes_json_path or 'N/A'}" -ForegroundColor Yellow
Write-Host ""
Write-Host "================================================================" -ForegroundColor Cyan
Write-Host "  Analysis completed!" -ForegroundColor Green
Write-Host "  Press any key to close this window..." -ForegroundColor Gray
Write-Host "================================================================" -ForegroundColor Cyan
$null = $Host.UI.RawUI.ReadKey("NoEcho,IncludeKeyDown")
'''

    # v13.12: Save with UTF-8 BOM for PowerShell Korean compatibility
    ps1_file.write_text(ps1_content, encoding='utf-8-sig')
    print(f"[Claude Code] PowerShell script created (UTF-8 BOM): {ps1_file}")

    # v13.17: Batch file - Fixed: Use -File instead of inline -Command to avoid ^ issues
    ps1_file_escaped = str(ps1_file).replace("/", chr(92))
    batch_content = f'''@echo off
chcp 65001 > nul
setlocal EnableDelayedExpansion
title Claude Code Scene Analysis

REM ================================================================
REM   Claude Code Auto Execution (v13.17 - Fixed PowerShell ^ error)
REM   - Uses PowerShell -File parameter (not -Command)
REM   - Full UTF-8 encoding support for Korean
REM   - Window stays open until user closes
REM ================================================================

echo.
echo ================================================================
echo   Claude Code Scene Analysis Starting
echo   (v13.17 - PowerShell encoding fixed)
echo ================================================================
echo.
echo [INFO] Running PowerShell script...
echo [INFO] Script: {ps1_file_escaped}
echo.

REM v13.17: Use -File parameter to run PowerShell script directly
REM This avoids the ^ line continuation issue that was causing errors
powershell -ExecutionPolicy Bypass -NoProfile -File "{ps1_file_escaped}"

echo.
echo ================================================================
echo   PowerShell script execution completed
echo ================================================================
echo.
echo Press any key to close this window...
pause > nul
'''

    # v13.12: Save batch file with UTF-8 encoding
    batch_file.write_text(batch_content, encoding='utf-8')
    print(f"[Claude Code] Batch file created: {batch_file}")

    # 5. 새 CMD 창에서 실행
    try:
        subprocess.Popen(
            f'start "Claude Code 자동 실행" cmd /k "{batch_file}"',
            shell=True,
            cwd=str(project_path)
        )

        print(f"[Claude Code] 자동 실행 시작!")
        print(f"[Claude Code] 프롬프트 자동 입력됨: {prompt_ref}")

        return AutoExecutionResult(
            success=True,
            status='running',
            prompt_file=str(prompt_file),
            batch_file=str(batch_file),
            ps1_file=str(completion_flag),  # v13.3: 완료 플래그 경로 저장
            message=f'Claude Code가 자동으로 실행되었습니다.\n\n분석이 완료되면 자동으로 창이 닫힙니다.\n완료 신호 파일: {completion_flag}'
        )

    except Exception as e:
        print(f"[Claude Code] 오류: {e}")
        return AutoExecutionResult(
            success=False,
            status='failed',
            prompt_file=str(prompt_file),
            batch_file=str(batch_file),
            ps1_file='',
            error=str(e),
            message=f'실행 오류: {e}'
        )


def create_auto_execution_prompt(
    scenes_json_path: str,
    project_path: str,
    scene_range: tuple = None,
    bundle_mode: bool = True,
    custom_instructions: str = ""
) -> str:
    """
    자동 실행용 프롬프트 생성

    Args:
        scenes_json_path: scenes.json 파일 경로
        project_path: 프로젝트 경로
        scene_range: 분석할 씬 범위 (start, end)
        bundle_mode: 묶음 모드
        custom_instructions: 추가 지시사항

    Returns:
        프롬프트 텍스트
    """
    return build_scene_analysis_prompt(
        scenes_json_path=scenes_json_path,
        project_path=project_path,
        scene_range=scene_range,
        bundle_mode=bundle_mode,
        custom_instructions=custom_instructions
    )


def run_scene_analysis_auto(
    scenes_json_path: str,
    project_path: str,
    scene_range: tuple = None,
    bundle_mode: bool = True,
    custom_instructions: str = ""
) -> AutoExecutionResult:
    """
    씬 분석 자동 실행 (새 CMD 창에서)

    Args:
        scenes_json_path: scenes.json 파일 경로
        project_path: 프로젝트 경로
        scene_range: 분석할 씬 범위
        bundle_mode: 묶음 모드
        custom_instructions: 추가 지시사항

    Returns:
        AutoExecutionResult
    """
    # 프롬프트 생성
    prompt = create_auto_execution_prompt(
        scenes_json_path=scenes_json_path,
        project_path=project_path,
        scene_range=scene_range,
        bundle_mode=bundle_mode,
        custom_instructions=custom_instructions
    )

    # 자동 실행
    return execute_claude_code_in_new_window(
        prompt_text=prompt,
        project_path=project_path,
        scenes_json_path=scenes_json_path
    )


# ============================================================
# ⭐ v13.4: 진행률 + 완료 감지 함수
# ============================================================

def get_progress_file_path(project_path: str) -> Path:
    """
    진행률 파일 경로 반환

    Args:
        project_path: 프로젝트 경로

    Returns:
        진행률 파일 Path 객체
    """
    return Path(project_path) / "logs" / "claude_code" / "_progress.json"


def get_completion_flag_path(project_path: str) -> Path:
    """
    완료 신호 파일 경로 반환

    Args:
        project_path: 프로젝트 경로

    Returns:
        완료 신호 파일 Path 객체
    """
    return Path(project_path) / "logs" / "claude_code" / "_analysis_complete.flag"


def check_claude_code_completion(project_path: str) -> bool:
    """
    Claude Code 완료 여부 확인 (v13.12: BOM 처리 추가)

    Args:
        project_path: 프로젝트 경로

    Returns:
        완료 여부 (True=성공 완료, False=미완료 또는 오류)
    """
    completion_flag = get_completion_flag_path(project_path)
    if not completion_flag.exists():
        return False

    # v13.12: read_text_safe 사용 (BOM 자동 처리)
    try:
        content = read_text_safe(str(completion_flag))
        if content:
            content = content.strip().upper()
            if content == "COMPLETE":
                return True
            elif "ERROR" in content or "FAIL" in content:
                print(f"[check_completion] 오류 감지: {content}")
                return False
            else:
                # 알 수 없는 내용이면 완료로 간주 (호환성)
                return True
        else:
            return completion_flag.exists()
    except Exception as e:
        print(f"[check_completion] 플래그 파일 읽기 실패: {e}")
        return completion_flag.exists()  # fallback: 존재 여부만 확인


def get_analysis_status(project_path: str) -> dict:
    """
    Claude Code 분석 상태 상세 확인 (v13.11 신규)

    Args:
        project_path: 프로젝트 경로

    Returns:
        상태 딕셔너리:
        - status: 'not_started', 'running', 'complete', 'error'
        - message: 상태 메시지
        - progress: 진행률 정보 (있으면)
        - error: 오류 메시지 (있으면)
    """
    completion_flag = get_completion_flag_path(project_path)
    progress_file = get_progress_file_path(project_path)

    result = {
        'status': 'not_started',
        'message': '',
        'progress': None,
        'error': None
    }

    # 1. 진행률 파일 확인 (v13.12: BOM 처리)
    if progress_file.exists():
        try:
            # v13.12: load_json_safe 사용 (BOM 자동 처리)
            progress = load_json_safe(str(progress_file))
            if progress:
                result['progress'] = progress

                if progress.get('status') == 'complete':
                    result['status'] = 'complete'
                    result['message'] = progress.get('message', '분석 완료')

                    # 오류 체크
                    exit_code = progress.get('exit_code', 0)
                    if exit_code != 0:
                        result['status'] = 'error'
                        result['error'] = f'종료 코드: {exit_code}'
                    return result

                elif progress.get('status') == 'running':
                    result['status'] = 'running'
                    current = progress.get('current', 0)
                    total = progress.get('total', 0)
                    result['message'] = f"분석 중: {current}/{total}"
                    return result

                elif progress.get('status') == 'starting':
                    result['status'] = 'running'
                    result['message'] = '시작 중...'
                    return result

        except Exception as e:
            print(f"[get_analysis_status] 진행률 파일 파싱 실패: {e}")

    # 2. 완료 플래그 확인 (v13.12: BOM 처리)
    if completion_flag.exists():
        try:
            content = read_text_safe(str(completion_flag))
            if content:
                content = content.strip()
                if content.upper() == "COMPLETE":
                    result['status'] = 'complete'
                    result['message'] = '분석 완료'
                elif "ERROR" in content.upper() or "FAIL" in content.upper():
                    result['status'] = 'error'
                    result['error'] = content
                    result['message'] = f'오류 발생: {content}'
                else:
                    result['status'] = 'complete'
                    result['message'] = '분석 완료 (내용 불명)'
            else:
                result['status'] = 'complete'
                result['message'] = '분석 완료 (파일 읽기 실패)'
        except Exception as e:
            result['status'] = 'complete'
            result['message'] = '분석 완료 (파일 읽기 실패)'

    return result


def clear_completion_flag(project_path: str) -> bool:
    """
    완료 신호 파일 삭제

    Args:
        project_path: 프로젝트 경로

    Returns:
        삭제 성공 여부
    """
    completion_flag = get_completion_flag_path(project_path)
    try:
        if completion_flag.exists():
            completion_flag.unlink()
            print(f"[Claude Code] 완료 신호 파일 삭제됨: {completion_flag}")
            return True
        return False
    except Exception as e:
        print(f"[Claude Code] 완료 신호 파일 삭제 실패: {e}")
        return False


def wait_for_claude_code_completion(
    project_path: str,
    timeout: int = 600,
    poll_interval: float = 2.0,
    progress_callback = None
) -> dict:
    """
    Claude Code 완료 대기 (폴링 방식)

    Args:
        project_path: 프로젝트 경로
        timeout: 최대 대기 시간 (초)
        poll_interval: 폴링 간격 (초)
        progress_callback: 진행 상황 콜백 (선택)

    Returns:
        완료 결과 딕셔너리:
        - success: 완료 여부
        - elapsed: 경과 시간
        - error: 오류 메시지 (실패 시)
    """
    start_time = time.time()
    completion_flag = get_completion_flag_path(project_path)

    print(f"[Claude Code] 완료 대기 시작 (최대 {timeout}초)")
    print(f"[Claude Code] 완료 신호 파일: {completion_flag}")

    while True:
        elapsed = time.time() - start_time

        # 타임아웃 체크
        if elapsed > timeout:
            print(f"[Claude Code] 타임아웃 ({timeout}초)")
            return {
                'success': False,
                'elapsed': elapsed,
                'error': f'타임아웃 ({timeout}초)'
            }

        # 완료 신호 파일 체크
        if completion_flag.exists():
            print(f"[Claude Code] 완료 신호 감지! ({elapsed:.1f}초)")

            # 완료 신호 파일 삭제
            try:
                completion_flag.unlink()
            except:
                pass

            return {
                'success': True,
                'elapsed': elapsed,
                'message': '분석 완료!'
            }

        # 진행 상황 콜백
        if progress_callback:
            progress_callback(elapsed, timeout)

        # 폴링 대기
        time.sleep(poll_interval)


def get_claude_code_progress(project_path: str) -> dict:
    """
    Claude Code 진행률 읽기

    Args:
        project_path: 프로젝트 경로

    Returns:
        진행률 딕셔너리 또는 None:
        - status: 'starting', 'running', 'complete'
        - current: 현재 진행 씬 수
        - total: 전체 씬 수
        - message: 상태 메시지
    """
    progress_file = get_progress_file_path(project_path)

    if not progress_file.exists():
        return None

    try:
        return json.loads(progress_file.read_text(encoding='utf-8'))
    except Exception as e:
        print(f"[Claude Code] 진행률 파일 읽기 실패: {e}")
        return None


def cleanup_claude_code_files(project_path: str) -> bool:
    """
    Claude Code 임시 파일 정리 (진행률 + 완료 플래그)

    Args:
        project_path: 프로젝트 경로

    Returns:
        정리 성공 여부
    """
    files_to_remove = [
        get_progress_file_path(project_path),
        get_completion_flag_path(project_path)
    ]

    success = True
    for f in files_to_remove:
        try:
            if f.exists():
                f.unlink()
                print(f"[Claude Code] 파일 삭제됨: {f}")
        except Exception as e:
            print(f"[Claude Code] 파일 삭제 실패 ({f}): {e}")
            success = False

    return success


def wait_for_claude_code_with_progress(
    project_path: str,
    timeout: int = 600,
    poll_interval: float = 1.0,
    progress_callback = None
) -> dict:
    """
    Claude Code 완료 대기 + 실시간 진행률 모니터링

    Args:
        project_path: 프로젝트 경로
        timeout: 최대 대기 시간 (초)
        poll_interval: 폴링 간격 (초)
        progress_callback: 진행 상황 콜백
            - 호출 형식: callback(progress_dict, elapsed_time)
            - progress_dict: {status, current, total, message}

    Returns:
        완료 결과 딕셔너리:
        - success: 완료 여부
        - elapsed: 경과 시간
        - progress: 마지막 진행률 정보
        - error: 오류 메시지 (실패 시)
    """
    start_time = time.time()
    completion_flag = get_completion_flag_path(project_path)
    last_progress = None

    print(f"[Claude Code] 진행률 모니터링 시작 (최대 {timeout}초)")

    while True:
        elapsed = time.time() - start_time

        # 타임아웃 체크
        if elapsed > timeout:
            print(f"[Claude Code] 타임아웃 ({timeout}초)")
            return {
                'success': False,
                'elapsed': elapsed,
                'progress': last_progress,
                'error': f'타임아웃 ({timeout}초)'
            }

        # 완료 신호 파일 체크
        if completion_flag.exists():
            print(f"[Claude Code] 완료 신호 감지! ({elapsed:.1f}초)")

            return {
                'success': True,
                'elapsed': elapsed,
                'progress': last_progress,
                'message': '분석 완료!'
            }

        # 진행률 읽기
        progress = get_claude_code_progress(project_path)

        if progress:
            last_progress = progress

            # 진행 상황 콜백
            if progress_callback:
                progress_callback(progress, elapsed)

            # 진행률 완료 상태 체크 (완료 플래그 없어도 진행률이 complete면 완료)
            if progress.get('status') == 'complete':
                print(f"[Claude Code] 진행률 완료 상태 감지! ({elapsed:.1f}초)")
                return {
                    'success': True,
                    'elapsed': elapsed,
                    'progress': progress,
                    'message': progress.get('message', '분석 완료!')
                }

        # 폴링 대기
        time.sleep(poll_interval)


def reload_scenes_json(scenes_json_path: str) -> list:
    """
    scenes.json 파일 다시 로드

    Args:
        scenes_json_path: scenes.json 파일 경로

    Returns:
        로드된 씬 목록 (실패 시 None)
    """
    try:
        scenes_path = Path(scenes_json_path)
        if scenes_path.exists():
            scenes = json.loads(scenes_path.read_text(encoding='utf-8'))
            print(f"[Claude Code] scenes.json 다시 로드됨: {len(scenes)}개 씬")
            return scenes
        else:
            print(f"[Claude Code] scenes.json 파일 없음: {scenes_json_path}")
            return None
    except Exception as e:
        print(f"[Claude Code] scenes.json 로드 실패: {e}")
        return None


def sync_scenes_to_session_state(scenes: list, scenes_json_path: str = None) -> dict:
    """
    씬 데이터를 Streamlit session_state의 모든 관련 키에 동기화

    v13.16: 캐릭터 추출 및 characters.json 저장 추가!

    이 함수는 Streamlit 컨텍스트에서 호출해야 합니다.
    utils 모듈에서는 동기화할 키 목록만 반환합니다.

    Args:
        scenes: 씬 데이터 리스트
        scenes_json_path: scenes.json 파일 경로 (선택)

    Returns:
        동기화할 데이터 딕셔너리
    """
    from datetime import datetime

    # 분석 완료 여부 확인
    analyzed_count = sum(1 for s in scenes if s.get('background_prompt_en'))

    # ⭐ v13.16: 씬에서 캐릭터 추출
    characters = extract_characters_from_scenes(scenes)
    print(f"[Sync] 캐릭터 추출: {len(characters)}개")

    # ⭐ v13.16: characters.json 파일 저장
    if scenes_json_path and characters:
        try:
            characters_path = Path(scenes_json_path).parent / "characters.json"
            with open(characters_path, 'w', encoding='utf-8') as f:
                json.dump(characters, f, ensure_ascii=False, indent=2)
            print(f"[Sync] ✅ characters.json 저장: {characters_path}")
        except Exception as e:
            print(f"[Sync] ⚠️ characters.json 저장 실패: {e}")

    # 동기화할 데이터
    sync_data = {
        # 메인 씬 데이터 (여러 키에 동일 데이터)
        'scenes': scenes,
        'scenes_data': scenes,
        'analysis_scenes': scenes,
        'loaded_scenes': scenes,
        'current_scenes': scenes,

        # 분석 상태 플래그
        'analysis_complete': True,
        'has_analysis_data': analyzed_count > 0,
        'scenes_analyzed': analyzed_count > 0,
        'scenes_json_loaded': True,

        # 메타 정보
        'scenes_count': len(scenes),
        'analyzed_scenes_count': analyzed_count,
        'scenes_loaded_at': datetime.now().isoformat(),
        'last_analysis_time': datetime.now().isoformat(),

        # ⭐ v13.16: 캐릭터 데이터 추가
        'scene_characters': characters,
        'characters_count': len(characters),
    }

    if scenes_json_path:
        sync_data['scenes_json_path'] = scenes_json_path

    print(f"[Sync] 동기화 데이터 준비됨: {len(scenes)}개 씬, {analyzed_count}개 분석됨, {len(characters)}개 캐릭터")

    return sync_data


def extract_characters_from_scenes(scenes: list) -> list:
    """
    씬 리스트에서 캐릭터 정보 추출 (v13.16)

    scenes.json의 각 씬에서 characters 필드와 character_prompt_en 필드를 수집합니다.

    Args:
        scenes: 씬 데이터 리스트

    Returns:
        고유 캐릭터 리스트 [{name, description, description_en, visual_prompt, scenes, ...}]
    """

    character_map = {}  # {name: character_data}

    for scene in scenes:
        scene_id = scene.get('scene_id', scene.get('scene_number'))

        # 1. characters 필드에서 추출
        scene_chars = scene.get('characters', [])

        if scene_chars:
            for char in scene_chars:
                if isinstance(char, dict):
                    # 딕셔너리 형식: {"name": "이재용", "visual_prompt": "..."}
                    char_name = char.get('name', '')

                    if not char_name or char_name.lower() in ['narrator', '나레이터', 'unknown']:
                        continue

                    if char_name not in character_map:
                        character_map[char_name] = {
                            'name': char_name,
                            'name_ko': char_name,
                            'name_en': char.get('name_en', ''),
                            'description': char.get('description', ''),
                            'description_en': char.get('description_en', ''),
                            'visual_prompt': char.get('visual_prompt', ''),
                            'character_prompt': char.get('visual_prompt', ''),
                            'role': char.get('role', '등장인물'),
                            'scenes': [],
                            'appearance_count': 0
                        }

                    # 씬 정보 추가
                    if scene_id and scene_id not in character_map[char_name]['scenes']:
                        character_map[char_name]['scenes'].append(scene_id)
                        character_map[char_name]['appearance_count'] += 1

                    # visual_prompt 업데이트 (비어있으면)
                    if not character_map[char_name]['visual_prompt'] and char.get('visual_prompt'):
                        character_map[char_name]['visual_prompt'] = char.get('visual_prompt')
                        character_map[char_name]['character_prompt'] = char.get('visual_prompt')

                elif isinstance(char, str):
                    # 문자열 형식: "이재용"
                    char_name = char

                    if not char_name or char_name.lower() in ['narrator', '나레이터', 'unknown']:
                        continue

                    if char_name not in character_map:
                        character_map[char_name] = {
                            'name': char_name,
                            'name_ko': char_name,
                            'name_en': '',
                            'description': '',
                            'description_en': '',
                            'visual_prompt': '',
                            'character_prompt': '',
                            'role': '등장인물',
                            'scenes': [],
                            'appearance_count': 0
                        }

                    if scene_id and scene_id not in character_map[char_name]['scenes']:
                        character_map[char_name]['scenes'].append(scene_id)
                        character_map[char_name]['appearance_count'] += 1

        # 2. character_prompt_en에서 visual_prompt 추출 (캐릭터가 있는 경우)
        char_prompt_en = scene.get('character_prompt_en', '')
        if char_prompt_en:
            # 이미 등록된 캐릭터의 visual_prompt 업데이트
            for char_name in character_map:
                if not character_map[char_name]['visual_prompt']:
                    # 씬에 이 캐릭터가 등장하면 프롬프트 할당
                    if scene_id in character_map[char_name]['scenes']:
                        character_map[char_name]['visual_prompt'] = char_prompt_en
                        character_map[char_name]['character_prompt'] = char_prompt_en

    # 딕셔너리를 리스트로 변환
    characters = list(character_map.values())

    # 등장 횟수 순으로 정렬
    characters.sort(key=lambda x: x.get('appearance_count', 0), reverse=True)

    print(f"[Extract Characters] {len(characters)}개 캐릭터 추출:")
    for char in characters[:5]:  # 상위 5개만 로그
        print(f"  - {char['name']}: {char['appearance_count']}개 씬")

    return characters


def get_scenes_from_any_source(scenes_json_path: str = None, session_state: dict = None) -> list:
    """
    씬 데이터를 여러 소스에서 가져오기 (session_state 또는 파일)

    Args:
        scenes_json_path: scenes.json 파일 경로 (선택)
        session_state: Streamlit session_state 딕셔너리 (선택)

    Returns:
        씬 데이터 리스트 (없으면 빈 리스트)
    """
    # 1. session_state에서 시도
    if session_state:
        possible_keys = ['scenes', 'scenes_data', 'analysis_scenes', 'loaded_scenes', 'current_scenes']
        for key in possible_keys:
            if key in session_state and session_state[key]:
                return session_state[key]

    # 2. 파일에서 로드
    if scenes_json_path:
        scenes = reload_scenes_json(scenes_json_path)
        if scenes:
            return scenes

    return []


# ============================================================
# ⭐ v13.13: Bundle 병합 기능 추가
# Claude Code 분석 후 대표 씬 결과를 묶음 내 다른 씬에 적용
# ============================================================

def save_bundle_info_for_claude_code(
    scenes: list,
    video_path: str,
    selected_scene_ids: list = None
) -> dict:
    """
    Claude Code 분석 전 Bundle 정보 저장 (v13.20 최적화)

    토큰 초과 방지를 위해 묶음 정보와 combined_script를 미리 생성합니다.
    Claude Code는 이 파일을 읽어서 scenes.json 전체 읽기 없이 분석 가능.

    Args:
        scenes: 전체 씬 리스트
        video_path: 비디오/프로젝트 경로
        selected_scene_ids: 선택된 씬 ID 목록 (None이면 전체)

    Returns:
        bundle_info 데이터 및 저장 경로
    """
    from datetime import datetime

    print(f"\n[Bundle Info] ========== v13.20 최적화 Bundle 정보 저장 ==========")

    # 선택된 씬 필터링
    if selected_scene_ids:
        target_scenes = [s for s in scenes if s.get('scene_id') in selected_scene_ids]
    else:
        target_scenes = scenes

    # 씬 정렬
    sorted_scenes = sorted(target_scenes, key=lambda x: x.get('scene_id', 0))

    # scene_id로 빠른 검색을 위한 맵
    scene_map = {s.get('scene_id'): s for s in sorted_scenes}

    # Bundle 구조 생성 (combined_script 포함!)
    bundle_dict = {}  # {bundle_id: {"scene_ids": [], "scenes": []}}

    for scene in sorted_scenes:
        scene_id = scene.get('scene_id')
        bundle_id = scene.get('bundle_id', scene_id)

        if bundle_id not in bundle_dict:
            bundle_dict[bundle_id] = {"scene_ids": [], "scenes": []}

        bundle_dict[bundle_id]["scene_ids"].append(scene_id)
        bundle_dict[bundle_id]["scenes"].append(scene)

    # 묶음 리스트로 변환 (combined_script 생성!)
    bundles = []
    for bundle_id in sorted(bundle_dict.keys()):
        bundle_data = bundle_dict[bundle_id]
        scene_ids = bundle_data["scene_ids"]
        bundle_scenes = bundle_data["scenes"]

        # combined_script 생성 (핵심!)
        combined_parts = []
        for s in bundle_scenes:
            script = s.get('script') or s.get('script_ko') or s.get('script_text') or s.get('narration') or ''
            if script:
                combined_parts.append(f"[씬 {s.get('scene_id')}] {script}")

        combined_script = "\n".join(combined_parts)

        bundle = {
            "bundle_id": bundle_id,
            "scene_ids": scene_ids,
            "scene_count": len(scene_ids),
            "combined_script": combined_script,
            "primary_scene_id": scene_ids[0] if scene_ids else None
        }
        bundles.append(bundle)

    # 저장 경로
    analysis_dir = Path(video_path) / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    bundle_info_path = analysis_dir / "bundle_info_claude_code.json"

    # 저장 데이터 (v13.20 최적화 형식)
    save_data = {
        "version": "1.0",
        "generated_at": datetime.now().isoformat(),
        "config": {
            "process_batch_size": 5,  # 5개 묶음씩 처리
            "max_read_lines": 100     # 한 번에 최대 100줄
        },
        "summary": {
            "total_scenes": len(sorted_scenes),
            "total_bundles": len(bundles),
        },
        "rules": {
            "no_full_file_read": True,
            "use_grep_or_offset": True,
            "update_every_n_bundles": 5,
            "no_background_agents": True,
            "no_python_scripts": True,
            "no_questions": True
        },
        "bundles": bundles,
        # 레거시 호환성 유지
        "bundle_info": {b["bundle_id"]: b["scene_ids"] for b in bundles},
        "primary_scene_ids": [b["primary_scene_id"] for b in bundles if b["primary_scene_id"]],
        "all_scene_ids": [s.get('scene_id') for s in sorted_scenes]
    }

    # 파일 저장
    with open(bundle_info_path, 'w', encoding='utf-8') as f:
        json.dump(save_data, f, ensure_ascii=False, indent=2)

    print(f"[Bundle Info] 전체 씬: {len(sorted_scenes)}개")
    print(f"[Bundle Info] 전체 묶음: {len(bundles)}개")
    print(f"[Bundle Info] combined_script 포함: ✅")
    print(f"[Bundle Info] 5개 묶음씩 처리 규칙: ✅")
    print(f"[Bundle Info] 저장 경로: {bundle_info_path}")
    print(f"[Bundle Info] ==========================================\n")

    return {
        "bundle_info": save_data["bundle_info"],
        "primary_scene_ids": save_data["primary_scene_ids"],
        "all_scene_ids": save_data["all_scene_ids"],
        "bundle_info_path": str(bundle_info_path),
        "bundles": bundles
    }


def apply_bundle_merge_after_claude_code(
    video_path: str,
    all_scenes: list = None
) -> dict:
    """
    Claude Code 분석 완료 후 Bundle 병합 적용 (v13.14)

    대표 씬의 분석 결과를 같은 묶음의 다른 씬에 복사합니다.

    ⭐ v13.14: script_ko 보존 수정
    - script_ko, script_en은 각 씬 고유 데이터로 복사하지 않음
    - 원본 scenes_original.json 또는 SRT에서 script_ko 복구

    Args:
        video_path: 비디오/프로젝트 경로
        all_scenes: 전체 씬 리스트 (None이면 백업에서 로드)

    Returns:
        {
            "success": bool,
            "merged_count": int,
            "total_scenes": int,
            "scenes": 병합된 씬 리스트,
            "error": 에러 메시지 (실패 시)
        }
    """
    print(f"\n[Bundle Merge] ========== Bundle 병합 시작 (v13.14) ==========")

    try:
        analysis_dir = Path(video_path) / "analysis"
        scenes_json_path = analysis_dir / "scenes.json"
        bundle_info_path = analysis_dir / "bundle_info_claude_code.json"

        # 1. Bundle 정보 로드
        if not bundle_info_path.exists():
            print(f"[Bundle Merge] ⚠️ bundle_info_claude_code.json 없음 - scenes.json에서 추출")
            bundle_info = _extract_bundle_info_from_scenes(str(scenes_json_path))
        else:
            bundle_data = load_json_safe(str(bundle_info_path))
            if bundle_data:
                bundle_info = bundle_data.get("bundle_info", {})
                print(f"[Bundle Merge] ✅ Bundle 정보 로드: {len(bundle_info)}개 묶음")
            else:
                bundle_info = _extract_bundle_info_from_scenes(str(scenes_json_path))

        if not bundle_info:
            print(f"[Bundle Merge] ⚠️ Bundle 정보 없음 - 병합 스킵")
            return {"success": False, "error": "Bundle 정보 없음", "merged_count": 0}

        # 2. Claude Code가 분석한 scenes.json 로드
        analyzed_scenes = load_json_safe(str(scenes_json_path))
        if not analyzed_scenes:
            return {"success": False, "error": "scenes.json 로드 실패", "merged_count": 0}

        # 분석된 씬을 딕셔너리로 변환
        analyzed_dict = {s.get('scene_id'): s for s in analyzed_scenes}
        print(f"[Bundle Merge] Claude Code 분석 결과: {len(analyzed_scenes)}개 씬")

        # ⭐ v13.14: 원본 스크립트 로드 (script_ko 보존용)
        original_scripts = _load_original_scripts(video_path)
        if original_scripts:
            print(f"[Bundle Merge] ✅ 원본 스크립트 로드: {len(original_scripts)}개 씬")
        else:
            print(f"[Bundle Merge] ⚠️ 원본 스크립트 없음 - 분석 결과의 script_ko 사용")

        # 3. 전체 씬 준비 (all_scenes가 없으면 분석된 씬 사용)
        if all_scenes is None:
            # 백업 파일에서 로드 시도
            backup_pattern = list(analysis_dir.glob("scenes_backup_*.json"))
            if backup_pattern:
                latest_backup = max(backup_pattern, key=lambda p: p.stat().st_mtime)
                all_scenes = load_json_safe(str(latest_backup))
                if all_scenes:
                    print(f"[Bundle Merge] 백업에서 전체 씬 로드: {len(all_scenes)}개")

            # 백업이 없으면 분석된 씬 사용
            if not all_scenes:
                all_scenes = analyzed_scenes
                print(f"[Bundle Merge] 분석된 씬을 기준으로 병합")

        all_scenes_dict = {s.get('scene_id'): s for s in all_scenes}

        # ⭐ v13.14: 분석 결과 필드 정의 (script_ko, script_en 제외!)
        # script_ko, script_en은 각 씬 고유 데이터이므로 대표 씬에서 복사하면 안됨
        analysis_fields = [
            'image_prompt', 'image_prompt_en',
            'image_prompt_korean_text',
            'background_prompt', 'background_prompt_en',
            'character_prompt', 'character_prompt_en',
            'visual_elements', 'direction_guide',
            'camera_suggestion', 'video_prompt_character',
            'video_prompt_full', 'characters', 'location', 'mood',
            'korean_text_prompt'
            # ❌ 'script_en', 'script_ko' 제외! - 각 씬 고유 데이터
        ]

        # 5. Bundle 병합 수행
        result_scenes = []
        merged_count = 0
        processed_scene_ids = set()

        # bundle_info의 키를 정수로 변환 (JSON에서 문자열로 저장될 수 있음)
        for bundle_id_str, scene_ids in bundle_info.items():
            bundle_id = int(bundle_id_str) if isinstance(bundle_id_str, str) else bundle_id_str
            scene_ids_sorted = sorted(scene_ids)

            if not scene_ids_sorted:
                continue

            # 대표 씬 찾기 (분석된 씬 중 첫 번째)
            primary_scene_id = None
            primary_data = None

            for sid in scene_ids_sorted:
                if sid in analyzed_dict:
                    candidate = analyzed_dict[sid]
                    # 분석 결과가 있는지 확인
                    if candidate.get('background_prompt_en') or candidate.get('image_prompt_en'):
                        primary_scene_id = sid
                        primary_data = candidate
                        break

            if not primary_data:
                # 분석 결과 없음 - 원본 씬 그대로 사용
                for sid in scene_ids_sorted:
                    if sid in all_scenes_dict and sid not in processed_scene_ids:
                        result_scenes.append(all_scenes_dict[sid])
                        processed_scene_ids.add(sid)
                continue

            print(f"[Bundle Merge] 📦 묶음 {bundle_id} (대표: 씬 {primary_scene_id})")

            # 묶음 내 모든 씬에 결과 적용
            for sid in scene_ids_sorted:
                if sid in processed_scene_ids:
                    continue

                # 원본 씬 데이터 가져오기
                if sid in all_scenes_dict:
                    scene = all_scenes_dict[sid].copy()
                elif sid in analyzed_dict:
                    scene = analyzed_dict[sid].copy()
                else:
                    continue

                # 분석 결과 필드 복사 (script_ko, script_en 제외됨)
                for field in analysis_fields:
                    if field in primary_data and primary_data[field]:
                        scene[field] = primary_data[field]

                # ⭐ v13.14: script_ko 복원 (원본에서 가져오기)
                if original_scripts and sid in original_scripts:
                    orig_script = original_scripts[sid]
                    if orig_script.get('script_ko'):
                        scene['script_ko'] = orig_script['script_ko']
                    if orig_script.get('script_en') and not scene.get('script_en'):
                        scene['script_en'] = orig_script['script_en']

                # 대표 씬 플래그 설정
                scene['is_bundle_primary'] = (sid == primary_scene_id)
                scene['is_primary'] = (sid == primary_scene_id)

                result_scenes.append(scene)
                processed_scene_ids.add(sid)

                if sid != primary_scene_id:
                    merged_count += 1
                    print(f"[Bundle Merge]   ✅ 씬 {sid}: 대표 씬 결과 병합됨")
                else:
                    print(f"[Bundle Merge]   ✅ 씬 {sid}: 대표 씬 (원본)")

        # 6. 병합되지 않은 씬 추가 (단독 씬)
        for scene in all_scenes:
            sid = scene.get('scene_id')
            if sid not in processed_scene_ids:
                # 분석 결과가 있으면 사용
                if sid in analyzed_dict:
                    scene_to_add = analyzed_dict[sid].copy()
                else:
                    scene_to_add = scene.copy()

                # ⭐ v13.14: script_ko 복원 (단독 씬도)
                if original_scripts and sid in original_scripts:
                    orig_script = original_scripts[sid]
                    if orig_script.get('script_ko'):
                        scene_to_add['script_ko'] = orig_script['script_ko']
                    if orig_script.get('script_en') and not scene_to_add.get('script_en'):
                        scene_to_add['script_en'] = orig_script['script_en']

                result_scenes.append(scene_to_add)
                processed_scene_ids.add(sid)

        # 7. scene_id로 정렬
        result_scenes = sorted(result_scenes, key=lambda x: x.get('scene_id', 0))

        # 8. 결과 저장
        with open(scenes_json_path, 'w', encoding='utf-8') as f:
            json.dump(result_scenes, f, ensure_ascii=False, indent=2)

        # ⭐ v13.14: script_ko 보존 검증
        scenes_with_script = sum(1 for s in result_scenes if s.get('script_ko'))

        print(f"\n[Bundle Merge] 📊 병합 결과:")
        print(f"[Bundle Merge]   - 전체 씬: {len(result_scenes)}개")
        print(f"[Bundle Merge]   - 병합된 씬: {merged_count}개")
        print(f"[Bundle Merge]   - script_ko 있는 씬: {scenes_with_script}개")
        print(f"[Bundle Merge] ✅ scenes.json 저장 완료")
        print(f"[Bundle Merge] ==========================================\n")

        return {
            "success": True,
            "merged_count": merged_count,
            "total_scenes": len(result_scenes),
            "scenes_with_script": scenes_with_script,
            "scenes": result_scenes
        }

    except Exception as e:
        print(f"[Bundle Merge] ❌ 오류: {e}")
        import traceback
        traceback.print_exc()
        return {"success": False, "error": str(e), "merged_count": 0}


def _extract_bundle_info_from_scenes(scenes_json_path: str) -> dict:
    """scenes.json에서 Bundle 정보 추출 (헬퍼 함수)"""
    scenes = load_json_safe(scenes_json_path)
    if not scenes:
        return {}

    bundle_info = {}
    for scene in scenes:
        bundle_id = scene.get('bundle_id', scene.get('scene_id'))
        scene_id = scene.get('scene_id')

        if bundle_id not in bundle_info:
            bundle_info[bundle_id] = []

        if scene_id not in bundle_info[bundle_id]:
            bundle_info[bundle_id].append(scene_id)

    return bundle_info


def _load_original_scripts(video_path: str) -> dict:
    """
    원본 스크립트(script_ko, script_en) 로드 (v13.14)

    우선순위:
    1. scenes_original.json (분석 전 백업)
    2. scenes_backup_*.json (가장 최근 백업)
    3. SRT 파일에서 직접 파싱

    Returns:
        {scene_id: {"script_ko": "...", "script_en": "..."}, ...}
    """
    import re

    analysis_dir = Path(video_path) / "analysis"
    result = {}

    # 1. scenes_original.json 확인 (분석 전 백업)
    original_path = analysis_dir / "scenes_original.json"
    if original_path.exists():
        scenes = load_json_safe(str(original_path))
        if scenes:
            for s in scenes:
                sid = s.get('scene_id')
                if sid and s.get('script_ko'):
                    result[sid] = {
                        'script_ko': s.get('script_ko', ''),
                        'script_en': s.get('script_en', '')
                    }
            if result:
                print(f"[Original Scripts] ✅ scenes_original.json에서 로드: {len(result)}개")
                return result

    # 2. scenes_backup_*.json 확인 (가장 최근 백업)
    backup_files = list(analysis_dir.glob("scenes_backup_*.json"))
    if backup_files:
        latest_backup = max(backup_files, key=lambda p: p.stat().st_mtime)
        scenes = load_json_safe(str(latest_backup))
        if scenes:
            for s in scenes:
                sid = s.get('scene_id')
                if sid and s.get('script_ko'):
                    result[sid] = {
                        'script_ko': s.get('script_ko', ''),
                        'script_en': s.get('script_en', '')
                    }
            if result:
                print(f"[Original Scripts] ✅ 백업에서 로드: {latest_backup.name}")
                return result

    # 3. SRT 파일에서 직접 파싱
    srt_path = Path(video_path) / "subtitles.srt"
    if not srt_path.exists():
        # videos 폴더 상위에서 찾기
        srt_path = Path(video_path).parent / "subtitles.srt"

    if srt_path.exists():
        try:
            with open(srt_path, 'r', encoding='utf-8-sig') as f:
                content = f.read()

            # SRT 블록 파싱
            blocks = re.split(r'\n\s*\n', content.strip())

            for block in blocks:
                lines = block.strip().split('\n')
                if len(lines) >= 3:
                    try:
                        scene_id = int(lines[0])
                        script = '\n'.join(lines[2:]).strip()
                        result[scene_id] = {
                            'script_ko': script,
                            'script_en': ''
                        }
                    except ValueError:
                        continue

            if result:
                print(f"[Original Scripts] ✅ SRT에서 파싱: {len(result)}개 씬")
                return result
        except Exception as e:
            print(f"[Original Scripts] ⚠️ SRT 파싱 실패: {e}")

    return result


def backup_original_scenes_before_analysis(video_path: str) -> bool:
    """
    Claude Code 분석 시작 전 원본 scenes.json 백업 (v13.14)

    script_ko 등 원본 데이터 보존용
    """
    import shutil

    analysis_dir = Path(video_path) / "analysis"
    scenes_path = analysis_dir / "scenes.json"
    backup_path = analysis_dir / "scenes_original.json"

    if scenes_path.exists():
        # 기존 백업이 없을 때만 백업 (처음 분석 시)
        if not backup_path.exists():
            shutil.copy2(scenes_path, backup_path)
            print(f"[Backup] ✅ 원본 scenes.json 백업됨: {backup_path}")
        else:
            print(f"[Backup] ℹ️ 기존 백업 존재, 유지: {backup_path}")

        return True

    return False


def sync_claude_code_results_with_bundle_merge(
    video_path: str,
    all_scenes: list = None
) -> dict:
    """
    Claude Code 분석 결과 연동 + Bundle 병합 (v13.14)

    UI에서 "분석 결과 연동" 버튼 클릭 시 호출됩니다.

    ⭐ v13.14: script_ko 보존 검증 추가

    Args:
        video_path: 비디오/프로젝트 경로
        all_scenes: 전체 씬 리스트 (선택)

    Returns:
        {
            "success": bool,
            "merged_count": int,
            "total_scenes": int,
            "scenes_with_script": int,
            "scenes": 병합된 씬 리스트,
            "sync_data": session_state 동기화용 데이터
        }
    """
    print(f"\n[Claude Code Sync] ========== 결과 연동 시작 (v13.14) ==========")

    # 1. Bundle 병합 적용 (script_ko 보존됨)
    merge_result = apply_bundle_merge_after_claude_code(video_path, all_scenes)

    if not merge_result.get("success"):
        return {
            "success": False,
            "error": merge_result.get("error", "Bundle 병합 실패"),
            "merged_count": 0
        }

    merged_scenes = merge_result.get("scenes", [])
    scenes_with_script = merge_result.get("scenes_with_script", 0)

    # 2. Session State 동기화 데이터 생성
    scenes_json_path = str(Path(video_path) / "analysis" / "scenes.json")
    sync_data = sync_scenes_to_session_state(merged_scenes, scenes_json_path)

    # 추가 플래그
    sync_data['claude_code_synced'] = True
    sync_data['bundle_merge_applied'] = True
    sync_data['scenes_need_refresh'] = True

    print(f"[Claude Code Sync] ✅ 연동 완료")
    print(f"[Claude Code Sync]   - 전체 씬: {len(merged_scenes)}개")
    print(f"[Claude Code Sync]   - 병합된 씬: {merge_result.get('merged_count', 0)}개")
    print(f"[Claude Code Sync]   - script_ko 있는 씬: {scenes_with_script}개")
    print(f"[Claude Code Sync] ==========================================\n")

    return {
        "success": True,
        "merged_count": merge_result.get("merged_count", 0),
        "total_scenes": len(merged_scenes),
        "scenes_with_script": scenes_with_script,
        "scenes": merged_scenes,
        "sync_data": sync_data
    }
