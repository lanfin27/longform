# -*- coding: utf-8 -*-
"""
Claude Code Agent 래퍼 모듈

기능:
1. subprocess로 Claude Code CLI 호출
2. Agent용 입력 파일 생성
3. Agent 출력 파일 파싱
4. --dangerously-skip-permissions 모드 지원
"""

import os
import json
import subprocess
import tempfile
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class AgentResult:
    """Agent 실행 결과"""
    success: bool
    data: dict
    error: str = ""
    stdout: str = ""
    stderr: str = ""
    return_code: int = 0


class ClaudeCodeAgent:
    """Claude Code Agent 래퍼"""

    # Agent 프롬프트 파일 경로
    PROMPTS_DIR = "data/prompts/agent"

    # Claude CLI 명령어
    CLAUDE_CMD = "claude"

    def __init__(self, base_path: str = "."):
        self.base_path = Path(base_path)
        self.prompts_dir = self.base_path / self.PROMPTS_DIR

        # 프롬프트 디렉토리 확인
        if not self.prompts_dir.exists():
            self.prompts_dir.mkdir(parents=True, exist_ok=True)
            print(f"[ClaudeCodeAgent] 프롬프트 디렉토리 생성: {self.prompts_dir}")

    def _check_claude_available(self) -> bool:
        """Claude CLI 사용 가능 여부 확인"""
        try:
            result = subprocess.run(
                [self.CLAUDE_CMD, "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            return result.returncode == 0
        except Exception:
            return False

    def _create_workspace(self, task_name: str) -> Path:
        """작업용 임시 디렉토리 생성"""
        workspace = Path(tempfile.mkdtemp(prefix=f"claude_agent_{task_name}_"))
        (workspace / "input").mkdir()
        (workspace / "output").mkdir()
        return workspace

    def _cleanup_workspace(self, workspace: Path):
        """작업 디렉토리 정리"""
        try:
            shutil.rmtree(workspace)
        except Exception as e:
            print(f"[ClaudeCodeAgent] 정리 실패: {e}")

    def _run_agent(
        self,
        prompt_file: str,
        workspace: Path,
        timeout: int = 300
    ) -> AgentResult:
        """
        Claude Code Agent 실행

        Args:
            prompt_file: 프롬프트 MD 파일 경로
            workspace: 작업 디렉토리
            timeout: 타임아웃 (초)

        Returns:
            AgentResult
        """

        # Claude CLI 확인
        if not self._check_claude_available():
            return AgentResult(
                success=False,
                data={},
                error="Claude CLI를 찾을 수 없습니다. 'claude' 명령어가 PATH에 있는지 확인하세요."
            )

        # 프롬프트 파일 읽기
        prompt_path = self.prompts_dir / prompt_file
        if not prompt_path.exists():
            return AgentResult(
                success=False,
                data={},
                error=f"프롬프트 파일을 찾을 수 없습니다: {prompt_path}"
            )

        with open(prompt_path, 'r', encoding='utf-8') as f:
            prompt_content = f.read()

        # 작업 디렉토리 정보 추가
        full_prompt = f"""작업 디렉토리: {workspace}

입력 파일 위치: {workspace / 'input'}
출력 파일 위치: {workspace / 'output'}

---

{prompt_content}
"""

        print(f"[ClaudeCodeAgent] Agent 실행 중...")
        print(f"[ClaudeCodeAgent]   프롬프트: {prompt_file}")
        print(f"[ClaudeCodeAgent]   작업 디렉토리: {workspace}")

        try:
            # Claude CLI 실행
            result = subprocess.run(
                [
                    self.CLAUDE_CMD,
                    "--dangerously-skip-permissions",
                    "-p", full_prompt,
                    "--output-format", "text"
                ],
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(workspace)
            )

            print(f"[ClaudeCodeAgent]   반환 코드: {result.returncode}")

            if result.returncode != 0:
                return AgentResult(
                    success=False,
                    data={},
                    error=result.stderr or "Agent 실행 실패",
                    stdout=result.stdout,
                    stderr=result.stderr,
                    return_code=result.returncode
                )

            return AgentResult(
                success=True,
                data={},
                stdout=result.stdout,
                stderr=result.stderr,
                return_code=result.returncode
            )

        except subprocess.TimeoutExpired:
            return AgentResult(
                success=False,
                data={},
                error=f"Agent 실행 타임아웃 ({timeout}초)"
            )
        except Exception as e:
            return AgentResult(
                success=False,
                data={},
                error=str(e)
            )

    def recommend_topics(
        self,
        channel_identity: dict,
        trending_videos: List[dict],
        custom_instructions: str = ""
    ) -> AgentResult:
        """
        주제 추천 Agent 실행

        Args:
            channel_identity: 채널 정체성 정보
            trending_videos: 급등 영상 목록
            custom_instructions: 추가 지시사항

        Returns:
            AgentResult
        """

        print(f"\n[ClaudeCodeAgent] 주제 추천 Agent 시작")

        # 작업 디렉토리 생성
        workspace = self._create_workspace("topic_recommendation")

        try:
            # 입력 파일 생성
            input_dir = workspace / "input"

            with open(input_dir / "channel_identity.json", 'w', encoding='utf-8') as f:
                json.dump(channel_identity, f, ensure_ascii=False, indent=2)

            with open(input_dir / "trending_videos.json", 'w', encoding='utf-8') as f:
                json.dump(trending_videos, f, ensure_ascii=False, indent=2)

            if custom_instructions:
                with open(input_dir / "custom_instructions.txt", 'w', encoding='utf-8') as f:
                    f.write(custom_instructions)

            # Agent 실행
            result = self._run_agent("topic_recommendation.md", workspace, timeout=180)

            if not result.success:
                return result

            # 출력 파일 읽기
            output_file = workspace / "output" / "recommendations.json"
            if output_file.exists():
                with open(output_file, 'r', encoding='utf-8') as f:
                    result.data = json.load(f)
                print(f"[ClaudeCodeAgent] 주제 추천 완료: {len(result.data.get('recommendations', []))}개")
            else:
                # stdout에서 JSON 추출 시도
                import re
                json_match = re.search(r'\{[\s\S]*\}', result.stdout)
                if json_match:
                    try:
                        result.data = json.loads(json_match.group())
                    except json.JSONDecodeError:
                        result.success = False
                        result.error = "출력 파일을 찾을 수 없고 JSON 파싱 실패"
                else:
                    result.success = False
                    result.error = "출력 파일을 찾을 수 없습니다"

            return result

        finally:
            self._cleanup_workspace(workspace)

    def split_scenes(
        self,
        sentences: List[dict],
        config: dict
    ) -> AgentResult:
        """
        씬 분할 Agent 실행

        Args:
            sentences: Whisper 추출 문장 리스트
            config: 분할 설정

        Returns:
            AgentResult
        """

        print(f"\n[ClaudeCodeAgent] 씬 분할 Agent 시작")
        print(f"[ClaudeCodeAgent]   문장: {len(sentences)}개")
        print(f"[ClaudeCodeAgent]   스타일: {config.get('style', '기본')}")

        workspace = self._create_workspace("scene_split")

        try:
            input_dir = workspace / "input"

            with open(input_dir / "sentences.json", 'w', encoding='utf-8') as f:
                json.dump(sentences, f, ensure_ascii=False, indent=2)

            with open(input_dir / "config.json", 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)

            result = self._run_agent("scene_split.md", workspace, timeout=300)

            if not result.success:
                return result

            output_file = workspace / "output" / "scenes.json"
            if output_file.exists():
                with open(output_file, 'r', encoding='utf-8') as f:
                    result.data = json.load(f)
                print(f"[ClaudeCodeAgent] 씬 분할 완료: {result.data.get('total_scenes', 0)}개")
            else:
                # stdout에서 JSON 추출 시도
                import re
                json_match = re.search(r'\{[\s\S]*\}', result.stdout)
                if json_match:
                    try:
                        result.data = json.loads(json_match.group())
                    except json.JSONDecodeError:
                        result.success = False
                        result.error = "출력 파일을 찾을 수 없고 JSON 파싱 실패"
                else:
                    result.success = False
                    result.error = "출력 파일을 찾을 수 없습니다"

            return result

        finally:
            self._cleanup_workspace(workspace)

    def correct_text(
        self,
        srt_scenes: List[dict],
        original_script: str
    ) -> AgentResult:
        """
        텍스트 교정 Agent 실행

        Args:
            srt_scenes: SRT 씬 리스트
            original_script: 원문 스크립트

        Returns:
            AgentResult
        """

        print(f"\n[ClaudeCodeAgent] 텍스트 교정 Agent 시작")
        print(f"[ClaudeCodeAgent]   씬: {len(srt_scenes)}개")

        workspace = self._create_workspace("text_correction")

        try:
            input_dir = workspace / "input"

            with open(input_dir / "srt_scenes.json", 'w', encoding='utf-8') as f:
                json.dump(srt_scenes, f, ensure_ascii=False, indent=2)

            with open(input_dir / "original_script.txt", 'w', encoding='utf-8') as f:
                f.write(original_script)

            result = self._run_agent("text_correction.md", workspace, timeout=300)

            if not result.success:
                return result

            output_file = workspace / "output" / "corrections.json"
            if output_file.exists():
                with open(output_file, 'r', encoding='utf-8') as f:
                    result.data = json.load(f)
                print(f"[ClaudeCodeAgent] 교정 완료: {result.data.get('total_corrections', 0)}개")
            else:
                # stdout에서 JSON 추출 시도
                import re
                json_match = re.search(r'\{[\s\S]*\}', result.stdout)
                if json_match:
                    try:
                        result.data = json.loads(json_match.group())
                    except json.JSONDecodeError:
                        result.success = False
                        result.error = "출력 파일을 찾을 수 없고 JSON 파싱 실패"
                else:
                    result.success = False
                    result.error = "출력 파일을 찾을 수 없습니다"

            return result

        finally:
            self._cleanup_workspace(workspace)

    def validate_final(
        self,
        srt_scenes: List[dict],
        original_script: str
    ) -> AgentResult:
        """
        최종 검증 Agent 실행

        Args:
            srt_scenes: 교정된 SRT 씬 리스트
            original_script: 원문 스크립트

        Returns:
            AgentResult
        """

        print(f"\n[ClaudeCodeAgent] 최종 검증 Agent 시작")

        workspace = self._create_workspace("final_validation")

        try:
            input_dir = workspace / "input"

            with open(input_dir / "srt_scenes.json", 'w', encoding='utf-8') as f:
                json.dump(srt_scenes, f, ensure_ascii=False, indent=2)

            with open(input_dir / "original_script.txt", 'w', encoding='utf-8') as f:
                f.write(original_script)

            result = self._run_agent("final_validation.md", workspace, timeout=300)

            if not result.success:
                return result

            output_file = workspace / "output" / "final_srt.json"
            if output_file.exists():
                with open(output_file, 'r', encoding='utf-8') as f:
                    result.data = json.load(f)
                print(f"[ClaudeCodeAgent] 최종 검증 완료: {result.data.get('total_final_corrections', 0)}개")
            else:
                # stdout에서 JSON 추출 시도
                import re
                json_match = re.search(r'\{[\s\S]*\}', result.stdout)
                if json_match:
                    try:
                        result.data = json.loads(json_match.group())
                    except json.JSONDecodeError:
                        result.success = False
                        result.error = "출력 파일을 찾을 수 없고 JSON 파싱 실패"
                else:
                    result.success = False
                    result.error = "출력 파일을 찾을 수 없습니다"

            return result

        finally:
            self._cleanup_workspace(workspace)


# 싱글톤
_agent = None


def get_claude_code_agent(base_path: str = ".") -> ClaudeCodeAgent:
    """ClaudeCodeAgent 싱글톤"""
    global _agent
    if _agent is None:
        _agent = ClaudeCodeAgent(base_path)
    return _agent


def is_claude_code_available() -> bool:
    """Claude Code CLI 사용 가능 여부 확인 (claude_code_runner 사용)"""
    try:
        from utils.claude_code_runner import is_claude_code_available as check_runner
        return check_runner()
    except Exception:
        return False
