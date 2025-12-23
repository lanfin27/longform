# -*- coding: utf-8 -*-
"""
AI 시각 자료 추천기

씬 내용을 분석하여 적합한 시각 자료 타입 추천

추천 로직:
- 데이터/통계 키워드 → 인포그래픽
- 감정/스토리 키워드 → AI 이미지
- 캐릭터 언급 → 캐릭터 합성
"""

import re
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass

from utils.models.infographic import VisualType, SceneVisualSelection


@dataclass
class RecommendationResult:
    """추천 결과"""
    visual_type: VisualType
    score: float  # 0~1
    reason: str
    keywords_found: List[str]


class AIVisualRecommender:
    """AI 시각 자료 추천기"""

    # 인포그래픽 관련 키워드
    INFOGRAPHIC_KEYWORDS = {
        # 데이터/통계
        "통계", "데이터", "수치", "퍼센트", "%", "비율", "증가", "감소",
        "성장", "하락", "추이", "변화", "비교", "분석", "조사", "결과",

        # 차트/그래프
        "차트", "그래프", "도표", "표", "다이어그램", "플로우", "프로세스",

        # 숫자 관련
        "만", "억", "조", "배", "달러", "원", "유로", "엔",

        # 비교/순위
        "순위", "랭킹", "top", "best", "worst", "최고", "최저",
        "1위", "2위", "3위", "vs", "대비",

        # 시간 흐름
        "연도별", "월별", "분기별", "년간", "기간",

        # 구조/관계
        "구조", "체계", "관계", "연결", "네트워크", "조직도"
    }

    # AI 이미지 관련 키워드
    AI_IMAGE_KEYWORDS = {
        # 감정/분위기
        "감동", "눈물", "웃음", "기쁨", "슬픔", "분노", "공포", "희망",
        "사랑", "그리움", "외로움", "행복", "불안", "긴장",

        # 장면/상황
        "장면", "순간", "모습", "표정", "눈빛", "미소",

        # 자연/풍경
        "하늘", "바다", "산", "숲", "강", "호수", "일출", "일몰",
        "별", "달", "태양", "구름", "비", "눈", "바람",

        # 추상적 개념
        "꿈", "상상", "환상", "비전", "미래", "과거", "추억",

        # 액션/동작
        "달리다", "걷다", "뛰다", "날다", "춤추다", "싸우다",

        # 장소
        "도시", "마을", "집", "학교", "사무실", "공원", "거리"
    }

    # 캐릭터 합성 관련 키워드
    CHARACTER_KEYWORDS = {
        "캐릭터", "인물", "주인공", "등장인물", "화자", "나레이터",
        "그", "그녀", "그들", "우리", "나", "저",
        "말했다", "생각했다", "느꼈다", "보았다"
    }

    def __init__(
        self,
        infographic_weight: float = 1.0,
        ai_image_weight: float = 1.0,
        character_weight: float = 0.8
    ):
        """
        Args:
            infographic_weight: 인포그래픽 가중치
            ai_image_weight: AI 이미지 가중치
            character_weight: 캐릭터 합성 가중치
        """
        self.weights = {
            VisualType.INFOGRAPHIC: infographic_weight,
            VisualType.AI_IMAGE: ai_image_weight,
            VisualType.COMPOSITE: character_weight
        }

    def recommend(
        self,
        script_text: str,
        scene_title: str = "",
        has_infographic: bool = True,
        has_character: bool = False
    ) -> RecommendationResult:
        """
        시각 자료 추천

        Args:
            script_text: 씬 스크립트
            scene_title: 씬 제목
            has_infographic: 인포그래픽 사용 가능 여부
            has_character: 캐릭터 사용 가능 여부

        Returns:
            RecommendationResult
        """
        text = f"{scene_title} {script_text}".lower()

        # 각 타입별 점수 계산
        scores = {}
        keywords_found = {}

        # 인포그래픽 점수
        if has_infographic:
            info_score, info_keywords = self._calculate_score(
                text, self.INFOGRAPHIC_KEYWORDS
            )
            # 숫자 패턴 보너스
            number_bonus = self._count_numbers(text) * 0.05
            scores[VisualType.INFOGRAPHIC] = (info_score + number_bonus) * self.weights[VisualType.INFOGRAPHIC]
            keywords_found[VisualType.INFOGRAPHIC] = info_keywords
        else:
            scores[VisualType.INFOGRAPHIC] = 0
            keywords_found[VisualType.INFOGRAPHIC] = []

        # AI 이미지 점수
        ai_score, ai_keywords = self._calculate_score(
            text, self.AI_IMAGE_KEYWORDS
        )
        scores[VisualType.AI_IMAGE] = ai_score * self.weights[VisualType.AI_IMAGE]
        keywords_found[VisualType.AI_IMAGE] = ai_keywords

        # 캐릭터 합성 점수
        if has_character:
            char_score, char_keywords = self._calculate_score(
                text, self.CHARACTER_KEYWORDS
            )
            scores[VisualType.COMPOSITE] = char_score * self.weights[VisualType.COMPOSITE]
            keywords_found[VisualType.COMPOSITE] = char_keywords
        else:
            scores[VisualType.COMPOSITE] = 0
            keywords_found[VisualType.COMPOSITE] = []

        # 최고 점수 타입 선택
        best_type = max(scores, key=scores.get)
        best_score = scores[best_type]

        # 점수가 매우 낮으면 기본값 (AI 이미지)
        if best_score < 0.1:
            best_type = VisualType.AI_IMAGE
            best_score = 0.5

        # 추천 이유 생성
        reason = self._generate_reason(best_type, keywords_found[best_type], best_score)

        return RecommendationResult(
            visual_type=best_type,
            score=min(best_score, 1.0),
            reason=reason,
            keywords_found=keywords_found[best_type]
        )

    def _calculate_score(
        self,
        text: str,
        keywords: set
    ) -> Tuple[float, List[str]]:
        """키워드 매칭 점수 계산"""
        found = []

        for keyword in keywords:
            if keyword.lower() in text:
                found.append(keyword)

        if not found:
            return 0.0, []

        # 기본 점수: 키워드 수 기반
        base_score = min(len(found) * 0.15, 0.9)

        # 다양성 보너스
        if len(found) >= 3:
            base_score += 0.1

        return base_score, found

    def _count_numbers(self, text: str) -> int:
        """텍스트 내 숫자 패턴 개수"""
        patterns = [
            r'\d+%',           # 퍼센트
            r'\d+,\d{3}',      # 천 단위 쉼표
            r'\d+\s*[만억조]',  # 큰 숫자
            r'\$\d+',          # 달러
            r'\d+위'           # 순위
        ]

        count = 0
        for pattern in patterns:
            count += len(re.findall(pattern, text))

        return count

    def _generate_reason(
        self,
        visual_type: VisualType,
        keywords: List[str],
        score: float
    ) -> str:
        """추천 이유 생성"""
        if not keywords:
            if visual_type == VisualType.AI_IMAGE:
                return "일반적인 스토리텔링 씬으로 AI 이미지 추천"
            elif visual_type == VisualType.INFOGRAPHIC:
                return "데이터 시각화에 적합"
            else:
                return "캐릭터 중심 씬"

        keywords_str = ", ".join(keywords[:5])

        if visual_type == VisualType.INFOGRAPHIC:
            return f"데이터/통계 관련 키워드 감지 ({keywords_str})"
        elif visual_type == VisualType.AI_IMAGE:
            return f"감정/장면 표현에 적합 ({keywords_str})"
        else:
            return f"캐릭터 등장 감지 ({keywords_str})"

    def recommend_batch(
        self,
        scenes: List[Dict],
        has_infographic: bool = True,
        has_character: bool = False
    ) -> Dict[int, RecommendationResult]:
        """
        여러 씬 일괄 추천

        Args:
            scenes: 씬 데이터 목록
            has_infographic: 인포그래픽 사용 가능 여부
            has_character: 캐릭터 사용 가능 여부

        Returns:
            씬 번호 -> 추천 결과 딕셔너리
        """
        results = {}

        for i, scene in enumerate(scenes):
            scene_id = scene.get("scene_id", i + 1)
            script_text = scene.get("script_text", "")
            scene_title = scene.get("title", "")

            result = self.recommend(
                script_text=script_text,
                scene_title=scene_title,
                has_infographic=has_infographic,
                has_character=has_character
            )

            results[scene_id] = result

        return results

    def get_summary(
        self,
        recommendations: Dict[int, RecommendationResult]
    ) -> Dict[str, int]:
        """추천 결과 요약"""
        summary = {t.value: 0 for t in VisualType}

        for result in recommendations.values():
            summary[result.visual_type.value] += 1

        return summary


def get_ai_recommender(**kwargs) -> AIVisualRecommender:
    """추천기 인스턴스 생성"""
    return AIVisualRecommender(**kwargs)


def recommend_visual_type(
    script_text: str,
    scene_title: str = "",
    has_infographic: bool = True,
    has_character: bool = False
) -> RecommendationResult:
    """
    시각 자료 추천 (헬퍼 함수)

    Args:
        script_text: 씬 스크립트
        scene_title: 씬 제목
        has_infographic: 인포그래픽 사용 가능 여부
        has_character: 캐릭터 사용 가능 여부

    Returns:
        RecommendationResult
    """
    recommender = AIVisualRecommender()
    return recommender.recommend(
        script_text=script_text,
        scene_title=scene_title,
        has_infographic=has_infographic,
        has_character=has_character
    )
