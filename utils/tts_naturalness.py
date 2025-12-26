# -*- coding: utf-8 -*-
"""
TTS 자연스러움 최적화기

핵심 기능:
1. Temperature 높여서 다양성 확보 (0.7 → 0.85)
2. Repetition Penalty 낮춰서 자연스러운 흐름 (1.4 → 1.2)
3. 문장별 미세 변화로 단조로움 방지

사용:
    params = get_natural_params("안녕하세요!", scene_index=0, total_scenes=5)
    # params = {
    #     "exaggeration": 0.70,
    #     "cfg_weight": 0.35,
    #     "temperature": 0.87,
    #     "repetition_penalty": 1.2
    # }
"""

import re
import math
from typing import Dict, List
from dataclasses import dataclass


@dataclass
class NaturalParams:
    """자연스러운 TTS 파라미터"""
    exaggeration: float
    cfg_weight: float
    temperature: float
    repetition_penalty: float


class TTSNaturalnessOptimizer:
    """
    TTS 자연스러움 최적화기

    핵심 원리:
    1. Temperature 높여서 다양성 확보
    2. Repetition Penalty 낮춰서 자연스러운 흐름
    3. 문장별 미세 변화로 단조로움 방지
    """

    # 기본 파라미터 (자연스러움 최적화)
    BASE_PARAMS = {
        "exaggeration": 0.65,      # 0.7 → 0.65 (약간 낮춤)
        "cfg_weight": 0.35,        # 0.4 → 0.35 (자유로움)
        "temperature": 0.85,       # 0.7 → 0.85 (핵심!)
        "repetition_penalty": 1.2,  # 1.4 → 1.2 (핵심!)
    }

    # 문장 유형별 조정
    SENTENCE_TYPE_ADJUSTMENTS = {
        "question": {  # 의문문
            "exaggeration": +0.1,
            "temperature": +0.05,
        },
        "exclamation": {  # 감탄문
            "exaggeration": +0.15,
            "temperature": +0.05,
        },
        "statement": {  # 평서문
            "exaggeration": 0,
            "temperature": 0,
        },
        "emphasis": {  # 강조 (숫자, 고유명사 포함)
            "exaggeration": +0.05,
            "cfg_weight": +0.05,
        },
    }

    # 문장 길이별 조정
    LENGTH_ADJUSTMENTS = {
        "short": {  # < 30자
            "temperature": +0.05,
            "exaggeration": +0.05,
        },
        "medium": {  # 30~80자
            "temperature": 0,
            "exaggeration": 0,
        },
        "long": {  # > 80자
            "temperature": -0.05,
            "repetition_penalty": +0.1,
        },
    }

    def __init__(self, variation_strength: float = 0.5):
        """
        Args:
            variation_strength: 문장별 변화 강도 (0~1)
                0 = 모든 문장 동일 파라미터
                0.5 = 적당한 변화 (권장)
                1 = 최대 변화
        """
        self.variation_strength = variation_strength

        print(f"[NaturalnessOptimizer] 초기화")
        print(f"  기본 파라미터:")
        print(f"    temperature: {self.BASE_PARAMS['temperature']} (다양성 증가)")
        print(f"    repetition_penalty: {self.BASE_PARAMS['repetition_penalty']} (자연스러움)")
        print(f"  변화 강도: {variation_strength}")

    def get_params_for_sentence(
        self,
        text: str,
        sentence_index: int = 0,
        total_sentences: int = 1
    ) -> Dict[str, float]:
        """
        문장에 최적화된 파라미터 반환

        Args:
            text: 문장 텍스트
            sentence_index: 문장 순서 (0부터)
            total_sentences: 전체 문장 수

        Returns:
            최적화된 파라미터 dict
        """

        # 기본 파라미터 복사
        params = dict(self.BASE_PARAMS)

        # 1. 문장 유형 분석 및 조정
        sentence_type = self._analyze_sentence_type(text)
        type_adj = self.SENTENCE_TYPE_ADJUSTMENTS.get(sentence_type, {})

        for key, adj in type_adj.items():
            if key in params:
                params[key] += adj * self.variation_strength

        # 2. 문장 길이 분석 및 조정
        length_type = self._analyze_length(text)
        length_adj = self.LENGTH_ADJUSTMENTS.get(length_type, {})

        for key, adj in length_adj.items():
            if key in params:
                params[key] += adj * self.variation_strength

        # 3. 문장 순서에 따른 미세 변화 (단조로움 방지)
        position_variation = self._get_position_variation(
            sentence_index, total_sentences
        )

        params["temperature"] += position_variation * 0.03
        params["exaggeration"] += position_variation * 0.02

        # 4. 범위 제한
        params = self._clamp_params(params)

        return params

    def get_params_for_scene(
        self,
        scene_text: str,
        scene_index: int = 0,
        total_scenes: int = 1
    ) -> Dict[str, float]:
        """
        씬(여러 문장)에 최적화된 파라미터 반환
        """

        # 씬의 평균적 특성 분석
        sentences = self._split_sentences(scene_text)

        if not sentences:
            return dict(self.BASE_PARAMS)

        # 첫 문장 기준으로 파라미터 결정 (대표성)
        base_params = self.get_params_for_sentence(
            sentences[0],
            scene_index,
            total_scenes
        )

        # 씬 전체 특성 반영
        has_question = any("?" in s for s in sentences)
        has_exclamation = any("!" in s for s in sentences)

        if has_question and has_exclamation:
            # 다양한 문장 유형 → 더 표현적으로
            base_params["exaggeration"] = min(0.8, base_params["exaggeration"] + 0.05)
            base_params["temperature"] = min(0.95, base_params["temperature"] + 0.03)

        return base_params

    def _analyze_sentence_type(self, text: str) -> str:
        """문장 유형 분석"""

        text = text.strip()

        if text.endswith("?"):
            return "question"
        elif text.endswith("!"):
            return "exclamation"
        elif re.search(r'\d{4}년|\d+%|\d+억|\d+만', text):
            return "emphasis"
        else:
            return "statement"

    def _analyze_length(self, text: str) -> str:
        """문장 길이 분석"""

        # 공백 제외 글자 수
        char_count = len(text.replace(" ", "").replace("\n", ""))

        if char_count < 30:
            return "short"
        elif char_count > 80:
            return "long"
        else:
            return "medium"

    def _get_position_variation(
        self,
        index: int,
        total: int
    ) -> float:
        """
        위치 기반 미세 변화

        사인파 형태로 자연스러운 변화
        """

        if total <= 1:
            return 0

        # 0~1 정규화
        position = index / (total - 1)

        # 사인파 (0 → 1 → 0 → -1 → 0)
        variation = math.sin(position * math.pi * 2)

        return variation * self.variation_strength

    def _split_sentences(self, text: str) -> List[str]:
        """문장 분리"""

        # 간단한 문장 분리
        sentences = re.split(r'[.!?]\s*', text)
        return [s.strip() for s in sentences if s.strip()]

    def _clamp_params(self, params: Dict[str, float]) -> Dict[str, float]:
        """파라미터 범위 제한"""

        limits = {
            "exaggeration": (0.3, 0.85),
            "cfg_weight": (0.2, 0.6),
            "temperature": (0.7, 0.98),
            "repetition_penalty": (1.1, 1.5),
        }

        for key, (min_val, max_val) in limits.items():
            if key in params:
                params[key] = max(min_val, min(max_val, params[key]))
                params[key] = round(params[key], 2)

        return params


# ============================================================
# 싱글톤 및 간편 함수
# ============================================================

_naturalness_optimizer = None

def get_naturalness_optimizer(variation: float = 0.5) -> TTSNaturalnessOptimizer:
    """자연스러움 최적화기 싱글톤"""
    global _naturalness_optimizer
    if _naturalness_optimizer is None:
        _naturalness_optimizer = TTSNaturalnessOptimizer(variation)
    return _naturalness_optimizer


def get_natural_params(
    text: str,
    scene_index: int = 0,
    total_scenes: int = 1
) -> Dict[str, float]:
    """
    자연스러운 TTS 파라미터 반환 (간편 함수)

    사용 예:
        params = get_natural_params("안녕하세요!", 0, 7)
        # params = {
        #     "exaggeration": 0.70,
        #     "cfg_weight": 0.35,
        #     "temperature": 0.87,
        #     "repetition_penalty": 1.2
        # }
    """
    return get_naturalness_optimizer().get_params_for_scene(
        text, scene_index, total_scenes
    )


def get_base_natural_params() -> Dict[str, float]:
    """기본 자연스러움 파라미터 반환"""
    return dict(TTSNaturalnessOptimizer.BASE_PARAMS)
