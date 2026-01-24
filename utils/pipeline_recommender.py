# -*- coding: utf-8 -*-
"""
utils/pipeline_recommender.py
파이프라인 단계별 씬 추천 로직

각 단계에서 해당 타입에 적합한 씬을 AI 분석을 통해 추천합니다.
키워드 가중치 기반 점수 계산 방식을 사용합니다.

작성: 2025-01
"""

import re
from typing import Set, List, Dict, Tuple, Optional
from dataclasses import dataclass


@dataclass
class RecommendResult:
    """추천 결과"""
    scene_id: int
    score: float
    reasons: List[str]
    matched_keywords: List[str]
    confidence: str  # "high", "medium", "low"


# ============================================================
# 키워드 사전 (가중치 포함)
# ============================================================

REAL_IMAGE_KEYWORDS = {
    # 제품/상품 (가장 높은 가중치)
    '제품': 4, '상품': 4, '브랜드': 3, '패키지': 3, '포장': 2,
    '진열': 3, '디스플레이': 3, '샘플': 3, '프로토타입': 3,

    # 장소/건물
    '매장': 3, '사무실': 3, '회의실': 3, '공장': 4, '창고': 2,
    '병원': 3, '학교': 2, '도서관': 2, '연구소': 3, '랩': 3,
    '건물': 2, '거리': 2, '도시': 2, '번화가': 2, '광장': 2,

    # 자연/풍경
    '자연': 3, '풍경': 3, '산': 2, '바다': 2, '강': 2, '호수': 2,
    '숲': 2, '들판': 2, '하늘': 1, '일출': 3, '일몰': 3,

    # 사람/인물
    '인물': 3, '사진': 3, '모습': 2, '표정': 2, '얼굴': 2,
    '직원': 3, '고객': 3, '소비자': 2, '사용자': 2, '회사원': 2,
    '전문가': 3, '의사': 3, '연구원': 3, '엔지니어': 3,

    # 실제/현실
    '실제': 4, '현실': 3, '실생활': 3, '일상': 2, '현장': 4,
    '현지': 3, '촬영': 3, '사진': 3, '포토': 2,

    # 장비/설비
    '설비': 3, '장비': 3, '기계': 3, '시설': 3, '인프라': 2,
}

REAL_IMAGE_EXCLUDE = {
    '추상': -3, '개념': -2, '아이디어': -2, '상상': -3, '가상': -3,
    '그래프': -3, '차트': -3, '데이터': -2, '통계': -2, '수치': -2,
    '비교': -1, '순위': -1, '단계': -1, '프로세스': -1,
}

INFOGRAPHIC_KEYWORDS = {
    # 데이터/통계 (최고 가중치)
    '퍼센트': 5, '%': 5, '비율': 4, '비중': 4, '점유율': 4,
    '증가': 3, '감소': 3, '상승': 3, '하락': 3, '성장률': 4,
    '통계': 4, '데이터': 3, '수치': 3, '숫자': 2,

    # 비교/순위
    '순위': 4, '1위': 4, '2위': 3, '3위': 3, '톱': 3, 'top': 3,
    '비교': 4, '대비': 3, '차이': 3, '격차': 3, '우위': 2,
    '장점': 3, '단점': 3, '장단점': 4, '차별점': 3,

    # 프로세스/단계
    '단계': 4, '과정': 3, '프로세스': 4, '절차': 3, '방법': 2,
    '순서': 3, '첫째': 3, '둘째': 2, '셋째': 2,
    '1단계': 4, '2단계': 3, '3단계': 3, 'step': 3,

    # 구조/분류
    '구조': 3, '구성': 3, '분류': 3, '종류': 3, '유형': 3,
    '카테고리': 3, '목록': 2, '리스트': 2, '항목': 2,

    # 관계
    '관계': 3, '연결': 2, '연관': 2, '상호': 2, '영향': 2,
    '원인': 3, '결과': 3, '인과': 3, '배경': 2,
}

INFOGRAPHIC_EXCLUDE = {
    '감동': -2, '감성': -2, '스토리': -2, '이야기': -1,
    '장면': -1, '모습': -1, '풍경': -2,
}

