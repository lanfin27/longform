# -*- coding: utf-8 -*-
"""
최종 SRT 검증 모듈 (v9.0 - 숫자 매칭 강화 + 오타 패턴 면제)

변경사항 (v9.0):
- [NEW] 유사도 임계값 25% → 20%로 더 낮춤
- [NEW] _calculate_similarity() 숫자 매칭 가중치 50%로 높임
- [NEW] _should_bypass_similarity_check() 개선:
  - 숫자 동일하면 면제
  - 길이 차이 5자 이하면 면제
- [NEW] PHONETIC_BYPASS_PATTERNS 확장 (오타 패턴 추가)

변경사항 (v8.0):
- 유사도 임계값 50% → 25%로 낮춤 (음차 변환 고려)
- 음차 변환(영어↔한글) 면제 처리 추가
- PHONETIC_BYPASS_PATTERNS 추가

변경사항 (v7.0):
- 유사도 50% 미만 교정 거부 (싱크 보호)
- 오타/숫자/영문약자 교정은 유지
- 배치 크기 축소 (20 -> 10)
- 프롬프트 개선 (내용 변경 금지 강조)

기능:
1. 전체 SRT를 원문과 비교
2. Gemini로 불일치 부분 일괄 교정
3. 유사도 검증으로 잘못된 교정 거부 (숫자/오타/음차 면제)
4. 교정 결과를 SRT에 반영
"""

import os
import json
import re
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from difflib import SequenceMatcher

from utils.text_matcher import get_text_matcher, MatchResult


@dataclass
class ValidationResult:
    """검증 결과"""
    total_scenes: int
    scenes_needing_correction: int
    corrections_made: List[Dict]
    corrected_scenes: List
    provider_used: str = ""
    rejected_count: int = 0  # v7.0: 거부된 교정 수


@dataclass
class CorrectionResult:
    """개별 교정 결과"""
    scene_id: int
    original_text: str
    corrected_text: str
    similarity: float
    applied: bool
    reason: str = ""


