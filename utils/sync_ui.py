# -*- coding: utf-8 -*-
"""
utils/sync_ui.py
동기화 UI 컴포넌트
"""

import streamlit as st
from utils.sync_manager import SyncManager, ProcessType, get_sync_manager


def render_sync_status_bar():
    """동기화 상태 바 (사이드바 또는 상단에 표시)"""

    manager = get_sync_manager()
    status = manager.get_sync_status()

    with st.expander("🔄 동기화 상태", expanded=False):
        cols = st.columns(4)

        process_list = list(ProcessType)

        for idx, process in enumerate(process_list):
            col_idx = idx % 4
            proc_status = status.get(process.value, {})

            with cols[col_idx]:
                has_data = proc_status.get("has_data", False)
                is_synced = proc_status.get("is_synced", True)
                count = proc_status.get("data_count", 0)
                name = proc_status.get("name", process.value)

                # 상태 아이콘
                if has_data and is_synced:
                    icon = "✅"
                elif has_data and not is_synced:
                    icon = "⚠️"
                else:
                    icon = "⬜"

                st.caption(f"{icon} {name}")
                if has_data:
                    st.caption(f"   {count}개")


def render_sync_buttons(current_process: ProcessType = None):
    """현재 프로세스에 맞는 동기화 버튼 렌더링"""

    manager = get_sync_manager()

    st.markdown("#### 🔄 데이터 동기화")

    # ============================================================
    # 이미지 생성 페이지에서
    # ============================================================

    if current_process == ProcessType.IMAGE_GENERATION:
        col1, col2, col3 = st.columns(3)

        with col1:
            if st.button(
                "📤 Vrew Export에 반영",
                key="sync_images_to_vrew",
                help="생성된 이미지를 Vrew Export에 동기화",
                use_container_width=True
            ):
                result = manager.sync_to_vrew_export()
                if result["success"]:
                    st.success(f"✅ {result['message']}")
                else:
                    st.error(f"❌ {result['message']}")

        with col2:
            if st.button(
                "📤 스토리보드에 반영",
                key="sync_images_to_storyboard",
                help="생성된 이미지를 스토리보드에 동기화",
                use_container_width=True
            ):
                result = manager.sync_to_storyboard()
                if result["success"]:
                    st.success(f"✅ {result['message']}")
                else:
                    st.error(f"❌ {result['message']}")

        with col3:
            if st.button(
                "📂 폴더에서 이미지 스캔",
                key="sync_scan_images_folder",
                help="프로젝트 폴더에서 이미지를 스캔하여 매핑",
                use_container_width=True
            ):
                result = manager.sync_images_from_folder()
                if result["success"]:
                    st.success(f"✅ {result['message']}")
                else:
                    st.error(f"❌ {result['message']}")

    # ============================================================
    # Vrew Export 페이지에서
    # ============================================================

    elif current_process == ProcessType.VREW_EXPORT:
        col1, col2, col3 = st.columns(3)

        with col1:
            if st.button(
                "🔄 이미지 + TTS 동기화",
                key="sync_all_to_vrew",
                type="primary",
                help="이미지 생성과 TTS 결과를 모두 동기화",
                use_container_width=True
            ):
                result = manager.sync_to_vrew_export()
                if result["success"]:
                    st.success(f"✅ {result['message']}")
                    st.rerun()
                else:
                    st.error(f"❌ {result['message']}")

        with col2:
            if st.button(
                "📂 폴더에서 전체 스캔",
                key="sync_scan_all_folders",
                help="이미지와 오디오 폴더를 모두 스캔",
                use_container_width=True
            ):
                img_result = manager.sync_images_from_folder()
                audio_result = manager.sync_audio_from_folder()

                st.info(f"이미지: {img_result['message']}")
                st.info(f"오디오: {audio_result['message']}")

                # 다시 동기화
                manager.sync_to_vrew_export()
                st.rerun()

        with col3:
            if st.button(
                "📂 오디오만 스캔",
                key="sync_scan_audio_folder",
                help="오디오 폴더에서 TTS 파일 스캔",
                use_container_width=True
            ):
                result = manager.sync_audio_from_folder()
                if result["success"]:
                    st.success(f"✅ {result['message']}")
                else:
                    st.error(f"❌ {result['message']}")

    # ============================================================
    # 스토리보드 페이지에서
    # ============================================================

    elif current_process == ProcessType.STORYBOARD:
        col1, col2, col3 = st.columns(3)

        with col1:
            if st.button(
                "🔄 전체 자료 동기화",
                key="sync_all_to_storyboard",
                type="primary",
                help="이미지, 인포그래픽, 동영상 모두 동기화",
                use_container_width=True
            ):
                result = manager.sync_to_storyboard()
                if result["success"]:
                    st.success(f"✅ {result['message']}")
                    st.rerun()
                else:
                    st.error(f"❌ {result['message']}")

        with col2:
            if st.button(
                "📂 폴더에서 자료 스캔",
                key="sync_scan_storyboard_folders",
                help="프로젝트 폴더에서 모든 자료 스캔",
                use_container_width=True
            ):
                manager.sync_images_from_folder()
                manager.sync_audio_from_folder()
                manager.sync_to_storyboard()
                st.success("✅ 폴더 스캔 및 동기화 완료")
                st.rerun()

        with col3:
            if st.button(
                "📤 Vrew Export에도 반영",
                key="sync_storyboard_to_vrew",
                help="스토리보드 데이터를 Vrew Export에도 동기화",
                use_container_width=True
            ):
                result = manager.sync_to_vrew_export()
                if result["success"]:
                    st.success(f"✅ {result['message']}")
                else:
                    st.error(f"❌ {result['message']}")

    # ============================================================
    # 씬 분석 페이지에서
    # ============================================================

    elif current_process == ProcessType.SCENE_ANALYSIS:
        col1, col2 = st.columns(2)

        with col1:
            if st.button(
                "📤 모든 프로세스에 씬 데이터 전파",
                key="sync_scenes_to_all",
                type="primary",
                help="분석된 씬을 모든 하위 프로세스에 동기화",
                use_container_width=True
            ):
                result = manager.sync_scenes_to_all()
                if result["success"]:
                    st.success(f"✅ {result['message']}")
                else:
                    st.error(f"❌ {result['message']}")

        with col2:
            if st.button(
                "🔄 Vrew + 스토리보드 동기화",
                key="sync_scenes_to_exports",
                help="씬 데이터를 Vrew Export와 스토리보드에 동기화",
                use_container_width=True
            ):
                vrew_result = manager.sync_to_vrew_export()
                sb_result = manager.sync_to_storyboard()
                st.success(f"✅ Vrew: {vrew_result['message']}")
                st.success(f"✅ 스토리보드: {sb_result['message']}")

    # ============================================================
    # 기본 (프로세스 지정 없을 때)
    # ============================================================

    else:
        col1, col2, col3 = st.columns(3)

        with col1:
            if st.button(
                "🔄 Vrew Export 동기화",
                key="sync_default_to_vrew",
                use_container_width=True
            ):
                result = manager.sync_to_vrew_export()
                if result["success"]:
                    st.success(f"✅ {result['message']}")
                else:
                    st.error(f"❌ {result['message']}")

        with col2:
            if st.button(
                "🔄 스토리보드 동기화",
                key="sync_default_to_storyboard",
                use_container_width=True
            ):
                result = manager.sync_to_storyboard()
                if result["success"]:
                    st.success(f"✅ {result['message']}")
                else:
                    st.error(f"❌ {result['message']}")

        with col3:
            if st.button(
                "📂 폴더 스캔",
                key="sync_default_scan_folders",
                use_container_width=True
            ):
                img_result = manager.sync_images_from_folder()
                audio_result = manager.sync_audio_from_folder()
                st.info(f"이미지: {img_result['message']}")
                st.info(f"오디오: {audio_result['message']}")


