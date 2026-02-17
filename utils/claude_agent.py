# -*- coding: utf-8 -*-
"""
Claude Agent 모듈 (v5.0 - Max Plan + Gemini 폴백)

변경사항 (v5.0):
- Claude CLI (Max Plan) 기본
- Gemini 자동 폴백
- Anthropic API 직접 호출 완전 제거

에이전트:
1. SceneSplitAgent: Whisper 세그먼트를 스타일에 맞게 병합
2. TextCorrectorAgent: 원문과 SRT 간 오타/차이점 수정
"""

import os
import json
import re
import time
from typing import List, Dict, Tuple, Optional, Any
from dataclasses import dataclass

# Claude Code Runner (subprocess 방식)
try:
    from utils.claude_code_runner import get_claude_code_runner, is_claude_code_available
    CLAUDE_CODE_AVAILABLE = is_claude_code_available()
except ImportError:
    CLAUDE_CODE_AVAILABLE = False
    print("[ClaudeAgent] claude_code_runner 모듈을 찾을 수 없습니다")

# Gemini (폴백용)
GEMINI_AVAILABLE = False
_gemini_client = None
try:
    import google.generativeai as genai
    api_key = os.getenv("GOOGLE_API_KEY")
    if api_key:
        genai.configure(api_key=api_key)
        _gemini_client = genai.GenerativeModel("gemini-2.5-flash")
        GEMINI_AVAILABLE = True
        print("[ClaudeAgent] [OK] Gemini 폴백 준비 완료")
except Exception as e:
    print(f"[ClaudeAgent] [WARN] Gemini 초기화 실패: {e}")


@dataclass
class AgentResult:
    """에이전트 실행 결과"""
    success: bool
    data: Any
    error: str = ""
    tokens_used: int = 0
    provider_used: str = ""  # 사용된 제공자


class ClaudeAgentBase:
    """Claude 에이전트 베이스 클래스 (v5.1 - Gemini 기본 모드)"""

    def __init__(self):
        self.runner = None
        self.gemini_client = _gemini_client
        self._use_gemini = False  # 폴백 모드

        # Claude CLI 초기화 (비활성화 상태면 스킵)
        if CLAUDE_CODE_AVAILABLE:
            self.runner = get_claude_code_runner()
            if self.runner.available:
                print(f"[ClaudeAgent] [OK] Claude CLI 준비 완료 (Max Plan)")
                print(f"[ClaudeAgent]   경로: {self.runner.claude_path}")
            else:
                print(f"[ClaudeAgent] [WARN] Claude CLI 사용 불가 -> Gemini 사용")
                self._use_gemini = True
        else:
            # Claude CLI 비활성화 상태 - 즉시 Gemini 사용
            print(f"[ClaudeAgent] [DISABLED] Claude CLI 비활성화됨 -> Gemini 기본 사용")
            self._use_gemini = True

        # Gemini 초기화 확인
        if GEMINI_AVAILABLE:
            if self._use_gemini:
                print(f"[ClaudeAgent] [OK] Gemini 준비 완료 (기본 AI)")
            else:
                print(f"[ClaudeAgent] [OK] Gemini 폴백 준비 완료")

        if not (self.runner and self.runner.available) and not GEMINI_AVAILABLE:
            raise ValueError("사용 가능한 AI 제공자가 없습니다")

    def _call_cli(self, prompt: str, timeout: int = 180) -> Tuple[str, int]:
        """Claude CLI 또는 Gemini 호출 (자동 폴백)"""

        # Claude CLI 시도
        if not self._use_gemini and self.runner and self.runner.available:
            print(f"[ClaudeAgent] [CLAUDE] Claude CLI 실행 중 (Max Plan)...")

            result = self.runner.run(prompt, timeout=timeout)

            if result.success:
                estimated_tokens = len(prompt.split()) + len(result.output.split())
                return result.output, estimated_tokens

            # 폴백 필요?
            if result.should_fallback and GEMINI_AVAILABLE:
                print(f"[ClaudeAgent] [WARN] Claude CLI 실패: {result.error}")
                print(f"[ClaudeAgent] [FALLBACK] Gemini 폴백으로 전환")
                self._use_gemini = True
            else:
                raise Exception(f"Claude CLI 실행 실패: {result.error}")

        # Gemini 폴백
        if self._use_gemini or not (self.runner and self.runner.available):
            if not GEMINI_AVAILABLE or not self.gemini_client:
                raise Exception("사용 가능한 AI 제공자가 없습니다")

            print(f"[ClaudeAgent] [GEMINI] Gemini 실행 중 (폴백)...")

            try:
                response = self.gemini_client.generate_content(prompt)
                estimated_tokens = len(prompt.split()) + len(response.text.split())
                return response.text, estimated_tokens
            except Exception as e:
                raise Exception(f"Gemini 실행 실패: {e}")

        raise Exception("AI 호출 실패")

    def _parse_json_safely(self, response_text: str) -> dict:
        """안전한 JSON 파싱 (불완전한 JSON 복구)"""

        # 1. 정상 JSON 시도
        try:
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            if json_match:
                return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass

        # 2. 불완전한 JSON 복구 시도
        try:
            text = response_text

            # ```json 제거
            text = re.sub(r'```json\s*', '', text)
            text = re.sub(r'```\s*', '', text)

            # { 로 시작하는 부분 찾기
            start_idx = text.find('{')
            if start_idx == -1:
                raise ValueError("JSON 시작점을 찾을 수 없음")

            text = text[start_idx:]

            # 마지막 완전한 객체 찾기
            last_complete = text.rfind('},')
            if last_complete > 0:
                text = text[:last_complete + 1]
            else:
                last_complete = text.rfind('}')
                if last_complete > 0:
                    text = text[:last_complete + 1]

            # 열린 괄호 개수 세기
            open_brackets = text.count('[') - text.count(']')
            open_braces = text.count('{') - text.count('}')

            # 괄호 닫기
            text += ']' * max(0, open_brackets)
            text += '}' * max(0, open_braces)

            return json.loads(text)

        except Exception as e:
            print(f"[ClaudeAgent] JSON 복구 실패: {e}")

            # 3. 최소 구조 반환
            return {"scenes": [], "error": "JSON 파싱 실패"}


