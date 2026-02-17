# -*- coding: utf-8 -*-
"""
규칙 기반 씬 분할 모듈 (v6.0 - AI 완전 제거!)

⭐ 핵심 변경 (v6.0):
- Gemini/Claude AI 호출 완전 제거!
- 규칙 기반 단순 병합으로 전환
- 문제: AI가 일부 문장을 빈 텍스트/0.00 타임스탬프로 반환
- 해결: AI 없이 규칙 기반으로만 병합

핵심 원칙:
1. Whisper 문장과 타임스탬프는 절대 신뢰 (삭제/변경 금지!)
2. AI를 사용하지 않고 규칙 기반으로 병합
3. 빈 텍스트/0.00 타임스탬프 발생 절대 금지

이전 변경:
- v5.7: 빈 텍스트 씬 복구 기능
- v5.0~5.6: 스타일별 병합, 글자수 제한
"""

import json
import os
import re
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict

# 프로젝트 루트 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import GOOGLE_API_KEY, GEMINI_API_KEY

# ⭐ v6.0: AI 관련 코드 제거됨!
# Claude Code Runner, Gemini, Anthropic 모두 사용하지 않음
CLAUDE_CODE_AVAILABLE = False
GEMINI_FALLBACK_AVAILABLE = False
ANTHROPIC_AVAILABLE = False
_gemini_fallback_client = None

print("[AISceneMerger] v6.0 - 규칙 기반 병합 (AI 없음!)")


# ============================================================
# v5.0 스타일별 설정
# ============================================================

STYLE_CONFIG = {
    "잘게": {
        "name": "잘게",
        "description": "짧은 호흡 (1-2 문장, 50자 이하)",
        "min_sentences": 1,
        "max_sentences": 2,
        "max_chars": 50,   # ✅ 최대 50자 (캡컷 1-2줄)
        "target_scenes_ratio": 0.8,  # 문장 수의 80%
    },
    "기본": {
        "name": "기본",
        "description": "자연스러운 단위 (2-4 문장, 80자 이하)",
        "min_sentences": 2,
        "max_sentences": 4,
        "max_chars": 80,   # ✅ 최대 80자 (캡컷 2-3줄)
        "target_scenes_ratio": 0.4,  # 문장 수의 40%
    },
    "크게": {
        "name": "크게",
        "description": "큰 주제 단위 (4-8 문장, 150자 이하)",
        "min_sentences": 4,
        "max_sentences": 8,
        "max_chars": 150,  # ✅ 최대 150자 (캡컷 4줄)
        "target_scenes_ratio": 0.2,  # 문장 수의 20%
    }
}


# v5.1 병합 프롬프트 템플릿
MERGE_PROMPT_TEMPLATE = """당신은 영상 자막 편집 전문가입니다.

## 작업
아래 {sentence_count}개의 문장을 영상 씬(자막) 단위로 묶어주세요.

## 분할 스타일: {style_name}
- 한 씬에 **{min_sentences}~{max_sentences}개 문장**만 묶기
- ⚠️ 한 씬의 총 글자 수가 **{max_chars}자를 절대 초과하면 안 됨**
- 목표 씬 개수: 약 **{target_scenes}개**

## 문장 목록
{sentences}

## 응답 형식 (반드시 JSON만 출력)
```json
{{
  "scenes": [
    {{"scene_id": 1, "sentence_ids": [0, 1]}},
    {{"scene_id": 2, "sentence_ids": [2]}}
  ]
}}
```

## 매우 중요한 규칙!
1. 모든 문장 ID(0~{max_id})가 **반드시** 하나의 씬에 포함되어야 함
2. sentence_ids는 **연속된 번호**만 (예: [0,1,2] O, [0,2,4] X)
3. 한 씬에 **{min_sentences}~{max_sentences}개 문장**만!
4. ⚠️ 한 씬의 총 글자 수가 **{max_chars}자 초과 금지!**
5. 순서대로 묶기 (섞지 않기)
"""


# v4 호환성을 위한 MERGE_PROMPTS (레거시)
MERGE_PROMPTS = {
    "기본": {
        "name": "기본",
        "description": "자연스러운 문맥 단위 (2~4 세그먼트)",
        "target_segments": "2-4",
        "prompt_template": MERGE_PROMPT_TEMPLATE
    },
    "잘게": {
        "name": "잘게",
        "description": "짧은 호흡 단위 (1~2 세그먼트)",
        "target_segments": "1-2",
        "prompt_template": MERGE_PROMPT_TEMPLATE
    },
    "크게": {
        "name": "크게",
        "description": "큰 주제 단위 (4~8 세그먼트)",
        "target_segments": "4-8",
        "prompt_template": MERGE_PROMPT_TEMPLATE
    }
}


