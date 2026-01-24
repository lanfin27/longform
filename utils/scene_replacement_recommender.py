# -*- coding: utf-8 -*-
"""
utils/scene_replacement_recommender.py
씬 대체 AI 추천 로직

기능:
1. 실사이미지 대체 추천
2. 비디오 변환 추천
3. 인포그래픽 대체 추천
4. 캐릭터 합성 적합 씬 분석

작성: 2025-01
"""

import re
from typing import List, Dict, Set, Tuple, Optional
from dataclasses import dataclass


@dataclass
class RecommendationResult:
    """추천 결과"""
    scene_id: int
    score: float  # 0.0 ~ 1.0
    reasons: List[str]
    keywords_matched: List[str]


# ============================================================
# 키워드 기반 추천
# ============================================================

# 실사이미지 대체 추천 키워드
REAL_IMAGE_KEYWORDS = {
    "positive": [
        # 실제 장소/건물
        '매장', '사무실', '회의실', '공장', '창고', '병원', '학교', '도서관',
        '건물', '거리', '도시', '시내', '번화가', '공원', '광장',
        # 자연/풍경
        '자연', '풍경', '산', '바다', '강', '호수', '숲', '들판', '하늘',
        # 제품/상품
        '제품', '상품', '브랜드', '패키지', '포장', '진열', '디스플레이',
        # 사람 관련
        '인물', '사진', '모습', '표정', '얼굴', '손', '동작',
        '회사원', '직원', '고객', '소비자', '사용자',
        # 실제 상황
        '실제', '현실', '실생활', '일상', '현장', '현지',
        '촬영', '사진', '이미지', '포토',
    ],
    "negative": [
        # 추상적 개념
        '추상', '개념', '아이디어', '상상', '가상', '환상',
        # 데이터/통계
        '그래프', '차트', '데이터', '통계', '수치', '퍼센트',
        # 인포그래픽 관련
        '비교', '순위', '랭킹', '단계', '프로세스', '절차',
    ]
}

# 비디오 변환 추천 키워드
VIDEO_KEYWORDS = {
    "positive": [
        # 동작/움직임
        '움직', '달리', '걷', '뛰', '날', '흐르', '돌', '회전',
        '이동', '진행', '전진', '후진', '상승', '하강',
        # 변화/전환
        '변화', '변환', '전환', '성장', '발전', '진화', '확장', '축소',
        '증가', '감소', '상승', '하락',
        # 시간 경과
        '시간', '흐름', '경과', '과정', '단계별', '순차',
        '아침', '점심', '저녁', '밤', '새벽',
        # 감정 표현
        '폭발', '충돌', '터지', '깨지', '부서',
        '놀람', '충격', '감동', '흥분', '긴장',
        # 동적 장면
        '파도', '바람', '불', '물', '연기', '안개',
        '군중', '행렬', '퍼레이드', '축제',
    ],
    "negative": [
        # 정적 표현
        '고정', '정지', '멈춤', '정적', '안정',
        # 단순 설명
        '설명', '소개', '정의', '개념',
    ]
}

# 인포그래픽 대체 추천 키워드
INFOGRAPHIC_KEYWORDS = {
    "positive": [
        # 데이터/통계
        '퍼센트', '%', '비율', '비중', '점유율',
        '증가', '감소', '상승', '하락', '성장률',
        '수치', '숫자', '통계', '데이터',
        # 비교/순위
        '순위', '1위', '2위', '3위', '톱', 'top', '랭킹',
        '비교', '대비', '차이', '격차', '우위', '열위',
        '장점', '단점', '장단점', '차별점',
        # 프로세스/단계
        '단계', '과정', '프로세스', '절차', '방법', '순서',
        '첫째', '둘째', '셋째', '1단계', '2단계', '3단계',
        'step', '스텝',
        # 구조/분류
        '구조', '구성', '분류', '종류', '유형', '카테고리',
        '목록', '리스트', '항목', '요소',
        # 관계
        '관계', '연결', '연관', '상호', '영향',
        '원인', '결과', '인과', '배경',
    ],
    "negative": [
        # 감성적 표현
        '감동', '감성', '스토리', '이야기', '서사',
        # 구체적 장면
        '장면', '씬', '상황', '모습', '풍경',
    ]
}


