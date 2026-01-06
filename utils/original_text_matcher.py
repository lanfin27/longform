# -*- coding: utf-8 -*-
"""
OriginalTextMatcher - 원문 기반 텍스트 교정 (v1.0)

핵심 원칙:
1. 타임스탬프는 절대 변경하지 않음!
2. 텍스트만 원문과 일치시킴
3. 순차적 매칭으로 정확도 향상

기능:
- 확장된 오타 패턴 (50개+)
- 영어 ↔ 한글 음차 변환
- 순차적 원문 문장 매칭
- 핵심 단어(숫자, 고유명사) 기반 매칭
"""

import re
from typing import List, Dict, Tuple, Optional
from difflib import SequenceMatcher


class OriginalTextMatcher:
    """
    원문 스크립트와 SRT 씬을 매칭하여 텍스트 교정

    타임스탬프는 절대 변경하지 않음!
    """

    # ═══════════════════════════════════════════════════════════════════
    # 음차 변환 사전 (영어 ↔ 한글 발음)
    # ═══════════════════════════════════════════════════════════════════

    PHONETIC_MAP = {
        # 자동차/기술 관련
        'ADAS': ['에이디에이에스', '에이다스', '아다스', 'ADAS'],
        'Advanced': ['어드벤스드', '어드밴스드', '어밴스드'],
        'Driver': ['드라이버'],
        'Assistance': ['어시스턴스', '어시스턴트', '어시스탄스'],
        'System': ['시스템'],
        'Ready Care': ['레디케어', '레디 케어', '레디케아'],
        'BMW': ['비엠더블유', '비엠떠블유', 'BMW'],
        'ZF': ['제트에프', '지에프', 'DF', 'ZF'],
        'HBM': ['에이치비엠', 'HBIT', 'HBM'],
        'OLED': ['오엘이디', 'OLED'],
        'LED': ['엘이디', 'LED'],
        'AI': ['에이아이', 'AI'],
        'EV': ['이브이', 'EV'],
        'SUV': ['에스유브이', 'SUV'],
        'CEO': ['시이오', 'CEO'],
        'CES': ['씨이에스', 'CES'],

        # 회사명
        'Samsung': ['삼성'],
        'Hyundai': ['현대'],
        'LG': ['엘지', 'LG'],
        'SK': ['에스케이', 'SK'],
        'Harman': ['하만'],
        'Bosch': ['보쉬', '보쉬'],
        'Continental': ['컨티넨탈'],
        'Aptiv': ['앱티브'],
        'Mobileye': ['모빌아이'],
        'Waymo': ['웨이모'],
        'Tesla': ['테슬라'],

        # 기타 기술 용어
        'Cockpit': ['콕핏', '콕피트', '콕피시'],
        'Infotainment': ['인포테인먼트'],
        'Display': ['디스플레이'],
        'Sensor': ['센서'],
        'Radar': ['레이더'],
        'Lidar': ['라이다', '라이더'],
        'Camera': ['카메라'],
    }

    # ═══════════════════════════════════════════════════════════════════
    # 확장된 Whisper 오타 패턴 (50개+)
    # ═══════════════════════════════════════════════════════════════════

    TYPO_PATTERNS = {
        # ─────────────────────────────────────────────────────────────
        # 조사/어미 오류
        # ─────────────────────────────────────────────────────────────
        '하면은': '하면',
        '그러면은': '그러면',
        '이러면은': '이러면',
        '저러면은': '저러면',
        '있으면은': '있으면',
        '없으면은': '없으면',
        '되면은': '되면',
        '라면은': '라면',

        '분야안에서': '분야에서',
        '분야안에서서': '분야에서',
        '입장안에서': '입장에서',
        '시장안에서': '시장에서',
        '업계안에서': '업계에서',
        '회사안에서': '회사에서',
        '산업안에서': '산업에서',

        '와와중에': '와중에',
        '중중에': '중에',

        # ─────────────────────────────────────────────────────────────
        # 동사 어미 오류
        # ─────────────────────────────────────────────────────────────
        '해게요': '해볼게요',
        '나열해게요': '나열해볼게요',
        '정리해게요': '정리해볼게요',
        '시작해게요': '시작해볼게요',
        '종합해게요': '종합해볼게요',
        '살펴보게요': '살펴볼게요',
        '알아보게요': '알아볼게요',
        '설명해게요': '설명해볼게요',
        '비교해게요': '비교해볼게요',
        '분석해게요': '분석해볼게요',

        '들어갈가': '들어가',
        '만들어갈가': '만들어가',
        '들어갈가는': '들어가는',
        '만들어갈요': '만들어요',
        '만들어갈': '만들어',
        '이어갈가는': '이어가는',
        '나아갈가는': '나아가는',

        # ─────────────────────────────────────────────────────────────
        # 외래어/숫자 오류
        # ─────────────────────────────────────────────────────────────
        '류로': '유로',
        '유럽류로': '유럽 유로',

        '본 년': '기본',
        '본년': '기본',
        '지금년': '지금',
        '금년부터': '올해부터',

        # 숫자 중복 오류
        '조조원': '조원',
        '조 조원': '조원',
        '2조 조원': '2조원',
        '3조 조원': '3조원',
        '5조 조원': '5조원',
        '9조 조조원': '9조원',
        '10조 조원': '10조원',
        '14조 조원': '14조원',
        '20조 조원': '20조원',

        '억 천억': '천억',
        '4억 천억': '4천억',
        '3억 천억': '3천억',
        '5억 천억': '5천억',

        '억억원': '억원',
        '억 억원': '억원',

        # ─────────────────────────────────────────────────────────────
        # 반복/중복 오류
        # ─────────────────────────────────────────────────────────────
        '밟아보여주는': '밟아주는',
        '유지해주는 보여주는': '유지해주는',
        '보여주는 보여주는': '보여주는',
        '해주는 해주는': '해주는',

        '뭐라고고': '뭐라고',
        '뭐냐고고': '뭐냐고',
        '어떻냐고고': '어떻냐고',

        '설명해설명해': '설명해',
        '드릴게요 설명해드릴게요': '드릴게요',
        '말씀말씀': '말씀',
        '하겠습니다 하겠습니다': '하겠습니다',

        # ─────────────────────────────────────────────────────────────
        # 고유명사/전문용어 오류
        # ─────────────────────────────────────────────────────────────
        '전 회사': '가전회사',
        '전회사': '가전회사',
        '자외사': '자회사',
        '자외 사': '자회사',

        '노이의': '노이에',
        '노이의 클라세': '노이에 클라세',
        '콕피시': '콕핏',
        '콕핏시': '콕핏',

        # 영어 발음 → 영어
        '어드벤스드 드라이버, 어시스턴스 시스템': 'Advanced Driver Assistance System',
        '어드벤스드 드라이버 어시스턴스 시스템': 'Advanced Driver Assistance System',
        '에이디에이에스': 'ADAS',

        # ─────────────────────────────────────────────────────────────
        # 기타 오류
        # ─────────────────────────────────────────────────────────────
        '첫 번재': '첫 번째',
        '두 번재': '두 번째',
        '세 번재': '세 번째',
        '네 번재': '네 번째',

        '됬습니다': '됐습니다',
        '됬어요': '됐어요',
        '됬죠': '됐죠',
        '됬는데': '됐는데',

        '왜냐면요': '왜냐하면요',
        '왜냐면': '왜냐하면',
    }

    def __init__(self):
        print(f"[OriginalTextMatcher] v1.0 초기화")
        print(f"[OriginalTextMatcher]   오타 패턴: {len(self.TYPO_PATTERNS)}개")
        print(f"[OriginalTextMatcher]   음차 변환: {len(self.PHONETIC_MAP)}개")

    def match_and_correct(
        self,
        scenes: List[Dict],
        original_script: str
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        SRT 씬의 텍스트를 원문과 매칭하여 교정

        타임스탬프는 절대 변경하지 않음!

        Args:
            scenes: SRT 씬 리스트 (타임스탬프 + 텍스트)
            original_script: 원문 스크립트

        Returns:
            (교정된 씬 리스트, 교정 내역 리스트)
        """

        if not scenes or not original_script:
            return scenes, []

        print(f"[OriginalTextMatcher] 원문 매칭 교정 시작")
        print(f"[OriginalTextMatcher]   씬: {len(scenes)}개")
        print(f"[OriginalTextMatcher]   원문: {len(original_script)}자")

        # 1. 원문을 문장 단위로 분리
        original_sentences = self._split_sentences(original_script)
        print(f"[OriginalTextMatcher]   원문 문장: {len(original_sentences)}개")

        # 2. 각 씬에 대해 원문 매칭 및 교정
        corrected_scenes = []
        corrections = []

        # 순차적 매칭을 위한 인덱스
        last_matched_idx = -1

        for scene in scenes:
            # scene이 dict인 경우와 객체인 경우 모두 처리
            if isinstance(scene, dict):
                original_text = scene.get('text', '')
                scene_id = scene.get('scene_id', 0)
            else:
                original_text = getattr(scene, 'text', '')
                scene_id = getattr(scene, 'scene_id', 0)

            # 빈 텍스트 스킵
            if not original_text or not original_text.strip():
                corrected_scenes.append(scene)
                continue

            # Step 1: 단순 오타 패턴 먼저 적용
            text_after_typo = self._apply_typo_patterns(original_text)

            # Step 2: 원문에서 가장 유사한 문장 찾기 (순차적 매칭)
            best_match, best_idx, confidence = self._find_best_match(
                text_after_typo,
                original_sentences,
                last_matched_idx
            )

            # Step 3: 매칭된 원문으로 교정
            final_text = text_after_typo
            matched_original = False

            if best_match and confidence >= 0.30:  # 30% 이상이면 매칭
                # 원문 매칭 성공 - 원문 텍스트 사용
                final_text = best_match
                last_matched_idx = best_idx
                matched_original = True

            # 실제로 변경되었는지 확인
            if final_text != original_text:
                corrections.append({
                    'scene_id': scene_id,
                    'before': original_text,
                    'after': final_text,
                    'confidence': confidence if matched_original else 0,
                    'matched_idx': best_idx if matched_original else -1,
                    'typo_only': not matched_original
                })

                # 텍스트만 교체! 타임스탬프는 유지!
                if isinstance(scene, dict):
                    scene['text'] = final_text
                else:
                    scene.text = final_text

            corrected_scenes.append(scene)

        # 결과 출력
        print(f"[OriginalTextMatcher] 교정 완료")
        print(f"[OriginalTextMatcher]   총 교정: {len(corrections)}개")
        original_match_count = sum(1 for c in corrections if c.get('confidence', 0) > 0)
        typo_only_count = sum(1 for c in corrections if c.get('typo_only'))
        print(f"[OriginalTextMatcher]   원문 매칭: {original_match_count}개")
        print(f"[OriginalTextMatcher]   오타만: {typo_only_count}개")

        return corrected_scenes, corrections

    def _split_sentences(self, text: str) -> List[str]:
        """원문을 문장 단위로 분리"""

        # 줄바꿈으로 먼저 분리
        lines = text.strip().split('\n')

        sentences = []
        for line in lines:
            line = line.strip()
            if not line:
                continue

            # 마침표, 물음표, 느낌표로 분리
            parts = re.split(r'([.?!])', line)

            current = ''
            for part in parts:
                current += part
                if part in '.?!':
                    if current.strip():
                        sentences.append(current.strip())
                    current = ''

            # 남은 부분
            if current.strip():
                sentences.append(current.strip())

        return sentences

    def _apply_typo_patterns(self, text: str) -> str:
        """단순 오타 패턴 적용"""

        result = text
        for typo, fix in self.TYPO_PATTERNS.items():
            if typo in result:
                result = result.replace(typo, fix)

        return result

    def _find_best_match(
        self,
        whisper_text: str,
        original_sentences: List[str],
        last_matched_idx: int
    ) -> Tuple[Optional[str], int, float]:
        """
        Whisper 텍스트와 가장 유사한 원문 문장 찾기

        순차적 매칭: last_matched_idx 이후의 문장에서 우선 검색
        """

        if not original_sentences:
            return None, -1, 0

        best_match = None
        best_idx = -1
        best_score = 0

        # 검색 범위: last_matched_idx 이후 우선, 그 다음 전체
        # 순차 검색 우선 (±5 범위)
        priority_range = []
        for offset in range(6):
            idx = last_matched_idx + 1 + offset
            if 0 <= idx < len(original_sentences):
                priority_range.append(idx)

        # 나머지 범위
        other_range = [i for i in range(len(original_sentences)) if i not in priority_range]

        search_range = priority_range + other_range

        for idx in search_range:
            original = original_sentences[idx]

            # 유사도 계산 (여러 방법 조합)
            score = self._calculate_match_score(whisper_text, original)

            # 순차적 매칭 보너스
            if idx == last_matched_idx + 1:
                score += 0.15  # 바로 다음 문장이면 15% 보너스
            elif idx in priority_range:
                score += 0.05  # 근처 문장이면 5% 보너스

            if score > best_score:
                best_score = score
                best_match = original
                best_idx = idx

        return best_match, best_idx, best_score

    def _calculate_match_score(self, whisper_text: str, original_text: str) -> float:
        """
        매칭 점수 계산 (0~1)

        여러 방법 조합:
        1. 단어 기반 유사도
        2. 핵심 단어 매칭
        3. 음차 변환 고려
        """

        # 정규화
        w_text = whisper_text.lower().strip()
        o_text = original_text.lower().strip()

        # 1. 기본 시퀀스 유사도
        seq_score = SequenceMatcher(None, w_text, o_text).ratio()

        # 2. 단어 기반 유사도
        w_words = set(re.findall(r'\w+', w_text))
        o_words = set(re.findall(r'\w+', o_text))

        if w_words and o_words:
            common = len(w_words & o_words)
            word_score = common / max(len(w_words), len(o_words))
        else:
            word_score = 0

        # 3. 핵심 단어 매칭 (숫자, 고유명사)
        w_numbers = set(re.findall(r'\d+', whisper_text))
        o_numbers = set(re.findall(r'\d+', original_text))

        if w_numbers and o_numbers:
            number_match = len(w_numbers & o_numbers) / max(len(w_numbers), len(o_numbers))
        else:
            number_match = 1.0 if not w_numbers and not o_numbers else 0

        # 4. 음차 변환 점수
        phonetic_score = self._calculate_phonetic_score(whisper_text, original_text)

        # 가중 평균
        final_score = (
            seq_score * 0.30 +
            word_score * 0.30 +
            number_match * 0.25 +
            phonetic_score * 0.15
        )

        return final_score

    def _calculate_phonetic_score(self, whisper_text: str, original_text: str) -> float:
        """음차 변환 점수 계산"""

        score = 0
        total_checks = 0

        for english, korean_variants in self.PHONETIC_MAP.items():
            english_lower = english.lower()

            # 원문에 영어가 있고, Whisper에 한글 음차가 있는 경우
            if english_lower in original_text.lower():
                total_checks += 1
                for korean in korean_variants:
                    if korean.lower() in whisper_text.lower():
                        score += 1
                        break

            # 반대: Whisper에 영어가 있고, 원문에 한글이 있는 경우
            for korean in korean_variants:
                if korean.lower() in original_text.lower():
                    total_checks += 1
                    if english_lower in whisper_text.lower():
                        score += 1
                    break

        return score / max(total_checks, 1) if total_checks > 0 else 0.5


# ═══════════════════════════════════════════════════════════════════
# 팩토리 함수
# ═══════════════════════════════════════════════════════════════════

_matcher_instance: Optional[OriginalTextMatcher] = None


def get_original_text_matcher() -> OriginalTextMatcher:
    """OriginalTextMatcher 싱글톤"""
    global _matcher_instance
    if _matcher_instance is None:
        _matcher_instance = OriginalTextMatcher()
    return _matcher_instance


def create_original_text_matcher() -> OriginalTextMatcher:
    """OriginalTextMatcher 인스턴스 생성 (새 인스턴스)"""
    return OriginalTextMatcher()