def render_manual_sync_panel():
    """수동 동기화 패널 (전체 동기화 옵션)"""

    manager = get_sync_manager()

    with st.expander("🔧 수동 동기화 옵션", expanded=False):
        st.caption("자동 동기화가 작동하지 않을 때 수동으로 데이터를 동기화합니다.")

        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**데이터 소스:**")

            sync_source = st.radio(
                "소스",
                options=[
                    "세션 데이터 (현재 작업)",
                    "프로젝트 폴더 스캔"
                ],
                key="manual_sync_source",
                label_visibility="collapsed"
            )

        with col2:
            st.markdown("**동기화 대상:**")

            sync_targets = st.multiselect(
                "대상",
                options=[
                    "Vrew Export",
                    "스토리보드"
                ],
                default=["Vrew Export", "스토리보드"],
                key="manual_sync_targets",
                label_visibility="collapsed"
            )

        if st.button("🔄 수동 동기화 실행", type="primary", use_container_width=True, key="manual_sync_execute"):
            with st.spinner("동기화 중..."):
                results = []

                # 폴더 스캔
                if "프로젝트 폴더" in sync_source:
                    manager.sync_images_from_folder()
                    manager.sync_audio_from_folder()

                # 대상별 동기화
                if "Vrew Export" in sync_targets:
                    result = manager.sync_to_vrew_export()
                    results.append(f"Vrew Export: {result['message']}")

                if "스토리보드" in sync_targets:
                    result = manager.sync_to_storyboard()
                    results.append(f"스토리보드: {result['message']}")

                for msg in results:
                    st.success(msg)

            st.rerun()


def render_sync_log():
    """동기화 로그 표시"""

    manager = get_sync_manager()
    log = manager.get_sync_log(limit=10)

    if not log:
        st.info("동기화 로그가 없습니다.")
        return

    with st.expander("📋 최근 동기화 로그", expanded=False):
        for entry in reversed(log):
            timestamp = entry.get("timestamp", "")[:19]
            process = entry.get("process", "")
            result = entry.get("result", {})
            success = result.get("success", False)
            message = result.get("message", "")

            icon = "✅" if success else "❌"
            st.caption(f"{icon} [{timestamp}] {process}: {message}")


def render_quick_sync_sidebar():
    """사이드바용 간단한 동기화 버튼"""

    with st.sidebar.expander("🔄 빠른 동기화", expanded=False):
        manager = get_sync_manager()

        if st.button("🔄 전체 동기화", key="sidebar_sync_all", use_container_width=True):
            manager.sync_images_from_folder()
            manager.sync_audio_from_folder()
            manager.sync_to_vrew_export()
            manager.sync_to_storyboard()
            st.success("✅ 전체 동기화 완료!")
            st.rerun()

        if st.button("📂 폴더 스캔", key="sidebar_scan_folders", use_container_width=True):
            img_result = manager.sync_images_from_folder()
            audio_result = manager.sync_audio_from_folder()
            st.caption(f"이미지: {img_result.get('mapped_scenes', 0)}개")
            st.caption(f"오디오: {audio_result.get('mapped_scenes', 0)}개")