def _calculate_keyword_score(
    text: str,
    positive_keywords: List[str],
    negative_keywords: List[str]
) -> Tuple[float, List[str]]:
    """
    키워드 기반 점수 계산

    Returns:
        (score, matched_keywords)
    """
    text_lower = text.lower()
    matched = []
    score = 0.0

    for kw in positive_keywords:
        if kw in text_lower:
            score += 1.0
            matched.append(f"+{kw}")

    for kw in negative_keywords:
        if kw in text_lower:
            score -= 0.5
            matched.append(f"-{kw}")

    # 정규화 (0.0 ~ 1.0)
    max_possible = len(positive_keywords)
    if max_possible > 0:
        normalized_score = max(0.0, min(1.0, score / min(5, max_possible)))
    else:
        normalized_score = 0.0

    return normalized_score, matched


def recommend_real_image_replacement(
    scenes: List[Dict],
    threshold: float = 0.3
) -> List[RecommendationResult]:
    """
    실사이미지로 대체 추천할 씬 분석

    기준:
    - 실제 제품/장소/사람 묘사가 있는 씬
    - 사실적 표현이 필요한 씬
    - 추상적이지 않은 구체적 장면

    Args:
        scenes: 씬 데이터 리스트
        threshold: 추천 임계값 (0.0 ~ 1.0)

    Returns:
        추천 결과 리스트 (점수 내림차순)
    """
    results = []

    for scene in scenes:
        scene_id = scene.get('scene_id') or scene.get('id', 0)
        if not scene_id:
            continue

        # 분석 대상 텍스트
        script = scene.get('script', '') or scene.get('narration', '')
        prompt = scene.get('image_prompt', '') or scene.get('image_prompt_en', '')
        combined_text = f"{script} {prompt}"

        if not combined_text.strip():
            continue

        # 이미 실사이미지인 경우 스킵
        if scene.get('real_image_path') or scene.get('is_real_image'):
            continue

        # 점수 계산
        score, matched = _calculate_keyword_score(
            combined_text,
            REAL_IMAGE_KEYWORDS["positive"],
            REAL_IMAGE_KEYWORDS["negative"]
        )

        if score >= threshold:
            reasons = []
            if any(kw in combined_text.lower() for kw in ['제품', '상품', '브랜드']):
                reasons.append("제품/상품 관련 씬")
            if any(kw in combined_text.lower() for kw in ['매장', '사무실', '건물']):
                reasons.append("실제 장소 묘사")
            if any(kw in combined_text.lower() for kw in ['인물', '사진', '모습']):
                reasons.append("인물/사진 관련")
            if not reasons:
                reasons.append("사실적 표현 필요")

            results.append(RecommendationResult(
                scene_id=scene_id,
                score=score,
                reasons=reasons,
                keywords_matched=matched
            ))

    # 점수 내림차순 정렬
    results.sort(key=lambda x: x.score, reverse=True)

    print(f"[추천] 실사이미지 대체 추천: {len(results)}개 씬")
    return results


def recommend_video_replacement(
    scenes: List[Dict],
    threshold: float = 0.2
) -> List[RecommendationResult]:
    """
    비디오로 변환 추천할 씬 분석

    기준:
    - 동작/움직임이 있는 씬
    - 시간 경과가 필요한 씬
    - 감정 변화/동적 장면이 있는 씬

    Args:
        scenes: 씬 데이터 리스트
        threshold: 추천 임계값

    Returns:
        추천 결과 리스트
    """
    results = []

    for scene in scenes:
        scene_id = scene.get('scene_id') or scene.get('id', 0)
        if not scene_id:
            continue

        script = scene.get('script', '') or scene.get('narration', '')
        prompt = scene.get('image_prompt', '') or scene.get('video_prompt', '')
        combined_text = f"{script} {prompt}"

        if not combined_text.strip():
            continue

        # 이미 비디오인 경우 스킵
        if scene.get('video_path') or scene.get('background_video'):
            continue

        score, matched = _calculate_keyword_score(
            combined_text,
            VIDEO_KEYWORDS["positive"],
            VIDEO_KEYWORDS["negative"]
        )

        if score >= threshold:
            reasons = []
            if any(kw in combined_text.lower() for kw in ['움직', '달리', '뛰', '걷']):
                reasons.append("동작/움직임 표현")
            if any(kw in combined_text.lower() for kw in ['변화', '성장', '전환']):
                reasons.append("변화/전환 장면")
            if any(kw in combined_text.lower() for kw in ['폭발', '충돌', '흥분']):
                reasons.append("동적/감정 표현")
            if not reasons:
                reasons.append("동영상 표현 적합")

            results.append(RecommendationResult(
                scene_id=scene_id,
                score=score,
                reasons=reasons,
                keywords_matched=matched
            ))

    results.sort(key=lambda x: x.score, reverse=True)

    print(f"[추천] 비디오 변환 추천: {len(results)}개 씬")
    return results