class SceneSplitAgent(ClaudeAgentBase):
    """
    씬 분할 에이전트 (v5.0 - Max Plan + Gemini 폴백)

    역할: Whisper로 추출된 문장들을 영상 맥락에 맞게 씬 단위로 병합
    """

    MAX_SENTENCES_PER_BATCH = 80

    SYSTEM_PROMPT = """당신은 영상 자막 편집 전문가입니다.
Whisper로 추출된 문장들을 자연스러운 씬 단위로 묶어주세요.

규칙:
1. 의미 단위로 끊기 (문장 중간에서 끊지 않기)
2. sentence_ids는 반드시 연속된 번호
3. 모든 문장이 정확히 하나의 씬에 포함되어야 함

출력: JSON만 출력"""

    STYLE_CONFIG = {
        "잘게": {
            "description": "짧은 호흡, 숏폼 스타일",
            "sentences_per_scene": "1-2개",
            "max_chars": 50,
            "max_duration": 3
        },
        "기본": {
            "description": "일반 유튜브 스타일",
            "sentences_per_scene": "2-4개",
            "max_chars": 80,
            "max_duration": 5
        },
        "크게": {
            "description": "다큐멘터리 스타일",
            "sentences_per_scene": "4-8개",
            "max_chars": 150,
            "max_duration": 10
        }
    }

    def split_scenes(
        self,
        sentences: List[Dict],
        split_style: str = "기본"
    ) -> AgentResult:
        """문장들을 씬으로 분할 (배치 처리 지원)"""

        if not sentences:
            return AgentResult(success=False, data=[], error="문장이 없습니다")

        if len(sentences) > self.MAX_SENTENCES_PER_BATCH:
            num_batches = (len(sentences) - 1) // self.MAX_SENTENCES_PER_BATCH + 1
            print(f"[SceneSplitAgent] 배치 처리: {len(sentences)}개 문장 → {num_batches}개 배치")
            return self._split_scenes_batched(sentences, split_style)

        return self._split_scenes_single(sentences, split_style)

    def _split_scenes_batched(
        self,
        sentences: List[Dict],
        split_style: str
    ) -> AgentResult:
        """배치 단위로 씬 분할"""

        all_scenes = []
        scene_id_offset = 0
        total_tokens = 0

        for i in range(0, len(sentences), self.MAX_SENTENCES_PER_BATCH):
            batch = sentences[i:i + self.MAX_SENTENCES_PER_BATCH]
            batch_num = i // self.MAX_SENTENCES_PER_BATCH + 1
            total_batches = (len(sentences) - 1) // self.MAX_SENTENCES_PER_BATCH + 1

            print(f"[SceneSplitAgent] 배치 {batch_num}/{total_batches} 처리 중 ({len(batch)}개 문장)...")

            # ID 재할당 (0부터 시작)
            batch_with_local_ids = []
            id_mapping = {}

            for j, sent in enumerate(batch):
                original_id = sent.get("id", i + j)
                id_mapping[j] = original_id
                batch_with_local_ids.append({
                    "id": j,
                    "text": sent.get("text", ""),
                    "start": sent.get("start", 0),
                    "end": sent.get("end", 0)
                })

            result = self._split_scenes_single(batch_with_local_ids, split_style)

            if result.success:
                for scene in result.data:
                    scene["scene_id"] += scene_id_offset
                    scene["sentence_ids"] = [id_mapping[lid] for lid in scene["sentence_ids"] if lid in id_mapping]
                    all_scenes.append(scene)

                scene_id_offset = len(all_scenes)
                total_tokens += result.tokens_used
            else:
                print(f"[SceneSplitAgent] 배치 {batch_num} 실패: {result.error}")

            if i + self.MAX_SENTENCES_PER_BATCH < len(sentences):
                time.sleep(2)

        provider = "gemini" if self._use_gemini else "claude_code_agent"
        print(f"[SceneSplitAgent] [OK] 전체 완료: {len(all_scenes)}개 씬 (토큰: {total_tokens}, {provider})")

        return AgentResult(
            success=len(all_scenes) > 0,
            data=all_scenes,
            tokens_used=total_tokens,
            provider_used=provider
        )

    def _split_scenes_single(
        self,
        sentences: List[Dict],
        split_style: str
    ) -> AgentResult:
        """단일 배치 씬 분할"""

        style_config = self.STYLE_CONFIG.get(split_style, self.STYLE_CONFIG["기본"])
        user_prompt = self._build_prompt(sentences, split_style, style_config)

        try:
            prompt = self.SYSTEM_PROMPT + "\n\n" + user_prompt
            response_text, tokens = self._call_cli(prompt, timeout=180)

            if response_text:
                print(f"[SceneSplitAgent] 출력 길이: {len(response_text)}자")
                preview = response_text[:300].replace('\n', ' ')
                print(f"[SceneSplitAgent] 출력 처음 300자: {preview}")

            # JSON 파싱
            if self.runner and not self._use_gemini:
                data = self.runner.extract_json(response_text)
            else:
                data = self._parse_json_safely(response_text)

            if not data:
                print(f"[SceneSplitAgent] JSON 파싱 실패 - 전체 출력:")
                print(response_text[:1000] if response_text else "(empty)")
                return AgentResult(success=False, data=[], error="JSON 파싱 실패")

            if "error" in data and data.get("error"):
                return AgentResult(success=False, data=[], error=data["error"])

            scenes = self._process_scenes(data, sentences)

            provider = "gemini" if self._use_gemini else "claude_code_agent"
            print(f"[SceneSplitAgent] [OK] 완료: {len(scenes)}개 씬 (토큰: {tokens}, {provider})")

            return AgentResult(success=True, data=scenes, tokens_used=tokens, provider_used=provider)

        except Exception as e:
            print(f"[SceneSplitAgent] 오류: {e}")
            return AgentResult(success=False, data=[], error=str(e))

    def _process_scenes(self, data: dict, sentences: List[Dict]) -> List[Dict]:
        """파싱된 데이터에서 씬 생성"""

        scenes_data = data.get("scenes", [])
        result = []

        for sd in scenes_data:
            sentence_ids = sd.get("sentence_ids", [])
            if not sentence_ids:
                continue

            valid_ids = [i for i in sentence_ids if i < len(sentences)]
            if not valid_ids:
                continue

            selected = [sentences[i] for i in valid_ids]

            result.append({
                "scene_id": sd.get("scene_id", len(result) + 1),
                "sentence_ids": valid_ids,
                "text": " ".join(s.get("text", "") for s in selected),
                "start_time": selected[0].get("start", 0),
                "end_time": selected[-1].get("end", 0),
                "reasoning": sd.get("reasoning", "")
            })

        return result

    def _build_prompt(
        self,
        sentences: List[Dict],
        split_style: str,
        style_config: Dict
    ) -> str:
        """프롬프트 생성"""

        sentence_lines = [f"[{s.get('id', i)}] {s.get('start', 0):.1f}s: {s.get('text', '')}" for i, s in enumerate(sentences)]

        return f"""## 분할 스타일: {split_style}
- 씬당: {style_config['sentences_per_scene']}
- 최대: {style_config['max_chars']}자, {style_config['max_duration']}초

## 문장 ({len(sentences)}개)
{chr(10).join(sentence_lines)}

## 출력 (JSON만)
{{"scenes": [{{"scene_id": 1, "sentence_ids": [0, 1]}}, ...]}}

## 규칙
1. 모든 문장 ID (0~{len(sentences)-1}) 포함
2. sentence_ids는 연속 번호만"""