CHARACTER_KEYWORDS = {
    # 설명/소개 (캐릭터가 설명하는 느낌)
    '설명': 4, '소개': 4, '알려': 3, '말씀': 3, '안내': 3,
    '보여': 2, '공개': 2, '발표': 2,

    # 감정 표현
    '기쁨': 3, '슬픔': 2, '놀람': 3, '화남': 2, '걱정': 2,
    '행복': 3, '좋은': 2, '나쁜': 2, '최고': 3, '최악': 2,
    '흥미': 3, '재미': 3, '신기': 3, '대박': 4,

    # 대화/상호작용
    '질문': 3, '답변': 3, '대화': 2, '말하': 2, '이야기': 2,
    '여러분': 4, '당신': 3, '우리': 2,

    # 강조
    '중요': 4, '핵심': 4, '포인트': 3, '주목': 3, '강조': 3,
    '특히': 3, '바로': 3, '여기서': 3, '주의': 3,

    # 추천/팁
    '추천': 4, '팁': 4, '비법': 3, '노하우': 3, '비결': 3,
}

CHARACTER_EXCLUDE = {
    '전체': -3, '전경': -3, '파노라마': -3, '넓은': -2,
    '그래프': -2, '차트': -2, '표': -2, '데이터': -1,
    '복잡': -2, '가득': -2, '빼곡': -2,
}

VIDEO_KEYWORDS = {
    # 동작/움직임 (최고 가중치)
    '움직': 5, '달리': 4, '걷': 3, '뛰': 4, '날': 4, '흐르': 4,
    '돌': 3, '회전': 4, '이동': 3, '진행': 3, '전진': 3, '후진': 2,
    '상승': 3, '하강': 3, '올라': 3, '내려': 3,

    # 변화/전환
    '변화': 4, '변환': 4, '전환': 3, '성장': 3, '발전': 3, '진화': 3,
    '확장': 3, '축소': 2, '증가': 2, '감소': 2,

    # 시간 경과
    '시간': 3, '흐름': 3, '경과': 3, '과정': 2, '단계별': 3,
    '아침': 2, '점심': 2, '저녁': 2, '밤': 2, '새벽': 2,
    '전후': 3, '비포애프터': 4,

    # 동적 장면
    '폭발': 5, '충돌': 4, '터지': 4, '깨지': 3, '부서': 3,
    '파도': 3, '바람': 3, '불': 3, '물': 2, '연기': 3, '안개': 2,
    '흔들': 3, '파동': 4, '진동': 3,

    # 감정 동적 표현
    '놀람': 3, '충격': 4, '감동': 3, '흥분': 3, '긴장': 3,
}

VIDEO_EXCLUDE = {
    '고정': -3, '정지': -3, '멈춤': -3, '정적': -3, '안정': -2,
    '단순': -1, '간단': -1,
}


# ============================================================
# 점수 계산 함수
# ============================================================

def _calculate_score(
    text: str,
    positive_keywords: Dict[str, int],
    negative_keywords: Dict[str, int],
    threshold: float = 3.0
) -> Tuple[float, List[str], str]:
    """
    키워드 가중치 기반 점수 계산

    Args:
        text: 분석할 텍스트
        positive_keywords: {키워드: 가중치} 양수
        negative_keywords: {키워드: 가중치} 음수
        threshold: 추천 임계값

    Returns:
        (점수, 매칭된 키워드, 신뢰도)
    """
    text_lower = text.lower()
    matched = []
    score = 0.0

    # 양수 키워드
    for kw, weight in positive_keywords.items():
        if kw in text_lower:
            score += weight
            matched.append(f"+{kw}({weight})")

    # 음수 키워드
    for kw, weight in negative_keywords.items():
        if kw in text_lower:
            score += weight  # 이미 음수
            matched.append(f"-{kw}({abs(weight)})")

    # 숫자/퍼센트 패턴 보너스 (인포그래픽용)
    number_pattern = r'\d+(\.\d+)?%|\d+위|\d+단계'
    number_matches = re.findall(number_pattern, text)
    if number_matches:
        bonus = len(number_matches) * 2
        score += bonus
        matched.append(f"+숫자패턴({bonus})")

    # 신뢰도 결정
    if score >= threshold * 1.5:
        confidence = "high"
    elif score >= threshold:
        confidence = "medium"
    else:
        confidence = "low"

    return score, matched, confidence


def _get_scene_text(scene: Dict) -> str:
    """씬에서 분석용 텍스트 추출"""
    parts = []

    # 스크립트/나레이션
    script = scene.get('script', '') or scene.get('narration', '')
    if script:
        parts.append(script)

    # 이미지 프롬프트
    prompt = scene.get('image_prompt', '') or scene.get('image_prompt_en', '')
    if prompt:
        parts.append(prompt)

    # 비디오 프롬프트
    video_prompt = scene.get('video_prompt', '')
    if video_prompt:
        parts.append(video_prompt)

    return ' '.join(parts)


