# -*- coding: utf-8 -*-
"""
Claude Code 프롬프트 최적화 v1.0

scenes.json 토큰 초과 방지를 위한 최적화된 프롬프트 생성

핵심 규칙:
1. scenes.json 전체 읽기 금지 (52,522 토큰 > 25,000 제한)
2. Grep 또는 offset/limit로 필요한 씬만 읽기
3. 5개 묶음 처리 후 바로 Update
4. Task()/백그라운드 에이전트 금지
5. Python 스크립트 생성 금지
6. 질문 금지, 즉시 실행
"""

import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Any

from .claude_code_config import get_bundle_size, get_claude_code_config


# ═══════════════════════════════════════════════════════════════════
# 최적화된 Claude Code 프롬프트 템플릿
# ═══════════════════════════════════════════════════════════════════

OPTIMIZED_PROMPT_TEMPLATE = '''# Claude Code 씬 분석 - 최적화 버전

## 필수 규칙 (반드시 준수!)

### 1. 파일 읽기 제한
- scenes.json 전체 읽기 **금지** (토큰 초과 발생!)
- Read tool 사용 시 **offset/limit 필수** 지정
- 한 번에 최대 100줄만 읽기

### 2. 처리 방식
- **5개 묶음**씩 처리 후 **즉시 Update**
- 모든 씬 분석 후 한 번에 저장하지 말 것!
- 처리 완료된 씬은 바로 scenes.json에 반영

### 3. 금지 사항
- Task() 또는 백그라운드 에이전트 사용 금지
- Python 스크립트 작성/실행 금지
- 추가 질문 금지 - 즉시 실행할 것

---

## 작업 정보

- **프로젝트 경로**: `{project_path}`
- **scenes.json 경로**: `{scenes_json_path}`
- **bundle_info 경로**: `{bundle_info_path}`
- **총 씬 수**: {total_scenes}개
- **총 묶음 수**: {total_bundles}개
- **묶음 크기**: {bundle_size}개 씬/묶음

---

## 실행 단계

### Step 1: bundle_info 파일 읽기
먼저 묶음 정보 파일을 읽으세요:
```
{bundle_info_path}
```

이 파일에는 각 묶음의 scene_id 목록이 있습니다.

### Step 2: 묶음별 처리 (5개씩)

각 묶음에 대해:

1. **씬 데이터 읽기** (Grep 사용)
   ```
   Grep pattern="scene_id": {scene_id}" path="{scenes_json_path}"
   ```

2. **프롬프트 생성** (15개 필드)
   - image_prompt, image_prompt_en
   - background_prompt, background_prompt_en
   - character_prompt, character_prompt_en
   - video_prompt_character, video_prompt_full
   - visual_elements, direction_guide
   - camera_suggestion, location, mood
   - characters, image_prompt_korean_text

3. **즉시 Update** (Edit tool 사용)
   - 5개 묶음 처리 후 scenes.json 업데이트
   - 전체 완료까지 기다리지 말 것!

### Step 3: 진행 상황 보고

매 5개 묶음 처리 후:
- "묶음 X-Y 처리 완료 (Z개 씬)"
- 오류 발생 시 해당 씬 ID 기록

---

## 출력 필드 상세

각 씬에 추가할 필드:

```json
{{
  "image_prompt": "한글 이미지 프롬프트",
  "image_prompt_en": "English image prompt for AI generation",
  "image_prompt_korean_text": "한글 텍스트 오버레이",
  "background_prompt": "배경만 묘사 (캐릭터 제외)",
  "background_prompt_en": "Background description in English",
  "character_prompt": "캐릭터 외모, 표정, 동작",
  "character_prompt_en": "Character description in English",
  "video_prompt_character": "캐릭터 동작 중심 비디오 프롬프트",
  "video_prompt_full": "전체 씬 비디오 프롬프트",
  "visual_elements": ["요소1", "요소2"],
  "direction_guide": "연출 가이드",
  "camera_suggestion": "카메라 앵글/움직임",
  "location": "장소",
  "mood": "분위기",
  "characters": ["캐릭터1", "캐릭터2"]
}}
```

---

## 묶음 목록

{bundle_list}

---

## 시작

1. `{bundle_info_path}` 읽기
2. 첫 5개 묶음부터 처리 시작
3. 5개 묶음마다 scenes.json Update
4. 모든 묶음 처리 완료까지 반복

**즉시 시작하세요. 질문하지 마세요.**
'''