# ============================================================
# SceneGroup - 씬 그룹 (병합 결과)
# ============================================================

@dataclass
class SceneGroup:
    """씬 그룹 (병합 결과)"""
    scene_id: int
    sentence_ids: List[int]
    text: str
    start_time: float
    end_time: float
    mood: str = ""
    scene_break_reason: str = ""

    @property
    def duration(self) -> float:
        return self.end_time - self.start_time

    @property
    def timecode(self) -> str:
        mins = int(self.start_time // 60)
        secs = int(self.start_time % 60)
        return f"{mins:02d}:{secs:02d}"

    # v4 호환성
    @property
    def segment_ids(self) -> List[int]:
        return self.sentence_ids


# ============================================================
# AISceneMerger - 규칙 기반 씬 병합기 (v6.0 - AI 완전 제거!)
# ============================================================

class AISceneMerger:
    """
    규칙 기반 씬 병합기 (v6.0 - AI 완전 제거!)

    변경 이력:
    - v6.0: Gemini/Claude AI 호출 완전 제거!
    - 문제: AI가 일부 문장을 빈 텍스트/0.00 타임스탬프로 반환
    - 해결: 규칙 기반으로 단순 병합 (AI 없음!)

    ⭐ 핵심 원칙:
    1. Whisper 문장과 타임스탬프는 절대 신뢰 (삭제/변경 금지!)
    2. AI를 사용하지 않고 규칙 기반으로 병합
    3. 빈 텍스트/0.00 타임스탬프 발생 금지
    """

    def __init__(
        self,
        provider: str = "google",
        model: str = "gemini-2.5-flash",
        api_key: str = None
    ):
        # ⭐ v6.0: AI 클라이언트를 생성하지 않음!
        # 하위 호환성을 위해 파라미터는 받지만 무시함
        self.provider = provider
        self.model = model
        self.client = None
        self.runner = None
        self._initialized = True  # 항상 초기화 완료 상태

        print(f"[AISceneMerger] v6.0 초기화 (규칙 기반 병합 - AI 없음!)")
        print(f"[AISceneMerger] ⚠️ Gemini/Claude 호출하지 않음 (빈 텍스트 문제 해결)")

    def _initialize_client(self):
        """✅ Provider별 클라이언트 초기화"""
        if self._initialized:
            return

        try:
            if self.provider == "google":
                import google.generativeai as genai
                if not self.api_key:
                    raise ValueError("GOOGLE_API_KEY 환경 변수가 필요합니다")
                genai.configure(api_key=self.api_key)
                self.client = genai.GenerativeModel(self.model)
                self._initialized = True
                print(f"[AISceneMerger] [OK] Gemini 클라이언트 초기화 완료")

            elif self.provider == "anthropic":
                if not ANTHROPIC_AVAILABLE:
                    raise ImportError("anthropic 패키지가 필요합니다: pip install anthropic")
                if not self.api_key:
                    raise ValueError("ANTHROPIC_API_KEY 환경 변수가 필요합니다")
                self.client = anthropic.Anthropic(api_key=self.api_key)
                self._initialized = True
                print(f"[AISceneMerger] [OK] Claude API 클라이언트 초기화 완료")

            elif self.provider == "claude_code_agent":
                # Claude Code Agent (subprocess 방식)
                try:
                    from utils.claude_code_runner import get_claude_code_runner
                    self.runner = get_claude_code_runner()
                    if self.runner.available:
                        self._initialized = True
                        print(f"[AISceneMerger] [OK] Claude Code Agent 초기화 완료 (subprocess)")
                        print(f"[AISceneMerger]   경로: {self.runner.claude_path}")
                    else:
                        raise ValueError("Claude CLI를 찾을 수 없습니다")
                except ImportError:
                    raise ValueError("claude_code_runner 모듈을 찾을 수 없습니다")

            else:
                raise ValueError(f"지원하지 않는 provider: {self.provider}")

        except Exception as e:
            print(f"[AISceneMerger] [WARN] 클라이언트 초기화 실패: {e}")
            self.client = None
            raise

    def merge_sentences(
        self,
        whisper_result,  # WhisperResult
        split_style: str = "기본"
    ) -> List[SceneGroup]:
        """
        ⭐ v6.0: 규칙 기반으로 문장들을 씬으로 병합 (AI 없음!)

        Args:
            whisper_result: WhisperResult (문장 리스트)
            split_style: "잘게", "기본", "크게"

        Returns:
            List[SceneGroup]

        핵심 원칙:
        1. Whisper 문장과 타임스탬프 절대 신뢰!
        2. AI 호출 없이 규칙 기반으로만 병합
        3. 빈 텍스트 발생 금지
        """
        sentences = whisper_result.sentences
        config = STYLE_CONFIG.get(split_style, STYLE_CONFIG["기본"])

        max_chars = config.get("max_chars", 100)
        max_sentences = config.get("max_sentences", 4)

        print(f"[AISceneMerger] ⭐ v6.0 규칙 기반 병합 시작 (AI 없음!)")
        print(f"[AISceneMerger]   입력 문장: {len(sentences)}개")
        print(f"[AISceneMerger]   스타일: {split_style} (최대 {max_sentences}문장/씬, 최대 {max_chars}자)")

        # ⭐ v6.0: 항상 규칙 기반 병합 사용!
        groups = self._rule_based_merge(whisper_result, config)

        # 타임스탬프 및 빈 텍스트 검증
        groups = self._validate_timestamps_and_text(groups, whisper_result)

        # 글자 수 통계
        if groups:
            char_counts = [len(g.text) for g in groups]
            over_limit = [g for g in groups if len(g.text) > max_chars]
            print(f"[AISceneMerger] [OK] {len(groups)}개 씬 생성 완료")
            print(f"[AISceneMerger]   평균 글자 수: {sum(char_counts)/len(char_counts):.1f}자")
            print(f"[AISceneMerger]   최대 글자 수: {max(char_counts)}자")
            if over_limit:
                print(f"[AISceneMerger]   ⚠️ 글자 수 초과 씬: {len(over_limit)}개 (후처리로 분할)")
                groups = self._split_oversized_scenes(groups, whisper_result, max_chars)

            # 빈 텍스트 검증
            empty_count = sum(1 for g in groups if not g.text or not g.text.strip())
            if empty_count > 0:
                print(f"[AISceneMerger]   ❌ 빈 텍스트 씬: {empty_count}개 (심각한 오류!)")

            # 타임스탬프 검증
            zero_ts_count = sum(1 for g in groups if g.start_time == 0 and g.end_time < 1)
            if zero_ts_count > 0:
                print(f"[AISceneMerger]   ⚠️ 타임스탬프 0인 씬: {zero_ts_count}개")

        return groups

    def _rule_based_merge(self, whisper_result, config: dict) -> List[SceneGroup]:
        """
        ⭐ v6.0: 규칙 기반 병합 (AI 없음!)

        로직:
        1. 글자 수 기준으로 문장 병합
        2. max_chars 초과 시 새 씬 시작
        3. max_sentences 초과 시 새 씬 시작
        """
        sentences = whisper_result.sentences
        max_chars = config.get("max_chars", 100)
        max_sentences = config.get("max_sentences", 4)

        groups = []
        current_ids = []
        current_text = ""

        for sentence in sentences:
            sid = sentence.id
            text = sentence.text.strip() if sentence.text else ""

            # 빈 텍스트는 건너뛰지 않고 그대로 포함 (Whisper 신뢰!)
            # 텍스트가 비어있어도 타임스탬프를 위해 포함

            # 현재 씬에 추가했을 때 조건 체크
            test_text = (current_text + " " + text).strip() if current_text else text
            would_exceed_chars = len(test_text) > max_chars and current_ids
            would_exceed_sentences = len(current_ids) >= max_sentences

            if would_exceed_chars or would_exceed_sentences:
                # 현재까지 모은 것으로 씬 생성
                if current_ids:
                    merged_text, start, end = whisper_result.merge_sentences(current_ids)
                    groups.append(SceneGroup(
                        scene_id=len(groups) + 1,
                        sentence_ids=current_ids.copy(),
                        text=merged_text,
                        start_time=start,
                        end_time=end
                    ))
                # 새 씬 시작
                current_ids = [sid]
                current_text = text
            else:
                # 현재 씬에 추가
                current_ids.append(sid)
                current_text = test_text

        # 남은 문장 처리
        if current_ids:
            merged_text, start, end = whisper_result.merge_sentences(current_ids)
            groups.append(SceneGroup(
                scene_id=len(groups) + 1,
                sentence_ids=current_ids,
                text=merged_text,
                start_time=start,
                end_time=end
            ))

        print(f"[AISceneMerger] 규칙 기반 병합: {len(sentences)}개 문장 → {len(groups)}개 씬")
        return groups

    def _split_oversized_scenes(self, groups: List[SceneGroup], whisper_result, max_chars: int) -> List[SceneGroup]:
        """글자수 초과 씬 후처리 분할"""
        result = []

        for g in groups:
            if len(g.text) > max_chars and len(g.sentence_ids) > 1:
                # 분할 필요
                split_scenes = self._force_split_scene(g, whisper_result, max_chars)
                result.extend(split_scenes)
            else:
                result.append(g)

        # scene_id 재할당
        for i, scene in enumerate(result):
            scene.scene_id = i + 1

        return result

    def _build_prompt(self, sentences, config: dict, target_scenes: int) -> str:
        """⚠️ DEPRECATED (v6.0): AI 프롬프트 생성 - 더 이상 사용하지 않음"""

        # 문장 목록 텍스트 (글자 수 포함)
        sentence_lines = []
        for s in sentences:
            char_count = len(s.text) if hasattr(s, 'text') else 0
            sentence_lines.append(f"[{s.id}] ({char_count}자) {s.text}")

        return MERGE_PROMPT_TEMPLATE.format(
            sentence_count=len(sentences),
            style_name=config["name"],
            min_sentences=config["min_sentences"],
            max_sentences=config["max_sentences"],
            max_chars=config.get("max_chars", 100),  # ✅ max_chars 추가
            target_scenes=target_scenes,
            sentences="\n".join(sentence_lines),
            max_id=len(sentences) - 1
        )

    def _call_api(self, prompt: str) -> str:
        """⚠️ DEPRECATED (v6.0): AI API 호출 - 더 이상 사용하지 않음"""
        raise NotImplementedError("v6.0에서 AI 호출 제거됨. _rule_based_merge() 사용")

        if not hasattr(self, '_use_gemini_fallback'):
            self._use_gemini_fallback = False

        try:
            # Claude Code Agent (Max Plan) - 우선
            if self.provider == "claude_code_agent" or (self.runner and self.runner.available):
                if not self._use_gemini_fallback:
                    result = self._call_claude_cli(prompt)
                    return result

            # Gemini (폴백 또는 google provider)
            if self.provider == "google" or self._use_gemini_fallback:
                if self._use_gemini_fallback and _gemini_fallback_client:
                    print(f"[AISceneMerger] [GEMINI] Gemini 실행 중 (폴백)...")
                    response = _gemini_fallback_client.generate_content(
                        prompt,
                        generation_config={
                            "temperature": 0.3,
                            "max_output_tokens": 8192
                        }
                    )
                    return response.text
                elif self.client is not None:
                    response = self.client.generate_content(
                        prompt,
                        generation_config={
                            "temperature": 0.3,
                            "max_output_tokens": 8192
                        }
                    )
                    return response.text
                else:
                    raise ValueError("Gemini 클라이언트가 초기화되지 않았습니다")

            raise ValueError(f"지원하지 않는 provider: {self.provider}")

        except Exception as e:
            print(f"[AISceneMerger] API 오류: {e}")
            raise

    def _call_claude_cli(self, prompt: str) -> str:
        """⚠️ DEPRECATED (v6.0): Claude CLI 호출 - 더 이상 사용하지 않음"""
        raise NotImplementedError("v6.0에서 AI 호출 제거됨. _rule_based_merge() 사용")

        if not self.runner or not self.runner.available:
            if CLAUDE_CODE_AVAILABLE:
                self.runner = get_claude_code_runner()

        if not self.runner or not self.runner.available:
            raise ValueError("Claude CLI Runner가 초기화되지 않았습니다")

        print(f"[AISceneMerger] [CLAUDE] Claude CLI 실행 중 (Max Plan)...")

        result = self.runner.run(prompt, timeout=180)

        if result.success:
            return result.output

        # 폴백 필요?
        if result.should_fallback and GEMINI_FALLBACK_AVAILABLE:
            print(f"[AISceneMerger] [WARN] Claude CLI 실패: {result.error}")
            print(f"[AISceneMerger] [FALLBACK] Gemini 폴백으로 전환")
            self._use_gemini_fallback = True

            # Gemini로 재시도
            print(f"[AISceneMerger] [GEMINI] Gemini 실행 중 (폴백)...")
            response = _gemini_fallback_client.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.3,
                    "max_output_tokens": 8192
                }
            )
            return response.text

        raise Exception(f"Claude CLI 실행 실패: {result.error}")

    def _parse_response(self, response: str, whisper_result) -> List[SceneGroup]:
        """⚠️ DEPRECATED (v6.0): AI 응답 파싱 - 더 이상 사용하지 않음"""

        # claude_code_agent의 경우 강화된 JSON 파싱 사용
        if self.provider == "claude_code_agent" and self.runner:
            data = self.runner.extract_json(response)
            if not data:
                print(f"[AISceneMerger] JSON 파싱 실패 (claude_code_agent)")
                return []
        else:
            json_match = re.search(r'\{[\s\S]*\}', response)
            if not json_match:
                print(f"[AISceneMerger] JSON 파싱 실패")
                return []

            try:
                data = json.loads(json_match.group())
            except json.JSONDecodeError as e:
                print(f"[AISceneMerger] JSON 파싱 오류: {e}")
                return []

        try:
            pass  # dummy for indent

            # scenes 또는 scene_groups 키 지원
            scenes_data = data.get("scenes", data.get("scene_groups", []))

            groups = []
            for sd in scenes_data:
                sentence_ids = sd.get("sentence_ids", sd.get("segment_ids", []))
                if not sentence_ids:
                    continue

                text, start, end = whisper_result.merge_sentences(sentence_ids)

                groups.append(SceneGroup(
                    scene_id=sd.get("scene_id", len(groups) + 1),
                    sentence_ids=sentence_ids,
                    text=text,
                    start_time=start,
                    end_time=end,
                    mood=sd.get("mood", ""),
                    scene_break_reason=sd.get("scene_break_reason", "")
                ))

            return groups

        except json.JSONDecodeError as e:
            print(f"[AISceneMerger] JSON 파싱 오류: {e}")
            return []

    def _simple_merge(self, whisper_result, config: dict) -> List[SceneGroup]:
        """⚠️ DEPRECATED (v6.0): _rule_based_merge()로 대체됨"""
        sentences = whisper_result.sentences
        groups = []

        step = config["max_sentences"]
        for i in range(0, len(sentences), step):
            chunk = sentences[i:i+step]
            ids = [s.id for s in chunk]
            text = " ".join(s.text for s in chunk)

            groups.append(SceneGroup(
                scene_id=len(groups) + 1,
                sentence_ids=ids,
                text=text,
                start_time=chunk[0].start,
                end_time=chunk[-1].end
            ))

        return groups

    def _chunked_merge(self, whisper_result, config: dict, target_scenes: int) -> List[SceneGroup]:
        """⚠️ DEPRECATED (v6.0): AI 기반 청크 병합 - 더 이상 사용하지 않음"""
        sentences = whisper_result.sentences
        chunk_size = 40  # 한 번에 처리할 문장 수

        all_groups = []
        current_scene_id = 1

        for chunk_start in range(0, len(sentences), chunk_size):
            chunk_end = min(chunk_start + chunk_size, len(sentences))
            chunk_sentences = sentences[chunk_start:chunk_end]

            # 청크별 목표 씬 개수
            chunk_target = max(3, int(len(chunk_sentences) * config["target_scenes_ratio"]))

            # 청크용 임시 WhisperResult 생성
            class ChunkResult:
                def __init__(self, sents):
                    self.sentences = sents

                def merge_sentences(self, indices):
                    if not indices:
                        return "", 0.0, 0.0
                    selected = [self.sentences[i] for i in indices if i < len(self.sentences)]
                    if not selected:
                        return "", 0.0, 0.0
                    text = " ".join(s.text for s in selected)
                    return text, selected[0].start, selected[-1].end

            chunk_result = ChunkResult(chunk_sentences)

            # AI 호출 또는 간단 분할
            if len(chunk_sentences) <= 10:
                chunk_groups = self._simple_merge(chunk_result, config)
            else:
                prompt = self._build_prompt(chunk_sentences, config, chunk_target)
                try:
                    response = self._call_api(prompt)
                    chunk_groups = self._parse_response(response, chunk_result)
                    if not chunk_groups:
                        chunk_groups = self._simple_merge(chunk_result, config)
                except Exception:
                    chunk_groups = self._simple_merge(chunk_result, config)

            # 씬 ID 재할당
            for g in chunk_groups:
                g.scene_id = current_scene_id
                current_scene_id += 1
                all_groups.append(g)

        return all_groups

    def _validate_and_fix(self, groups: List[SceneGroup], whisper_result, config: dict) -> List[SceneGroup]:
        """⚠️ DEPRECATED (v6.0): _validate_timestamps_and_text()로 대체됨"""

        max_chars = config.get("max_chars", 250)

        all_ids = set(range(len(whisper_result.sentences)))
        covered_ids = set()

        for g in groups:
            covered_ids.update(g.sentence_ids)

        missing_ids = all_ids - covered_ids

        if missing_ids:
            print(f"[AISceneMerger] 누락된 문장 {len(missing_ids)}개 추가")

            # 누락된 문장들을 그룹으로 추가
            missing_sorted = sorted(missing_ids)
            step = config["max_sentences"]

            for i in range(0, len(missing_sorted), step):
                chunk_ids = missing_sorted[i:i+step]
                text, start, end = whisper_result.merge_sentences(chunk_ids)

                groups.append(SceneGroup(
                    scene_id=0,  # 나중에 재할당
                    sentence_ids=chunk_ids,
                    text=text,
                    start_time=start,
                    end_time=end
                ))

        # 시간순 정렬
        groups.sort(key=lambda g: g.start_time)

        # ⚠️ 글자수 초과 씬 강제 분할
        validated_groups = []
        split_count = 0

        for g in groups:
            if len(g.text) > max_chars and len(g.sentence_ids) > 1:
                # 글자수 초과 → 강제 분할
                split_scenes = self._force_split_scene(g, whisper_result, max_chars)
                validated_groups.extend(split_scenes)
                split_count += len(split_scenes) - 1
            else:
                validated_groups.append(g)

        if split_count > 0:
            print(f"[AISceneMerger] 📏 글자수 초과 씬 {split_count}개 추가 분할됨")

        # 시간순 재정렬 및 ID 재할당
        validated_groups.sort(key=lambda g: g.start_time)
        for i, g in enumerate(validated_groups):
            g.scene_id = i + 1

        # 씬 개수 검증
        expected_min = int(len(whisper_result.sentences) * config["target_scenes_ratio"] * 0.5)
        if len(validated_groups) < expected_min:
            print(f"[AISceneMerger] [WARN] 씬 개수 부족 ({len(validated_groups)}개), 재분할 수행")
            return self._force_split(whisper_result, config)

        # v5.6: 타임스탬프 및 빈 텍스트 검증
        validated_groups = self._validate_timestamps_and_text(validated_groups, whisper_result)

        return validated_groups

    def _validate_timestamps_and_text(self, groups: List[SceneGroup], whisper_result) -> List[SceneGroup]:
        """
        v5.7: 타임스탬프 및 빈 텍스트 검증 (빈 텍스트 복구!)

        1. 빈 텍스트 → 원본 Whisper 문장에서 복구 (삭제 X!)
        2. 타임스탬프 검증 (음수, 역전)
        3. 타임스탬프 정렬
        """

        original_count = len(groups)

        # ⭐ v5.7: 빈 텍스트 씬 복구 (삭제하지 않음!)
        recovered_count = 0
        still_empty = []

        for g in groups:
            if not g.text or not g.text.strip():
                # 원본 Whisper 문장에서 텍스트 복구 시도
                if g.sentence_ids:
                    try:
                        text, start, end = whisper_result.merge_sentences(g.sentence_ids)
                        if text and text.strip():
                            g.text = text
                            if start > 0:
                                g.start_time = start
                            if end > 0:
                                g.end_time = end
                            recovered_count += 1
                            print(f"[AISceneMerger] 🔄 빈 텍스트 복구: '{text[:30]}...' (ids={g.sentence_ids})")
                        else:
                            still_empty.append(g)
                    except Exception as e:
                        print(f"[AISceneMerger] ⚠️ 텍스트 복구 실패 (ids={g.sentence_ids}): {e}")
                        still_empty.append(g)
                else:
                    still_empty.append(g)

        if recovered_count > 0:
            print(f"[AISceneMerger] [OK] 빈 텍스트 {recovered_count}개 복구됨")

        # 복구 실패한 씬만 제거 (최소화)
        if still_empty:
            print(f"[AISceneMerger] ⚠️ 복구 불가 빈 씬 {len(still_empty)}개 (타임스탬프 출력):")
            for i, g in enumerate(still_empty[:5]):
                print(f"  [{i+1}] {g.start_time:.2f}~{g.end_time:.2f}, ids={g.sentence_ids}")
            groups = [g for g in groups if g.text and g.text.strip()]

        if not groups:
            print(f"[AISceneMerger] [WARN] 모든 씬이 빈 텍스트!")
            return groups

        # 2. 타임스탬프 검증 및 복구
        fixed_count = 0
        for g in groups:
            # 음수 수정
            if g.start_time < 0:
                g.start_time = 0
                fixed_count += 1
            if g.end_time < 0:
                g.end_time = g.start_time + 0.3
                fixed_count += 1

            # start > end 수정
            if g.start_time > g.end_time:
                g.start_time, g.end_time = g.end_time, g.start_time
                fixed_count += 1

            # 타임스탬프 0인 경우 원본에서 복구 시도
            if g.start_time == 0 and g.end_time == 0 and g.sentence_ids:
                try:
                    _, start, end = whisper_result.merge_sentences(g.sentence_ids)
                    if start > 0 or end > 0:
                        g.start_time = start
                        g.end_time = end
                        fixed_count += 1
                except Exception:
                    pass

        if fixed_count > 0:
            print(f"[AISceneMerger] [OK] 타임스탬프 {fixed_count}개 수정됨")

        # 3. 타임스탬프 정렬
        groups.sort(key=lambda g: g.start_time)

        # 4. scene_id 재할당
        for i, g in enumerate(groups):
            g.scene_id = i + 1

        return groups

    def _force_split_scene(self, scene: SceneGroup, whisper_result, max_chars: int) -> List[SceneGroup]:
        """
        글자수 초과 씬을 강제로 분할

        Args:
            scene: 분할할 씬
            whisper_result: WhisperResult
            max_chars: 최대 글자수

        Returns:
            분할된 씬 리스트
        """
        result = []
        current_ids = []
        current_text = ""

        for sid in scene.sentence_ids:
            sentence = whisper_result.sentences[sid]
            sentence_text = sentence.text

            # 현재 씬에 추가하면 초과하는지 체크
            test_text = (current_text + " " + sentence_text).strip() if current_text else sentence_text

            if len(test_text) > max_chars and current_ids:
                # 현재까지 모은 것으로 씬 생성
                text, start, end = whisper_result.merge_sentences(current_ids)
                result.append(SceneGroup(
                    scene_id=0,
                    sentence_ids=current_ids.copy(),
                    text=text,
                    start_time=start,
                    end_time=end,
                    mood=scene.mood,
                    scene_break_reason="글자수 초과 분할"
                ))
                # 새 씬 시작
                current_ids = [sid]
                current_text = sentence_text
            else:
                # 현재 씬에 추가
                current_ids.append(sid)
                current_text = test_text

        # 남은 문장 처리
        if current_ids:
            text, start, end = whisper_result.merge_sentences(current_ids)
            result.append(SceneGroup(
                scene_id=0,
                sentence_ids=current_ids,
                text=text,
                start_time=start,
                end_time=end,
                mood=scene.mood,
                scene_break_reason="글자수 초과 분할" if len(result) > 0 else scene.scene_break_reason
            ))

        return result if result else [scene]

    def _force_split(self, whisper_result, config: dict) -> List[SceneGroup]:
        """강제 분할 (AI 실패 시)"""
        sentences = whisper_result.sentences
        groups = []

        step = config["max_sentences"]

        for i in range(0, len(sentences), step):
            chunk = sentences[i:i+step]
            ids = [s.id for s in chunk]
            text = " ".join(s.text for s in chunk)

            groups.append(SceneGroup(
                scene_id=len(groups) + 1,
                sentence_ids=ids,
                text=text,
                start_time=chunk[0].start,
                end_time=chunk[-1].end
            ))

        return groups

    # v4 호환성: merge_segments 별칭
    def merge_segments(self, whisper_result, split_style: str = "기본") -> List[SceneGroup]:
        return self.merge_sentences(whisper_result, split_style)