def _generate_reasons(matched: List[str], scene_type: str) -> List[str]:
    """매칭된 키워드에서 이유 생성"""
    reasons = []

    positive_matches = [m for m in matched if m.startswith('+')]

    if scene_type == "real_image":
        if any('제품' in m or '상품' in m for m in positive_matches):
            reasons.append("제품/상품 관련 씬")
        if any('매장' in m or '사무실' in m or '건물' in m for m in positive_matches):
            reasons.append("실제 장소 묘사")
        if any('인물' in m or '사진' in m or '모습' in m for m in positive_matches):
            reasons.append("인물/사진 관련")
        if any('실제' in m or '현장' in m for m in positive_matches):
            reasons.append("현장/실제 상황")

    elif scene_type == "infographic":
        if any('퍼센트' in m or '%' in m or '비율' in m for m in positive_matches):
            reasons.append("데이터/통계 표현")
        if any('순위' in m or '비교' in m for m in positive_matches):
            reasons.append("비교/순위 정보")
        if any('단계' in m or '프로세스' in m for m in positive_matches):
            reasons.append("프로세스/단계 설명")
        if any('구조' in m or '분류' in m for m in positive_matches):
            reasons.append("구조/분류 정보")

    elif scene_type == "character":
        if any('설명' in m or '소개' in m or '안내' in m for m in positive_matches):
            reasons.append("설명/안내 씬")
        if any('기쁨' in m or '놀람' in m or '행복' in m or '대박' in m for m in positive_matches):
            reasons.append("감정 표현 씬")
        if any('중요' in m or '핵심' in m or '강조' in m for m in positive_matches):
            reasons.append("강조 씬")
        if any('추천' in m or '팁' in m for m in positive_matches):
            reasons.append("추천/팁 씬")

    elif scene_type == "video":
        if any('움직' in m or '달리' in m or '회전' in m for m in positive_matches):
            reasons.append("동작/움직임 표현")
        if any('변화' in m or '성장' in m or '전환' in m for m in positive_matches):
            reasons.append("변화/전환 장면")
        if any('폭발' in m or '충돌' in m or '충격' in m for m in positive_matches):
            reasons.append("동적/임팩트 장면")
        if any('시간' in m or '경과' in m or '흐름' in m for m in positive_matches):
            reasons.append("시간 경과 표현")

    if not reasons:
        reasons.append(f"{scene_type} 적합")

    return reasons


# ============================================================
# 단계별 추천 함수
# ============================================================

def recommend_real_image_scenes(
    pool: Set[int],
    scenes_data: List[Dict],
    threshold: float = 5.0,
    max_results: int = 50
) -> List[RecommendResult]:
    """
    실사이미지 대체 추천 (AI 소모: 낮음)

    추천 기준:
    - 실제 제품/장소/사람이 언급된 씬
    - 사실적 표현이 필요한 씬
    - 스톡 이미지로 대체 가능한 씬
    """
    results = []

    scene_map = {s.get('scene_id') or s.get('id', i+1): s for i, s in enumerate(scenes_data)}

    for scene_id in pool:
        scene = scene_map.get(scene_id)
        if not scene:
            continue

        text = _get_scene_text(scene)
        if not text.strip():
            continue

        score, matched, confidence = _calculate_score(
            text, REAL_IMAGE_KEYWORDS, REAL_IMAGE_EXCLUDE, threshold
        )

        if score >= threshold:
            reasons = _generate_reasons(matched, "real_image")
            results.append(RecommendResult(
                scene_id=scene_id,
                score=score,
                reasons=reasons,
                matched_keywords=matched,
                confidence=confidence
            ))

    # 점수 내림차순 정렬
    results.sort(key=lambda x: x.score, reverse=True)

    print(f"[Pipeline추천] 실사이미지: {len(results)}개 추천 (풀: {len(pool)}개)")
    return results[:max_results]


def recommend_infographic_scenes(
    pool: Set[int],
    scenes_data: List[Dict],
    threshold: float = 5.0,
    max_results: int = 50
) -> List[RecommendResult]:
    """
    인포그래픽 대체 추천 (AI 소모: 중간)

    추천 기준:
    - 데이터/통계가 언급된 씬
    - 비교/순위가 있는 씬
    - 프로세스/단계가 있는 씬
    """
    results = []

    scene_map = {s.get('scene_id') or s.get('id', i+1): s for i, s in enumerate(scenes_data)}

    for scene_id in pool:
        scene = scene_map.get(scene_id)
        if not scene:
            continue

        text = _get_scene_text(scene)
        if not text.strip():
            continue

        score, matched, confidence = _calculate_score(
            text, INFOGRAPHIC_KEYWORDS, INFOGRAPHIC_EXCLUDE, threshold
        )

        if score >= threshold:
            reasons = _generate_reasons(matched, "infographic")
            results.append(RecommendResult(
                scene_id=scene_id,
                score=score,
                reasons=reasons,
                matched_keywords=matched,
                confidence=confidence
            ))

    results.sort(key=lambda x: x.score, reverse=True)

    print(f"[Pipeline추천] 인포그래픽: {len(results)}개 추천 (풀: {len(pool)}개)")
    return results[:max_results]


