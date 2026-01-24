# -*- coding: utf-8 -*-
"""
Claude Code CLI 래퍼 (v11.0)

변경사항:
- ⭐ v11.0: 새 CMD 창에서 자동 실행 (pipe 방식)
- ⭐ v11.0: subprocess API 크레딧 문제 해결
- ⭐ v10.0: subprocess 방식 비활성화
- ⭐ Max Plan 전용 (API 크레딧 사용 안 함)
- ⭐ Rate limit 감지 추가
- ⭐ 배치 간 딜레이 추가
- ⭐ 재시도 로직 추가

✅ v11.0 자동 실행 방식:
1. 프롬프트 파일 생성 (.md)
2. 배치 파일 생성 (.bat)
3. 새 CMD 창에서 자동 실행:
   type prompt.md | claude --dangerously-skip-permissions
4. Max Plan 적용 - API 크레딧 소모 없음
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


def build_scene_analysis_prompt(
    scenes_json_path: str,
    project_path: str,
    scene_range: tuple = None,
    bundle_mode: bool = True,
    custom_instructions: str = ""
) -> str:
    """
    씬 분석용 프롬프트 생성

    Args:
        scenes_json_path: scenes.json 파일 경로
        project_path: 프로젝트 루트 경로
        scene_range: 분석할 씬 범위 (start, end) 또는 None (전체)
        bundle_mode: 묶음 모드 사용 여부
        custom_instructions: 추가 지시사항

    Returns:
        Claude Code에 전달할 프롬프트 문자열
    """

    # 에이전트 프롬프트 파일 로드
    agent_file = Path(project_path) / "agents" / "scene_analysis_agent.md"
    agent_prompt = ""
    if agent_file.exists():
        agent_prompt = agent_file.read_text(encoding='utf-8')

    # 프롬프트 구성
    prompt_parts = [
        "# 씬 분석 작업",
        "",
        "## 작업 파일",
        f"- scenes.json 경로: `{scenes_json_path}`",
        f"- 프로젝트 경로: `{project_path}`",
        "",
    ]

    # 씬 범위
    if scene_range:
        prompt_parts.append("## 분석 범위")
        prompt_parts.append(f"- 씬 {scene_range[0]}번부터 {scene_range[1]}번까지 분석")
        prompt_parts.append("")
    else:
        prompt_parts.append("## 분석 범위")
        prompt_parts.append("- 전체 씬 분석")
        prompt_parts.append("")

    # 묶음 모드
    if bundle_mode:
        prompt_parts.append("## 묶음 처리")
        prompt_parts.append("- 동일 bundle_id를 가진 씬들은 같은 프롬프트 공유")
        prompt_parts.append("- 대표 씬(첫 번째 씬)만 분석하고 나머지는 복사")
        prompt_parts.append("")

    # 커스텀 지시사항
    if custom_instructions:
        prompt_parts.append("## 추가 지시사항")
        prompt_parts.append(custom_instructions)
        prompt_parts.append("")

    # 에이전트 프롬프트 추가
    if agent_prompt:
        prompt_parts.append("## 분석 가이드라인")
        prompt_parts.append(agent_prompt)

    # 실행 지시
    prompt_parts.extend([
        "",
        "## 실행 지시",
        "",
        "1. 위 경로의 scenes.json 파일을 읽으세요",
        "2. 각 씬을 분석하여 필수 필드를 생성하세요:",
        "   - background_prompt_en: 배경 이미지 생성용 영문 프롬프트",
        "   - character_prompt_en: 캐릭터 이미지 생성용 영문 프롬프트",
        "   - characters: 등장 캐릭터 이름 목록",
        "   - visual_elements: 시각적 요소 설명",
        "   - scene_mood: 씬 분위기",
        "3. 분석 결과를 scenes.json에 직접 저장하세요 (기존 필드 유지, 새 필드 추가)",
        "4. 완료 후 분석 요약을 출력하세요",
        "",
        "**중요**: script 필드는 절대 수정하지 마세요!",
        "",
        "지금 바로 분석을 시작하세요."
    ])

    return "\n".join(prompt_parts)


def run_scene_analysis_agent(
    scenes_json_path: str,
    project_path: str = None,
    scene_range: tuple = None,
    bundle_mode: bool = True,
    custom_instructions: str = "",
    timeout: int = 600,
    progress_callback = None
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

        # 프롬프트 생성
        prompt = build_scene_analysis_prompt(
            scenes_json_path=scenes_json_path,
            project_path=project_path,
            scene_range=scene_range,
            bundle_mode=bundle_mode,
            custom_instructions=custom_instructions
        )

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

    # 프롬프트 생성
    prompt = build_scene_analysis_prompt(
        scenes_json_path=scenes_json_path,
        project_path=project_path,
        scene_range=scene_range,
        bundle_mode=bundle_mode,
        custom_instructions=custom_instructions
    )

    # 프롬프트 파일로 저장 (디버깅용)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    prompt_file = log_dir / f"prompt_{timestamp}.md"
    prompt_file.write_text(prompt, encoding='utf-8')

    print(f"\n{'='*70}")
    print(f"[ClaudeCode] 씬 분석 시작")
    print(f"[ClaudeCode] 프롬프트 파일: {prompt_file}")
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
    message: str = ""
    error: str = ""


def execute_claude_code_in_new_window(
    prompt_text: str,
    project_path: str,
    scenes_json_path: str = None
) -> AutoExecutionResult:
    """
    Claude Code를 새 CMD 창에서 자동 실행

    새 CMD 창에서 실행되므로:
    - 사용자의 Claude Code Max Plan이 적용됩니다
    - API 크레딧이 소모되지 않습니다
    - 실행 과정을 사용자가 볼 수 있습니다

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

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    # 1. 프롬프트 파일 생성
    prompt_file = logs_dir / f'prompt_auto_{timestamp}.md'
    prompt_file.write_text(prompt_text, encoding='utf-8')

    print(f"\n{'='*70}")
    print(f"[Claude Code 자동 실행] 프롬프트 파일 생성됨")
    print(f"[Claude Code 자동 실행] 경로: {prompt_file}")
    print(f"{'='*70}\n")

    # 2. 배치 파일 생성
    claude_path = ClaudeCodeRunner.HARDCODED_CLAUDE_PATH
    batch_file = logs_dir / f'run_auto_{timestamp}.bat'

    batch_content = f'''@echo off
chcp 65001 > nul
cd /d "{project_path}"

echo ==========================================
echo   Claude Code 자동 실행
echo ==========================================
echo.
echo [INFO] 프로젝트: {project_path}
echo [INFO] 프롬프트: {prompt_file}
echo [INFO] 시작 시간: %date% %time%
echo.
echo [실행 중] Claude Code...
echo.

type "{prompt_file}" | "{claude_path}" --dangerously-skip-permissions

echo.
echo ==========================================
echo   완료!
echo ==========================================
echo [INFO] 종료 시간: %date% %time%
echo.
echo Streamlit에서 "결과 확인" 버튼을 클릭하세요.
echo.
echo 이 창은 10초 후 자동으로 닫힙니다...
timeout /t 10 /nobreak > nul
'''

    batch_file.write_text(batch_content, encoding='utf-8')

    print(f"[Claude Code 자동 실행] 배치 파일 생성됨: {batch_file}")

    # 3. 새 CMD 창에서 실행
    try:
        subprocess.Popen(
            f'start "Claude Code 실행 중..." cmd /c "{batch_file}"',
            shell=True,
            cwd=str(project_path)
        )

        print(f"[Claude Code 자동 실행] 새 CMD 창에서 실행 시작!")

        return AutoExecutionResult(
            success=True,
            status='running',
            prompt_file=str(prompt_file),
            batch_file=str(batch_file),
            message='Claude Code가 새 창에서 실행되었습니다. 완료 후 "결과 확인" 버튼을 클릭하세요.'
        )

    except Exception as e:
        print(f"[Claude Code 자동 실행] 오류: {e}")
        return AutoExecutionResult(
            success=False,
            status='failed',
            prompt_file=str(prompt_file),
            batch_file=str(batch_file),
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