class FinalSRTValidator:
    """최종 SRT 검증기 (v9.0 - 숫자 매칭 강화 + 오타 패턴 면제)"""

    # v9.0: 유사도 임계값 (20%로 더 낮춤 - 숫자/오타 교정 우선)
    SIMILARITY_REJECT = 0.20   # 20% 미만: 거부
    SIMILARITY_WARN = 0.50     # 20~50%: 경고 후 적용

    # 배치 크기 (작을수록 정확)
    BATCH_SIZE = 10

    # v9.0: 음차 변환 + 오타 교정 면제 패턴
    PHONETIC_BYPASS_PATTERNS = [
        # ═══════════════════════════════════════════════════════════════
        # 영어 발음 → 영어
        # ═══════════════════════════════════════════════════════════════
        ('어드벤스드', 'Advanced'),
        ('드라이버', 'Driver'),
        ('어시스턴스', 'Assistance'),
        ('시스템', 'System'),
        ('에이디에이에스', 'ADAS'),
        ('에이다스', 'ADAS'),
        ('아다스', 'ADAS'),
        ('레디케어', 'Ready Care'),
        ('레디 케어', 'Ready Care'),
        ('에이치비엠', 'HBM'),

        # ═══════════════════════════════════════════════════════════════
        # 회사명/브랜드명
        # ═══════════════════════════════════════════════════════════════
        ('비엠더블유', 'BMW'),
        ('비엠떠블유', 'BMW'),
        ('제트에프', 'ZF'),
        ('지에프', 'ZF'),
        ('엘지', 'LG'),
        ('에스케이', 'SK'),

        # ═══════════════════════════════════════════════════════════════
        # 기술 용어
        # ═══════════════════════════════════════════════════════════════
        ('오엘이디', 'OLED'),
        ('엘이디', 'LED'),
        ('콕피시', '콕핏'),
        ('콕핏시', '콕핏'),
        ('인포테인먼트', 'Infotainment'),
        ('노이의', '노이에'),

        # ═══════════════════════════════════════════════════════════════
        # 숫자/금액 표현 (v9.0 추가)
        # ═══════════════════════════════════════════════════════════════
        ('조 조원', '조원'),
        ('조조원', '조원'),
        ('억 천억', '천억'),
        ('억억원', '억원'),
        ('원안에서', '원에서'),
        ('원안에', '원에'),
        ('조원안에서', '조원에서'),

        # ═══════════════════════════════════════════════════════════════
        # 동사 어미 오류 (v9.0 추가)
        # ═══════════════════════════════════════════════════════════════
        ('만들어갈요', '만들어요'),
        ('만들어갈', '만들어'),
        ('들어갈가는', '들어가는'),
        ('해게요', '해볼게요'),
    ]

    def __init__(self, api_key: str = None):
        """
        초기화

        api_key는 무시됨 - Gemini 사용
        """
        self.matcher = get_text_matcher()
        self.gemini_client = None
        self._init_gemini()

        print(f"[FinalValidator] v9.0 초기화 (숫자 매칭 강화 + 오타 패턴 면제)")
        print(f"[FinalValidator]   유사도 거부 임계값: {self.SIMILARITY_REJECT:.0%}")
        print(f"[FinalValidator]   면제 패턴: {len(self.PHONETIC_BYPASS_PATTERNS)}개")
        print(f"[FinalValidator]   배치 크기: {self.BATCH_SIZE}")

    def _init_gemini(self):
        """Gemini 초기화"""
        try:
            import google.generativeai as genai
            api_key = os.getenv("GOOGLE_API_KEY")
            if api_key:
                genai.configure(api_key=api_key)
                self.gemini_client = genai.GenerativeModel("gemini-2.0-flash-exp")
                print("[FinalValidator] [OK] Gemini 준비 완료")
            else:
                print("[FinalValidator] [ERROR] GOOGLE_API_KEY 없음")
        except Exception as e:
            print(f"[FinalValidator] [ERROR] Gemini 초기화 실패: {e}")

    def validate_and_correct(
        self,
        srt_scenes: List,
        original_script: str
    ) -> ValidationResult:
        """
        SRT 최종 검증 및 교정

        v7.0: 유사도 검증으로 잘못된 교정 방지

        Args:
            srt_scenes: SRT 씬 리스트
            original_script: 원문 스크립트

        Returns:
            ValidationResult
        """

        print(f"\n[Step 7] 최종 SRT 검증")
        print(f"[FinalValidator] 검증 시작: {len(srt_scenes)}개 씬")

        if not original_script or len(original_script) < 50:
            print("[FinalValidator] [WARN] 원문 스크립트 없음, 검증 스킵")
            return ValidationResult(
                total_scenes=len(srt_scenes),
                scenes_needing_correction=0,
                corrections_made=[],
                corrected_scenes=srt_scenes
            )

        if not self.gemini_client:
            print("[FinalValidator] [ERROR] Gemini 없음, 검증 스킵")
            return ValidationResult(
                total_scenes=len(srt_scenes),
                scenes_needing_correction=0,
                corrections_made=[],
                corrected_scenes=srt_scenes
            )

        # 1. 원문과 매칭
        match_results = self.matcher.match_srt_to_original(srt_scenes, original_script)

        # 2. 교정 필요한 씬 식별
        scenes_to_correct = []
        for i, result in enumerate(match_results):
            if result.needs_correction:
                scene = srt_scenes[i]
                if isinstance(scene, dict):
                    scene_id = scene.get('scene_id', i + 1)
                    text = scene.get('text', '')
                else:
                    scene_id = getattr(scene, 'scene_id', i + 1)
                    text = getattr(scene, 'text', '')

                scenes_to_correct.append({
                    'scene_idx': i,
                    'scene_id': scene_id,
                    'srt_text': result.srt_text,
                    'original_text': result.original_text,
                    'similarity': result.similarity,
                    'differences': result.differences,
                    'current_text': text  # v7.0: 현재 텍스트 저장
                })

        print(f"[FinalValidator]   매칭 완료: {len(scenes_to_correct)}개 씬 교정 필요")

        if not scenes_to_correct:
            return ValidationResult(
                total_scenes=len(srt_scenes),
                scenes_needing_correction=0,
                corrections_made=[],
                corrected_scenes=srt_scenes
            )

        # 원문 문장 추출 (프롬프트용)
        original_sentences = self._extract_sentences(original_script)

        # 3. 배치별 교정 + 유사도 검증
        all_corrections = []
        total_rejected = 0
        correction_results: List[CorrectionResult] = []

        batch_size = self.BATCH_SIZE
        total_batches = (len(scenes_to_correct) - 1) // batch_size + 1

        for i in range(0, len(scenes_to_correct), batch_size):
            batch = scenes_to_correct[i:i + batch_size]
            batch_num = i // batch_size + 1

            print(f"[FinalValidator]   배치 {batch_num}/{total_batches} 처리 중 ({len(batch)}개)...")

            try:
                # AI 교정 받기
                ai_corrections = self._correct_batch(batch, original_sentences)

                # v7.0: 유사도 검증 후 적용
                for item in batch:
                    scene_id = item['scene_id']
                    scene_idx = item['scene_idx']
                    current_text = item['current_text']

                    if scene_id not in ai_corrections:
                        continue

                    corrected_text = ai_corrections[scene_id]

                    # v8.0: 유사도 계산
                    similarity = self._calculate_similarity(current_text, corrected_text)

                    # v8.0: 음차 변환 면제 체크
                    is_phonetic_bypass = self._should_bypass_similarity_check(current_text, corrected_text)

                    # v8.0: 유사도 기반 판정 (음차 변환은 면제)
                    if similarity < self.SIMILARITY_REJECT and not is_phonetic_bypass:
                        # 25% 미만: 거부! (음차 변환 제외)
                        result = CorrectionResult(
                            scene_id=scene_id,
                            original_text=current_text,
                            corrected_text=corrected_text,
                            similarity=similarity,
                            applied=False,
                            reason=f"유사도 {similarity:.0%} < {self.SIMILARITY_REJECT:.0%}"
                        )
                        correction_results.append(result)
                        total_rejected += 1
                        print(f"[FinalValidator]     [REJECT] 씬 {scene_id}: 유사도 {similarity:.0%}")
                        print(f"[FinalValidator]        원본: {current_text[:40]}...")
                        print(f"[FinalValidator]        교정: {corrected_text[:40]}...")
                        continue  # 원본 유지!

                    elif is_phonetic_bypass:
                        # 음차 변환 면제: 강제 적용
                        print(f"[FinalValidator]     [BYPASS] 씬 {scene_id}: 음차 변환 면제 (유사도 {similarity:.0%})")

                    elif similarity < self.SIMILARITY_WARN:
                        # 25~50%: 경고 후 적용
                        print(f"[FinalValidator]     [WARN] 씬 {scene_id}: 유사도 {similarity:.0%}")

                    # 교정 적용
                    all_corrections.append({
                        'scene_id': scene_id,
                        'scene_idx': scene_idx,
                        'original_srt': current_text,
                        'corrected': corrected_text,
                        'similarity': similarity,
                        'reason': 'ai_correction'
                    })

                    result = CorrectionResult(
                        scene_id=scene_id,
                        original_text=current_text,
                        corrected_text=corrected_text,
                        similarity=similarity,
                        applied=True
                    )
                    correction_results.append(result)

            except Exception as e:
                print(f"[FinalValidator]   배치 오류: {e}")
                # 로컬 교정 폴백
                local_corrections = self._local_correction(batch)
                all_corrections.extend(local_corrections)

        # 4. 교정 적용
        corrected_scenes = self._apply_corrections(srt_scenes, all_corrections)

        print(f"[FinalValidator] [OK] 검증 완료")
        print(f"[FinalValidator]   적용된 교정: {len(all_corrections)}개")
        print(f"[FinalValidator]   거부된 교정: {total_rejected}개 (유사도 {self.SIMILARITY_REJECT:.0%} 미만)")

        # 거부된 교정 상세 로그
        if total_rejected > 0:
            print(f"[FinalValidator]   [WARN] 거부된 교정 목록:")
            for r in correction_results:
                if not r.applied:
                    print(f"[FinalValidator]     씬 {r.scene_id}: {r.reason}")

        return ValidationResult(
            total_scenes=len(srt_scenes),
            scenes_needing_correction=len(scenes_to_correct),
            corrections_made=all_corrections,
            corrected_scenes=corrected_scenes,
            provider_used="gemini",
            rejected_count=total_rejected
        )

    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """
        ⭐ v9.0: 숫자 매칭 가중치 강화 유사도 계산

        숫자가 같으면 유사도 높게 평가 (오타 교정 우선)
        """
        if not text1 or not text2:
            return 0.0

        # 1. 숫자 매칭 (가장 중요!)
        import re
        nums1 = set(re.findall(r'\d+', text1))
        nums2 = set(re.findall(r'\d+', text2))

        if nums1 and nums2:
            num_match = len(nums1 & nums2) / max(len(nums1), len(nums2))
        else:
            num_match = 1.0 if not nums1 and not nums2 else 0

        # 2. 핵심 단어 매칭 (2글자 이상 한글)
        words1 = set(re.findall(r'[가-힣]{2,}', text1))
        words2 = set(re.findall(r'[가-힣]{2,}', text2))

        if words1 and words2:
            word_match = len(words1 & words2) / max(len(words1), len(words2))
        else:
            word_match = 0

        # 3. 시퀀스 유사도
        seq_score = SequenceMatcher(None, text1.lower(), text2.lower()).ratio()

        # ⭐ 숫자 매칭 가중치 50%로 높임!
        combined = num_match * 0.5 + word_match * 0.3 + seq_score * 0.2

        return combined

    def _should_bypass_similarity_check(self, before: str, after: str) -> bool:
        """
        ⭐ v9.0: 음차 변환 + 오타 교정인 경우 유사도 검사 면제

        영어↔한글 변환, 오타 교정은 유사도가 낮을 수밖에 없으므로 면제
        """
        # 1. 패턴 기반 면제
        for korean, english in self.PHONETIC_BYPASS_PATTERNS:
            # 한글 → 영어 변환
            if korean in before and english in after:
                return True
            # 영어 → 한글 변환
            if english in before and korean in after:
                return True
            # 오타 → 교정 (둘 다 한글인 경우)
            if korean in before and english in after:
                return True

        # 2. v9.0: 숫자가 동일하면 면제 (오타 교정일 가능성 높음)
        import re
        nums_before = set(re.findall(r'\d+', before))
        nums_after = set(re.findall(r'\d+', after))

        if nums_before and nums_after and nums_before == nums_after:
            # 숫자가 완전히 동일하면 면제
            return True

        # 3. v9.0: 길이 차이가 적으면 면제 (오타 교정)
        len_diff = abs(len(before) - len(after))
        if len_diff <= 5:
            return True

        return False

    def _extract_sentences(self, script: str) -> List[str]:
        """원문에서 문장 추출"""
        if not script:
            return []

        # 문장 분리
        sentences = re.split(r'[.!?。！？]\s*', script)
        return [s.strip() for s in sentences if s.strip() and len(s.strip()) > 5]

    def _correct_batch(
        self,
        batch: List[Dict],
        original_sentences: List[str]
    ) -> Dict[int, str]:
        """단일 배치 교정 (Gemini)"""

        prompt = self._build_prompt(batch, original_sentences)

        print(f"[FinalValidator]     [GEMINI] Gemini 실행 중...")

        try:
            response = self.gemini_client.generate_content(prompt)
            return self._parse_response(response.text, batch)
        except Exception as e:
            print(f"[FinalValidator]     [ERROR] Gemini 오류: {e}")
            raise

    def _build_prompt(self, batch: List[Dict], original_sentences: List[str]) -> str:
        """
        교정 프롬프트 생성

        v7.0: 내용 변경 금지 강조, 오타/숫자/약자만 수정
        """

        # 씬 텍스트 (씬 ID 명확히)
        scene_lines = []
        for item in batch:
            scene_lines.append(f"[씬 {item['scene_id']}] {item['srt_text']}")

        scenes_text = "\n".join(scene_lines)

        # 원문 일부 (참고용)
        original_text = "\n".join(original_sentences[:80])

        return f"""## 작업: 음성 인식 오류 교정

음성 인식(Whisper)으로 생성된 자막을 원본 스크립트와 비교하여 교정해주세요.

## 매우 중요한 규칙

1. **씬의 내용 자체를 바꾸면 절대 안 됩니다!**
   - 씬 5의 내용을 씬 10의 내용으로 바꾸면 안 됨
   - 각 씬의 원래 의미와 문장 구조를 유지해야 함

2. **수정 가능한 항목 (오타/인식 오류만):**
   - 오타: "청담" -> "첨단", "하면은" -> "하면"
   - 영문 약자: "에이다스" -> "ADAS", "비엠더블유" -> "BMW"
   - 숫자 표기: "삼천억" -> "3천억", "오나노" -> "5나노"
   - 띄어쓰기: "자회사하만" -> "자회사 하만"
   - 맞춤법: "왜냐면요" -> "왜냐하면요"

3. **수정 불가능한 항목:**
   - 문장 순서 변경
   - 문장 추가/삭제
   - 의미 변경
   - 다른 씬의 내용으로 대체

4. **확실하지 않으면 원본 그대로 유지하세요!**

## 원본 스크립트 (참고용)
{original_text}

## 교정할 씬 목록
{scenes_text}

## 출력 형식 (JSON만, 씬 번호 정확히!)

```json
{{
  "corrections": [
    {{"scene_id": 5, "text": "씬 5의 교정된 텍스트"}},
    {{"scene_id": 6, "text": "씬 6의 교정된 텍스트"}}
  ]
}}
```

## 주의사항
- scene_id는 입력에 있는 씬 번호와 정확히 일치해야 합니다
- 오타/숫자/약자만 수정하고, 문장 내용은 그대로 유지하세요
- 교정할 필요 없는 씬은 출력에서 제외해도 됩니다

JSON만 출력하세요:"""

    def _parse_response(self, response_text: str, batch: List[Dict]) -> Dict[int, str]:
        """
        응답 파싱

        v7.0: 씬 ID 검증 추가
        """

        corrections = {}

        # 배치에 있는 씬 ID 목록
        valid_scene_ids = {item['scene_id'] for item in batch}

        try:
            # JSON 추출
            match = re.search(r'```json\s*([\s\S]*?)\s*```', response_text)
            if match:
                text = match.group(1)
            else:
                json_match = re.search(r'\{[\s\S]*\}', response_text)
                if not json_match:
                    return {}
                text = json_match.group()

            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                # 괄호 닫기 시도
                open_brackets = text.count('[') - text.count(']')
                open_braces = text.count('{') - text.count('}')
                text += ']' * max(0, open_brackets)
                text += '}' * max(0, open_braces)
                data = json.loads(text)

            # corrections 배열 파싱
            if "corrections" in data:
                for item in data["corrections"]:
                    scene_id = item.get("scene_id")
                    corrected_text = item.get("text") or item.get("corrected", "")

                    if scene_id is None:
                        continue

                    scene_id = int(scene_id)

                    # v7.0: 씬 ID 검증
                    if scene_id not in valid_scene_ids:
                        print(f"[FinalValidator]     [WARN] 잘못된 씬 ID: {scene_id} (무시)")
                        continue

                    if corrected_text:
                        corrections[scene_id] = corrected_text

        except json.JSONDecodeError as e:
            print(f"[FinalValidator]     [WARN] JSON 파싱 오류: {e}")
        except Exception as e:
            print(f"[FinalValidator]     [WARN] 파싱 오류: {e}")

        return corrections

    def _local_correction(self, scenes: List[Dict]) -> List[Dict]:
        """로컬 교정 (AI 없을 때)"""

        corrections = []

        for item in scenes:
            srt_text = item['srt_text']
            orig_text = item['original_text']
            current_text = item.get('current_text', srt_text)

            if not orig_text:
                continue

            corrected_text = current_text
            for diff in item.get('differences', []):
                if diff.get('type') == 'replace':
                    srt_word = diff.get('srt', '')
                    orig_word = diff.get('original', '')

                    if srt_word and orig_word and srt_word in corrected_text:
                        corrected_text = corrected_text.replace(srt_word, orig_word)

            # v7.0: 유사도 검증
            similarity = self._calculate_similarity(current_text, corrected_text)

            if similarity < self.SIMILARITY_REJECT:
                print(f"[FinalValidator]     [REJECT] 씬 {item['scene_id']}: 로컬 교정 거부 (유사도 {similarity:.0%})")
                continue

            if corrected_text != current_text:
                corrections.append({
                    'scene_id': item['scene_id'],
                    'scene_idx': item['scene_idx'],
                    'original_srt': current_text,
                    'corrected': corrected_text,
                    'similarity': similarity,
                    'reason': 'local_replace'
                })

        return corrections

    def _apply_corrections(
        self,
        scenes: List,
        corrections: List[Dict]
    ) -> List:
        """교정 적용"""

        correction_map = {}
        for corr in corrections:
            sid = corr.get('scene_id')
            if sid is not None:
                correction_map[sid] = corr.get('corrected', '')

        result = []
        for scene in scenes:
            if isinstance(scene, dict):
                scene_copy = dict(scene)
                sid = scene_copy.get('scene_id')
                text_key = 'text'
            else:
                scene_copy = self._copy_scene(scene)
                sid = getattr(scene_copy, 'scene_id', None)
                text_key = None

            if sid in correction_map and correction_map[sid]:
                if text_key:
                    old_text = scene_copy.get('text', '')
                else:
                    old_text = getattr(scene_copy, 'text', '')

                new_text = correction_map[sid]

                if old_text != new_text:
                    print(f"[FinalValidator]     씬 {sid}: {old_text[:30]}... -> {new_text[:30]}...")

                    if text_key:
                        scene_copy['text'] = new_text
                        scene_copy['original_text'] = old_text
                    else:
                        scene_copy.text = new_text
                        if hasattr(scene_copy, 'original_text'):
                            scene_copy.original_text = old_text

            result.append(scene_copy)

        return result

    def _copy_scene(self, scene):
        """씬 객체 복사"""
        from dataclasses import fields, is_dataclass
        import copy

        if is_dataclass(scene):
            return copy.copy(scene)
        else:
            return copy.copy(scene)


# 싱글톤
_validator_instance = None


def get_final_validator(api_key: str = None) -> FinalSRTValidator:
    """FinalSRTValidator 싱글톤"""
    global _validator_instance
    if _validator_instance is None:
        _validator_instance = FinalSRTValidator(api_key)
    return _validator_instance


def validate_srt_final(
    srt_scenes: List,
    original_script: str
) -> Tuple[List, List[Dict]]:
    """
    편의 함수: 최종 SRT 검증

    Args:
        srt_scenes: SRT 씬 리스트
        original_script: 원문 스크립트

    Returns:
        (교정된 씬 리스트, 교정 내역)
    """
    validator = get_final_validator()
    result = validator.validate_and_correct(srt_scenes, original_script)
    return result.corrected_scenes, result.corrections_made
