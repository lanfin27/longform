# -*- coding: utf-8 -*-
"""
씬 묶음 유틸리티 (Scene Merger) v1.0

기능:
- N개의 연속된 씬을 하나로 묶음
- 타임스탬프: 첫 씬 시작 → 마지막 씬 끝
- 텍스트: 공백으로 연결

예시:
    입력: 씬 1, 씬 2, 씬 3 (merge_count=3)
    출력: 묶인 씬 1개 (타임스탬프: 씬1 시작 ~ 씬3 끝, 텍스트: 씬1 + 씬2 + 씬3)
"""

from typing import List, Dict
import copy


def merge_scenes_by_count(scenes: List[Dict], merge_count: int = 2) -> List[Dict]:
    """
    N개의 연속된 씬을 하나로 묶음

    Args:
        scenes: 원본 씬 리스트
        merge_count: 묶을 씬 개수 (1이면 변경 없음)

    Returns:
        묶인 씬 리스트 (새 리스트, 원본 변경 없음)
    """
    if merge_count <= 1:
        return copy.deepcopy(scenes)

    if not scenes:
        return []

    merged = []
    total_scenes = len(scenes)

    print(f"[SceneMerger] 시작: {total_scenes}개 씬을 {merge_count}개씩 묶음")

    i = 0
    merged_scene_id = 1

    while i < total_scenes:
        # 묶을 씬들 선택 (마지막 그룹은 남은 것 전부)
        group = scenes[i:i + merge_count]

        if len(group) == 1:
            # 씬 1개면 그대로 복사
            new_scene = copy.deepcopy(group[0])
            new_scene['scene_id'] = merged_scene_id
        else:
            # 여러 씬 묶기
            new_scene = _merge_group(group, merged_scene_id)

        merged.append(new_scene)
        merged_scene_id += 1
        i += merge_count

    print(f"[SceneMerger] ✅ 완료: {total_scenes}개 → {len(merged)}개 씬")

    return merged


def _merge_group(group: List[Dict], new_scene_id: int) -> Dict:
    """
    씬 그룹을 하나의 씬으로 병합

    Args:
        group: 병합할 씬 리스트
        new_scene_id: 새 씬 ID

    Returns:
        병합된 씬 딕셔너리
    """
    first_scene = group[0]
    last_scene = group[-1]

    # 타임스탬프: 첫 씬 시작 ~ 마지막 씬 끝
    start_time = _get_start_time(first_scene)
    end_time = _get_end_time(last_scene)

    # 텍스트: 공백으로 연결
    texts = [s.get('text', '').strip() for s in group if s.get('text', '').strip()]
    merged_text = ' '.join(texts)

    # 원본 씬 ID들 기록 (디버깅용)
    original_ids = [s.get('scene_id', '?') for s in group]

    return {
        'scene_id': new_scene_id,
        'start_time': start_time,
        'end_time': end_time,
        'text': merged_text,
        '_merged_from': original_ids  # 디버깅용 메타데이터
    }


def _get_start_time(scene: Dict) -> float:
    """씬의 시작 시간 추출 (다양한 키 이름 지원)"""
    for key in ['start_time', 'start', 'start_sec', '_start_seconds']:
        if key in scene and scene[key] is not None:
            return float(scene[key])
    return 0.0


def _get_end_time(scene: Dict) -> float:
    """씬의 종료 시간 추출 (다양한 키 이름 지원)"""
    for key in ['end_time', 'end', 'end_sec', '_end_seconds']:
        if key in scene and scene[key] is not None:
            return float(scene[key])
    return 0.0


def get_merge_preview(scenes: List[Dict], merge_count: int) -> Dict:
    """
    묶음 미리보기 정보 반환

    Args:
        scenes: 씬 리스트
        merge_count: 묶을 씬 개수

    Returns:
        미리보기 정보 딕셔너리
    """
    if not scenes or merge_count <= 1:
        return {
            'original_count': len(scenes) if scenes else 0,
            'merged_count': len(scenes) if scenes else 0,
            'reduction_percent': 0
        }

    original_count = len(scenes)
    # 올림 나눗셈: (n + d - 1) // d
    merged_count = (original_count + merge_count - 1) // merge_count
    reduction = round((1 - merged_count / original_count) * 100, 1)

    return {
        'original_count': original_count,
        'merged_count': merged_count,
        'reduction_percent': reduction
    }


# 테스트 코드
if __name__ == "__main__":
    # 테스트 데이터
    test_scenes = [
        {'scene_id': 1, 'start_time': 0.0, 'end_time': 2.5, 'text': '첫 번째 자막입니다.'},
        {'scene_id': 2, 'start_time': 2.5, 'end_time': 5.0, 'text': '두 번째 자막입니다.'},
        {'scene_id': 3, 'start_time': 5.0, 'end_time': 7.5, 'text': '세 번째 자막입니다.'},
        {'scene_id': 4, 'start_time': 7.5, 'end_time': 10.0, 'text': '네 번째 자막입니다.'},
        {'scene_id': 5, 'start_time': 10.0, 'end_time': 12.5, 'text': '다섯 번째 자막입니다.'},
    ]

    print("=" * 60)
    print("SceneMerger 테스트")
    print("=" * 60)

    for merge_count in [1, 2, 3]:
        print(f"\n[merge_count = {merge_count}]")
        preview = get_merge_preview(test_scenes, merge_count)
        print(f"미리보기: {preview['original_count']}개 → {preview['merged_count']}개 ({preview['reduction_percent']}% 감소)")

        merged = merge_scenes_by_count(test_scenes, merge_count)
        for scene in merged:
            print(f"  씬 {scene['scene_id']}: {scene['start_time']:.1f}s ~ {scene['end_time']:.1f}s")
            print(f"    텍스트: {scene['text'][:50]}...")
            if '_merged_from' in scene:
                print(f"    (원본: {scene['_merged_from']})")
