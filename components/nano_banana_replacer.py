# -*- coding: utf-8 -*-
"""
components/nano_banana_replacer.py
나노바나나 이미지 대체 UI 컴포넌트

필터로 선택된 씬들의 이미지를 Gemini Nano Banana 모델로 재생성

작성: 2025-01
"""

import streamlit as st
from pathlib import Path
from typing import List, Dict, Optional, Callable
import time
import json

from utils.gemini_image_generator import (
    GeminiImageGenerator,
    GeminiGenerationResult,
    GEMINI_IMAGE_MODELS,
    check_gemini_api_key
)


def render_nano_banana_replacer(
    filtered_scenes: List[Dict],
    project_path: str,
    all_scenes: List[Dict] = None,
    on_complete: Callable = None
):
    """
    나노바나나 이미지 대체 UI 렌더링

    Args:
        filtered_scenes: 필터링된 씬 목록
        project_path: 프로젝트 경로
        all_scenes: 전체 씬 목록 (업데이트용)
        on_complete: 완료 콜백
    """

    st.markdown("### 🍌 나노바나나로 이미지 대체")
    st.caption("선택된 씬들의 이미지를 Gemini Nano Banana 모델로 재생성합니다.")

    # API 키 확인
    if not check_gemini_api_key():
        st.error("⚠️ Gemini API 키가 설정되지 않았습니다. `.env` 파일에 `GEMINI_API_KEY`를 추가하세요.")
        return

    # 대상 씬 확인
    if not filtered_scenes:
        st.warning("⚠️ 필터로 선택된 씬이 없습니다. 먼저 필터를 적용하세요.")
        return

    st.info(f"📌 대상 씬: **{len(filtered_scenes)}개**")

    # ═══════════════════════════════════════════════════════════════
    # 설정 섹션
    # ═══════════════════════════════════════════════════════════════

    col1, col2 = st.columns(2)

    with col1:
        # 모델 선택
        st.markdown("**🤖 모델 선택**")

        model_options = {
            "gemini_nano_banana": "🍌 Nano Banana (빠른 생성, ~15원/장)",
            "gemini_nano_banana_pro": "🍌✨ Nano Banana Pro (고품질, ~25원/장)"
        }

        selected_model = st.radio(
            "모델",
            options=list(model_options.keys()),
            format_func=lambda x: model_options[x],
            key="nano_banana_model",
            horizontal=True,
            label_visibility="collapsed"
        )

    with col2:
        # 프롬프트 선택
        st.markdown("**📝 프롬프트 선택**")

        prompt_options = {
            "korean": "🇰🇷 한글 텍스트 프롬프트",
            "english": "🇺🇸 원본 영어 프롬프트"
        }

        selected_prompt_type = st.radio(
            "프롬프트 타입",
            options=list(prompt_options.keys()),
            format_func=lambda x: prompt_options[x],
            key="nano_banana_prompt_type",
            horizontal=True,
            label_visibility="collapsed"
        )

    # ═══════════════════════════════════════════════════════════════
    # 레퍼런스 이미지 설정
    # ═══════════════════════════════════════════════════════════════

    st.markdown("---")
    st.markdown("**📷 레퍼런스 이미지 설정**")

    use_reference = st.checkbox(
        "🖼️ 현재 씬 이미지를 레퍼런스로 사용",
        value=True,
        key="nano_banana_use_reference",
        help="각 씬에 이미 생성된 이미지를 레퍼런스로 사용하여 스타일 일관성을 유지합니다."
    )

    ref_type = "style"
    ref_strength = 0.7

    if use_reference:
        col1, col2 = st.columns(2)

        with col1:
            # 레퍼런스 타입
            ref_type_options = {
                "style": "🎨 스타일 참조 (색감, 화풍, 분위기)",
                "character": "👤 캐릭터 참조 (외모, 의상, 특징)",
                "composition": "📐 구도 참조 (배치, 앵글, 프레이밍)"
            }

            ref_type = st.selectbox(
                "레퍼런스 타입",
                options=list(ref_type_options.keys()),
                format_func=lambda x: ref_type_options[x],
                key="nano_banana_ref_type"
            )

        with col2:
            # 레퍼런스 강도
            ref_strength = st.slider(
                "레퍼런스 강도",
                min_value=0.1,
                max_value=1.0,
                value=0.7,
                step=0.1,
                key="nano_banana_ref_strength",
                help="1.0에 가까울수록 원본 이미지와 유사하게 생성됩니다."
            )

        # 레퍼런스 이미지 미리보기
        with st.expander("🔍 레퍼런스 이미지 미리보기", expanded=False):
            preview_cols = st.columns(5)

            for idx, scene in enumerate(filtered_scenes[:5]):
                with preview_cols[idx]:
                    scene_num = scene.get('scene_id', scene.get('scene_num', idx + 1))
                    image_path = _get_scene_image_path(scene, project_path)

                    if image_path and Path(image_path).exists():
                        st.image(image_path, caption=f"씬 {scene_num}", use_container_width=True)
                    else:
                        st.caption(f"씬 {scene_num}: 이미지 없음")

            if len(filtered_scenes) > 5:
                st.caption(f"... 외 {len(filtered_scenes) - 5}개 씬")

    # ═══════════════════════════════════════════════════════════════
    # 비용 예상
    # ═══════════════════════════════════════════════════════════════

    st.markdown("---")

    cost_per_image = 15 if selected_model == "gemini_nano_banana" else 25
    total_cost = len(filtered_scenes) * cost_per_image

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("대상 씬", f"{len(filtered_scenes)}개")

    with col2:
        st.metric("이미지당 비용", f"~{cost_per_image}원")

    with col3:
        st.metric("예상 총 비용", f"~{total_cost:,}원")

    # ═══════════════════════════════════════════════════════════════
    # 실행 버튼
    # ═══════════════════════════════════════════════════════════════

    st.markdown("---")

    col1, col2 = st.columns([3, 1])

    with col1:
        if st.button(
            f"🍌 나노바나나로 {len(filtered_scenes)}개 씬 이미지 대체",
            type="primary",
            use_container_width=True,
            key="nano_banana_execute"
        ):
            _execute_nano_banana_replacement(
                scenes=filtered_scenes,
                all_scenes=all_scenes,
                project_path=project_path,
                model=selected_model,
                prompt_type=selected_prompt_type,
                use_reference=use_reference,
                ref_type=ref_type,
                ref_strength=ref_strength,
                on_complete=on_complete
            )

    with col2:
        if st.button("🔄 새로고침", key="nano_banana_refresh"):
            st.rerun()