class TextCorrectorAgent(ClaudeAgentBase):
    """
    텍스트 교정 에이전트 (v5.0 - Max Plan + Gemini 폴백)

    역할: 원문 스크립트와 SRT 자막 간의 차이점을 찾아 수정
    """

    MAX_SCENES_PER_BATCH = 15

    SYSTEM_PROMPT = """당신은 자막 교정 전문가입니다.
원문과 비교하여 오타, 영어, 숫자를 교정하세요.
출력: JSON만"""

    def correct_text(
        self,
        srt_scenes: List[Dict],
        original_script: str
    ) -> AgentResult:
        """SRT 텍스트 교정 (배치 처리)"""

        if not srt_scenes or not original_script:
            return AgentResult(
                success=False,
                data={"corrections": [], "corrected_scenes": srt_scenes},
                error="입력 데이터가 부족합니다"
            )

        all_corrections = []
        corrected_scenes = list(srt_scenes)
        total_tokens = 0

        num_batches = (len(srt_scenes) - 1) // self.MAX_SCENES_PER_BATCH + 1
        print(f"[TextCorrectorAgent] 배치 처리: {len(srt_scenes)}개 씬 → {num_batches}개 배치")

        for i in range(0, len(srt_scenes), self.MAX_SCENES_PER_BATCH):
            batch = srt_scenes[i:i + self.MAX_SCENES_PER_BATCH]
            batch_num = i // self.MAX_SCENES_PER_BATCH + 1

            print(f"[TextCorrectorAgent] 배치 {batch_num}/{num_batches} 처리 중...")

            try:
                user_prompt = self._build_prompt(batch, original_script)
                prompt = self.SYSTEM_PROMPT + "\n\n" + user_prompt
                response_text, tokens = self._call_cli(prompt, timeout=120)

                data = self._parse_json_safely(response_text)

                corrections = data.get("corrections", [])
                corrected_texts = data.get("corrected_scenes", {})

                for corr in corrections:
                    all_corrections.append(corr)

                for scene_id_str, new_text in corrected_texts.items():
                    scene_id = int(scene_id_str) if scene_id_str.isdigit() else scene_id_str
                    for j, scene in enumerate(corrected_scenes):
                        if scene.get("scene_id") == scene_id:
                            corrected_scenes[j] = scene.copy()
                            corrected_scenes[j]["text"] = new_text
                            corrected_scenes[j]["original_text"] = scene.get("text", "")
                            break

                total_tokens += tokens

            except Exception as e:
                print(f"[TextCorrectorAgent] 배치 오류: {e}")

            if i + self.MAX_SCENES_PER_BATCH < len(srt_scenes):
                time.sleep(2)

        provider = "gemini" if self._use_gemini else "claude_code_agent"
        print(f"[TextCorrectorAgent] [OK] 완료: {len(all_corrections)}개 교정 (토큰: {total_tokens}, {provider})")

        return AgentResult(
            success=True,
            data={
                "corrections": all_corrections,
                "corrected_scenes": corrected_scenes
            },
            tokens_used=total_tokens,
            provider_used=provider
        )

    def _build_prompt(
        self,
        srt_scenes: List[Dict],
        original_script: str
    ) -> str:
        """프롬프트 생성"""

        srt_lines = [f"[{s.get('scene_id', i)}] {s.get('text', '')}" for i, s in enumerate(srt_scenes)]

        return f"""## 원문
{original_script[:2000]}

## SRT
{chr(10).join(srt_lines)}

## 출력 (JSON만)
{{"corrections": [{{"scene_id": 1, "original": "...", "corrected": "..."}}], "corrected_scenes": {{"1": "교정된 텍스트"}}}}"""