def recommend_infographic_replacement(
    scenes: List[Dict],
    threshold: float = 0.25
) -> List[RecommendationResult]:
    """
    인포그래픽으로 대체 추천할 씬 분석

    기준:
    - 데이터/통계가 언급된 씬
    - 비교/순위가 있는 씬
    - 프로세스/단계가 있는 씬

    Args:
        scenes: 씬 데이터 리스트
        threshold: 추천 임계값

    Returns:
        추천 결과 리스트
    """
    results = []

    for scene in scenes:
        scene_id = scene.get('scene_id') or scene.get('id', 0)
        if not scene_id:
            continue

        script = scene.get('script', '') or scene.get('narration', '')
        combined_text = script

        if not combined_text.strip():
            continue

        # 이미 인포그래픽인 경우 스킵
        if scene.get('infographic_path') or scene.get('visual_type') == 'infographic':
            continue

        score, matched = _calculate_keyword_score(
            combined_text,
            INFOGRAPHIC_KEYWORDS["positive"],
            INFOGRAPHIC_KEYWORDS["negative"]
        )

        # 숫자/퍼센트 패턴 추가 점수
        number_pattern = r'\d+(\.\d+)?%|\d+위|\d+단계'
        number_matches = re.findall(number_pattern, combined_text)
        if number_matches:
            score += 0.2 * len(number_matches)
            matched.append(f"+숫자패턴({len(number_matches)}개)")

        if score >= threshold:
            reasons = []
            if any(kw in combined_text.lower() for kw in ['퍼센트', '%', '비율']):
                reasons.append("데이터/통계 표현")
            if any(kw in combined_text.lower() for kw in ['순위', '1위', '비교']):
                reasons.append("비교/순위 정보")
            if any(kw in combined_text.lower() for kw in ['단계', '과정', '프로세스']):
                reasons.append("프로세스/단계 설명")
            if not reasons:
                reasons.append("시각화 적합")

            results.append(RecommendationResult(
                scene_id=scene_id,
                score=min(1.0, score),  # 최대 1.0
                reasons=reasons,
                keywords_matched=matched
            ))

    results.sort(key=lambda x: x.score, reverse=True)

    print(f"[추천] 인포그래픽 대체 추천: {len(results)}개 씬")
    return results


# ============================================================
# 캐릭터 합성 적합 씬 분석
# ============================================================

CHARACTER_SUITABLE_KEYWORDS = {
    "positive": [
        # 설명/소개
        '설명', '소개', '알려', '말씀', '안내',
        # 감정 표현
        '기쁨', '슬픔', '놀람', '화남', '걱정', '행복',
        '좋은', '나쁜', '최고', '최악',
        # 대화/상호작용
        '질문', '답변', '대화', '말하', '이야기',
        # 강조
        '중요', '핵심', '포인트', '주목', '강조',
        '특히', '바로', '여기서',
    ],
    "negative": [
        # 전체 장면
        '전체', '전경', '파노라마', '넓은',
        # 데이터 중심
        '그래프', '차트', '표', '데이터',
        # 복잡한 배경
        '복잡', '가득', '빼곡',
    ]
}