def _execute_nano_banana_replacement(
    scenes: List[Dict],
    all_scenes: List[Dict],
    project_path: str,
    model: str,
    prompt_type: str,
    use_reference: bool,
    ref_type: str,
    ref_strength: float,
    on_complete: Callable = None
):
    """
    나노바나나 이미지 대체 실행
    """

    st.markdown("### 🚀 이미지 생성 진행")

    # 진행 상황 표시
    progress_bar = st.progress(0)
    status_text = st.empty()
    result_container = st.container()

    # 결과 저장
    results = {
        "success": [],
        "failed": [],
        "skipped": []
    }

    try:
        # Gemini 생성기 초기화
        generator = GeminiImageGenerator()

        total = len(scenes)

        for idx, scene in enumerate(scenes):
            scene_id = scene.get('scene_id', scene.get('scene_num', idx + 1))

            # 진행률 업데이트
            progress = (idx + 1) / total
            progress_bar.progress(progress)
            status_text.text(f"🍌 씬 {scene_id} 처리 중... ({idx + 1}/{total})")

            # 프롬프트 가져오기
            prompt = _get_scene_prompt(scene, prompt_type)

            if not prompt:
                results["skipped"].append({
                    "scene_id": scene_id,
                    "reason": "프롬프트 없음"
                })
                print(f"[NanoBanana] ⏭️ 씬 {scene_id}: 프롬프트 없음 - 스킵")
                continue

            # 레퍼런스 이미지 설정
            reference_images = None
            if use_reference:
                ref_image_path = _get_scene_image_path(scene, project_path)

                if ref_image_path and Path(ref_image_path).exists():
                    reference_images = [ref_image_path]
                    print(f"[NanoBanana] 📷 씬 {scene_id}: 레퍼런스 이미지 사용")

            # 출력 경로 설정
            output_dir = Path(project_path) / "images" / "nano_banana"
            output_dir.mkdir(parents=True, exist_ok=True)
            timestamp = int(time.time() * 1000)
            output_path = str(output_dir / f"nano_scene_{scene_id:03d}_{timestamp}.png")

            # 이미지 생성
            print(f"[NanoBanana] ========== 씬 {scene_id} ==========")
            print(f"[NanoBanana] 모델: {model}")
            print(f"[NanoBanana] 프롬프트 타입: {prompt_type}")
            print(f"[NanoBanana] 프롬프트: {prompt[:100]}...")

            result = generator.generate_image(
                prompt=prompt,
                model_key=model,
                reference_images=reference_images,
                reference_type=ref_type,
                reference_strength=ref_strength
            )

            if result.success and result.image_data:
                # 이미지 저장
                with open(output_path, 'wb') as f:
                    f.write(result.image_data)

                results["success"].append({
                    "scene_id": scene_id,
                    "path": output_path
                })
                print(f"[NanoBanana] ✅ 씬 {scene_id} 성공: {output_path}")

                # 씬 데이터 업데이트
                _update_scene_image_path(scene, output_path, all_scenes, project_path)
            else:
                results["failed"].append({
                    "scene_id": scene_id,
                    "error": result.error or "알 수 없는 오류"
                })
                print(f"[NanoBanana] ❌ 씬 {scene_id} 실패: {result.error}")

            # API 레이트 리밋 방지
            time.sleep(1.5)

        # 완료
        progress_bar.progress(1.0)
        status_text.text("✅ 완료!")

        # 결과 표시
        with result_container:
            st.markdown("### 📊 결과")

            col1, col2, col3 = st.columns(3)

            with col1:
                st.metric("✅ 성공", len(results["success"]))

            with col2:
                st.metric("❌ 실패", len(results["failed"]))

            with col3:
                st.metric("⏭️ 스킵", len(results["skipped"]))

            # 실패한 씬 상세
            if results["failed"]:
                with st.expander("❌ 실패한 씬 상세"):
                    for item in results["failed"]:
                        st.error(f"씬 {item['scene_id']}: {item['error']}")

            # 스킵한 씬 상세
            if results["skipped"]:
                with st.expander("⏭️ 스킵한 씬 상세"):
                    for item in results["skipped"]:
                        st.warning(f"씬 {item['scene_id']}: {item['reason']}")

            # 성공 메시지
            if results["success"]:
                st.success(f"🍌 {len(results['success'])}개 씬의 이미지가 나노바나나로 대체되었습니다!")

        # 콜백 호출
        if on_complete:
            on_complete(results)

    except Exception as e:
        st.error(f"❌ 오류 발생: {e}")
        print(f"[NanoBanana] 실행 오류: {e}")
        import traceback
        traceback.print_exc()