# ═══════════════════════════════════════════════════════════════════
# Bundle Info 생성
# ═══════════════════════════════════════════════════════════════════

def generate_bundle_info_for_claude_code(
    scenes: List[Dict],
    output_dir: str,
    bundle_size: int = None
) -> Dict[str, Any]:
    """
    Claude Code용 bundle_info_claude_code.json 생성

    Args:
        scenes: 전체 씬 목록
        output_dir: 출력 디렉토리
        bundle_size: 묶음 크기 (None이면 사용자 설정 사용)

    Returns:
        생성된 bundle_info 데이터
    """
    if bundle_size is None:
        bundle_size = get_bundle_size()

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # 씬 정렬
    sorted_scenes = sorted(scenes, key=lambda x: x.get("scene_id", 0))

    # 묶음 생성
    bundles = []
    bundle_id = 1

    for i in range(0, len(sorted_scenes), bundle_size):
        bundle_scenes = sorted_scenes[i:i + bundle_size]

        bundle = {
            "bundle_id": bundle_id,
            "scene_ids": [s.get("scene_id") for s in bundle_scenes],
            "scene_count": len(bundle_scenes),
            "line_hint": {
                "start": i * 50,  # 대략적인 줄 번호 힌트
                "end": (i + len(bundle_scenes)) * 50
            }
        }

        bundles.append(bundle)
        bundle_id += 1

    # bundle_info 데이터
    bundle_info = {
        "version": "1.0",
        "generated_at": datetime.now().isoformat(),
        "config": {
            "bundle_size": bundle_size,
            "process_batch_size": 5,  # 5개 묶음씩 처리
            "max_read_lines": 100      # 한 번에 최대 100줄
        },
        "summary": {
            "total_scenes": len(sorted_scenes),
            "total_bundles": len(bundles),
            "scenes_per_bundle": bundle_size
        },
        "bundles": bundles,
        "rules": {
            "no_full_file_read": True,
            "use_grep_or_offset": True,
            "update_every_n_bundles": 5,
            "no_background_agents": True,
            "no_python_scripts": True,
            "no_questions": True
        }
    }

    # 파일 저장
    bundle_info_path = output_path / "bundle_info_claude_code.json"
    with open(bundle_info_path, 'w', encoding='utf-8') as f:
        json.dump(bundle_info, f, ensure_ascii=False, indent=2)

    print(f"[BundleInfo] bundle_info_claude_code.json 생성: {bundle_info_path}")
    print(f"[BundleInfo] 총 씬: {len(sorted_scenes)}개, 묶음: {len(bundles)}개")

    return {
        "path": str(bundle_info_path),
        "data": bundle_info
    }


# ═══════════════════════════════════════════════════════════════════
# 최적화된 프롬프트 생성
# ═══════════════════════════════════════════════════════════════════

def generate_optimized_claude_code_prompt(
    project_path: str,
    scenes_json_path: str,
    bundle_info_path: str,
    bundle_info_data: Dict
) -> str:
    """
    최적화된 Claude Code 프롬프트 생성

    Args:
        project_path: 프로젝트 경로
        scenes_json_path: scenes.json 경로
        bundle_info_path: bundle_info_claude_code.json 경로
        bundle_info_data: bundle_info 데이터

    Returns:
        최적화된 프롬프트 문자열
    """
    bundles = bundle_info_data.get("bundles", [])
    summary = bundle_info_data.get("summary", {})
    config = bundle_info_data.get("config", {})

    # 묶음 목록 생성 (요약)
    bundle_list_lines = []
    for i, bundle in enumerate(bundles):
        scene_ids = bundle.get("scene_ids", [])
        scene_ids_str = ", ".join(str(sid) for sid in scene_ids[:5])
        if len(scene_ids) > 5:
            scene_ids_str += f" ... (+{len(scene_ids) - 5}개)"

        bundle_list_lines.append(
            f"- 묶음 {bundle['bundle_id']}: 씬 [{scene_ids_str}]"
        )

    bundle_list = "\n".join(bundle_list_lines)

    prompt = OPTIMIZED_PROMPT_TEMPLATE.format(
        project_path=project_path,
        scenes_json_path=scenes_json_path,
        bundle_info_path=bundle_info_path,
        total_scenes=summary.get("total_scenes", 0),
        total_bundles=summary.get("total_bundles", 0),
        bundle_size=config.get("bundle_size", 5),
        bundle_list=bundle_list
    )

    return prompt


