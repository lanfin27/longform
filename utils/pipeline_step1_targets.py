# -*- coding: utf-8 -*-
"""
utils/pipeline_step1_targets.py
Step 1 실사이미지 대체 - 우선 대상 관리

1차 대상 (자동 선별):
- 묶음별 대표 이미지 씬
- 한글 텍스트 씬

2차 대상 (AI 추천):
- 1차 대상 제외 후 AI가 추가 선별

작성: 2025-01
"""

import streamlit as st
from typing import Set, List, Dict, Tuple, Optional


class Step1PriorityTargets:
    """Step 1 실사이미지 대체 - 우선 대상 관리"""

    def __init__(self, scenes: List[Dict]):
        self.scenes = scenes
        self.all_scene_ids = {
            s.get('scene_id') or s.get('id', i + 1)
            for i, s in enumerate(scenes)
        }

    def get_bundle_representative_scenes(self) -> Set[int]:
        """
        묶음별 대표 이미지 씬 ID 반환

        묶음(번들)의 첫 번째 이미지 = 대표 이미지
        이들은 실사이미지로 대체하면 묶음 전체의 품질이 향상됨
        """
        bundle_reps = set()

        # 묶음 정보 수집
        bundle_map = {}  # {bundle_id: [scenes]}

        for i, scene in enumerate(self.scenes):
            scene_id = scene.get('scene_id') or scene.get('id', i + 1)
            bundle_id = scene.get('bundle_id')

            # 묶음 ID가 없으면 scene_id를 묶음 ID로 사용 (각 씬이 개별 묶음)
            if bundle_id is None:
                bundle_id = scene_id

            if bundle_id not in bundle_map:
                bundle_map[bundle_id] = []
            bundle_map[bundle_id].append((scene_id, scene))

        # 각 묶음의 첫 번째 씬 선택
        for bundle_id, scenes_in_bundle in bundle_map.items():
            if not scenes_in_bundle:
                continue

            # scene_id로 정렬
            scenes_in_bundle.sort(key=lambda x: x[0])

            # 첫 번째 씬 또는 is_bundle_representative 플래그가 있는 씬
            for scene_id, scene in scenes_in_bundle:
                if scene.get('is_bundle_representative', False):
                    bundle_reps.add(scene_id)
                    break
            else:
                # 플래그가 없으면 첫 번째 씬
                first_scene_id = scenes_in_bundle[0][0]
                bundle_reps.add(first_scene_id)

        print(f"[Step1] 묶음별 대표 이미지: {len(bundle_reps)}개")
        return bundle_reps

    def get_korean_text_scenes(self) -> Set[int]:
        """
        한글 텍스트 씬 ID 반환

        한글 오버레이가 들어갈 씬들
        실사이미지 위에 한글 텍스트를 올리면 더 자연스러움
        """
        korean_scenes = set()

        # 1. session_state에서 한글 씬 정보 가져오기 (korean_scene_state 모듈)
        korean_scene_state = st.session_state.get('korean_scene_state', {})

        # 자동 선택 + 수동 추가 - 수동 제거
        auto_selected = korean_scene_state.get('auto_selected', set())
        manual_added = korean_scene_state.get('manual_added', set())
        manual_removed = korean_scene_state.get('manual_removed', set())

        korean_from_state = (auto_selected | manual_added) - manual_removed

        if korean_from_state:
            korean_scenes = korean_from_state
            print(f"[Step1] 한글 씬 (session_state): {len(korean_scenes)}개")
        else:
            # 2. 씬 데이터에서 직접 확인 (폴백)
            for i, scene in enumerate(self.scenes):
                scene_id = scene.get('scene_id') or scene.get('id', i + 1)

                # 다양한 필드에서 한글 텍스트 여부 확인
                korean_prompt = scene.get('image_prompt_korean_text', '')
                has_korean = scene.get('has_korean_text', False)
                is_korean_scene = scene.get('is_korean_scene', False)

                if korean_prompt and korean_prompt.strip():
                    korean_scenes.add(scene_id)
                elif has_korean or is_korean_scene:
                    korean_scenes.add(scene_id)

            print(f"[Step1] 한글 씬 (씬 데이터): {len(korean_scenes)}개")

        # 3. 기존 korean_selected_scenes 체크 (레거시 호환)
        legacy_korean = st.session_state.get('korean_selected_scenes', set())
        if legacy_korean and not korean_scenes:
            korean_scenes = set(legacy_korean)
            print(f"[Step1] 한글 씬 (레거시): {len(korean_scenes)}개")

        return korean_scenes

    def get_priority_targets(self) -> Tuple[Set[int], Dict]:
        """
        1차 우선 대상 통합 반환

        Returns:
            (통합 씬 ID set, 상세 정보 dict)
        """
        bundle_reps = self.get_bundle_representative_scenes()
        korean_scenes = self.get_korean_text_scenes()

        # 중복 제거 통합
        combined = bundle_reps | korean_scenes

        # 중복 씬 (묶음 대표이면서 한글 씬)
        overlap = bundle_reps & korean_scenes

        details = {
            'bundle_representative': {
                'scenes': bundle_reps,
                'count': len(bundle_reps),
                'label': '묶음별 대표 이미지'
            },
            'korean_text': {
                'scenes': korean_scenes,
                'count': len(korean_scenes),
                'label': '한글 텍스트 씬'
            },
            'overlap': {
                'scenes': overlap,
                'count': len(overlap),
                'label': '중복 (묶음대표 + 한글)'
            },
            'combined': {
                'scenes': combined,
                'count': len(combined),
                'label': '1차 대상 합계 (중복 제거)'
            }
        }

        print(f"[Step1] 1차 우선 대상: {len(combined)}개 (중복 {len(overlap)}개 제거)")

        return combined, details

    def get_remaining_for_ai(self, priority_targets: Set[int]) -> Set[int]:
        """
        AI 추천 대상 씬 반환 (1차 대상 제외)
        """
        remaining = self.all_scene_ids - priority_targets

        print(f"[Step1] AI 추천 대상 (1차 제외): {len(remaining)}개")
        return remaining