def recommend_character_scenes(
    pool: Set[int],
    scenes_data: List[Dict],
    threshold: float = 4.0,
    max_results: int = 50
) -> List[RecommendResult]:
    """
    캐릭터 합성 추천 (AI 소모: 중간)

    추천 기준:
    - 설명/소개 씬 (캐릭터가 설명하는 느낌)
    - 감정 표현이 필요한 씬
    - 강조 씬
    - 제외: 데이터 중심 씬, 전경 씬
    """
    results = []

    scene_map = {s.get('scene_id') or s.get('id', i+1): s for i, s in enumerate(scenes_data)}

    for scene_id in pool:
        scene = scene_map.get(scene_id)
        if not scene:
            continue

        text = _get_scene_text(scene)
        if not text.strip():
            continue

        score, matched, confidence = _calculate_score(
            text, CHARACTER_KEYWORDS, CHARACTER_EXCLUDE, threshold
        )

        if score >= threshold:
            reasons = _generate_reasons(matched, "character")
            results.append(RecommendResult(
                scene_id=scene_id,
                score=score,
                reasons=reasons,
                matched_keywords=matched,
                confidence=confidence
            ))

    results.sort(key=lambda x: x.score, reverse=True)

    print(f"[Pipeline추천] 캐릭터: {len(results)}개 추천 (풀: {len(pool)}개)")
    return results[:max_results]


def recommend_video_scenes(
    pool: Set[int],
    scenes_data: List[Dict],
    threshold: float = 6.0,  # 높은 임계값 (비용이 높으므로 신중하게)
    max_results: int = 30
) -> List[RecommendResult]:
    """
    비디오 변환 추천 (AI 소모: 높음 - 가장 신중하게!)

    추천 기준:
    - 동작/움직임이 있는 씬
    - 시간 경과가 필요한 씬
    - 임팩트가 필요한 씬
    - 높은 임계값 적용
    """
    results = []

    scene_map = {s.get('scene_id') or s.get('id', i+1): s for i, s in enumerate(scenes_data)}

    for scene_id in pool:
        scene = scene_map.get(scene_id)
        if not scene:
            continue

        text = _get_scene_text(scene)
        if not text.strip():
            continue

        score, matched, confidence = _calculate_score(
            text, VIDEO_KEYWORDS, VIDEO_EXCLUDE, threshold
        )

        if score >= threshold:
            reasons = _generate_reasons(matched, "video")
            results.append(RecommendResult(
                scene_id=scene_id,
                score=score,
                reasons=reasons,
                matched_keywords=matched,
                confidence=confidence
            ))

    results.sort(key=lambda x: x.score, reverse=True)

    print(f"[Pipeline추천] 비디오: {len(results)}개 추천 (풀: {len(pool)}개)")
    return results[:max_results]


# ============================================================
# 유틸리티 함수
# ============================================================

def get_recommendation_summary(results: List[RecommendResult]) -> Dict:
    """추천 결과 요약"""
    if not results:
        return {"count": 0, "high": 0, "medium": 0, "low": 0}

    high = sum(1 for r in results if r.confidence == "high")
    medium = sum(1 for r in results if r.confidence == "medium")
    low = sum(1 for r in results if r.confidence == "low")

    return {
        "count": len(results),
        "high": high,
        "medium": medium,
        "low": low,
        "avg_score": sum(r.score for r in results) / len(results),
        "top_reasons": _get_top_reasons(results)
    }


def _get_top_reasons(results: List[RecommendResult], top_n: int = 3) -> List[str]:
    """상위 이유 추출"""
    reason_counts = {}
    for r in results:
        for reason in r.reasons:
            reason_counts[reason] = reason_counts.get(reason, 0) + 1

    sorted_reasons = sorted(reason_counts.items(), key=lambda x: x[1], reverse=True)
    return [r[0] for r in sorted_reasons[:top_n]]


def filter_by_confidence(
    results: List[RecommendResult],
    min_confidence: str = "medium"
) -> List[RecommendResult]:
    """신뢰도 기준 필터링"""
    confidence_order = {"high": 3, "medium": 2, "low": 1}
    min_level = confidence_order.get(min_confidence, 2)

    return [r for r in results if confidence_order.get(r.confidence, 0) >= min_level]
