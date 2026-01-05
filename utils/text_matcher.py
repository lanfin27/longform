# -*- coding: utf-8 -*-
"""
원문-SRT 텍스트 매칭 모듈

기능:
1. 원문을 문장 단위로 분리
2. SRT 텍스트와 유사도 매칭
3. 불일치 부분 식별
"""

import re
from typing import List, Dict, Tuple
from dataclasses import dataclass
from difflib import SequenceMatcher


@dataclass
class MatchResult:
    """매칭 결과"""
    srt_text: str
    original_text: str
    similarity: float
    differences: List[Dict]
    needs_correction: bool


class TextMatcher:
    """원문-SRT 텍스트 매칭기"""

    # 유사도 임계값 (이하면 교정 필요)
    SIMILARITY_THRESHOLD = 0.95

    def __init__(self):
        self.sentence_pattern = re.compile(r'[.!?。！？]\s*')

    def split_sentences(self, text: str) -> List[str]:
        """텍스트를 문장 단위로 분리"""

        # 줄바꿈 정규화
        text = text.replace('\r\n', '\n').replace('\r', '\n')

        # 문장 분리
        sentences = []
        current = ""

        for char in text:
            current += char
            if char in '.!?。！？\n':
                sentence = current.strip()
                if sentence and len(sentence) > 2:
                    sentences.append(sentence)
                current = ""

        if current.strip():
            sentences.append(current.strip())

        return sentences

    def extract_words(self, text: str) -> List[str]:
        """텍스트에서 단어 추출"""

        # 한글, 영어, 숫자만 추출
        words = re.findall(r'[가-힣]+|[a-zA-Z]+|[0-9]+', text)
        return words

    def calculate_similarity(self, text1: str, text2: str) -> float:
        """두 텍스트의 유사도 계산"""

        # 공백 제거 후 비교
        clean1 = re.sub(r'\s+', '', text1)
        clean2 = re.sub(r'\s+', '', text2)

        if not clean1 or not clean2:
            return 0.0

        return SequenceMatcher(None, clean1, clean2).ratio()

    def find_differences(self, srt_text: str, original_text: str) -> List[Dict]:
        """두 텍스트의 차이점 찾기"""

        differences = []

        # 단어 단위 비교
        srt_words = self.extract_words(srt_text)
        orig_words = self.extract_words(original_text)

        # diff 계산
        matcher = SequenceMatcher(None, srt_words, orig_words)

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'replace':
                differences.append({
                    'type': 'replace',
                    'srt': ' '.join(srt_words[i1:i2]),
                    'original': ' '.join(orig_words[j1:j2]),
                    'position': i1
                })
            elif tag == 'delete':
                differences.append({
                    'type': 'extra_in_srt',
                    'srt': ' '.join(srt_words[i1:i2]),
                    'position': i1
                })
            elif tag == 'insert':
                differences.append({
                    'type': 'missing_in_srt',
                    'original': ' '.join(orig_words[j1:j2]),
                    'position': i1
                })

        return differences

    def match_srt_to_original(
        self,
        srt_scenes: List,
        original_script: str
    ) -> List[MatchResult]:
        """
        SRT 씬들을 원문과 매칭

        Args:
            srt_scenes: SRT 씬 리스트 (dict 또는 객체)
            original_script: 원문 스크립트

        Returns:
            각 씬의 매칭 결과 리스트
        """

        # 원문 문장 분리
        original_sentences = self.split_sentences(original_script)

        if not original_sentences:
            return []

        results = []
        orig_idx = 0

        for scene in srt_scenes:
            # dict 또는 객체에서 text 추출
            if isinstance(scene, dict):
                srt_text = scene.get('text', '')
            else:
                srt_text = getattr(scene, 'text', '')

            if not srt_text:
                results.append(MatchResult(
                    srt_text="",
                    original_text="",
                    similarity=1.0,
                    differences=[],
                    needs_correction=False
                ))
                continue

            # 가장 유사한 원문 문장 찾기
            best_match = None
            best_similarity = 0
            best_orig_idx = orig_idx

            # 주변 문장들과 비교 (앞뒤 5문장)
            search_start = max(0, orig_idx - 2)
            search_end = min(len(original_sentences), orig_idx + 5)

            for i in range(search_start, search_end):
                similarity = self.calculate_similarity(srt_text, original_sentences[i])
                if similarity > best_similarity:
                    best_similarity = similarity
                    best_match = original_sentences[i]
                    best_orig_idx = i

            # 여러 원문 문장 결합 시도
            if best_similarity < 0.7 and orig_idx < len(original_sentences) - 1:
                combined = ' '.join(original_sentences[orig_idx:orig_idx+2])
                combined_sim = self.calculate_similarity(srt_text, combined)
                if combined_sim > best_similarity:
                    best_similarity = combined_sim
                    best_match = combined

            # 3문장 결합 시도
            if best_similarity < 0.6 and orig_idx < len(original_sentences) - 2:
                combined = ' '.join(original_sentences[orig_idx:orig_idx+3])
                combined_sim = self.calculate_similarity(srt_text, combined)
                if combined_sim > best_similarity:
                    best_similarity = combined_sim
                    best_match = combined

            # 차이점 분석
            differences = []
            needs_correction = False

            if best_match and best_similarity < self.SIMILARITY_THRESHOLD:
                differences = self.find_differences(srt_text, best_match)
                needs_correction = len(differences) > 0

            results.append(MatchResult(
                srt_text=srt_text,
                original_text=best_match or "",
                similarity=best_similarity,
                differences=differences,
                needs_correction=needs_correction
            ))

            # 인덱스 업데이트
            if best_orig_idx >= orig_idx:
                orig_idx = best_orig_idx + 1

        return results

    def get_correction_candidates(
        self,
        match_results: List[MatchResult]
    ) -> List[Dict]:
        """
        교정 후보 추출

        Args:
            match_results: 매칭 결과 리스트

        Returns:
            교정이 필요한 씬 정보 리스트
        """

        candidates = []

        for i, result in enumerate(match_results):
            if result.needs_correction:
                candidates.append({
                    'scene_idx': i,
                    'srt_text': result.srt_text,
                    'original_text': result.original_text,
                    'similarity': result.similarity,
                    'differences': result.differences
                })

        return candidates


# 싱글톤
_matcher_instance = None


def get_text_matcher() -> TextMatcher:
    """TextMatcher 싱글톤"""
    global _matcher_instance
    if _matcher_instance is None:
        _matcher_instance = TextMatcher()
    return _matcher_instance