def recommend_character_composite(
    scenes: List[Dict],
    threshold: float = 0.2
) -> List[RecommendationResult]:
    """
    캐릭터 합성에 적합한 씬 분석

    기준:
    - 설명/소개 씬
    - 감정 표현이 필요한 씬
    - 대화/상호작용 씬
    - 배경이 단순한 씬

    Args:
        scenes: 씬 데이터 리스트
        threshold: 추천 임계값

    Returns:
        추천 결과 리스트
    """
    results = []

    for scene in scenes:
        scene_id = scene.get('scene_id') or scene.get('id', 0)
        if not scene_id:
            continue

        script = scene.get('script', '') or scene.get('narration', '')

        if not script.strip():
            continue

        score, matched = _calculate_keyword_score(
            script,
            CHARACTER_SUITABLE_KEYWORDS["positive"],
            CHARACTER_SUITABLE_KEYWORDS["negative"]
        )

        if score >= threshold:
            reasons = []
            if any(kw in script.lower() for kw in ['설명', '소개', '안내']):
                reasons.append("설명/안내 씬")
            if any(kw in script.lower() for kw in ['기쁨', '놀람', '행복']):
                reasons.append("감정 표현 씬")
            if any(kw in script.lower() for kw in ['중요', '핵심', '강조']):
                reasons.append("강조 씬")
            if not reasons:
                reasons.append("캐릭터 합성 적합")

            results.append(RecommendationResult(
                scene_id=scene_id,
                score=score,
                reasons=reasons,
                keywords_matched=matched
            ))

    results.sort(key=lambda x: x.score, reverse=True)

    print(f"[추천] 캐릭터 합성 추천: {len(results)}개 씬")
    return results


def analyze_character_position(scene: Dict) -> str:
    """
    씬 분석하여 캐릭터 합성 위치 결정

    Args:
        scene: 씬 데이터

    Returns:
        "left_bottom" | "right_bottom"
    """
    script = scene.get('script', '')

    # 왼쪽 관련 키워드
    left_keywords = ['왼쪽', '좌측', '시작', '처음', '앞서']
    # 오른쪽 관련 키워드
    right_keywords = ['오른쪽', '우측', '다음', '끝', '마지막']

    left_score = sum(1 for kw in left_keywords if kw in script)
    right_score = sum(1 for kw in right_keywords if kw in script)

    # 기본값은 오른쪽 (더 자연스러움)
    if left_score > right_score:
        return "left_bottom"
    return "right_bottom"


def suggest_character_pose(scene: Dict) -> str:
    """
    씬 맥락에 맞는 캐릭터 포즈 제안

    Returns:
        "standing" | "pointing" | "thinking" | "waving" | "surprised"
    """
    script = scene.get('script', '').lower()

    if any(kw in script for kw in ['설명', '소개', '알려', '보여']):
        return "pointing"
    elif any(kw in script for kw in ['생각', '고민', '의문', '왜']):
        return "thinking"
    elif any(kw in script for kw in ['안녕', '반갑', '환영', '인사']):
        return "waving"
    elif any(kw in script for kw in ['놀람', '충격', '대박', '와']):
        return "surprised"
    else:
        return "standing"


def suggest_character_expression(scene: Dict) -> str:
    """
    씬 맥락에 맞는 캐릭터 표정 제안

    Returns:
        "happy" | "surprised" | "explaining" | "thoughtful" | "neutral"
    """
    script = scene.get('script', '').lower()

    if any(kw in script for kw in ['기쁨', '좋은', '행복', '최고', '성공']):
        return "happy"
    elif any(kw in script for kw in ['놀람', '충격', '대박', '믿기 어려운']):
        return "surprised"
    elif any(kw in script for kw in ['설명', '소개', '알려', '안내']):
        return "explaining"
    elif any(kw in script for kw in ['생각', '고민', '분석', '검토']):
        return "thoughtful"
    else:
        return "neutral"


# ============================================================
# 통합 추천
# ============================================================

def get_all_recommendations(
    scenes: List[Dict]
) -> Dict[str, List[RecommendationResult]]:
    """
    모든 유형의 추천 결과 반환

    Returns:
        {
            "real_image": [...],
            "video": [...],
            "infographic": [...],
            "character": [...]
        }
    """
    return {
        "real_image": recommend_real_image_replacement(scenes),
        "video": recommend_video_replacement(scenes),
        "infographic": recommend_infographic_replacement(scenes),
        "character": recommend_character_composite(scenes)
    }


def get_recommendation_summary(recommendations: Dict) -> str:
    """추천 결과 요약 문자열"""
    parts = []

    if recommendations.get("real_image"):
        parts.append(f"📷 실사이미지 {len(recommendations['real_image'])}개")
    if recommendations.get("video"):
        parts.append(f"🎬 비디오 {len(recommendations['video'])}개")
    if recommendations.get("infographic"):
        parts.append(f"📊 인포그래픽 {len(recommendations['infographic'])}개")
    if recommendations.get("character"):
        parts.append(f"🎭 캐릭터합성 {len(recommendations['character'])}개")

    return ", ".join(parts) if parts else "추천 없음"
