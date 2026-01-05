# -*- coding: utf-8 -*-
"""
Claude Code CLI 래퍼 (v9.0)

변경사항:
- ⭐ Max Plan 전용 (API 크레딧 사용 안 함)
- ⭐ Rate limit 감지 추가
- ⭐ 배치 간 딜레이 추가
- ⭐ 재시도 로직 추가
"""

import os
import subprocess
import shutil
import json
import re
import time
import tempfile
from pathlib import Path
from typing import Optional
from dataclasses import dataclass

# ============================================================
# ⭐ Claude CLI 비활성화 플래그
# Max Plan 인증 문제로 인해 Claude CLI 사용 안 함
# Gemini가 기본 AI로 사용됨
# True로 설정하면 Claude CLI 시도하지 않고 즉시 Gemini 폴백
# ============================================================
CLAUDE_CLI_DISABLED = True


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
        """stdin으로 프롬프트 전달"""

        print(f"[ClaudeCodeRunner]   방식: stdin")

        cmd = [
            self.claude_path,
            "--dangerously-skip-permissions",
            "--output-format", "text"
        ]

        if model:
            cmd.extend(["--model", model])

        result = subprocess.run(
            cmd,
            input=prompt,
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
        """임시 파일로 프롬프트 전달 (대안)"""

        print(f"[ClaudeCodeRunner]   방식: 임시 파일")

        with tempfile.NamedTemporaryFile(
            mode='w',
            suffix='.txt',
            delete=False,
            encoding='utf-8'
        ) as f:
            f.write(prompt)
            prompt_file = f.name

        try:
            cmd = [
                self.claude_path,
                "--dangerously-skip-permissions",
                "--output-format", "text"
            ]

            if model:
                cmd.extend(["--model", model])

            with open(prompt_file, 'r', encoding='utf-8') as f:
                prompt_content = f.read()

            result = subprocess.run(
                cmd,
                input=prompt_content,
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
