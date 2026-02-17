# -*- coding: utf-8 -*-
"""
인포그래픽 씬 JSON 내보내기 유틸리티
v1.0: 선택된 씬에서 필요한 필드만 추출하여 JSON 다운로드

주요 기능:
- 선택된 씬만 추출
- 지정된 6개 필드만 포함
- 기존 scenes.json 변경 없음 (읽기 전용)
"""

import json
from datetime import datetime
from typing import List, Dict, Set


# 추출할 필드 목록 (이것만 포함)
INFOGRAPHIC_EXPORT_FIELDS = [
    "scene_id",
    "start_time",
    "end_time",
    "script_ko",
    "image_prompt_en",
    "visual_elements"
]


def extract_infographic_scenes(
    scenes: List[Dict],
    selected_scene_ids: Set[int]
) -> List[Dict]:
    """
    선택된 씬들에서 인포그래픽용 필드만 추출

    Args:
        scenes: 전체 씬 데이터 (scenes.json)
        selected_scene_ids: 선택된 씬 ID 집합

    Returns:
        추출된 씬 데이터 리스트
    """
    extracted_scenes = []

    for scene in scenes:
        # scene_id 추출 (여러 키 이름 지원)
        scene_id = scene.get("scene_id", scene.get("id", 0))

        # 선택된 씬만 처리
        if scene_id not in selected_scene_ids:
            continue

        # 필요한 필드만 추출
        extracted_scene = {}

        for field in INFOGRAPHIC_EXPORT_FIELDS:
            if field in scene:
                extracted_scene[field] = scene[field]
            elif field == "scene_id":
                # scene_id는 id 필드에서도 가져올 수 있음
                extracted_scene[field] = scene_id
            else:
                # 필드가 없으면 기본값 설정
                if field == "visual_elements":
                    extracted_scene[field] = []
                elif field in ["script_ko", "image_prompt_en"]:
                    extracted_scene[field] = ""
                else:
                    extracted_scene[field] = None

        extracted_scenes.append(extracted_scene)

    # scene_id 순으로 정렬
    extracted_scenes.sort(key=lambda x: x.get("scene_id", 0))

    print(f"[Infographic Export] ✅ {len(extracted_scenes)}개 씬 추출 완료")
    print(f"[Infographic Export]    씬 ID: {[s['scene_id'] for s in extracted_scenes]}")
    print(f"[Infographic Export]    필드: {INFOGRAPHIC_EXPORT_FIELDS}")

    return extracted_scenes


def create_infographic_export_json(
    scenes: List[Dict],
    selected_scene_ids: Set[int],
    video_name: str = ""
) -> str:
    """
    인포그래픽용 JSON 문자열 생성

    Args:
        scenes: 전체 씬 데이터
        selected_scene_ids: 선택된 씬 ID 집합
        video_name: 영상 이름 (메타데이터용)

    Returns:
        JSON 문자열
    """
    # 씬 데이터 추출
    extracted_scenes = extract_infographic_scenes(scenes, selected_scene_ids)

    # 내보내기 데이터 구조
    export_data = {
        "export_info": {
            "type": "infographic_scenes",
            "video_name": video_name,
            "total_scenes": len(extracted_scenes),
            "scene_ids": [s["scene_id"] for s in extracted_scenes],
            "exported_fields": INFOGRAPHIC_EXPORT_FIELDS,
            "exported_at": datetime.now().isoformat()
        },
        "scenes": extracted_scenes
    }

    # JSON 문자열로 변환 (한글 유지, 들여쓰기)
    json_str = json.dumps(
        export_data,
        ensure_ascii=False,
        indent=2
    )

    return json_str


def get_infographic_export_filename(video_name: str, scene_ids: List[int]) -> str:
    """다운로드 파일명 생성"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # 비디오 이름 정리 (파일명에 부적합한 문자 제거)
    safe_video_name = "".join(c for c in video_name if c.isalnum() or c in ('_', '-'))
    if not safe_video_name:
        safe_video_name = "video"

    # 씬 범위 문자열
    sorted_ids = sorted(scene_ids)
    if len(sorted_ids) <= 3:
        scene_str = "_".join(str(s) for s in sorted_ids)
    else:
        scene_str = f"{sorted_ids[0]}-{sorted_ids[-1]}"

    return f"infographic_scenes_{safe_video_name}_{scene_str}_{timestamp}.json"
