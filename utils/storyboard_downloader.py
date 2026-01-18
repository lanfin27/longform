# -*- coding: utf-8 -*-
"""
스토리보드 다운로드 관리자 (v1.2)

기능:
- 개별/일괄 파일 다운로드
- ZIP 압축 다운로드
- 이미지, 비디오, 스크립트, 프롬프트, 연출가이드 지원
- SRT 자막 파일 생성 및 다운로드 (v1.1)
- 타입 안전 씬 ID 필터링 (v1.2) - 문자열/정수 혼합 ID 처리
"""

import streamlit as st
import os
import io
import zipfile
from pathlib import Path
from typing import List, Dict, Set, Optional
from datetime import datetime

# SRT 생성 유틸리티 import
try:
    from utils.srt_generator import (
        generate_srt_content,
        generate_vtt_content,
        generate_individual_srt_files,
        get_srt_stats,
        calculate_scene_timings
    )
    SRT_GENERATOR_AVAILABLE = True
except ImportError:
    SRT_GENERATOR_AVAILABLE = False


class StoryboardDownloader:
    """스토리보드 다운로드 관리자"""

    def __init__(self, project_path: str, key_prefix: str = "sb_dl"):
        self.project_path = Path(project_path)
        self.key_prefix = key_prefix

    def get_scene_files(self, scene: dict) -> dict:
        """
        씬의 다운로드 가능한 파일/데이터 목록 반환

        Args:
            scene: 씬 데이터 딕셔너리

        Returns:
            {
                "image": 이미지 경로 또는 None,
                "video": 비디오 경로 또는 None,
                "script": 스크립트 텍스트,
                "direction_guide": 연출가이드 텍스트,
                "video_prompt_character": 캐릭터 비디오 프롬프트,
                "video_prompt_full": 전체 비디오 프롬프트
            }
        """
        files = {
            "image": None,
            "video": None,
            "script": "",
            "direction_guide": "",
            "video_prompt_character": "",
            "video_prompt_full": "",
        }

        # 이미지 경로 (여러 키 시도)
        for key in ["image_path", "composite_path", "background_path"]:
            path = scene.get(key, "")
            if path and os.path.exists(str(path)):
                files["image"] = str(path)
                break

        # 비디오 경로
        video_path = scene.get("video_path", "")
        if video_path and os.path.exists(str(video_path)):
            files["video"] = str(video_path)

        # 스크립트
        files["script"] = scene.get("script_text", "") or scene.get("narration", "") or ""

        # 연출가이드
        files["direction_guide"] = (
            scene.get("direction_guide", "") or
            scene.get("visual_direction", "") or
            scene.get("image_prompt", "") or
            ""
        )

        # 비디오 프롬프트
        video_prompts = scene.get("video_prompts", {})
        if isinstance(video_prompts, dict):
            files["video_prompt_character"] = video_prompts.get("character", "")
            files["video_prompt_full"] = video_prompts.get("full", "") or scene.get("video_prompt", "")
        else:
            files["video_prompt_full"] = scene.get("video_prompt", "")

        return files

    def create_zip(
        self,
        scenes: List[dict],
        selected_ids: Set[int],
        include_images: bool = True,
        include_videos: bool = True,
        include_scripts: bool = True,
        include_prompts: bool = True,
        include_guides: bool = True,
        include_srt: bool = False
    ) -> io.BytesIO:
        """
        선택된 씬들의 ZIP 파일 생성

        Args:
            scenes: 전체 씬 데이터 리스트
            selected_ids: 선택된 씬 ID 집합
            include_*: 각 항목 포함 여부

        Returns:
            ZIP 파일 BytesIO 버퍼
        """
        buffer = io.BytesIO()

        # ⭐ v1.2: 타입 안전 처리
        def get_scene_id_safe(scene):
            """씬 ID를 정수로 안전하게 가져오기"""
            sid = scene.get("scene_id") or scene.get("id") or scene.get("scene_num")
            if sid is None:
                return 0
            try:
                return int(sid)
            except (ValueError, TypeError):
                return 0

        # 선택된 ID를 정수 집합으로 변환
        selected_ids_int = {int(sid) for sid in selected_ids if sid is not None}

        print(f"[ZIP] 선택된 ID (정수 변환): {sorted(selected_ids_int)}")

        with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            all_scripts = []
            all_char_prompts = []
            all_full_prompts = []
            all_guides = []

            for scene in sorted(scenes, key=get_scene_id_safe):
                scene_id = get_scene_id_safe(scene)

                if scene_id not in selected_ids_int:
                    continue

                files = self.get_scene_files(scene)
                prefix = f"scene_{scene_id:03d}"

                # 이미지
                if include_images and files["image"]:
                    ext = Path(files["image"]).suffix or ".png"
                    zf.write(files["image"], f"images/{prefix}{ext}")

                # 비디오
                if include_videos and files["video"]:
                    ext = Path(files["video"]).suffix or ".mp4"
                    zf.write(files["video"], f"videos/{prefix}{ext}")

                # 스크립트
                if include_scripts and files["script"]:
                    zf.writestr(f"scripts/{prefix}_script.txt", files["script"])
                    all_scripts.append(f"[씬 {scene_id}]\n{files['script']}\n///\n")

                # 연출가이드
                if include_guides and files["direction_guide"]:
                    zf.writestr(f"guides/{prefix}_guide.txt", files["direction_guide"])
                    all_guides.append(f"[씬 {scene_id}]\n{files['direction_guide']}\n")

                # 비디오 프롬프트
                if include_prompts:
                    if files["video_prompt_character"]:
                        zf.writestr(
                            f"prompts/{prefix}_video_prompt_character.txt",
                            files["video_prompt_character"]
                        )
                        all_char_prompts.append(f"[씬 {scene_id}]\n{files['video_prompt_character']}\n")

                    if files["video_prompt_full"]:
                        zf.writestr(
                            f"prompts/{prefix}_video_prompt_full.txt",
                            files["video_prompt_full"]
                        )
                        all_full_prompts.append(f"[씬 {scene_id}]\n{files['video_prompt_full']}\n")

            # 통합 파일들
            if include_scripts and all_scripts:
                zf.writestr("_전체_스크립트.txt", "\n".join(all_scripts))

            if include_guides and all_guides:
                zf.writestr("_전체_연출가이드.txt", "\n".join(all_guides))

            if include_prompts:
                if all_char_prompts:
                    zf.writestr("_전체_비디오프롬프트_캐릭터.txt", "\n".join(all_char_prompts))
                if all_full_prompts:
                    zf.writestr("_전체_비디오프롬프트_전체.txt", "\n".join(all_full_prompts))

            # SRT 자막 파일 (v1.1, v1.2: 타입 안전 처리)
            if include_srt and SRT_GENERATOR_AVAILABLE:
                # 선택된 씬만 필터링 (타입 안전)
                selected_scenes = [
                    s for s in scenes
                    if get_scene_id_safe(s) in selected_ids_int
                ]
                selected_scenes = sorted(selected_scenes, key=get_scene_id_safe)
                print(f"[ZIP/SRT] SRT 생성 대상 씬 ID: {[get_scene_id_safe(s) for s in selected_scenes]}")

                # 통합 SRT 생성
                srt_content = generate_srt_content(selected_scenes)
                if srt_content:
                    zf.writestr("subtitles.srt", srt_content.encode("utf-8"))

                # VTT 형식도 추가
                vtt_content = generate_vtt_content(selected_scenes)
                if vtt_content:
                    zf.writestr("subtitles.vtt", vtt_content.encode("utf-8"))

        buffer.seek(0)
        return buffer

    def get_download_preview(self, scenes: List[dict], selected_ids: Set[int]) -> dict:
        """다운로드 내용 미리보기 통계"""
        preview = {
            "image_count": 0,
            "video_count": 0,
            "script_count": 0,
            "guide_count": 0,
            "prompt_count": 0,
            "srt_count": 0,  # SRT 카운트 추가
        }

        # ⭐ v1.2: 타입 안전 처리
        def get_scene_id_safe(scene):
            sid = scene.get("scene_id") or scene.get("id") or scene.get("scene_num")
            if sid is None:
                return 0
            try:
                return int(sid)
            except (ValueError, TypeError):
                return 0

        selected_ids_int = {int(sid) for sid in selected_ids if sid is not None}

        for scene in scenes:
            scene_id = get_scene_id_safe(scene)
            if scene_id not in selected_ids_int:
                continue

            files = self.get_scene_files(scene)

            if files["image"]:
                preview["image_count"] += 1
            if files["video"]:
                preview["video_count"] += 1
            if files["script"]:
                preview["script_count"] += 1
                preview["srt_count"] += 1  # 스크립트가 있으면 SRT도 생성 가능
            if files["direction_guide"]:
                preview["guide_count"] += 1
            if files["video_prompt_character"] or files["video_prompt_full"]:
                preview["prompt_count"] += 1

        return preview

    def render_download_ui(self, scenes: List[dict], selected_ids: Set[int]):
        """다운로드 UI 렌더링"""

        if not selected_ids:
            st.warning("다운로드할 씬을 선택해주세요.")
            return

        st.markdown("### 📥 다운로드")
        st.markdown(f"**선택된 씬: {len(selected_ids)}개**")

        # 다운로드 옵션
        st.markdown("**포함할 항목:**")

        col1, col2, col3 = st.columns(3)

        with col1:
            include_images = st.checkbox("🖼️ 이미지", value=True, key=f"{self.key_prefix}_opt_images")
            include_videos = st.checkbox("🎬 비디오", value=True, key=f"{self.key_prefix}_opt_videos")

        with col2:
            include_scripts = st.checkbox("📝 스크립트", value=True, key=f"{self.key_prefix}_opt_scripts")
            include_guides = st.checkbox("🎯 연출가이드", value=True, key=f"{self.key_prefix}_opt_guides")

        with col3:
            include_prompts = st.checkbox("💬 비디오 프롬프트", value=True, key=f"{self.key_prefix}_opt_prompts")
            # SRT 체크박스 추가 (v1.1)
            include_srt = st.checkbox(
                "📄 SRT (자막)",
                value=False,
                key=f"{self.key_prefix}_opt_srt",
                disabled=not SRT_GENERATOR_AVAILABLE,
                help="스크립트 기반 SRT 자막 파일 생성" if SRT_GENERATOR_AVAILABLE else "SRT 생성 모듈 없음"
            )

        st.markdown("---")

        # 다운로드 방식 선택
        download_mode = st.radio(
            "다운로드 방식",
            ["📦 일괄 다운로드 (ZIP)", "📄 개별 다운로드"],
            horizontal=True,
            key=f"{self.key_prefix}_mode"
        )

        if download_mode == "📦 일괄 다운로드 (ZIP)":
            self._render_zip_download(
                scenes, selected_ids,
                include_images, include_videos,
                include_scripts, include_prompts, include_guides,
                include_srt
            )
        else:
            self._render_individual_downloads(
                scenes, selected_ids,
                include_images, include_videos,
                include_scripts, include_prompts, include_guides,
                include_srt
            )

    def _render_zip_download(
        self,
        scenes: List[dict],
        selected_ids: Set[int],
        include_images: bool,
        include_videos: bool,
        include_scripts: bool,
        include_prompts: bool,
        include_guides: bool,
        include_srt: bool = False
    ):
        """ZIP 일괄 다운로드 UI"""

        # 미리보기
        preview = self.get_download_preview(scenes, selected_ids)

        with st.expander("📋 다운로드 내용 미리보기", expanded=True):
            col1, col2 = st.columns(2)

            with col1:
                st.markdown(f"- 🖼️ 이미지: **{preview['image_count']}개** {'✅' if include_images else '⬜'}")
                st.markdown(f"- 🎬 비디오: **{preview['video_count']}개** {'✅' if include_videos else '⬜'}")
                st.markdown(f"- 📝 스크립트: **{preview['script_count']}개** {'✅' if include_scripts else '⬜'}")

            with col2:
                st.markdown(f"- 🎯 연출가이드: **{preview['guide_count']}개** {'✅' if include_guides else '⬜'}")
                st.markdown(f"- 💬 비디오 프롬프트: **{preview['prompt_count']}개** {'✅' if include_prompts else '⬜'}")
                st.markdown(f"- 📄 SRT 자막: **{preview['srt_count']}개** {'✅' if include_srt else '⬜'}")

        # ZIP 생성 버튼
        if st.button("📦 ZIP 파일 생성", type="primary", use_container_width=True, key=f"{self.key_prefix}_create_zip"):
            with st.spinner("ZIP 파일 생성 중..."):
                try:
                    zip_buffer = self.create_zip(
                        scenes, selected_ids,
                        include_images, include_videos,
                        include_scripts, include_prompts, include_guides,
                        include_srt
                    )

                    # 파일명 생성
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    project_name = self.project_path.name[:20]
                    filename = f"storyboard_{project_name}_{len(selected_ids)}scenes_{timestamp}.zip"

                    # v1.2: BytesIO → bytes 변환으로 다운로드 안정성 개선
                    st.download_button(
                        label="📥 ZIP 다운로드",
                        data=zip_buffer.getvalue(),  # bytes로 변환
                        file_name=filename,
                        mime="application/zip",
                        use_container_width=True,
                        key=f"{self.key_prefix}_download_zip"
                    )

                    st.success(f"✅ ZIP 파일 준비 완료!")

                except Exception as e:
                    st.error(f"ZIP 생성 실패: {e}")

    def _render_individual_downloads(
        self,
        scenes: List[dict],
        selected_ids: Set[int],
        include_images: bool,
        include_videos: bool,
        include_scripts: bool,
        include_prompts: bool,
        include_guides: bool,
        include_srt: bool = False
    ):
        """개별 파일 다운로드 UI"""

        # ⭐ v1.2: 선택된 씬만 필터링 (타입 안전 처리)
        def get_scene_id(scene):
            """씬 ID를 정수로 안전하게 가져오기"""
            sid = scene.get("scene_id") or scene.get("id") or scene.get("scene_num")
            if sid is None:
                return None
            try:
                return int(sid)
            except (ValueError, TypeError):
                return None

        # 선택된 ID를 정수 집합으로 변환
        selected_ids_int = {int(sid) for sid in selected_ids if sid is not None}

        # 선택된 씬만 필터링
        selected_scenes = []
        for s in scenes:
            sid = get_scene_id(s)
            if sid is not None and sid in selected_ids_int:
                selected_scenes.append(s)

        selected_scenes = sorted(selected_scenes, key=lambda x: get_scene_id(x) or 0)

        # 디버그 로그
        selected_scene_ids = [get_scene_id(s) for s in selected_scenes]
        print(f"[Download] 선택된 ID: {sorted(selected_ids_int)}")
        print(f"[Download] 필터링된 씬 ID: {selected_scene_ids}")
        print(f"[Download] 필터링 결과: {len(selected_scenes)}개 / 전체 {len(scenes)}개")

        # 탭 구성 (SRT 탭 조건부 추가)
        tab_names = ["🖼️ 이미지", "🎬 비디오", "📝 스크립트", "💬 프롬프트", "🎯 연출"]
        if include_srt and SRT_GENERATOR_AVAILABLE:
            tab_names.append("📄 SRT")

        tabs = st.tabs(tab_names)

        with tabs[0]:  # 이미지
            if include_images:
                self._render_image_downloads(selected_scenes)
            else:
                st.info("이미지 다운로드가 선택되지 않았습니다.")

        with tabs[1]:  # 비디오
            if include_videos:
                self._render_video_downloads(selected_scenes)
            else:
                st.info("비디오 다운로드가 선택되지 않았습니다.")

        with tabs[2]:  # 스크립트
            if include_scripts:
                self._render_script_downloads(selected_scenes)
            else:
                st.info("스크립트 다운로드가 선택되지 않았습니다.")

        with tabs[3]:  # 프롬프트
            if include_prompts:
                self._render_prompt_downloads(selected_scenes)
            else:
                st.info("프롬프트 다운로드가 선택되지 않았습니다.")

        with tabs[4]:  # 연출가이드
            if include_guides:
                self._render_guide_downloads(selected_scenes)
            else:
                st.info("연출가이드 다운로드가 선택되지 않았습니다.")

        # SRT 탭 (v1.1)
        if include_srt and SRT_GENERATOR_AVAILABLE and len(tabs) > 5:
            with tabs[5]:
                self._render_srt_downloads(selected_scenes)

    def _render_image_downloads(self, scenes: List[dict]):
        """이미지 개별 다운로드"""

        has_images = False
        cols = st.columns(4)

        for i, scene in enumerate(scenes):
            scene_id = scene.get("scene_id", scene.get("id", 0))
            files = self.get_scene_files(scene)

            if files["image"]:
                has_images = True
                with cols[i % 4]:
                    st.image(files["image"], width=100)

                    with open(files["image"], "rb") as f:
                        ext = Path(files["image"]).suffix or ".png"
                        st.download_button(
                            f"씬 {scene_id}",
                            data=f.read(),
                            file_name=f"scene_{scene_id:03d}{ext}",
                            mime=f"image/{ext[1:]}",
                            key=f"{self.key_prefix}_img_{scene_id}",
                            use_container_width=True
                        )

        if not has_images:
            st.info("다운로드 가능한 이미지가 없습니다.")

    def _render_video_downloads(self, scenes: List[dict]):
        """비디오 개별 다운로드"""

        has_videos = False

        for scene in scenes:
            scene_id = scene.get("scene_id", scene.get("id", 0))
            files = self.get_scene_files(scene)

            if files["video"]:
                has_videos = True
                col1, col2 = st.columns([1, 3])

                with col1:
                    st.markdown(f"**씬 {scene_id}**")

                with col2:
                    with open(files["video"], "rb") as f:
                        st.download_button(
                            "📥 다운로드",
                            data=f.read(),
                            file_name=f"scene_{scene_id:03d}.mp4",
                            mime="video/mp4",
                            key=f"{self.key_prefix}_video_{scene_id}"
                        )

        if not has_videos:
            st.info("다운로드 가능한 비디오가 없습니다.")

    def _render_script_downloads(self, scenes: List[dict]):
        """스크립트 다운로드"""

        # 통합 다운로드
        all_scripts = []
        for scene in sorted(scenes, key=lambda x: x.get("scene_id", 0)):
            files = self.get_scene_files(scene)
            if files["script"]:
                scene_id = scene.get("scene_id", scene.get("id", 0))
                all_scripts.append(f"{files['script']}///")

        if all_scripts:
            st.download_button(
                "📥 전체 스크립트 다운로드",
                data="\n".join(all_scripts),
                file_name="전체_스크립트.txt",
                mime="text/plain",
                use_container_width=True,
                key=f"{self.key_prefix}_all_scripts"
            )

            st.markdown("---")

        # 개별 다운로드
        for scene in scenes:
            scene_id = scene.get("scene_id", scene.get("id", 0))
            files = self.get_scene_files(scene)

            if files["script"]:
                preview = files["script"][:50] + "..." if len(files["script"]) > 50 else files["script"]

                with st.expander(f"씬 {scene_id}: {preview}"):
                    st.text(files["script"])
                    st.download_button(
                        "📥 다운로드",
                        data=files["script"],
                        file_name=f"scene_{scene_id:03d}_script.txt",
                        mime="text/plain",
                        key=f"{self.key_prefix}_script_{scene_id}"
                    )

    def _render_prompt_downloads(self, scenes: List[dict]):
        """비디오 프롬프트 다운로드"""

        tab1, tab2 = st.tabs(["👤 캐릭터 프롬프트", "🌐 전체 프롬프트"])

        with tab1:
            all_char_prompts = []
            for scene in sorted(scenes, key=lambda x: x.get("scene_id", 0)):
                files = self.get_scene_files(scene)
                if files["video_prompt_character"]:
                    scene_id = scene.get("scene_id", scene.get("id", 0))
                    all_char_prompts.append(f"[씬 {scene_id}]\n{files['video_prompt_character']}\n")

            if all_char_prompts:
                st.download_button(
                    "📥 전체 캐릭터 프롬프트",
                    data="\n".join(all_char_prompts),
                    file_name="전체_캐릭터_프롬프트.txt",
                    mime="text/plain",
                    use_container_width=True,
                    key=f"{self.key_prefix}_all_char_prompts"
                )

                for scene in scenes:
                    scene_id = scene.get("scene_id", scene.get("id", 0))
                    files = self.get_scene_files(scene)
                    if files["video_prompt_character"]:
                        with st.expander(f"씬 {scene_id}"):
                            st.code(files["video_prompt_character"], language=None)
            else:
                st.info("캐릭터 프롬프트가 없습니다.")

        with tab2:
            all_full_prompts = []
            for scene in sorted(scenes, key=lambda x: x.get("scene_id", 0)):
                files = self.get_scene_files(scene)
                if files["video_prompt_full"]:
                    scene_id = scene.get("scene_id", scene.get("id", 0))
                    all_full_prompts.append(f"[씬 {scene_id}]\n{files['video_prompt_full']}\n")

            if all_full_prompts:
                st.download_button(
                    "📥 전체 프롬프트",
                    data="\n".join(all_full_prompts),
                    file_name="전체_비디오_프롬프트.txt",
                    mime="text/plain",
                    use_container_width=True,
                    key=f"{self.key_prefix}_all_full_prompts"
                )

                for scene in scenes:
                    scene_id = scene.get("scene_id", scene.get("id", 0))
                    files = self.get_scene_files(scene)
                    if files["video_prompt_full"]:
                        with st.expander(f"씬 {scene_id}"):
                            st.code(files["video_prompt_full"], language=None)
            else:
                st.info("비디오 프롬프트가 없습니다.")

    def _render_guide_downloads(self, scenes: List[dict]):
        """연출가이드 다운로드"""

        all_guides = []
        for scene in sorted(scenes, key=lambda x: x.get("scene_id", 0)):
            files = self.get_scene_files(scene)
            if files["direction_guide"]:
                scene_id = scene.get("scene_id", scene.get("id", 0))
                all_guides.append(f"[씬 {scene_id}]\n{files['direction_guide']}\n")

        if all_guides:
            st.download_button(
                "📥 전체 연출가이드",
                data="\n".join(all_guides),
                file_name="전체_연출가이드.txt",
                mime="text/plain",
                use_container_width=True,
                key=f"{self.key_prefix}_all_guides"
            )

            st.markdown("---")

            for scene in scenes:
                scene_id = scene.get("scene_id", scene.get("id", 0))
                files = self.get_scene_files(scene)
                if files["direction_guide"]:
                    preview = files["direction_guide"][:50] + "..." if len(files["direction_guide"]) > 50 else files["direction_guide"]

                    with st.expander(f"씬 {scene_id}: {preview}"):
                        st.text(files["direction_guide"])
        else:
            st.info("연출가이드가 없습니다.")

    def _render_srt_downloads(self, scenes: List[dict]):
        """SRT 자막 다운로드 (v1.1)"""

        if not SRT_GENERATOR_AVAILABLE:
            st.error("SRT 생성 모듈이 없습니다.")
            return

        st.markdown("### 📄 SRT 자막 다운로드")

        # 스크립트가 있는 씬만 필터링
        scenes_with_script = [
            s for s in scenes
            if (s.get("script_text") or s.get("스크립트") or "").strip()
        ]

        if not scenes_with_script:
            st.warning("스크립트가 있는 씬이 없습니다.")
            return

        # ─────────────────────────────────────────────────────
        # SRT 옵션
        # ─────────────────────────────────────────────────────
        st.markdown("**SRT 옵션**")

        col1, col2 = st.columns(2)

        with col1:
            include_timecode = st.checkbox(
                "⏱️ 타임코드 포함",
                value=True,
                key=f"{self.key_prefix}_srt_timecode",
                help="TTS duration이 없으면 스크립트 길이로 추정합니다."
            )

            include_scene_number = st.checkbox(
                "🔢 씬 번호 포함",
                value=False,
                key=f"{self.key_prefix}_srt_scene_number",
                help="자막 텍스트에 [씬 N] 형태로 번호를 추가합니다."
            )

        with col2:
            srt_mode = st.radio(
                "파일 형식",
                options=["merged", "individual"],
                format_func=lambda x: "통합 SRT (1개 파일)" if x == "merged" else "개별 SRT (씬별)",
                key=f"{self.key_prefix}_srt_mode"
            )

            srt_format = st.radio(
                "자막 형식",
                options=["srt", "vtt"],
                format_func=lambda x: "SRT (일반)" if x == "srt" else "VTT (웹 호환)",
                key=f"{self.key_prefix}_srt_format"
            )

        st.markdown("---")

        # ─────────────────────────────────────────────────────
        # SRT 통계 및 미리보기
        # ─────────────────────────────────────────────────────
        stats = get_srt_stats(scenes_with_script)

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("자막 수", f"{stats['subtitle_count']}개")
        with col2:
            st.metric("총 길이", stats['total_duration_formatted'])
        with col3:
            st.metric("TTS 기반", f"{stats.get('tts_duration_count', 0)}개")
        with col4:
            st.metric("추정치", f"{stats.get('estimated_count', 0)}개")

        if stats.get('estimated_count', 0) > 0:
            st.caption("⚠️ TTS duration이 없는 씬은 스크립트 길이로 타임코드를 추정합니다.")

        st.markdown("---")

        # ─────────────────────────────────────────────────────
        # 미리보기 및 다운로드
        # ─────────────────────────────────────────────────────
        if srt_mode == "merged":
            # 통합 SRT 생성
            if srt_format == "srt":
                content = generate_srt_content(
                    scenes_with_script,
                    include_scene_number=include_scene_number,
                    include_timecode=include_timecode
                )
                file_ext = "srt"
                mime_type = "text/plain"
            else:
                content = generate_vtt_content(
                    scenes_with_script,
                    include_scene_number=include_scene_number
                )
                file_ext = "vtt"
                mime_type = "text/vtt"

            # 미리보기
            st.markdown("**📋 미리보기**")
            preview = content[:800] if len(content) > 800 else content
            if len(content) > 800:
                preview += "\n..."

            st.code(preview, language=None)

            # 다운로드 버튼
            col1, col2 = st.columns(2)

            with col1:
                st.download_button(
                    f"📄 {srt_format.upper()} 다운로드",
                    data=content.encode("utf-8"),
                    file_name=f"subtitles.{file_ext}",
                    mime=mime_type,
                    use_container_width=True,
                    key=f"{self.key_prefix}_srt_download"
                )

            with col2:
                # UTF-8 BOM 버전
                content_bom = '\ufeff' + content
                st.download_button(
                    f"📄 {srt_format.upper()} (BOM)",
                    data=content_bom.encode("utf-8-sig"),
                    file_name=f"subtitles_bom.{file_ext}",
                    mime=mime_type,
                    use_container_width=True,
                    key=f"{self.key_prefix}_srt_download_bom",
                    help="Windows 메모장 호환용"
                )

        else:
            # 개별 SRT 파일
            individual_files = generate_individual_srt_files(
                scenes_with_script,
                include_scene_number=include_scene_number
            )

            st.write(f"**생성될 파일: {len(individual_files)}개**")

            # 파일 목록
            with st.expander("📁 파일 목록", expanded=False):
                for filename, content in individual_files[:15]:
                    st.text(f"📄 {filename}")
                if len(individual_files) > 15:
                    st.caption(f"... 외 {len(individual_files) - 15}개")

            # ZIP으로 다운로드
            if st.button("📦 전체 SRT 다운로드 (ZIP)", use_container_width=True, key=f"{self.key_prefix}_srt_zip"):
                zip_buffer = io.BytesIO()

                with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
                    for filename, content in individual_files:
                        zf.writestr(filename, content.encode("utf-8"))

                zip_buffer.seek(0)

                # v1.2: BytesIO → bytes 변환으로 다운로드 안정성 개선
                st.download_button(
                    "💾 ZIP 다운로드",
                    data=zip_buffer.getvalue(),  # bytes로 변환
                    file_name="srt_files.zip",
                    mime="application/zip",
                    use_container_width=True,
                    key=f"{self.key_prefix}_srt_zip_download"
                )


def render_storyboard_download_section(
    project_path: str,
    scenes: List[dict],
    selected_ids: Set[int],
    key_prefix: str = "sb_dl"
):
    """
    스토리보드 다운로드 섹션 렌더링 (단축 함수)

    Args:
        project_path: 프로젝트 경로
        scenes: 씬 데이터 리스트
        selected_ids: 선택된 씬 ID 집합
        key_prefix: Streamlit UI 요소 키 prefix
    """
    downloader = StoryboardDownloader(project_path, key_prefix=key_prefix)
    downloader.render_download_ui(scenes, selected_ids)