# ============================================================
# v4 호환성을 위한 별칭
# ============================================================

AISegmentMerger = AISceneMerger


# ============================================================
# 싱글톤
# ============================================================

_merger_instance: Optional[AISceneMerger] = None


def get_scene_merger(
    provider: str = "google",
    model: str = "gemini-2.5-flash"
) -> AISceneMerger:
    """씬 병합기 싱글톤"""
    global _merger_instance

    if _merger_instance is None or _merger_instance.model != model:
        _merger_instance = AISceneMerger(provider=provider, model=model)

    return _merger_instance


# v4 호환성
def get_segment_merger(provider: str = "google", model: str = "gemini-2.5-flash") -> AISceneMerger:
    return get_scene_merger(provider, model)


# ============================================================
# 레거시 클래스들 (하위 호환성 유지)
# ============================================================

@dataclass
class AISceneSegment:
    """AI가 분할한 씬 (레거시)"""
    scene_id: int
    script_text: str
    mood: str
    visual_elements: List[str]
    direction_guide: str
    camera_work: str
    characters: List[str]
    scene_break_reason: str


class AISceneSplitter:
    """AI 기반 씬 분할기 (레거시 - 텍스트 기반, v5.2 Provider별 분기)"""

    def __init__(
        self,
        provider: str = "google",
        model: str = "gemini-2.5-flash",
        api_key: str = None
    ):
        self.provider = provider
        self.model = model
        self.client = None
        self._initialized = False

        # ✅ Provider별 API 키 설정
        if provider == "google":
            self.api_key = api_key or GOOGLE_API_KEY or GEMINI_API_KEY
        elif provider == "anthropic":
            self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        elif provider == "claude_code_agent":
            self.api_key = None  # subprocess 방식은 API 키 불필요
        else:
            self.api_key = api_key or GOOGLE_API_KEY or GEMINI_API_KEY

        print(f"[AISceneSplitter] 초기화 (provider: {provider}, model: {model})")

    def _initialize_client(self):
        """✅ Provider별 클라이언트 초기화"""
        if self._initialized:
            return

        try:
            if self.provider == "google":
                import google.generativeai as genai
                genai.configure(api_key=self.api_key)
                self.client = genai.GenerativeModel(self.model)
                self._initialized = True

            elif self.provider == "anthropic":
                if ANTHROPIC_AVAILABLE:
                    self.client = anthropic.Anthropic(api_key=self.api_key)
                    self._initialized = True
                else:
                    raise ImportError("anthropic 패키지가 필요합니다")
        except Exception as e:
            print(f"[AISceneSplitter] 클라이언트 초기화 실패: {e}")
            raise

    def split_script(
        self,
        script: str,
        language: str = "ko",
        split_style: str = "기본",
        custom_prompt: str = None
    ) -> List[AISceneSegment]:
        """스크립트를 씬으로 분할 (레거시)"""
        self._initialize_client()

        print(f"[AISceneSplitter] 레거시 분할 - 스크립트: {len(script)}자")

        # 간단한 분할
        parts = re.split(r'\n\n+|(?<=[.?!])\s+', script)

        segments = []
        for i, part in enumerate(parts, 1):
            part = part.strip()
            if part:
                segments.append(AISceneSegment(
                    scene_id=i,
                    script_text=part,
                    mood="",
                    visual_elements=[],
                    direction_guide="",
                    camera_work="",
                    characters=[],
                    scene_break_reason=""
                ))

        return segments