# ═══════════════════════════════════════════════════════════════
# 헬퍼 함수
# ═══════════════════════════════════════════════════════════════

def _get_scene_prompt(scene: Dict, prompt_type: str) -> str:
    """
    씬에서 프롬프트 추출

    Args:
        scene: 씬 데이터
        prompt_type: "korean" 또는 "english"

    Returns:
        프롬프트 문자열
    """

    if prompt_type == "korean":
        # 한글 텍스트 씬 프롬프트
        prompt = (
            scene.get('image_prompt_korean_text') or
            scene.get('korean_text') or
            scene.get('script') or
            scene.get('script_text') or
            scene.get('text') or
            scene.get('narration') or
            ""
        )
    else:
        # 원본 영어 프롬프트
        prompt = (
            scene.get('image_prompt') or
            scene.get('prompt') or
            scene.get('background_prompt') or
            scene.get('english_prompt') or
            scene.get('scene_description') or
            ""
        )

    return prompt.strip()


def _get_scene_image_path(scene: Dict, project_path: str) -> Optional[str]:
    """
    씬의 현재 이미지 경로 반환
    """

    # 방법 1: 씬 데이터에서 직접
    image_path = (
        scene.get('composite_path') or
        scene.get('image_path') or
        scene.get('background_image') or
        scene.get('final_image') or
        scene.get('nano_banana_image')
    )

    if image_path and Path(image_path).exists():
        return image_path

    # 방법 2: 프로젝트 경로에서 찾기
    scene_id = scene.get('scene_id', scene.get('scene_num', 0))

    possible_paths = [
        Path(project_path) / "images" / "composites" / f"composite_{scene_id:03d}.png",
        Path(project_path) / "images" / "backgrounds" / f"bg_scene_{scene_id:03d}.png",
        Path(project_path) / "images" / f"scene_{scene_id:03d}.png",
    ]

    for path in possible_paths:
        if path.exists():
            return str(path)

    return None


def _update_scene_image_path(
    scene: Dict,
    new_path: str,
    all_scenes: List[Dict],
    project_path: str
):
    """
    씬의 이미지 경로 업데이트
    """

    # 씬 데이터 업데이트
    scene['nano_banana_image'] = new_path
    scene['last_image_update'] = time.strftime("%Y-%m-%d %H:%M:%S")

    # all_scenes에서도 업데이트
    if all_scenes:
        scene_id = scene.get('scene_id', scene.get('scene_num', 0))
        for s in all_scenes:
            if s.get('scene_id', s.get('scene_num', 0)) == scene_id:
                s['nano_banana_image'] = new_path
                s['last_image_update'] = scene['last_image_update']
                break

    print(f"[NanoBanana] 씬 이미지 경로 업데이트: {new_path}")


# 내보내기
__all__ = ['render_nano_banana_replacer']
