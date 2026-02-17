# -*- coding: utf-8 -*-
"""
components/storyboard_workflow/workflow_manager.py
5단계 워크플로우 관리자 (v1.2)

주요 기능:
1. 각 Step별 대상 씬 풀(pool) 계산
2. 씬 상태 관리 및 추적
3. 묶음(Bundle) 단위 처리 지원
4. Step 3 Prefix 규칙 구현
5. 워크플로우 상태 저장/로드

v1.1: Step 1 폴백 로직 제거 - 이미지 생성 탭에서 선택된 씬만 표시
v1.2: 🔧 풀 계산 캐싱 추가 - 중복 호출 방지 (성능 최적화)
"""

from dataclasses import dataclass, field
from typing import Dict, Set, List, Optional, Tuple
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import json

from .scene_status import SceneStatus, STEP_CONFIG


@dataclass
class WorkflowState:
    """워크플로우 상태 데이터"""

    # Step별 할당된 씬
    step1_scenes: Set[int] = field(default_factory=set)
    step2_scenes: Set[int] = field(default_factory=set)
    step3_scenes: Set[int] = field(default_factory=set)
    step4_scenes: Set[int] = field(default_factory=set)
    step5_scenes: Set[int] = field(default_factory=set)

    # Step별 완료된 씬
    completed_step1: Set[int] = field(default_factory=set)
    completed_step2: Set[int] = field(default_factory=set)
    completed_step3: Set[int] = field(default_factory=set)
    completed_step4: Set[int] = field(default_factory=set)
    completed_step5: Set[int] = field(default_factory=set)

    # 제외된 씬
    excluded_scenes: Set[int] = field(default_factory=set)

    # 현재 활성 Step
    current_step: int = 1

    # 타임스탬프
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class WorkflowManager:
    """
    5단계 워크플로우 관리자

    핵심 책임:
    1. 각 Step별 대상 씬 풀 계산
    2. 씬 할당/완료 상태 관리
    3. 묶음-씬 관계 처리
    4. 상태 저장/로드
    """

    def __init__(self, project_path: Path, scenes: List[Dict]):
        self.project_path = Path(project_path) if isinstance(project_path, str) else project_path
        self.scenes = scenes
        self.state = WorkflowState()

        # 인덱스 구축
        self.scene_map: Dict[int, Dict] = {}  # scene_id -> scene data
        self.bundle_map: Dict[int, List[int]] = {}  # bundle_id -> scene_ids

        # v2.4: 풀 계산 캐시 (반복 계산 방지)
        self._pool_cache: Dict[str, Set[int]] = {}
        self._pool_cache_valid = True

        self._build_indices()

    def _build_indices(self):
        """씬 및 묶음 인덱스 구축"""
        # scene_map 구축
        for scene in self.scenes:
            sid = scene.get('scene_id', scene.get('id', 0))
            if sid:
                self.scene_map[sid] = scene

        # bundle_map 구축
        bundle_dict = defaultdict(list)
        for scene in self.scenes:
            sid = scene.get('scene_id', scene.get('id', 0))
            bid = scene.get('bundle_id', sid)
            if sid:
                bundle_dict[bid].append(sid)

        # scene_id 순 정렬
        for bid in bundle_dict:
            bundle_dict[bid] = sorted(bundle_dict[bid])

        self.bundle_map = dict(bundle_dict)

    # ========================================
    # Step별 대상 풀 계산
    # ========================================

    def calculate_step1_pool(self) -> Set[int]:
        """
        Step 1: 한글 텍스트 씬 풀 (묶음 대표)

        - image_prompt_korean_text 필드가 있는 씬
        - 묶음 단위로 대표 씬만 반환

        v1.1: session_state 우선 사용 (이미지 생성 탭에서 선택한 씬)
        v1.2: 폴백 제거 - 이미지 생성 탭에서 선택한 씬만 표시
        v1.3: 🔧 캐싱 추가 - 중복 계산 방지 (성능 최적화)
        """
        import streamlit as st

        # ═══════════════════════════════════════════════════════════════
        # v1.3: 캐시 확인 - 이미 계산된 결과 재사용
        # ═══════════════════════════════════════════════════════════════
        cache_key = "step1_pool"
        korean_text_applied = st.session_state.get('korean_text_scenes_applied', False)
        applied_ids = st.session_state.get('korean_text_scene_ids', [])

        # 캐시 유효성 검사용 키
        state_key = f"{korean_text_applied}_{tuple(sorted(applied_ids)) if applied_ids else 'empty'}"
        cache_state_key = f"{cache_key}_state"

        # 캐시 히트: 상태가 변경되지 않은 경우
        if (cache_key in self._pool_cache and
            self._pool_cache.get(cache_state_key) == state_key):
            # 로그 없이 캐시된 결과 반환
            return self._pool_cache[cache_key]

        # ═══════════════════════════════════════════════════════════════
        # v1.2: 폴백 완전 제거 - 선택된 씬만 표시
        # ═══════════════════════════════════════════════════════════════
        if not korean_text_applied:
            # 🔴 v1.2: 적용되지 않은 경우 빈 set 반환 (폴백 없음!)
            print(f"[Step1 Pool] ⚠️ 한글 텍스트 씬 미적용 - 빈 풀 반환")
            self._pool_cache[cache_key] = set()
            self._pool_cache[cache_state_key] = state_key
            return set()

        if not applied_ids:
            # 적용됐지만 비어있으면 빈 set 반환
            print(f"[Step1 Pool] ⚠️ 적용됐으나 씬 ID 없음 - 빈 풀 반환")
            self._pool_cache[cache_key] = set()
            self._pool_cache[cache_state_key] = state_key
            return set()

        korean_ids = set(applied_ids)
        print(f"[Step1 Pool] ✅ session_state에서 로드: {len(korean_ids)}개")

        # 이미 처리된 씬 제외
        excluded = self.state.excluded_scenes | self.state.completed_step1
        eligible = korean_ids - excluded

        # 묶음 대표만 반환
        result = self._get_bundle_representatives(eligible)

        # v1.3: 결과 캐싱
        self._pool_cache[cache_key] = result
        self._pool_cache[cache_state_key] = state_key

        return result

    def calculate_step2_pool(self) -> Set[int]:
        """
        Step 2: 캐릭터 합성 씬 풀 (묶음 대표)

        - characters 필드가 있는 씬
        - Step 1 처리된 씬 제외
        - 묶음 단위로 대표 씬만 반환
        """
        from utils.storyboard_filter import get_has_characters_scene_ids

        char_ids = get_has_characters_scene_ids(self.scenes)

        # Step 1 묶음 전체 제외
        step1_bundles = self._get_bundle_ids_for_scenes(
            self.state.step1_scenes | self.state.completed_step1
        )
        step1_all_scenes = self._get_all_scenes_in_bundles(step1_bundles)

        # 제외 대상
        excluded = (
            self.state.excluded_scenes |
            step1_all_scenes |
            self.state.completed_step2
        )

        eligible = char_ids - excluded
        return self._get_bundle_representatives(eligible)

    def calculate_step3_pool(self) -> Set[int]:
        """
        Step 3: 실사 이미지 대체 씬 풀 (씬 단위)

        - Step 1, 2 처리된 씬 제외
        - 씬 단위 선택 (Prefix 규칙은 선택 시 적용)
        """
        # Step 1, 2 묶음 전체 제외
        step1_bundles = self._get_bundle_ids_for_scenes(
            self.state.step1_scenes | self.state.completed_step1
        )
        step2_bundles = self._get_bundle_ids_for_scenes(
            self.state.step2_scenes | self.state.completed_step2
        )

        step1_all = self._get_all_scenes_in_bundles(step1_bundles)
        step2_all = self._get_all_scenes_in_bundles(step2_bundles)

        excluded = (
            self.state.excluded_scenes |
            step1_all |
            step2_all |
            self.state.completed_step3
        )

        all_ids = set(self.scene_map.keys())
        return all_ids - excluded

    def calculate_step4_pool(self, duration_threshold: float = None, disable_filter: bool = False) -> Set[int]:
        """
        Step 4: 비디오 대체 씬 풀 (묶음 대표)

        - 묶음 duration 필터링 (v2.5: 사용자 조절 가능)
        - Step 1-3 처리된 씬 제외
        - 묶음 대표만 반환

        v2.5: duration_threshold 파라미터 추가, disable_filter 옵션 추가
              - duration_threshold: None이면 session_state 또는 기본값 5.0 사용
              - disable_filter: True이면 duration 필터 비활성화 (모든 묶음 포함)
        """
        # v2.5: session_state에서 사용자 설정 가져오기
        try:
            import streamlit as st
            if disable_filter is False:
                disable_filter = st.session_state.get("step4_show_all_bundles", True)
            if duration_threshold is None:
                duration_threshold = st.session_state.get("step4_max_duration", 5.0)
        except Exception:
            if duration_threshold is None:
                duration_threshold = 5.0

        # v2.5: 캐시 키에 필터 설정 포함 (설정 변경 시 재계산)
        cache_key = f"step4_pool_{duration_threshold}_{disable_filter}"
        if cache_key in self._pool_cache and self._pool_cache_valid:
            return self._pool_cache[cache_key]

        # 이전 Step 묶음들 수집
        prev_bundles = set()
        for step_scenes in [
            self.state.step1_scenes | self.state.completed_step1,
            self.state.step2_scenes | self.state.completed_step2,
            self.state.step3_scenes | self.state.completed_step3
        ]:
            prev_bundles.update(self._get_bundle_ids_for_scenes(step_scenes))

        prev_all_scenes = self._get_all_scenes_in_bundles(prev_bundles)

        excluded = (
            self.state.excluded_scenes |
            prev_all_scenes |
            self.state.completed_step4
        )

        eligible_bundles = set()
        excluded_count = 0

        for bundle_id, scene_ids in self.bundle_map.items():
            if not scene_ids:
                continue

            # 묶음 내 씬이 모두 제외 대상이면 건너뛰기
            if set(scene_ids).issubset(excluded):
                continue

            # v2.5: 필터 비활성화 시 모든 묶음 포함
            if disable_filter:
                eligible_bundles.add(bundle_id)
                continue

            # 묶음 duration 계산
            bundle_duration = self._get_bundle_duration(bundle_id)

            if bundle_duration <= duration_threshold:
                eligible_bundles.add(bundle_id)
            else:
                excluded_count += 1

        # 요약 로그 출력 (v2.9: 세션당 1회만 출력하여 중복 방지)
        import streamlit as st
        log_key = f"_step4pool_logged_{len(eligible_bundles)}_{disable_filter}_{excluded_count}"
        if log_key not in st.session_state:
            if disable_filter:
                print(f"[Step4Pool] 필터 해제 - 전체 {len(eligible_bundles)}개 묶음 포함")
            elif excluded_count > 0:
                print(f"[Step4Pool] {excluded_count}개 묶음 제외됨 (>{duration_threshold}초)")
            st.session_state[log_key] = True

        result = self._get_bundle_representatives_by_ids(eligible_bundles)

        # 결과 캐싱
        self._pool_cache[cache_key] = result
        return result

    def calculate_step5_pool(self) -> Set[int]:
        """
        Step 5: 인포그래픽 대체 씬 풀 (나머지)

        - Step 1-4 모두 처리/할당된 씬 제외
        - 나머지 전부
        """
        # 모든 이전 Step의 할당/완료 씬 수집
        all_assigned = (
            self.state.step1_scenes | self.state.completed_step1 |
            self.state.step2_scenes | self.state.completed_step2 |
            self.state.step3_scenes | self.state.completed_step3 |
            self.state.step4_scenes | self.state.completed_step4 |
            self.state.excluded_scenes |
            self.state.completed_step5
        )

        # 묶음 전체도 제외
        all_bundles = self._get_bundle_ids_for_scenes(all_assigned)
        all_bundle_scenes = self._get_all_scenes_in_bundles(all_bundles)

        excluded = all_assigned | all_bundle_scenes

        all_ids = set(self.scene_map.keys())
        return all_ids - excluded

    # ========================================
    # 묶음 헬퍼 함수
    # ========================================

    def _get_bundle_duration(self, bundle_id: int) -> float:
        """묶음의 총 duration 계산"""
        scene_ids = self.bundle_map.get(bundle_id, [])
        total = 0.0

        for sid in scene_ids:
            scene = self.scene_map.get(sid, {})
            duration = scene.get('duration', scene.get('duration_estimate', 0))
            if isinstance(duration, (int, float)):
                total += float(duration)

        return total

    def _get_bundle_representatives(self, scene_ids: Set[int]) -> Set[int]:
        """씬 집합에서 묶음 대표들만 추출"""
        bundle_ids = self._get_bundle_ids_for_scenes(scene_ids)
        return self._get_bundle_representatives_by_ids(bundle_ids)

    def _get_bundle_ids_for_scenes(self, scene_ids: Set[int]) -> Set[int]:
        """씬 집합이 속한 묶음 ID들 반환"""
        bundle_ids = set()
        for sid in scene_ids:
            scene = self.scene_map.get(sid, {})
            bid = scene.get('bundle_id', sid)
            bundle_ids.add(bid)
        return bundle_ids

    def _get_bundle_representatives_by_ids(self, bundle_ids: Set[int]) -> Set[int]:
        """묶음 ID들의 대표 씬 ID 반환"""
        representatives = set()

        for bid in bundle_ids:
            scene_ids = self.bundle_map.get(bid, [])
            if not scene_ids:
                continue

            # is_bundle_primary가 True인 씬 찾기
            primary_found = False
            for sid in scene_ids:
                scene = self.scene_map.get(sid, {})
                if scene.get('is_bundle_primary', False):
                    representatives.add(sid)
                    primary_found = True
                    break

            # primary가 없으면 첫 번째 씬
            if not primary_found and scene_ids:
                representatives.add(scene_ids[0])

        return representatives

    def _get_all_scenes_in_bundles(self, bundle_ids: Set[int]) -> Set[int]:
        """묶음들에 속한 모든 씬 ID 반환"""
        all_scenes = set()
        for bid in bundle_ids:
            all_scenes.update(self.bundle_map.get(bid, []))
        return all_scenes

    # ========================================
    # Step 3 Prefix 규칙
    # ========================================

    def get_prefix_scenes(self, scene_id: int) -> List[int]:
        """
        씬의 Prefix 씬들 반환 (Step 3용)

        묶음 내에서 선택된 씬 앞에 있는 모든 씬 반환
        예: 묶음 [1,2,3]에서 씬 3 선택 → [1,2] 반환
        """
        scene = self.scene_map.get(scene_id, {})
        bundle_id = scene.get('bundle_id', scene_id)
        bundle_scenes = self.bundle_map.get(bundle_id, [scene_id])

        try:
            idx = bundle_scenes.index(scene_id)
            return bundle_scenes[:idx]
        except ValueError:
            return []

    def expand_with_prefix_scenes(self, selected_ids: Set[int]) -> Set[int]:
        """선택된 씬들에 Prefix 씬들 추가"""
        expanded = set(selected_ids)

        for sid in selected_ids:
            prefix = self.get_prefix_scenes(sid)
            expanded.update(prefix)

        return expanded

    def get_scenes_affected_by_selection(self, selected_ids: Set[int], step: int) -> Dict:
        """
        선택으로 인해 영향받는 씬 정보 반환

        Returns:
            {
                "direct": Set[int],      # 직접 선택된 씬
                "prefix": Set[int],      # Prefix로 추가된 씬 (Step 3)
                "bundle": Set[int],      # 묶음 확장된 씬 (Step 1,2,4)
                "total": Set[int]        # 전체 영향받는 씬
            }
        """
        result = {
            "direct": set(selected_ids),
            "prefix": set(),
            "bundle": set(),
            "total": set(selected_ids)
        }

        step_config = STEP_CONFIG.get(step, {})
        unit = step_config.get("unit", "scene")

        if unit == "scene_with_prefix":
            # Step 3: Prefix 규칙 적용
            expanded = self.expand_with_prefix_scenes(selected_ids)
            result["prefix"] = expanded - selected_ids
            result["total"] = expanded

        elif unit == "bundle":
            # Step 1, 2, 4: 묶음 전체 확장
            bundle_ids = self._get_bundle_ids_for_scenes(selected_ids)
            all_bundle_scenes = self._get_all_scenes_in_bundles(bundle_ids)
            result["bundle"] = all_bundle_scenes - selected_ids
            result["total"] = all_bundle_scenes

        return result

    # ========================================
    # 씬 할당/완료 관리
    # ========================================

    def _invalidate_pool_cache(self):
        """v2.4: 풀 계산 캐시 무효화 (상태 변경 시 호출)"""
        self._pool_cache.clear()
        # v2.9: Step4Pool 로그 플래그도 리셋
        try:
            import streamlit as st
            keys = [k for k in st.session_state if k.startswith("_step4pool_logged_")]
            for k in keys:
                del st.session_state[k]
        except Exception:
            pass

    def assign_to_step(self, step: int, scene_ids: Set[int], apply_expansion: bool = True):
        """
        씬들을 Step에 할당

        Args:
            step: Step 번호 (1-5)
            scene_ids: 할당할 씬 ID 집합
            apply_expansion: True면 묶음/Prefix 확장 적용
        """
        self._invalidate_pool_cache()  # v2.4: 캐시 무효화

        if apply_expansion:
            affected = self.get_scenes_affected_by_selection(scene_ids, step)
            final_ids = affected["total"]
        else:
            final_ids = scene_ids

        now = datetime.now().isoformat()

        # scenes.json 데이터 업데이트
        step_status = STEP_CONFIG.get(step, {}).get("status", SceneStatus.PENDING)
        for sid in final_ids:
            scene = self.scene_map.get(sid)
            if scene:
                scene['scene_status'] = step_status.value
                scene['workflow_step_assigned'] = step
                scene['workflow_assigned_at'] = now

        # 상태 업데이트
        step_attr = f"step{step}_scenes"
        getattr(self.state, step_attr).update(final_ids)
        self.state.updated_at = now

    def mark_completed(self, step: int, scene_ids: Set[int]):
        """씬들을 완료로 표시"""
        self._invalidate_pool_cache()  # v2.4: 캐시 무효화
        now = datetime.now().isoformat()

        for sid in scene_ids:
            scene = self.scene_map.get(sid)
            if scene:
                scene['workflow_completed_at'] = now

        # assigned에서 completed로 이동
        step_scenes_attr = f"step{step}_scenes"
        completed_attr = f"completed_step{step}"

        getattr(self.state, step_scenes_attr).difference_update(scene_ids)
        getattr(self.state, completed_attr).update(scene_ids)

        self.state.updated_at = now

    def exclude_scenes(self, scene_ids: Set[int]):
        """씬들을 워크플로우에서 제외"""
        self._invalidate_pool_cache()  # v2.4: 캐시 무효화
        now = datetime.now().isoformat()

        for sid in scene_ids:
            scene = self.scene_map.get(sid)
            if scene:
                scene['scene_status'] = SceneStatus.EXCLUDED.value
                scene['workflow_assigned_at'] = now

        self.state.excluded_scenes.update(scene_ids)
        self.state.updated_at = now

    def unassign_from_step(self, step: int, scene_ids: Set[int]):
        """씬들의 할당 해제"""
        now = datetime.now().isoformat()

        for sid in scene_ids:
            scene = self.scene_map.get(sid)
            if scene:
                scene['scene_status'] = SceneStatus.PENDING.value
                scene['workflow_step_assigned'] = None
                scene['workflow_assigned_at'] = None

        step_attr = f"step{step}_scenes"
        getattr(self.state, step_attr).difference_update(scene_ids)
        self.state.updated_at = now

    # ========================================
    # 통계
    # ========================================

    def get_statistics(self) -> Dict:
        """워크플로우 통계 반환"""
        total = len(self.scenes)

        stats = {
            'total': total,
            'excluded': len(self.state.excluded_scenes),
            'current_step': self.state.current_step,
        }

        for step in range(1, 6):
            assigned_attr = f"step{step}_scenes"
            completed_attr = f"completed_step{step}"

            assigned = getattr(self.state, assigned_attr)
            completed = getattr(self.state, completed_attr)

            stats[f'step{step}'] = {
                'assigned': len(assigned),
                'completed': len(completed),
                'pending': len(assigned - completed),
                'pool': len(getattr(self, f'calculate_step{step}_pool')())
            }

        return stats

    def get_step_summary(self, step: int) -> Dict:
        """특정 Step의 상세 요약"""
        pool = getattr(self, f'calculate_step{step}_pool')()
        assigned = getattr(self.state, f'step{step}_scenes')
        completed = getattr(self.state, f'completed_step{step}')

        step_config = STEP_CONFIG.get(step, {})

        return {
            'step': step,
            'name': step_config.get('name', f'Step {step}'),
            'emoji': step_config.get('emoji', ''),
            'color': step_config.get('color', '#6B7280'),
            'unit': step_config.get('unit', 'scene'),
            'pool_count': len(pool),
            'assigned_count': len(assigned),
            'completed_count': len(completed),
            'pending_count': len(assigned - completed),
            'pool_ids': sorted(pool),
            'assigned_ids': sorted(assigned),
            'completed_ids': sorted(completed)
        }

    # ========================================
    # 저장/로드
    # ========================================

    def save(self):
        """워크플로우 상태 저장"""
        save_path = self.project_path / "data" / "workflow_state.json"
        save_path.parent.mkdir(parents=True, exist_ok=True)

        now = datetime.now().isoformat()
        if not self.state.created_at:
            self.state.created_at = now
        self.state.updated_at = now

        data = {
            'version': '1.0',
            'step1_scenes': sorted(self.state.step1_scenes),
            'step2_scenes': sorted(self.state.step2_scenes),
            'step3_scenes': sorted(self.state.step3_scenes),
            'step4_scenes': sorted(self.state.step4_scenes),
            'step5_scenes': sorted(self.state.step5_scenes),
            'completed_step1': sorted(self.state.completed_step1),
            'completed_step2': sorted(self.state.completed_step2),
            'completed_step3': sorted(self.state.completed_step3),
            'completed_step4': sorted(self.state.completed_step4),
            'completed_step5': sorted(self.state.completed_step5),
            'excluded_scenes': sorted(self.state.excluded_scenes),
            'current_step': self.state.current_step,
            'created_at': self.state.created_at,
            'updated_at': self.state.updated_at
        }

        with open(save_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def save_scenes(self):
        """scenes.json 저장"""
        scenes_path = self.project_path / "analysis" / "scenes.json"

        if scenes_path.exists():
            with open(scenes_path, 'w', encoding='utf-8') as f:
                json.dump(self.scenes, f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, project_path: Path, scenes: List[Dict]) -> 'WorkflowManager':
        """워크플로우 상태 로드"""
        manager = cls(project_path, scenes)

        load_path = Path(project_path) / "data" / "workflow_state.json"
        if load_path.exists():
            try:
                with open(load_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                manager.state.step1_scenes = set(data.get('step1_scenes', []))
                manager.state.step2_scenes = set(data.get('step2_scenes', []))
                manager.state.step3_scenes = set(data.get('step3_scenes', []))
                manager.state.step4_scenes = set(data.get('step4_scenes', []))
                manager.state.step5_scenes = set(data.get('step5_scenes', []))
                manager.state.completed_step1 = set(data.get('completed_step1', []))
                manager.state.completed_step2 = set(data.get('completed_step2', []))
                manager.state.completed_step3 = set(data.get('completed_step3', []))
                manager.state.completed_step4 = set(data.get('completed_step4', []))
                manager.state.completed_step5 = set(data.get('completed_step5', []))
                manager.state.excluded_scenes = set(data.get('excluded_scenes', []))
                manager.state.current_step = data.get('current_step', 1)
                manager.state.created_at = data.get('created_at')
                manager.state.updated_at = data.get('updated_at')
            except (json.JSONDecodeError, IOError):
                pass

        return manager


def get_workflow_manager(project_path: Path, scenes: List[Dict]) -> WorkflowManager:
    """워크플로우 관리자 인스턴스 반환 (with 캐싱)"""
    import streamlit as st

    cache_key = f"workflow_manager_{project_path}"

    if cache_key not in st.session_state:
        st.session_state[cache_key] = WorkflowManager.load(project_path, scenes)

    return st.session_state[cache_key]


def clear_workflow_manager_cache(project_path: Path = None):
    """워크플로우 관리자 캐시 클리어"""
    import streamlit as st

    if project_path:
        cache_key = f"workflow_manager_{project_path}"
        if cache_key in st.session_state:
            del st.session_state[cache_key]
    else:
        # 모든 워크플로우 캐시 클리어
        keys_to_delete = [k for k in st.session_state if k.startswith("workflow_manager_")]
        for k in keys_to_delete:
            del st.session_state[k]