class HybridPromptManager:
    """하이브리드 프롬프트 관리자 (레거시)"""

    DEFAULT_PROMPTS = {
        "기본": {
            "name": "기본 (1~3문장)",
            "description": "자연스러운 문맥 단위로 분할",
            "min_chars": 30,
            "max_chars": 250,
            "style_desc": "자연스러운 문맥 단위 (1~3문장)",
            "criteria": [],
            "custom_instructions": ""
        },
        "잘게": {
            "name": "잘게 (1문장)",
            "description": "짧은 호흡 단위로 분할",
            "min_chars": 15,
            "max_chars": 120,
            "style_desc": "짧은 호흡 단위 (1문장)",
            "criteria": [],
            "custom_instructions": ""
        },
        "크게": {
            "name": "크게 (3~5문장)",
            "description": "큰 주제 단위로 분할",
            "min_chars": 100,
            "max_chars": 500,
            "style_desc": "큰 주제 단위 (3~5문장)",
            "criteria": [],
            "custom_instructions": ""
        }
    }

    def __init__(self, config_path: str = None):
        self.prompts = dict(self.DEFAULT_PROMPTS)

    def get_prompt(self, style: str) -> Dict:
        return self.prompts.get(style, self.prompts["기본"])

    def update_prompt(self, style: str, **kwargs) -> bool:
        """
        프롬프트 설정 업데이트

        Args:
            style: 분할 스타일 ("잘게", "기본", "크게")
            **kwargs: 업데이트할 설정 값들
                - min_chars: 최소 글자 수
                - max_chars: 최대 글자 수
                - custom_instructions: 추가 지시사항

        Returns:
            bool: 성공 여부
        """
        try:
            if style not in self.prompts:
                print(f"[HybridPromptManager] 알 수 없는 스타일: {style}")
                return False

            for key, value in kwargs.items():
                if key in self.prompts[style]:
                    self.prompts[style][key] = value
                    print(f"[HybridPromptManager] {style}.{key} = {value}")

            # STYLE_CONFIG도 동기화
            if style in STYLE_CONFIG:
                if 'max_chars' in kwargs:
                    STYLE_CONFIG[style]['max_chars'] = kwargs['max_chars']
                if 'min_chars' in kwargs:
                    # min_sentences와 대략 매핑 (선택적)
                    pass

            print(f"[HybridPromptManager] {style} 설정 업데이트 완료")
            return True

        except Exception as e:
            print(f"[HybridPromptManager] 업데이트 실패: {e}")
            return False

    def reset_prompt(self, style: str) -> bool:
        """
        프롬프트를 기본값으로 복원

        Args:
            style: 분할 스타일

        Returns:
            bool: 성공 여부
        """
        try:
            if style in self.DEFAULT_PROMPTS:
                self.prompts[style] = dict(self.DEFAULT_PROMPTS[style])
                print(f"[HybridPromptManager] {style} 기본값 복원 완료")
                return True
            return False
        except Exception as e:
            print(f"[HybridPromptManager] 복원 실패: {e}")
            return False

    def build_prompt(self, style: str, script: str) -> str:
        config = self.get_prompt(style)
        return f"분할 스타일: {config['style_desc']}\n\n스크립트:\n{script}"


_prompt_manager: Optional[HybridPromptManager] = None


def get_prompt_manager() -> HybridPromptManager:
    global _prompt_manager
    if _prompt_manager is None:
        _prompt_manager = HybridPromptManager()
    return _prompt_manager


_splitter = None


def get_ai_splitter(provider: str = "google", model: str = "gemini-2.5-flash") -> AISceneSplitter:
    global _splitter
    if _splitter is None:
        _splitter = AISceneSplitter(provider=provider, model=model)
    return _splitter
