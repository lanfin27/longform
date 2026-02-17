# -*- coding: utf-8 -*-
"""
배치별 Claude Code 프롬프트 생성 v1.0

배치 분석용 최적화된 프롬프트 생성:
- 경량화된 입력 사용
- 출력 형식 명확히 지정
- 토큰 초과 방지
"""

import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional


# ═══════════════════════════════════════════════════════════════════
# 배치 프롬프트 템플릿
# ═══════════════════════════════════════════════════════════════════

BATCH_PROMPT_TEMPLATE = '''# 씬 분석 배치 {batch_idx}/{total_batches}

## 최적화 지침 (반드시 준수)

### 1. 입력 형식
- 이 배치에는 **{scene_count}개 씬**만 포함됨
- 각 씬에는 `scene_id`, `script`, `duration` 등 필수 필드만 있음
- 입력 파일: `{input_file}`

### 2. 출력 형식 (중요!)
- **한 번에 모든 씬 결과를 JSON 배열로 출력**
- 씬별로 개별 Update 하지 말 것!
- 출력 파일: `{output_file}`
- 형식:
```json
[
  {{"scene_id": 1, "image_prompt": "...", "image_prompt_en": "...", ...}},
  {{"scene_id": 2, "image_prompt": "...", "image_prompt_en": "...", ...}}
]
```

### 3. 필수 출력 필드 (15개)
각 씬에 다음 필드를 생성:

| 필드 | 설명 |
|------|------|
| `scene_id` | 원본 scene_id 그대로 |
| `image_prompt` | 한글 이미지 프롬프트 |
| `image_prompt_en` | 영어 이미지 프롬프트 |
| `image_prompt_korean_text` | 한글 텍스트 오버레이용 |
| `background_prompt` | 한글 배경 프롬프트 |
| `background_prompt_en` | 영어 배경 프롬프트 |
| `character_prompt` | 한글 캐릭터 프롬프트 |
| `character_prompt_en` | 영어 캐릭터 프롬프트 |
| `video_prompt_character` | 캐릭터 비디오 프롬프트 |
| `video_prompt_full` | 전체 비디오 프롬프트 |
| `visual_elements` | 시각 요소 배열 |
| `direction_guide` | 연출 가이드 |
| `camera_suggestion` | 카메라 제안 |
| `location` | 장소 |
| `mood` | 분위기 |
| `characters` | 등장 캐릭터 배열 |

### 4. 작업 순서

1. **프롬프트 템플릿 읽기** (선택사항)
   - 템플릿 경로: `{template_path}`
   - 기존 프롬프트 생성 규칙 참고

2. **입력 파일 읽기**
   - `{input_file}` 파일을 읽어 {scene_count}개 씬 확인

3. **씬별 분석 수행**
   - 각 씬의 `script` 필드를 분석
   - 15개 필수 필드 생성

4. **결과 저장**
   - 모든 결과를 JSON 배열로 `{output_file}`에 저장
   - **scenes.json 직접 수정 금지!**

---

## 분석 가이드라인

### 이미지 프롬프트 (image_prompt, image_prompt_en)
- 씬의 시각적 표현을 위한 상세한 설명
- 장면, 인물, 배경, 조명, 분위기 포함
- 영어 버전은 Stable Diffusion/DALL-E 호환 스타일

### 배경 프롬프트 (background_prompt, background_prompt_en)
- 캐릭터 제외한 순수 배경만 설명
- 장소, 시간대, 날씨, 분위기 포함

### 캐릭터 프롬프트 (character_prompt, character_prompt_en)
- 등장 캐릭터의 외모, 표정, 동작 설명
- 캐릭터가 없으면 빈 문자열

### 비디오 프롬프트
- `video_prompt_character`: 캐릭터 동작 중심
- `video_prompt_full`: 전체 씬 동영상화

### 메타데이터
- `visual_elements`: ["요소1", "요소2", ...]
- `direction_guide`: 연출 의도 설명
- `camera_suggestion`: 카메라 앵글/움직임
- `location`: 장소명
- `mood`: 분위기 키워드
- `characters`: ["캐릭터1", "캐릭터2", ...]

---

## 시작

1. 먼저 입력 파일을 읽으세요: `{input_file}`
2. {scene_count}개 씬을 분석하세요
3. 결과를 출력 파일에 저장하세요: `{output_file}`

**주의**: scenes.json을 직접 수정하지 마세요!
'''


def generate_batch_prompt(
    batch_idx: int,
    total_batches: int,
    scene_count: int,
    input_file: str,
    output_file: str,
    template_path: str = "",
    output_dir: Optional[Path] = None
) -> str:
    """
    배치별 프롬프트 생성

    Args:
        batch_idx: 배치 인덱스
        total_batches: 총 배치 수
        scene_count: 이 배치의 씬 수
        input_file: 입력 파일 경로
        output_file: 출력 파일 경로
        template_path: 프롬프트 템플릿 경로 (선택)
        output_dir: 프롬프트 파일 저장 디렉토리 (선택)

    Returns:
        프롬프트 내용 (str) 또는 저장된 파일 경로
    """
    prompt_content = BATCH_PROMPT_TEMPLATE.format(
        batch_idx=batch_idx + 1,  # 1-indexed for display
        total_batches=total_batches,
        scene_count=scene_count,
        input_file=input_file,
        output_file=output_file,
        template_path=template_path or "(템플릿 없음 - 기본 규칙 사용)"
    )

    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        prompt_file = output_dir / f"prompt_batch_{batch_idx:03d}.md"
        with open(prompt_file, 'w', encoding='utf-8') as f:
            f.write(prompt_content)
        return str(prompt_file)

    return prompt_content


