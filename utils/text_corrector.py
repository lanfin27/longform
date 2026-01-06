# -*- coding: utf-8 -*-
"""
원문 텍스트 교정 모듈 (v5.5)

Whisper 인식 결과를 원문 스크립트 기준으로 교정
- 오타 수정 (자외사 → 자회사)
- 영어 교정 (DF → ZF)
- 숫자 교정 (2015년 → 2025년)
- 고유명사 교정 (콕피시 → 콕핏)
- ✅ Claude CLI (Max Plan) 기본
- ✅ Gemini 자동 폴백
- ⭐ v5.5: 빈 텍스트 방지 로직 추가 (교정 결과가 비면 원본 유지)
"""

import os
import re
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from difflib import SequenceMatcher

# 프로젝트 루트 추가
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import GOOGLE_API_KEY, GEMINI_API_KEY

# Claude Code Runner 가용성 체크
try:
    from utils.claude_code_runner import get_claude_code_runner, is_claude_code_available
    CLAUDE_CODE_AVAILABLE = is_claude_code_available()
except ImportError:
    CLAUDE_CODE_AVAILABLE = False

# Gemini (폴백용) - 모듈 레벨 초기화
GEMINI_FALLBACK_AVAILABLE = False
_gemini_fallback_client = None
try:
    import google.generativeai as genai
    _gemini_api_key = os.getenv("GOOGLE_API_KEY")
    if _gemini_api_key:
        genai.configure(api_key=_gemini_api_key)
        _gemini_fallback_client = genai.GenerativeModel("gemini-2.0-flash-exp")
        GEMINI_FALLBACK_AVAILABLE = True
        print("[TextCorrector] ✅ Gemini 폴백 준비 완료")
except Exception as e:
    print(f"[TextCorrector] ⚠️ Gemini 폴백 초기화 실패: {e}")

# Anthropic (제거됨 - 주석 처리)
ANTHROPIC_AVAILABLE = False
# try:
#     import anthropic
#     ANTHROPIC_AVAILABLE = True
# except ImportError:
#     ANTHROPIC_AVAILABLE = False


@dataclass
class CorrectionResult:
    """교정 결과"""
    original_whisper: str  # Whisper 인식 텍스트
    corrected: str  # 교정된 텍스트
    corrections: List[Dict]  # 교정 내역


@dataclass
class SceneGroupCorrected:
    """교정된 씬 그룹"""
    scene_id: int
    sentence_ids: List[int]
    text: str  # 교정된 텍스트
    start_time: float
    end_time: float
    original_whisper_text: str  # 원본 Whisper 텍스트
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