def prepare_claude_code_analysis(
    scenes: List[Dict],
    project_path: str,
    output_dir: str = None,
    bundle_size: int = None
) -> Dict[str, Any]:
    """
    Claude Code 분석 준비 (통합 함수)

    Args:
        scenes: 전체 씬 목록
        project_path: 프로젝트 경로
        output_dir: 출력 디렉토리 (None이면 project_path/logs/claude_code)
        bundle_size: 묶음 크기

    Returns:
        준비 결과 (프롬프트 경로, bundle_info 경로 등)
    """
    project_path = Path(project_path)

    if output_dir is None:
        output_dir = project_path / "logs" / "claude_code"
    else:
        output_dir = Path(output_dir)

    output_dir.mkdir(parents=True, exist_ok=True)

    # scenes.json 경로
    scenes_json_path = project_path / "analysis" / "scenes.json"

    # 1. bundle_info 생성
    bundle_info_result = generate_bundle_info_for_claude_code(
        scenes=scenes,
        output_dir=str(output_dir),
        bundle_size=bundle_size
    )

    # 2. 최적화된 프롬프트 생성
    prompt = generate_optimized_claude_code_prompt(
        project_path=str(project_path),
        scenes_json_path=str(scenes_json_path),
        bundle_info_path=bundle_info_result["path"],
        bundle_info_data=bundle_info_result["data"]
    )

    # 3. 프롬프트 파일 저장
    prompt_file = output_dir / "optimized_prompt.md"
    with open(prompt_file, 'w', encoding='utf-8') as f:
        f.write(prompt)

    print(f"[Prepare] 최적화 프롬프트 저장: {prompt_file}")

    # 4. 결과 반환
    result = {
        "status": "ready",
        "project_path": str(project_path),
        "scenes_json_path": str(scenes_json_path),
        "bundle_info_path": bundle_info_result["path"],
        "prompt_path": str(prompt_file),
        "summary": bundle_info_result["data"]["summary"],
        "config": bundle_info_result["data"]["config"],
        "rules": bundle_info_result["data"]["rules"]
    }

    # 결과 메타 저장
    meta_file = output_dir / "analysis_meta.json"
    with open(meta_file, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"[Prepare] 메타 정보 저장: {meta_file}")

    return result


# ═══════════════════════════════════════════════════════════════════
# 간편 사용 함수
# ═══════════════════════════════════════════════════════════════════

def get_optimized_prompt_for_video(video_path: str) -> Optional[str]:
    """
    비디오 경로에서 최적화된 프롬프트 로드 또는 생성

    Args:
        video_path: 비디오 프로젝트 경로

    Returns:
        프롬프트 내용 또는 None
    """
    video_path = Path(video_path)
    prompt_file = video_path / "logs" / "claude_code" / "optimized_prompt.md"

    if prompt_file.exists():
        with open(prompt_file, 'r', encoding='utf-8') as f:
            return f.read()

    # 프롬프트가 없으면 생성 시도
    scenes_json = video_path / "analysis" / "scenes.json"
    if scenes_json.exists():
        with open(scenes_json, 'r', encoding='utf-8') as f:
            scenes = json.load(f)

        result = prepare_claude_code_analysis(
            scenes=scenes,
            project_path=str(video_path)
        )

        return prompt_file.read_text(encoding='utf-8') if prompt_file.exists() else None

    return None


if __name__ == "__main__":
    import sys

    # 테스트용 더미 씬
    test_scenes = [
        {"scene_id": i, "script": f"씬 {i}의 대사입니다.", "srt_duration": 3.5}
        for i in range(1, 101)
    ]

    if len(sys.argv) > 1:
        project_path = sys.argv[1]
    else:
        project_path = "./test_project"

    result = prepare_claude_code_analysis(
        scenes=test_scenes,
        project_path=project_path
    )

    print(f"\nResult: {json.dumps(result, indent=2, ensure_ascii=False, default=str)}")