def generate_all_batch_prompts(
    batch_info: dict,
    template_path: str = "",
    output_dir: Optional[str] = None
) -> List[str]:
    """
    모든 배치 프롬프트 생성

    Args:
        batch_info: prepare_batch_analysis() 결과
        template_path: 프롬프트 템플릿 경로
        output_dir: 프롬프트 파일 저장 디렉토리

    Returns:
        생성된 프롬프트 파일 경로 리스트
    """
    if batch_info.get("status") == "already_complete":
        print("[PromptGen] 모든 씬이 이미 분석되어 프롬프트 생성 스킵")
        return []

    prompt_files = []
    total_batches = batch_info.get("batches", 0)
    batch_files = batch_info.get("batch_files", [])
    batch_size = batch_info.get("batch_size", 50)
    unanalyzed_count = batch_info.get("unanalyzed_scenes", 0)

    if output_dir is None:
        output_dir = batch_info.get("output_dir", ".")

    output_path = Path(output_dir)

    for idx, input_file in enumerate(batch_files):
        output_file = input_file.replace("_input.json", "_output.json")

        # 씬 수 계산
        if idx == total_batches - 1:
            # 마지막 배치는 남은 씬 수
            scene_count = unanalyzed_count % batch_size
            if scene_count == 0:
                scene_count = batch_size
        else:
            scene_count = batch_size

        prompt_file = generate_batch_prompt(
            batch_idx=idx,
            total_batches=total_batches,
            scene_count=scene_count,
            input_file=input_file,
            output_file=output_file,
            template_path=template_path,
            output_dir=output_path
        )
        prompt_files.append(prompt_file)

        print(f"[PromptGen] 배치 {idx + 1}/{total_batches} 프롬프트 생성: {Path(prompt_file).name}")

    # 프롬프트 목록 저장
    prompts_meta = {
        "generated_at": datetime.now().isoformat(),
        "total_prompts": len(prompt_files),
        "prompt_files": prompt_files,
        "batch_info_ref": batch_info.get("output_dir")
    }

    meta_file = output_path / "prompts_meta.json"
    with open(meta_file, 'w', encoding='utf-8') as f:
        json.dump(prompts_meta, f, ensure_ascii=False, indent=2)

    print(f"\n[PromptGen] ═══════════════════════════════════════════")
    print(f"[PromptGen] 프롬프트 생성 완료: {len(prompt_files)}개")
    print(f"[PromptGen] 메타 파일: {meta_file}")
    print(f"[PromptGen] ═══════════════════════════════════════════\n")

    return prompt_files


def generate_master_prompt(
    batch_info: dict,
    output_dir: str,
    template_path: str = ""
) -> str:
    """
    전체 배치 실행을 위한 마스터 프롬프트 생성

    Claude Code에서 모든 배치를 순차적으로 처리하도록 지시하는
    상위 레벨 프롬프트를 생성합니다.
    """
    if batch_info.get("status") == "already_complete":
        return ""

    total_batches = batch_info.get("batches", 0)
    total_scenes = batch_info.get("unanalyzed_scenes", 0)
    batch_files = batch_info.get("batch_files", [])

    # 배치 파일 목록 생성
    batch_list = ""
    for i, bf in enumerate(batch_files):
        output_file = bf.replace("_input.json", "_output.json")
        batch_list += f"| {i + 1} | `{Path(bf).name}` | `{Path(output_file).name}` |\n"

    master_prompt = f'''# 씬 분석 배치 실행 마스터

## 개요

- **총 배치**: {total_batches}개
- **총 씬**: {total_scenes}개
- **배치당 씬**: 최대 {batch_info.get("batch_size", 50)}개
- **예상 시간**: ~{batch_info.get("estimated_time_minutes", 0)}분

## 배치 목록

| # | 입력 파일 | 출력 파일 |
|---|-----------|-----------|
{batch_list}

## 실행 방법

각 배치에 대해 순차적으로:

1. 입력 파일 읽기 (`batch_XXX_input.json`)
2. 씬별 프롬프트 생성 (15개 필드)
3. 결과를 출력 파일에 저장 (`batch_XXX_output.json`)

## 중요 지침

- **scenes.json 직접 수정 금지**
- 각 배치의 출력은 별도 JSON 파일로 저장
- 출력 형식: JSON 배열 (씬 객체들의 배열)
- 모든 배치 완료 후 병합 스크립트가 scenes.json 업데이트

## 프롬프트 템플릿

{f"- 템플릿 경로: `{template_path}`" if template_path else "- 기본 규칙 사용"}

## 시작

배치 1부터 순차적으로 처리하세요.
각 배치의 상세 지침은 `prompt_batch_XXX.md` 파일을 참조하세요.
'''

    output_path = Path(output_dir)
    master_file = output_path / "master_prompt.md"
    with open(master_file, 'w', encoding='utf-8') as f:
        f.write(master_prompt)

    print(f"[PromptGen] 마스터 프롬프트 생성: {master_file}")
    return str(master_file)


if __name__ == "__main__":
    import sys

    # 테스트용 배치 정보
    test_batch_info = {
        "status": "ready",
        "batches": 3,
        "batch_size": 50,
        "unanalyzed_scenes": 125,
        "batch_files": [
            "./batches/batch_000_input.json",
            "./batches/batch_001_input.json",
            "./batches/batch_002_input.json"
        ],
        "output_dir": "./batches"
    }

    if len(sys.argv) > 1:
        # 메타 파일에서 로드
        meta_path = sys.argv[1]
        with open(meta_path, 'r', encoding='utf-8') as f:
            test_batch_info = json.load(f)

    prompts = generate_all_batch_prompts(test_batch_info)
    print(f"Generated {len(prompts)} prompt files")