def recommend_real_image_from_pool(
    pool: Set[int],
    scenes: List[Dict],
    threshold: float = 3.0
) -> List[Tuple[int, float, List[str]]]:
    """
    특정 풀에서만 실사이미지 적합 씬 추천

    Args:
        pool: 추천 대상 씬 ID set (1차 대상 제외된 풀)
        scenes: 전체 씬 데이터
        threshold: 추천 임계값

    Returns:
        [(scene_id, score, reasons), ...] 점수 내림차순 정렬
    """
    # 실사 이미지 적합 키워드 (가중치)
    real_image_keywords = {
        # 제품/상품
        '제품': 3, '상품': 3, '패키지': 2, '포장': 2,
        # 장소
        '매장': 2, '사무실': 2, '회의실': 2, '공장': 3, '창고': 2,
        # 실물
        '실제': 3, '현실': 2, '사진': 3, '촬영': 3,
        # 인물
        '인물': 2, '사람': 1, '직원': 2, '팀': 1, '고객': 2,
        # 건물/풍경
        '건물': 2, '거리': 2, '도시': 2, '자연': 2, '풍경': 2,
        # 장비/설비
        '설비': 3, '장비': 2, '기계': 2, '시스템': 1,
        # 일반
        '모습': 1, '현장': 2, '환경': 1
    }

    # 제외 키워드
    exclude_keywords = ['추상', '개념', '아이디어', '상상', '그래프', '차트', '아이콘', '다이어그램']

    results = []

    for i, scene in enumerate(scenes):
        scene_id = scene.get('scene_id') or scene.get('id', i + 1)

        # 풀에 없으면 건너뛰기
        if scene_id not in pool:
            continue

        script = scene.get('script', '').lower()
        image_prompt = scene.get('image_prompt', '').lower()
        combined_text = f"{script} {image_prompt}"

        # 점수 계산
        score = 0.0
        reasons = []

        for keyword, weight in real_image_keywords.items():
            if keyword in combined_text:
                score += weight
                reasons.append(keyword)

        # 제외 키워드 감점
        for keyword in exclude_keywords:
            if keyword in combined_text:
                score -= 2

        if score >= threshold:
            results.append((scene_id, score, reasons[:3]))

    # 점수 내림차순 정렬
    results.sort(key=lambda x: x[1], reverse=True)

    return results


def get_step1_selection_summary(
    priority_targets: Set[int],
    priority_details: Dict,
    ai_recommended: Set[int],
    final_targets: Set[int],
    total_scenes: int
) -> Dict:
    """
    Step 1 선택 요약 정보 반환
    """
    return {
        # 1차 대상
        'priority': {
            'total': priority_details['combined']['count'],
            'bundle_rep': priority_details['bundle_representative']['count'],
            'korean_text': priority_details['korean_text']['count'],
            'overlap': priority_details['overlap']['count']
        },
        # 2차 대상
        'ai_recommended': {
            'count': len(ai_recommended),
            'scenes': ai_recommended
        },
        # 최종
        'final': {
            'count': len(final_targets),
            'percentage': len(final_targets) / total_scenes * 100 if total_scenes > 0 else 0,
            'scenes': final_targets
        }
    }


# ============================================================
# 세션 상태 관리
# ============================================================

def init_step1_state():
    """Step 1 상태 초기화"""
    if 'step1_state' not in st.session_state:
        st.session_state.step1_state = {
            'priority_targets': set(),
            'priority_details': {},
            'ai_recommended': set(),
            'ai_analyzed': False,
            'final_targets': set(),
            'confirmed': False,
            'include_bundle': True,
            'include_korean': True
        }


def get_step1_state() -> Dict:
    """Step 1 상태 가져오기"""
    init_step1_state()
    return st.session_state.step1_state


def set_step1_priority_targets(targets: Set[int], details: Dict):
    """1차 대상 설정"""
    init_step1_state()
    st.session_state.step1_state['priority_targets'] = targets
    st.session_state.step1_state['priority_details'] = details


def set_step1_ai_recommended(scenes: Set[int]):
    """AI 추천 결과 설정"""
    init_step1_state()
    st.session_state.step1_state['ai_recommended'] = scenes
    st.session_state.step1_state['ai_analyzed'] = True


def set_step1_final_targets(targets: Set[int]):
    """최종 대상 설정"""
    init_step1_state()
    st.session_state.step1_state['final_targets'] = targets


def confirm_step1():
    """Step 1 확정"""
    init_step1_state()
    st.session_state.step1_state['confirmed'] = True


def reset_step1_state():
    """Step 1 상태 초기화"""
    if 'step1_state' in st.session_state:
        del st.session_state.step1_state
    init_step1_state()


# ============================================================
# 내보내기
# ============================================================

__all__ = [
    'Step1PriorityTargets',
    'recommend_real_image_from_pool',
    'get_step1_selection_summary',
    'init_step1_state',
    'get_step1_state',
    'set_step1_priority_targets',
    'set_step1_ai_recommended',
    'set_step1_final_targets',
    'confirm_step1',
    'reset_step1_state'
]