# =========================================================
# 팩토리 함수
# =========================================================

def get_scene_split_agent(api_key: str = None) -> SceneSplitAgent:
    """씬 분할 에이전트 생성 (api_key는 무시됨)"""
    return SceneSplitAgent()


def get_text_corrector_agent(api_key: str = None) -> TextCorrectorAgent:
    """텍스트 교정 에이전트 생성 (api_key는 무시됨)"""
    return TextCorrectorAgent()


def is_claude_agent_available() -> bool:
    """Claude Agent 사용 가능 여부"""
    return CLAUDE_CODE_AVAILABLE or GEMINI_AVAILABLE


def check_api_key() -> bool:
    """사용 가능한 AI 제공자 확인"""
    return CLAUDE_CODE_AVAILABLE or GEMINI_AVAILABLE


# 하위 호환성
is_anthropic_available = is_claude_agent_available


# =========================================================
# 통합 함수
# =========================================================

def process_with_claude_agents(
    sentences: List[Dict],
    original_script: str,
    split_style: str = "기본",
    api_key: str = None
) -> Tuple[List[Dict], List[Dict]]:
    """Claude 에이전트로 전체 처리"""

    # Step 1: 씬 분할
    split_agent = get_scene_split_agent()
    split_result = split_agent.split_scenes(sentences, split_style)

    if not split_result.success:
        raise Exception(f"씬 분할 실패: {split_result.error}")

    scenes = split_result.data

    # Step 2: 텍스트 교정
    if original_script:
        corrector_agent = get_text_corrector_agent()
        correct_result = corrector_agent.correct_text(scenes, original_script)

        if correct_result.success:
            return correct_result.data["corrected_scenes"], correct_result.data["corrections"]

    return scenes, []