class TextCorrector:
    """텍스트 교정기 (v5.3 - Provider별 분기 + 배치 처리 + Rate Limit 대응 + Claude Code Agent)"""

    # Rate Limit 설정
    BATCH_SIZE = 10  # 한 번에 처리할 씬 개수
    MIN_DELAY_BETWEEN_BATCHES = 6.0  # 배치 간 최소 대기 시간 (초)
    MAX_RETRIES = 3  # 최대 재시도 횟수

    def __init__(
        self,
        provider: str = "google",
        model: str = "gemini-2.0-flash-exp",
        api_key: str = None
    ):
        self.provider = provider
        self.model = model
        self.client = None
        self.claude_runner = None  # v5.3: Claude Code Runner
        self._initialized = False
        self._last_api_call = 0.0

        # v5.4: Gemini 폴백 속성 초기화
        self._use_gemini_fallback = False
        self._gemini_client = _gemini_fallback_client  # 모듈 레벨 클라이언트 참조

        # Provider별 API 키 설정
        if provider == "google":
            self.api_key = api_key or GOOGLE_API_KEY or GEMINI_API_KEY
        elif provider == "anthropic":
            self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        elif provider == "claude_code_agent":
            # ✅ v5.3: Claude Code Agent는 API 키 불필요 (로컬 CLI)
            self.api_key = None
        else:
            self.api_key = api_key or GOOGLE_API_KEY or GEMINI_API_KEY

        print(f"[TextCorrector] 초기화 (provider: {provider})")

        # ✅ 즉시 클라이언트 초기화
        self._initialize_client()

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
                print(f"[TextCorrector] ✅ Gemini 클라이언트 초기화 완료")

            elif self.provider == "anthropic":
                if not ANTHROPIC_AVAILABLE:
                    raise ImportError("anthropic 패키지가 필요합니다: pip install anthropic")
                if not self.api_key:
                    raise ValueError("ANTHROPIC_API_KEY 환경 변수가 필요합니다")
                self.client = anthropic.Anthropic(api_key=self.api_key)
                self._initialized = True
                print(f"[TextCorrector] ✅ Claude API 클라이언트 초기화 완료")

            elif self.provider == "claude_code_agent":
                # ✅ v5.3: Claude Code Agent = subprocess 방식 (API 아님!)
                if not CLAUDE_CODE_AVAILABLE:
                    raise ImportError("Claude CLI가 설치되지 않았습니다. 'npm install -g @anthropic-ai/claude-code' 필요")
                self.claude_runner = get_claude_code_runner()
                if not self.claude_runner.available:
                    raise ValueError("Claude CLI를 사용할 수 없습니다")
                self._initialized = True
                print(f"[TextCorrector] ✅ Claude Code Runner 초기화 완료 (subprocess)")

            else:
                raise ValueError(f"지원하지 않는 provider: {self.provider}")

        except Exception as e:
            print(f"[TextCorrector] ⚠️ 클라이언트 초기화 실패: {e}")
            self.client = None
            self.claude_runner = None
            raise

    def _wait_for_rate_limit(self, retry_count: int = 0):
        """Rate Limit 대기"""
        now = time.time()
        elapsed = now - self._last_api_call

        # 기본 대기 시간 + 재시도 시 지수 백오프
        base_delay = self.MIN_DELAY_BETWEEN_BATCHES
        if retry_count > 0:
            base_delay = base_delay * (2 ** retry_count)  # 지수 백오프

        if elapsed < base_delay:
            wait_time = base_delay - elapsed
            print(f"[TextCorrector] ⏳ Rate Limit 대기: {wait_time:.1f}초")
            time.sleep(wait_time)

        self._last_api_call = time.time()

    def correct_scenes(
        self,
        scenes: List,  # SceneGroup 리스트
        original_script: str
    ) -> List[SceneGroupCorrected]:
        """
        씬 텍스트를 원문 기준으로 교정 (배치 처리)

        Args:
            scenes: 씬 리스트 (Whisper 텍스트)
            original_script: 원본 스크립트

        Returns:
            교정된 씬 리스트
        """
        self._initialize_client()

        print(f"[TextCorrector] 텍스트 교정 시작")
        print(f"[TextCorrector]   씬: {len(scenes)}개")
        print(f"[TextCorrector]   원문: {len(original_script)}자")

        # 원문을 문장 단위로 분리
        original_sentences = self._split_sentences(original_script)
        print(f"[TextCorrector]   원문 문장: {len(original_sentences)}개")

        # 배치 개수 계산
        num_batches = (len(scenes) + self.BATCH_SIZE - 1) // self.BATCH_SIZE
        print(f"[TextCorrector]   배치: {num_batches}개 (배치당 {self.BATCH_SIZE}씬)")

        # 배치 단위로 처리
        corrected_scenes = []
        corrections_made = 0

        for batch_idx in range(num_batches):
            start_idx = batch_idx * self.BATCH_SIZE
            end_idx = min(start_idx + self.BATCH_SIZE, len(scenes))
            batch_scenes = scenes[start_idx:end_idx]

            print(f"[TextCorrector] 📦 배치 {batch_idx + 1}/{num_batches} 처리 중 ({len(batch_scenes)}씬)...")

            # 배치 처리 (Rate Limit 대응)
            batch_result, batch_corrections = self._process_batch(
                batch_scenes,
                original_sentences
            )

            corrected_scenes.extend(batch_result)
            corrections_made += batch_corrections

        print(f"[TextCorrector] ✅ 교정 완료 ({corrections_made}개 씬 수정됨)")

        return corrected_scenes

    def _process_batch(
        self,
        batch_scenes: List,
        original_sentences: List[str]
    ) -> Tuple[List[SceneGroupCorrected], int]:
        """
        배치 단위로 씬 교정 (Rate Limit 처리 포함)

        Args:
            batch_scenes: 처리할 씬 배치
            original_sentences: 원문 문장 리스트

        Returns:
            (교정된 씬 리스트, 수정된 씬 개수)
        """
        corrected = []
        corrections_made = 0

        # 배치 내 씬들의 텍스트와 매칭 정보를 한 번에 수집
        batch_data = []
        for scene in batch_scenes:
            matched_originals = self._find_matching_sentences(
                scene.text,
                original_sentences
            )
            batch_data.append({
                "scene": scene,
                "matched_originals": matched_originals
            })

        # 배치 AI 교정 수행
        corrected_texts = self._batch_ai_correct(batch_data)

        # 결과 조합
        for i, scene in enumerate(batch_scenes):
            corrected_text = corrected_texts.get(i, scene.text)

            # ⭐ v5.5: 빈 텍스트 방지 - 교정 결과가 비어있으면 원본 유지
            if not corrected_text or not corrected_text.strip():
                if scene.text and scene.text.strip():
                    corrected_text = scene.text
                    print(f"[TextCorrector] ⚠️ 씬 {scene.scene_id}: 교정 결과 빈 텍스트, 원본 유지")
                else:
                    print(f"[TextCorrector] ⚠️ 씬 {scene.scene_id}: 원본도 빈 텍스트!")

            if corrected_text != scene.text:
                corrections_made += 1

            corrected_scene = SceneGroupCorrected(
                scene_id=scene.scene_id,
                sentence_ids=scene.sentence_ids if hasattr(scene, 'sentence_ids') else [],
                text=corrected_text,
                start_time=scene.start_time,
                end_time=scene.end_time,
                original_whisper_text=scene.text,
                mood=scene.mood if hasattr(scene, 'mood') else "",
                scene_break_reason=scene.scene_break_reason if hasattr(scene, 'scene_break_reason') else ""
            )
            corrected.append(corrected_scene)

        return corrected, corrections_made

    def _call_ai(self, prompt: str) -> str:
        """✅ Provider별 API 호출 (Claude CLI + Gemini 폴백)"""

        # Claude Code Agent (Max Plan) - 우선
        if self.provider == "claude_code_agent" or (self.claude_runner and self.claude_runner.available):
            if not hasattr(self, '_use_gemini_fallback'):
                self._use_gemini_fallback = False

            if not self._use_gemini_fallback:
                if self.claude_runner is None or not self.claude_runner.available:
                    if CLAUDE_CODE_AVAILABLE:
                        self.claude_runner = get_claude_code_runner()

                if self.claude_runner and self.claude_runner.available:
                    print(f"[TextCorrector] 🔵 Claude Code CLI 실행 중 (Max Plan)...")
                    result = self.claude_runner.run(prompt, timeout=120)

                    if result.success:
                        return result.output

                    # 폴백 필요?
                    if result.should_fallback and GEMINI_FALLBACK_AVAILABLE:
                        print(f"[TextCorrector] ⚠️ Claude CLI 실패: {result.error}")
                        print(f"[TextCorrector] 🔄 Gemini 폴백으로 전환")
                        self._use_gemini_fallback = True
                    else:
                        raise Exception(f"Claude Code 실행 실패: {result.error}")

        # Gemini (폴백 또는 google provider)
        if self.provider == "google" or (hasattr(self, '_use_gemini_fallback') and self._use_gemini_fallback):
            if self._use_gemini_fallback and _gemini_fallback_client:
                print(f"[TextCorrector] 🟡 Gemini 실행 중 (폴백)...")
                response = _gemini_fallback_client.generate_content(
                    prompt,
                    generation_config={
                        "temperature": 0.1,
                        "max_output_tokens": 4096
                    }
                )
                return response.text
            elif self.client is not None:
                response = self.client.generate_content(
                    prompt,
                    generation_config={
                        "temperature": 0.1,
                        "max_output_tokens": 4096
                    }
                )
                return response.text
            else:
                raise ValueError("Gemini 클라이언트가 초기화되지 않았습니다")

        raise ValueError(f"지원하지 않는 provider: {self.provider}")

    def _batch_ai_correct(self, batch_data: List[Dict]) -> Dict[int, str]:
        """
        배치 단위 AI 교정 (한 번의 API 호출로 여러 씬 처리)

        Args:
            batch_data: 씬 데이터 리스트

        Returns:
            {씬 인덱스: 교정된 텍스트} 딕셔너리
        """
        # 교정할 씬이 없으면 빈 결과 반환
        valid_batch = [(i, d) for i, d in enumerate(batch_data) if d["matched_originals"]]
        if not valid_batch:
            return {}

        # 배치 프롬프트 생성
        prompt = self._build_batch_prompt(valid_batch)

        # Rate Limit 대기 후 API 호출
        for retry in range(self.MAX_RETRIES):
            self._wait_for_rate_limit(retry)

            try:
                # ✅ Provider별 API 호출
                response_text = self._call_ai(prompt)

                # 응답 파싱
                return self._parse_batch_response(response_text, batch_data)

            except Exception as e:
                error_str = str(e)

                # Rate Limit 에러 처리
                if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                    # retry_delay 추출 시도
                    retry_delay = self._extract_retry_delay(error_str)
                    wait_time = max(retry_delay, self.MIN_DELAY_BETWEEN_BATCHES * (2 ** (retry + 1)))

                    print(f"[TextCorrector] ⚠️ Rate Limit 도달, {wait_time:.1f}초 대기 후 재시도 ({retry + 1}/{self.MAX_RETRIES})")
                    time.sleep(wait_time)
                    continue
                else:
                    print(f"[TextCorrector] AI 배치 교정 오류: {e}")
                    break

        # 실패 시 원본 반환
        return {}

    def _build_batch_prompt(self, valid_batch: List[Tuple[int, Dict]]) -> str:
        """배치 교정용 프롬프트 생성"""
        scenes_text = []
        for i, (idx, data) in enumerate(valid_batch):
            scene = data["scene"]
            refs = data["matched_originals"]
            scenes_text.append(f"""### 씬 {i + 1}
**Whisper 텍스트:** {scene.text}
**원문 참조:**
{chr(10).join(f'- {ref}' for ref in refs[:3])}
""")

        return f"""다음 음성 인식 텍스트들을 원문 참조를 바탕으로 교정해주세요.

## 교정 규칙
1. 오타 수정 (예: "자외사" → "자회사", "노이의" → "노이에")
2. 영어 교정 (예: "DF" → "ZF", "ADAS" 등 정확한 영어로)
3. 숫자 교정 (예: "2015년" → "2025년")
4. 고유명사 교정 (예: "콕피시" → "콕핏")
5. 문장 구조는 최대한 유지
6. 원문에 없는 내용은 추가하지 않기

## 교정할 씬들
{chr(10).join(scenes_text)}

## 출력 형식 (반드시 JSON만 출력)
```json
{{
  "corrections": [
    {{"scene": 1, "corrected": "교정된 텍스트 1"}},
    {{"scene": 2, "corrected": "교정된 텍스트 2"}}
  ]
}}
```

교정이 필요 없으면 원본 텍스트를 그대로 출력하세요.
"""

    def _parse_batch_response(self, response: str, batch_data: List[Dict]) -> Dict[int, str]:
        """배치 응답 파싱"""
        import json

        result = {}

        # JSON 추출
        json_match = re.search(r'\{[\s\S]*\}', response)
        if not json_match:
            return result

        try:
            data = json.loads(json_match.group())
            corrections = data.get("corrections", [])

            for corr in corrections:
                scene_num = corr.get("scene", 0) - 1  # 1-indexed → 0-indexed
                corrected_text = corr.get("corrected", "")

                if 0 <= scene_num < len(batch_data) and corrected_text:
                    original_text = batch_data[scene_num]["scene"].text

                    # ⭐ v5.5: 오타만 교정 원칙 - 엄격한 검증
                    # 1. 빈 텍스트 거부
                    if not corrected_text.strip():
                        print(f"[TextCorrector] ⚠️ 씬 {scene_num+1}: 교정 결과 빈 텍스트, 거부")
                        continue

                    # 2. 유사도 검증 (70% 이상이어야 적용)
                    similarity = SequenceMatcher(None, original_text, corrected_text).ratio()
                    if similarity < 0.7:
                        print(f"[TextCorrector] ⚠️ 씬 {scene_num+1}: 유사도 {similarity:.0%} 낮음, 원본 유지")
                        continue

                    # 3. 길이 검증 (원본의 50% 이상이어야 적용)
                    if len(corrected_text) < len(original_text) * 0.5:
                        print(f"[TextCorrector] ⚠️ 씬 {scene_num+1}: 길이 50% 미만, 원본 유지")
                        continue

                    result[scene_num] = corrected_text.replace('\n', ' ').strip()

        except (json.JSONDecodeError, KeyError) as e:
            print(f"[TextCorrector] 배치 응답 파싱 오류: {e}")

        return result

    def _extract_retry_delay(self, error_str: str) -> float:
        """에러 메시지에서 retry_delay 추출"""
        # "retry_delay: 30s" 또는 "retryDelay: 30" 형태 파싱
        match = re.search(r'retry[_]?delay[:\s]+(\d+)', error_str, re.IGNORECASE)
        if match:
            return float(match.group(1))
        return 30.0  # 기본값

    def _split_sentences(self, text: str) -> List[str]:
        """텍스트를 문장 단위로 분리"""
        # 줄바꿈 기준 분리
        lines = text.strip().split('\n')

        sentences = []
        for line in lines:
            line = line.strip()
            if line:
                # 문장 부호로 추가 분리
                parts = re.split(r'(?<=[.?!。？！])\s+', line)
                sentences.extend([p.strip() for p in parts if p.strip()])

        return sentences

    def _find_matching_sentences(
        self,
        whisper_text: str,
        original_sentences: List[str],
        threshold: float = 0.3
    ) -> List[str]:
        """유사한 원문 문장 찾기"""

        matches = []
        whisper_normalized = self._normalize(whisper_text)

        # Whisper 텍스트의 키워드 추출 (긴 단어들)
        whisper_keywords = set(w for w in whisper_normalized.split() if len(w) >= 3)

        for orig in original_sentences:
            orig_normalized = self._normalize(orig)

            # 유사도 계산
            similarity = SequenceMatcher(
                None,
                whisper_normalized,
                orig_normalized
            ).ratio()

            # 키워드 매칭 보너스
            orig_keywords = set(w for w in orig_normalized.split() if len(w) >= 3)
            common_keywords = whisper_keywords & orig_keywords
            if len(common_keywords) >= 2:
                similarity = max(similarity, 0.5)

            # 부분 문자열 체크
            if len(whisper_normalized) > 20 and len(orig_normalized) > 20:
                if whisper_normalized[:20] in orig_normalized or orig_normalized[:20] in whisper_normalized:
                    similarity = max(similarity, 0.6)

            if similarity >= threshold:
                matches.append((similarity, orig))

        # 유사도 높은 순 정렬
        matches.sort(reverse=True, key=lambda x: x[0])

        # 상위 5개 반환
        return [m[1] for m in matches[:5]]

    def _normalize(self, text: str) -> str:
        """텍스트 정규화"""
        text = text.lower()
        text = re.sub(r'[^\w\s]', '', text)
        text = re.sub(r'\s+', ' ', text)
        return text.strip()


# ═══════════════════════════════════════════════════════════════════
# TextCorrectorV3: 원문 기반 전체 SRT 교정 (v3.0)
# ═══════════════════════════════════════════════════════════════════

from difflib import get_close_matches
import json


class TextCorrectorV3:
    """
    텍스트 교정기 v3.0 - 원문 기반 전체 SRT 교정 (v7.0 - TYPO + REGEX 패턴 대폭 확장)

    특징:
    1. 전체 SRT를 한 번에 교정 (1-2회 API 호출)
    2. 원문 스크립트에서 단어 사전 추출
    3. 오타 후보 자동 감지 (원문에 없는 단어)
    4. AI 실패 시 로컬 교정 폴백
    5. Provider별 분기 처리 (Google/Anthropic/Claude Code Agent)
    6. ⭐ v7.0: 확장된 TYPO_PATTERNS (80개+) + REGEX_PATTERNS (정규식)
    """

    # ⭐ v7.0: 확장된 Whisper 오타 패턴 (80개+)
    TYPO_PATTERNS = {
        # ═══════════════════════════════════════════════════════════════
        # 1. 동사 어미 오류 (가장 흔함!)
        # ═══════════════════════════════════════════════════════════════
        '만들어갈요': '만들어요',
        '만들어갈': '만들어',
        '들어갈가': '들어가',
        '들어갈가는': '들어가는',
        '만들어갈가': '만들어가',
        '만들어갈가는': '만들어가는',
        '올라갈가': '올라가',
        '올라갈가는': '올라가는',
        '내려갈가': '내려가',
        '내려갈가는': '내려가는',
        '해갈요': '해요',
        '하갈요': '해요',

        # ═══════════════════════════════════════════════════════════════
        # 2. ~해게요 패턴 (해볼게요로 교정)
        # ═══════════════════════════════════════════════════════════════
        '해게요': '해볼게요',
        '나열해게요': '나열해볼게요',
        '정리해게요': '정리해볼게요',
        '시작해게요': '시작해볼게요',
        '종합해게요': '종합해볼게요',
        '설명해게요': '설명해볼게요',
        '말씀해게요': '말씀해볼게요',
        '살펴보게요': '살펴볼게요',
        '알아보게요': '알아볼게요',
        '보여드리게요': '보여드릴게요',
        '말씀드리게요': '말씀드릴게요',

        # ═══════════════════════════════════════════════════════════════
        # 3. 숫자/금액 오류 (매우 중요!)
        # ═══════════════════════════════════════════════════════════════
        # 조원 관련 (중복 오류)
        '조조원': '조원',
        '조 조원': '조원',
        '조조 원': '조원',
        '1조 조원': '1조원',
        '2조 조원': '2조원',
        '3조 조원': '3조원',
        '4조 조원': '4조원',
        '5조 조원': '5조원',
        '6조 조원': '6조원',
        '7조 조원': '7조원',
        '8조 조원': '8조원',
        '9조 조원': '9조원',
        '9조 조조원': '9조원',
        '10조 조원': '10조원',
        '14조 조원': '14조원',
        '15조 조원': '15조원',
        '20조 조원': '20조원',

        # 억원 관련
        '억억원': '억원',
        '억 억원': '억원',
        '4억 천억': '4천억',
        '4억천억': '4천억',
        '3조 4억 천억원': '3조 4천억원',
        '3조 4억천억원': '3조 4천억원',
        '억 천억': '천억',

        # 원 관련 (핵심!)
        '원안에서': '원에서',
        '원안에': '원에',
        '원안으로': '원으로',
        '조원안에서': '조원에서',
        '억원안에서': '억원에서',

        # ═══════════════════════════════════════════════════════════════
        # 4. 조사/어미 오류
        # ═══════════════════════════════════════════════════════════════
        '하면은': '하면',
        '그러면은': '그러면',
        '이러면은': '이러면',
        '보면은': '보면',
        '있으면은': '있으면',
        '없으면은': '없으면',
        '되면은': '되면',
        '하면은요': '하면요',

        # 안에서 → 에서
        '분야안에서': '분야에서',
        '분야안에서서': '분야에서',
        '입장안에서': '입장에서',
        '입장안에서는': '입장에서는',
        '시장안에서': '시장에서',
        '업계안에서': '업계에서',
        '안에서서': '에서',
        '안에서서는': '에서는',

        # ═══════════════════════════════════════════════════════════════
        # 5. 반복/중복 오류
        # ═══════════════════════════════════════════════════════════════
        '와와중에': '와중에',
        '뭐라고고': '뭐라고',
        '설명해설명해': '설명해',
        '드릴게요 설명해드릴게요': '드릴게요',
        '설명해 설명해드릴게요': '설명해드릴게요',
        '해드릴게요 해드릴게요': '해드릴게요',
        '밟아보여주는': '밟아주는',
        '유지해주는 보여주는': '유지해주는',

        # ═══════════════════════════════════════════════════════════════
        # 6. 외래어/영어 오류
        # ═══════════════════════════════════════════════════════════════
        '류로': '유로',

        # 영어 발음 → 영어
        '어드벤스드 드라이버, 어시스턴스 시스템': 'Advanced Driver Assistance System',
        '어드벤스드 드라이버 어시스턴스 시스템': 'Advanced Driver Assistance System',
        '에이디에이에스': 'ADAS',
        '에이다스': 'ADAS',
        '아다스': 'ADAS',

        # ═══════════════════════════════════════════════════════════════
        # 7. 고유명사/전문용어 오류
        # ═══════════════════════════════════════════════════════════════
        '전 회사': '가전회사',
        '자외사': '자회사',
        '노이의': '노이에',
        '노이의 클라세': '노이에 클라세',
        '콕피시': '콕핏',
        '콕핏시': '콕핏',

        # ═══════════════════════════════════════════════════════════════
        # 8. 기타 Whisper 오인식
        # ═══════════════════════════════════════════════════════════════
        '본 년': '기본',
        '지금년': '지금',
        '첫 번재': '첫 번째',
        '두 번재': '두 번째',
        '세 번재': '세 번째',
        '됬습니다': '됐습니다',
        '됬어요': '됐어요',
        '왜냐면요': '왜냐하면요',
        '왜냐면': '왜냐하면',
    }

    # ⭐ v7.0: 정규식 기반 패턴 (복잡한 패턴 처리)
    REGEX_PATTERNS = [
        # 숫자 + 조 + 조원 → 숫자 + 조원
        (r'(\d+)조\s*조원', r'\1조원'),

        # 숫자 + 조 + 조 + 원 → 숫자 + 조원
        (r'(\d+)조\s*조\s*원', r'\1조원'),

        # 숫자 + 억 + 억원 → 숫자 + 억원
        (r'(\d+)억\s*억원', r'\1억원'),

        # 원안에서 → 원에서 (숫자 뒤)
        (r'(\d+)원안에서', r'\1원에서'),
        (r'(\d+)원안에', r'\1원에'),
        (r'(\d+)원안으로', r'\1원으로'),

        # 조원안에서 → 조원에서
        (r'조원안에서', r'조원에서'),
        (r'억원안에서', r'억원에서'),

        # 만들어갈요/갈 패턴
        (r'만들어갈([요가])', r'만들어\1'),
        (r'들어갈가([는요])', r'들어가\1'),

        # 분야/시장/업계 + 안에서 → 에서
        (r'(분야|시장|업계|입장)안에서', r'\1에서'),

        # 숫자 + 억 + 천억 → 숫자 + 천억
        (r'(\d+)억\s*천억', r'\1천억'),
    ]

    def __init__(
        self,
        provider: str = "google",
        model: str = "gemini-2.0-flash-exp",
        api_key: str = None
    ):
        self.provider = provider
        self.model = model
        self.client = None
        self.claude_runner = None  # ✅ v5.3: Claude Code Runner
        self._initialized = False

        # ✅ Provider별 API 키 설정
        if provider == "google":
            self.api_key = api_key or GOOGLE_API_KEY or GEMINI_API_KEY
        elif provider == "anthropic":
            self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        elif provider == "claude_code_agent":
            # ✅ v5.3: Claude Code Agent는 API 키 불필요 (로컬 CLI)
            self.api_key = None
        else:
            self.api_key = api_key or GOOGLE_API_KEY or GEMINI_API_KEY

        # ⭐ v7.0: 정규식 패턴 컴파일
        self._compile_regex_patterns()

        print(f"[TextCorrectorV3] v7.0 초기화 (provider: {provider})")
        print(f"[TextCorrectorV3]   일반 패턴: {len(self.TYPO_PATTERNS)}개")
        print(f"[TextCorrectorV3]   정규식 패턴: {len(self.REGEX_PATTERNS)}개")

        # ✅ 즉시 클라이언트 초기화
        self._initialize_client()

    def _compile_regex_patterns(self):
        """⭐ v7.0: 정규식 패턴 컴파일"""
        self._compiled_patterns = [
            (re.compile(pattern), replacement)
            for pattern, replacement in self.REGEX_PATTERNS
        ]

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
                print(f"[TextCorrectorV3] ✅ Gemini 클라이언트 초기화 완료")

            elif self.provider == "anthropic":
                if not ANTHROPIC_AVAILABLE:
                    raise ImportError("anthropic 패키지가 필요합니다: pip install anthropic")
                if not self.api_key:
                    raise ValueError("ANTHROPIC_API_KEY 환경 변수가 필요합니다")
                self.client = anthropic.Anthropic(api_key=self.api_key)
                self._initialized = True
                print(f"[TextCorrectorV3] ✅ Claude API 클라이언트 초기화 완료")

            elif self.provider == "claude_code_agent":
                # ✅ v5.3: Claude Code Agent = subprocess 방식 (API 아님!)
                if not CLAUDE_CODE_AVAILABLE:
                    raise ImportError("Claude CLI가 설치되지 않았습니다. 'npm install -g @anthropic-ai/claude-code' 필요")
                self.claude_runner = get_claude_code_runner()
                if not self.claude_runner.available:
                    raise ValueError("Claude CLI를 사용할 수 없습니다")
                self._initialized = True
                print(f"[TextCorrectorV3] ✅ Claude Code Runner 초기화 완료 (subprocess)")

            else:
                raise ValueError(f"지원하지 않는 provider: {self.provider}")

        except Exception as e:
            print(f"[TextCorrectorV3] ⚠️ 클라이언트 초기화 실패: {e}")
            self.client = None
            self.claude_runner = None
            raise

    def correct_srt_with_script(
        self,
        srt_scenes: List,  # SceneGroup 리스트
        original_script: str
    ) -> Tuple[List, List[Dict]]:
        """
        ✅ 원문 스크립트 기반 SRT 교정 (핵심 기능)

        방법:
        1. 원문 스크립트에서 단어 사전 추출
        2. SRT 텍스트와 비교하여 오타 찾기
        3. AI로 전체 SRT 한 번에 교정

        Returns:
            (교정된 씬 리스트, 변경 내역)
        """
        if not original_script or len(original_script) < 50:
            print(f"[TextCorrectorV3] 원문 스크립트 없음, 교정 스킵")
            return srt_scenes, []

        print(f"[TextCorrectorV3] 원문 기반 교정 시작")
        print(f"[TextCorrectorV3]   씬: {len(srt_scenes)}개")
        print(f"[TextCorrectorV3]   원문: {len(original_script)}자")

        # Step 1: 원문에서 단어 사전 추출
        original_words = self._extract_words(original_script)
        print(f"[TextCorrectorV3]   원문 단어: {len(original_words)}개")

        # Step 2: SRT에서 오타 후보 찾기
        srt_full_text = " ".join(s.text for s in srt_scenes)
        srt_words = self._extract_words(srt_full_text)

        # Step 3: 오타 후보 식별 (원문에 없는 단어)
        typo_candidates = self._find_typo_candidates(srt_words, original_words)
        print(f"[TextCorrectorV3]   오타 후보: {len(typo_candidates)}개")

        if typo_candidates:
            for typo, suggestion in list(typo_candidates.items())[:5]:
                print(f"[TextCorrectorV3]     {typo} → {suggestion}")

        # Step 4: AI로 전체 교정 (1회 호출)
        corrected_scenes, changes = self._ai_correct_full_srt(
            srt_scenes,
            original_script,
            typo_candidates
        )

        print(f"[TextCorrectorV3] ✅ 교정 완료 ({len(changes)}개 수정)")

        return corrected_scenes, changes

    def _extract_words(self, text: str) -> set:
        """텍스트에서 단어 추출"""
        # 한글, 영어, 숫자 단어 추출
        words = re.findall(r'[가-힣]+|[a-zA-Z]+|[0-9]+', text)
        return set(words)

    def _find_typo_candidates(
        self,
        srt_words: set,
        original_words: set
    ) -> Dict[str, str]:
        """
        오타 후보 찾기

        SRT에만 있고 원문에 없는 단어 중
        원문의 유사한 단어로 교체 가능한 것 찾기
        """
        typo_map = {}

        # SRT에만 있는 단어
        srt_only = srt_words - original_words

        for word in srt_only:
            if len(word) < 2:
                continue

            # 원문에서 유사한 단어 찾기
            matches = get_close_matches(word, original_words, n=1, cutoff=0.6)

            if matches:
                typo_map[word] = matches[0]

        return typo_map

    def _call_ai(self, prompt: str) -> str:
        """✅ Provider별 API 호출 (Claude CLI + Gemini 폴백)"""

        # Claude Code Agent (Max Plan) - 우선
        if self.provider == "claude_code_agent" or (self.claude_runner and self.claude_runner.available):
            if not hasattr(self, '_use_gemini_fallback'):
                self._use_gemini_fallback = False

            if not self._use_gemini_fallback:
                if self.claude_runner is None or not self.claude_runner.available:
                    if CLAUDE_CODE_AVAILABLE:
                        self.claude_runner = get_claude_code_runner()

                if self.claude_runner and self.claude_runner.available:
                    print(f"[TextCorrectorV3] 🔵 Claude Code CLI 실행 중 (Max Plan)...")
                    result = self.claude_runner.run(prompt, timeout=180)

                    if result.success:
                        return result.output

                    # 폴백 필요?
                    if result.should_fallback and GEMINI_FALLBACK_AVAILABLE:
                        print(f"[TextCorrectorV3] ⚠️ Claude CLI 실패: {result.error}")
                        print(f"[TextCorrectorV3] 🔄 Gemini 폴백으로 전환")
                        self._use_gemini_fallback = True
                    else:
                        raise Exception(f"Claude Code 실행 실패: {result.error}")

        # Gemini (폴백 또는 google provider)
        if self.provider == "google" or (hasattr(self, '_use_gemini_fallback') and self._use_gemini_fallback):
            if self._use_gemini_fallback and _gemini_fallback_client:
                print(f"[TextCorrectorV3] 🟡 Gemini 실행 중 (폴백)...")
                response = _gemini_fallback_client.generate_content(
                    prompt,
                    generation_config={
                        "temperature": 0.1,
                        "max_output_tokens": 8192
                    }
                )
                return response.text
            elif self.client is not None:
                response = self.client.generate_content(
                    prompt,
                    generation_config={
                        "temperature": 0.1,
                        "max_output_tokens": 8192
                    }
                )
                return response.text
            else:
                raise ValueError("Gemini 클라이언트가 초기화되지 않았습니다")

        raise ValueError(f"지원하지 않는 provider: {self.provider}")

    def _ai_correct_full_srt(
        self,
        srt_scenes: List,
        original_script: str,
        typo_candidates: Dict[str, str]
    ) -> Tuple[List, List[Dict]]:
        """
        AI로 전체 SRT 교정 (1회 API 호출)

        v6.0: TYPO_PATTERNS 먼저 적용
        """
        self._initialize_client()

        # v6.0: TYPO_PATTERNS 먼저 적용
        pre_corrected_scenes = []
        for scene in srt_scenes:
            text = scene.text
            corrected_text = self._apply_typo_patterns(text)
            if corrected_text != text:
                # 복제 후 텍스트 교체
                scene = self._clone_scene_with_new_text(scene, corrected_text)
            pre_corrected_scenes.append(scene)

        # SRT 텍스트 추출 (TYPO_PATTERNS 적용 후)
        srt_items = []
        for i, scene in enumerate(pre_corrected_scenes):
            srt_items.append(f"[{i}] {scene.text}")

        # 프롬프트 생성
        prompt = self._build_correction_prompt(
            srt_items,
            original_script,
            typo_candidates
        )

        try:
            # ✅ Provider별 API 호출
            response_text = self._call_ai(prompt)

            # 파싱
            corrections = self._parse_correction_response(response_text)

            # 씬에 적용
            changes = []
            corrected_scenes = []

            for i, scene in enumerate(srt_scenes):
                if i in corrections and corrections[i] != scene.text:
                    corrected_text = corrections[i]

                    # v6.0: 빈 텍스트 방지 + 유사도 검증 (25%로 낮춤)
                    if not corrected_text or not corrected_text.strip():
                        print(f"[TextCorrectorV3] ⚠️ 씬 {i}: 교정 결과 빈 텍스트, 원본 유지")
                        corrected_scenes.append(scene)
                        continue

                    # v6.0: 유사도 검증 (25%로 낮춤 - 음차 변환 고려)
                    from difflib import SequenceMatcher
                    similarity = SequenceMatcher(None, scene.text, corrected_text).ratio()
                    if similarity < 0.25:
                        print(f"[TextCorrectorV3] ⚠️ 씬 {i}: 유사도 {similarity:.0%} 낮음, 원본 유지")
                        corrected_scenes.append(scene)
                        continue
                    elif similarity < 0.50:
                        print(f"[TextCorrectorV3] ⚠️ 씬 {i}: 유사도 {similarity:.0%} (경고, 적용)")

                    # 교정 적용
                    changes.append({
                        "scene_id": scene.scene_id if hasattr(scene, 'scene_id') else i,
                        "original": scene.text,
                        "corrected": corrected_text
                    })

                    # 새 씬 생성 (교정된 텍스트)
                    corrected_scene = self._clone_scene_with_new_text(
                        scene,
                        corrected_text
                    )
                    corrected_scenes.append(corrected_scene)
                else:
                    corrected_scenes.append(scene)

            return corrected_scenes, changes

        except Exception as e:
            print(f"[TextCorrectorV3] AI 교정 오류: {e}")

            # 실패 시 로컬 교정만 적용
            return self._apply_local_corrections(srt_scenes, typo_candidates)

    def _build_correction_prompt(
        self,
        srt_items: List[str],
        original_script: str,
        typo_candidates: Dict[str, str]
    ) -> str:
        """교정 프롬프트 생성"""

        # 오타 힌트 생성
        typo_hints = []
        for typo, correct in list(typo_candidates.items())[:20]:
            typo_hints.append(f"  - {typo} → {correct}")

        typo_hints_text = "\n".join(typo_hints) if typo_hints else "  (없음)"

        # 원문은 최대 4000자까지
        script_preview = original_script[:4000]
        if len(original_script) > 4000:
            script_preview += "\n... (이하 생략)"

        return f"""당신은 자막 교정 전문가입니다.

## 작업
음성 인식(Whisper)으로 생성된 자막을 원문 스크립트 기준으로 교정해주세요.

## 원문 스크립트 (정확한 텍스트)
{script_preview}

## 자막 (교정 필요)
{chr(10).join(srt_items)}

## 감지된 오타 후보
{typo_hints_text}

## 교정 규칙
1. 오타 수정 (예: "사운드봐" → "사운드바", "자외사" → "자회사")
2. 영어 교정 (예: "DF" → "ZF", "ADAS")
3. 숫자 교정 (예: "2015년" → "2025년")
4. 고유명사 교정 (예: "콕피시" → "콕핏", "노이의 클라세" → "노이에 클라세")
5. **문장 구조와 길이는 최대한 유지** (타임스탬프 정합성)
6. 원문에 없는 내용 추가 금지

## 출력 형식 (JSON만 출력)
```json
{{
  "corrections": {{
    "0": "교정된 첫 번째 자막",
    "1": "교정된 두 번째 자막",
    "2": "세 번째 자막 (변경 없으면 그대로)"
  }}
}}
```

## 중요!
- 모든 자막 번호를 포함해야 합니다
- 변경이 없는 자막도 원본 그대로 포함
- JSON 외에 다른 텍스트 출력 금지
"""

    def _parse_correction_response(self, response_text: str) -> Dict[int, str]:
        """교정 응답 파싱"""

        # JSON 추출
        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if not json_match:
            return {}

        try:
            data = json.loads(json_match.group())
            corrections = data.get("corrections", {})
            return {int(k): v for k, v in corrections.items()}
        except Exception as e:
            print(f"[TextCorrectorV3] JSON 파싱 오류: {e}")
            return {}

    def _apply_typo_patterns(self, text: str) -> str:
        """⭐ v7.0: TYPO_PATTERNS + REGEX_PATTERNS 모두 적용"""
        result = text

        # Step 1: 일반 패턴 적용
        for typo, fix in self.TYPO_PATTERNS.items():
            if typo in result:
                result = result.replace(typo, fix)

        # Step 2: 정규식 패턴 적용
        result = self._apply_regex_patterns(result)

        return result

    def _apply_regex_patterns(self, text: str) -> str:
        """⭐ v7.0: 정규식 패턴 적용"""
        result = text
        for pattern, replacement in self._compiled_patterns:
            result = pattern.sub(replacement, result)
        return result

    def _apply_local_corrections(
        self,
        srt_scenes: List,
        typo_candidates: Dict[str, str]
    ) -> Tuple[List, List[Dict]]:
        """
        로컬 교정 (AI 실패 시 폴백)

        v6.0: TYPO_PATTERNS + 감지된 오타 모두 적용
        """
        print(f"[TextCorrectorV3] 로컬 교정 폴백 사용 (TYPO_PATTERNS 포함)")

        changes = []
        corrected_scenes = []

        for scene in srt_scenes:
            corrected_text = scene.text

            # v6.0: TYPO_PATTERNS 먼저 적용
            corrected_text = self._apply_typo_patterns(corrected_text)

            # 감지된 오타 후보 적용
            for typo, correct in typo_candidates.items():
                if typo in corrected_text:
                    corrected_text = corrected_text.replace(typo, correct)

            if corrected_text != scene.text:
                changes.append({
                    "scene_id": scene.scene_id if hasattr(scene, 'scene_id') else 0,
                    "original": scene.text,
                    "corrected": corrected_text
                })

                corrected_scene = self._clone_scene_with_new_text(scene, corrected_text)
                corrected_scenes.append(corrected_scene)
            else:
                corrected_scenes.append(scene)

        return corrected_scenes, changes

    def _clone_scene_with_new_text(self, scene, new_text: str):
        """씬 복제 후 텍스트 교체"""
        from dataclasses import fields, is_dataclass

        if is_dataclass(scene):
            # dataclass 필드 복사
            field_values = {}
            for f in fields(scene):
                if f.name == 'text':
                    field_values[f.name] = new_text
                else:
                    field_values[f.name] = getattr(scene, f.name)
            return scene.__class__(**field_values)
        else:
            # 일반 객체 - 속성 복사 시도
            try:
                scene_copy = type(scene).__new__(type(scene))
                for key, value in scene.__dict__.items():
                    if key == 'text':
                        setattr(scene_copy, key, new_text)
                    else:
                        setattr(scene_copy, key, value)
                return scene_copy
            except Exception:
                # 실패 시 원본 반환
                return scene


# ═══════════════════════════════════════════════════════════════════
# 싱글톤 인스턴스
# ═══════════════════════════════════════════════════════════════════

_corrector_instance: Optional[TextCorrector] = None
_corrector_v3_instance: Optional[TextCorrectorV3] = None


def get_text_corrector(
    provider: str = "google",
    model: str = "gemini-2.0-flash-exp"
) -> TextCorrector:
    """텍스트 교정기 싱글톤 (v5.1)"""
    global _corrector_instance

    if _corrector_instance is None:
        _corrector_instance = TextCorrector(provider=provider, model=model)

    return _corrector_instance


def get_text_corrector_v3(
    provider: str = "google",
    model: str = "gemini-2.0-flash-exp"
) -> TextCorrectorV3:
    """텍스트 교정기 v3.0 싱글톤"""
    global _corrector_v3_instance

    if _corrector_v3_instance is None:
        _corrector_v3_instance = TextCorrectorV3(provider=provider, model=model)

    return _corrector_v3_instance
