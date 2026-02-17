# -*- coding: utf-8 -*-
"""
12단계: 프로젝트 초기화

3단계 레벨의 프로젝트 초기화 기능:
1. 영상(Video) 초기화 - 특정 영상의 모든 산출물 삭제
2. 채널(Channel) 초기화 - 특정 채널의 모든 프로젝트 삭제
3. 전체(All) 초기화 - 모든 프로젝트 삭제

삭제 모드:
- Hard Delete: 실제 파일 삭제 (복구 불가)
- Soft Delete: 숨김 처리 (복구 가능)
"""

import streamlit as st
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from utils.project_manager import render_project_sidebar
from utils.project_reset_manager import (
    get_reset_manager, DeleteMode,
    get_quick_select_presets, get_preserve_presets,
    get_category_name, get_category_icon
)

# 페이지 설정
st.set_page_config(
    page_title="프로젝트 초기화",
    page_icon="🗑️",
    layout="wide"
)

# 사이드바
render_project_sidebar()


def render_video_reset_tab():
    """영상 프로젝트 초기화 탭 (선택적 삭제 지원)"""
    st.markdown("### 🎬 영상 프로젝트 초기화")
    st.caption("특정 영상의 산출물을 선택적으로 초기화합니다. 프롬프트는 유지하고 이미지만 삭제하는 등 세밀한 제어가 가능합니다.")

    manager = get_reset_manager()

    # 프로젝트 선택
    projects = manager.get_all_projects()

    if not projects:
        st.info("초기화할 프로젝트가 없습니다.")
        return

    col1, col2 = st.columns(2)

    with col1:
        project_options = [p['project_id'] for p in projects]
        selected_project = st.selectbox(
            "프로젝트 선택",
            options=project_options,
            key="reset_video_project",
            help="초기화할 프로젝트를 선택하세요"
        )

    with col2:
        if selected_project:
            videos = manager.get_project_videos(selected_project)
            video_options = [v['video_id'] for v in videos]

            if video_options:
                selected_video = st.selectbox(
                    "영상 선택",
                    options=video_options,
                    key="reset_video_id",
                    help="초기화할 영상을 선택하세요"
                )
            else:
                st.warning("선택한 프로젝트에 영상이 없습니다.")
                selected_video = None
        else:
            selected_video = None

    # 영상이 선택되면 항목 스캔 및 선택 UI 표시
    if selected_project and selected_video:
        st.markdown("---")

        # 항목 스캔
        items = manager.scan_video_items(selected_project, selected_video)

        if not items:
            st.info("삭제할 항목이 없습니다.")
            return

        # 세션 상태 초기화
        state_key = f"selected_items_{selected_project}_{selected_video}"
        if state_key not in st.session_state:
            # 기본값: 미디어 선택, 프롬프트/분석 보존
            default_selected = set()
            for item in items:
                if item['category'] in ['media', 'output', 'audio']:
                    default_selected.add(item['id'])
            st.session_state[state_key] = default_selected

        # 빠른 선택 프리셋
        st.markdown("##### 빠른 선택")
        quick_presets = get_quick_select_presets()

        preset_cols = st.columns(len(quick_presets))
        for i, (preset_id, preset) in enumerate(quick_presets.items()):
            with preset_cols[i]:
                if st.button(
                    f"{preset['icon']} {preset['name']}",
                    key=f"quick_{preset_id}",
                    help=preset['description'],
                    use_container_width=True
                ):
                    new_selected = manager.get_items_by_preset(items, preset_id, 'select')
                    st.session_state[state_key] = new_selected
                    st.rerun()

        # 보존 프리셋
        st.markdown("##### 보존 프리셋")
        st.caption("선택된 항목 중 특정 카테고리를 보존합니다")

        preserve_presets = get_preserve_presets()
        preserve_cols = st.columns(len(preserve_presets))

        for i, (preset_id, preset) in enumerate(preserve_presets.items()):
            with preserve_cols[i]:
                if st.button(
                    f"{preset['icon']} {preset['name']}",
                    key=f"preserve_{preset_id}",
                    help=preset['description'],
                    use_container_width=True
                ):
                    # 현재 전체 선택 후 보존 프리셋 적용
                    all_ids = {item['id'] for item in items}
                    new_selected = manager.get_items_by_preset(items, preset_id, 'preserve')
                    st.session_state[state_key] = new_selected
                    st.rerun()

        st.markdown("---")

        # 항목 선택 UI (카테고리별 그룹화)
        st.markdown("##### 삭제할 항목 선택")

        # 카테고리별 그룹화
        items_by_category = {}
        for item in items:
            cat = item['category']
            if cat not in items_by_category:
                items_by_category[cat] = []
            items_by_category[cat].append(item)

        # 카테고리 순서 정의
        category_order = ['media', 'output', 'audio', 'analysis', 'settings', 'other']

        selected_ids = st.session_state[state_key].copy()

        for cat in category_order:
            if cat not in items_by_category:
                continue

            cat_items = items_by_category[cat]
            cat_name = get_category_name(cat)
            cat_icon = get_category_icon(cat)

            # 카테고리 헤더
            cat_total_size = sum(item['size'] for item in cat_items)
            cat_selected = sum(1 for item in cat_items if item['id'] in selected_ids)

            with st.expander(
                f"{cat_icon} {cat_name} ({cat_selected}/{len(cat_items)}개 선택, {manager.format_size(cat_total_size)})",
                expanded=(cat in ['media', 'output'])
            ):
                # 카테고리 전체 선택/해제
                col1, col2 = st.columns([3, 1])
                with col1:
                    select_all = st.checkbox(
                        f"{cat_name} 전체 선택",
                        value=(cat_selected == len(cat_items)),
                        key=f"cat_all_{cat}"
                    )
                with col2:
                    cat_selected_size = sum(item['size'] for item in cat_items if item['id'] in selected_ids)
                    st.caption(f"선택: {manager.format_size(cat_selected_size)}")

                # 전체 선택/해제 적용
                if select_all and cat_selected != len(cat_items):
                    for item in cat_items:
                        selected_ids.add(item['id'])
                    st.session_state[state_key] = selected_ids
                    st.rerun()
                elif not select_all and cat_selected > 0 and cat_selected == len(cat_items):
                    for item in cat_items:
                        selected_ids.discard(item['id'])
                    st.session_state[state_key] = selected_ids
                    st.rerun()

                # 개별 항목 체크박스
                for item in cat_items:
                    col1, col2, col3 = st.columns([0.5, 3, 1])

                    with col1:
                        is_selected = st.checkbox(
                            "",
                            value=item['id'] in selected_ids,
                            key=f"item_{item['id']}",
                            label_visibility="collapsed"
                        )

                        if is_selected and item['id'] not in selected_ids:
                            selected_ids.add(item['id'])
                            st.session_state[state_key] = selected_ids
                            st.rerun()
                        elif not is_selected and item['id'] in selected_ids:
                            selected_ids.discard(item['id'])
                            st.session_state[state_key] = selected_ids
                            st.rerun()

                    with col2:
                        file_info = f"{item['file_count']}개 파일" if item['type'] == 'folder' else ""
                        st.markdown(f"{item['icon']} **{item['name']}** {file_info}")

                    with col3:
                        st.caption(manager.format_size(item['size']))

        # 삭제 요약
        st.markdown("---")
        st.markdown("##### 삭제 요약")

        summary = manager.get_deletion_summary(items, selected_ids)

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("삭제 항목", f"{summary['selected_count']}개", delta=None)
        with col2:
            st.metric("삭제 크기", manager.format_size(summary['delete_size']), delta=None)
        with col3:
            st.metric("보존 항목", f"{summary['preserved_count']}개", delta=None)
        with col4:
            st.metric("보존 크기", manager.format_size(summary['preserve_size']), delta=None)

        # 카테고리별 상세
        with st.expander("카테고리별 상세", expanded=False):
            for cat in category_order:
                cat_summary = summary['by_category'].get(cat, {})
                if cat_summary.get('delete', 0) > 0 or cat_summary.get('preserve', 0) > 0:
                    cat_name = get_category_name(cat)
                    cat_icon = get_category_icon(cat)
                    st.markdown(
                        f"- {cat_icon} **{cat_name}**: "
                        f"삭제 {cat_summary.get('delete', 0)}개 ({manager.format_size(cat_summary.get('delete_size', 0))}), "
                        f"보존 {cat_summary.get('preserve', 0)}개"
                    )

        # 삭제 모드 선택
        st.markdown("---")
        st.markdown("##### 삭제 모드")

        delete_mode = st.radio(
            "삭제 모드 선택",
            options=["hard", "soft"],
            format_func=lambda x: {
                "hard": "🗑️ 하드 삭제 (실제 파일 삭제, 복구 불가)",
                "soft": "👁️ 소프트 삭제 (숨김 처리, 복구 가능)"
            }[x],
            key="reset_video_mode",
            horizontal=True,
            label_visibility="collapsed"
        )

        # 확인 및 실행
        st.markdown("---")

        if delete_mode == "hard":
            st.error("⚠️ **주의**: 하드 삭제는 복구할 수 없습니다!")

        if summary['selected_count'] == 0:
            st.warning("삭제할 항목을 선택하세요.")
            confirm = False
        else:
            confirm = st.checkbox(
                f"선택한 {summary['selected_count']}개 항목 ({manager.format_size(summary['delete_size'])}) 삭제에 동의합니다",
                key="confirm_reset_video"
            )

        btn_disabled = not confirm or summary['selected_count'] == 0

        if st.button(
            f"🗑️ 선택 항목 삭제 ({summary['selected_count']}개)",
            disabled=btn_disabled,
            type="primary" if not btn_disabled else "secondary",
            key="btn_reset_video",
            use_container_width=True
        ):
            with st.spinner("선택 항목 삭제 중..."):
                result = manager.delete_selected_items(
                    project_id=selected_project,
                    video_id=selected_video,
                    selected_ids=selected_ids,
                    mode=DeleteMode.HARD if delete_mode == "hard" else DeleteMode.SOFT,
                    confirm=True
                )

                if result['success']:
                    st.success(f"✅ 삭제 완료!")
                    st.info(
                        f"삭제: {len(result['deleted_items'])}개 ({manager.format_size(result['total_deleted_size'])}), "
                        f"보존: {len(result['preserved_items'])}개 ({manager.format_size(result['total_preserved_size'])})"
                    )
                    # 세션 상태 초기화
                    del st.session_state[state_key]
                    st.balloons()
                    st.rerun()
                else:
                    st.error(f"❌ 오류 발생:")
                    for err in result['errors']:
                        st.text(f"  • {err}")


def render_channel_reset_tab():
    """채널 프로젝트 초기화 탭"""
    st.markdown("### 📺 채널 프로젝트 초기화")
    st.caption("선택한 채널의 모든 프로젝트와 영상을 초기화합니다.")

    manager = get_reset_manager()

    # 채널 선택
    channels = manager.get_all_channels()

    if not channels:
        st.info("초기화할 채널이 없습니다.")
        return

    selected_channel = st.selectbox(
        "채널 선택",
        options=channels,
        key="reset_channel_select",
        help="초기화할 채널을 선택하세요"
    )

    # 삭제 모드 선택
    st.markdown("---")
    st.markdown("##### 삭제 모드")

    delete_mode = st.radio(
        "삭제 모드 선택",
        options=["hard", "soft"],
        format_func=lambda x: {
            "hard": "🗑️ 하드 삭제 (실제 파일 삭제)",
            "soft": "👁️ 소프트 삭제 (숨김 처리)"
        }[x],
        key="reset_channel_mode",
        horizontal=True,
        label_visibility="collapsed"
    )

    # 미리보기
    if selected_channel:
        with st.expander("📋 삭제될 항목 미리보기", expanded=True):
            preview = manager.preview_reset('channel', channel_name=selected_channel)
            projects = manager.get_channel_projects(selected_channel)

            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("프로젝트 수", f"{len(projects)}개")
            with col2:
                total_videos = sum(len(p.get('videos', [])) for p in projects)
                st.metric("총 영상 수", f"{total_videos}개")
            with col3:
                st.metric("총 크기", manager.format_size(preview['total_size']))

            if preview['items']:
                st.markdown("**삭제될 프로젝트:**")
                for item in preview['items'][:10]:
                    size_str = manager.format_size(item['size'])
                    videos = item.get('videos', 0)
                    st.text(f"  📁 {item['name']} ({videos}개 영상, {size_str})")

                if len(preview['items']) > 10:
                    st.caption(f"... 외 {len(preview['items']) - 10}개")

    # 확인 및 실행
    st.markdown("---")

    if delete_mode == "hard":
        st.error("⚠️ **주의**: 하드 삭제는 복구할 수 없습니다!")

    confirm = st.checkbox(
        f"'{selected_channel}' 채널 전체 초기화에 동의합니다",
        key="confirm_reset_channel",
        disabled=not selected_channel
    )

    btn_disabled = not (confirm and selected_channel)

    if st.button(
        "🗑️ 채널 초기화 실행",
        disabled=btn_disabled,
        type="primary" if not btn_disabled else "secondary",
        key="btn_reset_channel",
        use_container_width=True
    ):
        with st.spinner("채널 초기화 중..."):
            result = manager.reset_channel(
                channel_name=selected_channel,
                mode=DeleteMode.HARD if delete_mode == "hard" else DeleteMode.SOFT,
                confirm=True
            )

            if result['success']:
                st.success(f"✅ 채널 초기화 완료!")
                st.info(f"처리된 프로젝트: {len(result['projects_deleted'])}개, 영상: {len(result['videos_deleted'])}개")
                st.balloons()
            else:
                st.error(f"❌ 오류 발생:")
                for err in result['errors']:
                    st.text(f"  • {err}")


def render_all_reset_tab():
    """전체 초기화 탭"""
    st.markdown("### 🌐 전체 초기화")
    st.caption("모든 채널, 모든 프로젝트, 모든 영상을 초기화합니다.")

    manager = get_reset_manager()

    # 경고
    st.error("""
    ⚠️ **위험**: 이 작업은 모든 프로젝트 데이터를 삭제합니다!

    삭제되는 항목:
    - 모든 프로젝트 폴더
    - 모든 씬 분석 데이터
    - 모든 이미지 파일
    - 모든 오디오 파일 (TTS 제외)
    - 모든 비디오 파일
    """)

    # 삭제 모드 선택
    st.markdown("---")
    st.markdown("##### 삭제 모드")

    delete_mode = st.radio(
        "삭제 모드 선택",
        options=["hard", "soft"],
        format_func=lambda x: {
            "hard": "🗑️ 하드 삭제 (완전 삭제, 복구 불가)",
            "soft": "👁️ 소프트 삭제 (숨김 처리, 복구 가능)"
        }[x],
        key="reset_all_mode",
        horizontal=True,
        label_visibility="collapsed"
    )

    # 옵션
    st.markdown("##### 추가 옵션")
    col1, col2 = st.columns(2)

    with col1:
        keep_settings = st.checkbox(
            "설정 파일 유지",
            value=True,
            key="reset_all_keep_settings",
            help="API 설정 등 환경 설정 파일을 유지합니다"
        )

    with col2:
        delete_cache = st.checkbox(
            "캐시 삭제",
            value=True,
            key="reset_all_delete_cache",
            help="임시 파일과 캐시를 함께 삭제합니다"
        )

    # 미리보기
    with st.expander("📋 삭제될 항목 미리보기", expanded=True):
        preview = manager.preview_reset('all')
        channels = manager.get_all_channels()

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("채널 수", f"{len(channels)}개")
        with col2:
            st.metric("프로젝트 수", f"{len(preview['items'])}개")
        with col3:
            st.metric("총 파일 수", f"{preview['total_files']}개")
        with col4:
            st.metric("총 크기", manager.format_size(preview['total_size']))

        if preview['items']:
            st.markdown("**채널별 프로젝트:**")
            for channel in channels:
                channel_projects = [p for p in preview['items'] if p.get('channel') == channel]
                if channel_projects:
                    total_size = sum(p['size'] for p in channel_projects)
                    st.text(f"  📺 {channel}: {len(channel_projects)}개 프로젝트 ({manager.format_size(total_size)})")

    # 이중 확인
    st.markdown("---")
    st.warning("⚠️ 전체 초기화를 실행하려면 아래 두 가지 확인이 모두 필요합니다.")

    confirm_1 = st.checkbox(
        "전체 초기화에 동의합니다",
        key="confirm_reset_all_1"
    )

    confirm_text = st.text_input(
        "확인을 위해 'DELETE ALL'을 입력하세요",
        key="confirm_reset_all_2",
        placeholder="DELETE ALL"
    )

    can_reset = confirm_1 and confirm_text == "DELETE ALL"

    if st.button(
        "🗑️ 전체 초기화 실행",
        disabled=not can_reset,
        type="primary" if can_reset else "secondary",
        key="btn_reset_all",
        use_container_width=True
    ):
        with st.spinner("전체 초기화 중... (시간이 걸릴 수 있습니다)"):
            result = manager.reset_all(
                mode=DeleteMode.HARD if delete_mode == "hard" else DeleteMode.SOFT,
                confirm=True,
                keep_settings=keep_settings,
                delete_cache=delete_cache
            )

            if result['success']:
                st.success(f"✅ 전체 초기화 완료!")
                st.info(f"""
                처리 결과:
                - 채널: {len(result['channels_deleted'])}개
                - 프로젝트: {len(result['projects_deleted'])}개
                - 영상: {result['total_videos']}개
                - 크기: {manager.format_size(result['total_size'])}
                """)
                st.balloons()
                st.rerun()
            else:
                st.error(f"❌ 오류 발생:")
                for err in result['errors'][:10]:
                    st.text(f"  • {err}")
                if len(result['errors']) > 10:
                    st.caption(f"... 외 {len(result['errors']) - 10}개 오류")


def render_restore_tab():
    """복구 탭"""
    st.markdown("### ♻️ 소프트 삭제 복구")
    st.caption("숨김 처리된 항목을 복구합니다.")

    manager = get_reset_manager()

    # 숨김 항목 목록
    hidden_items = manager.get_hidden_items()

    if not hidden_items:
        st.info("숨김 처리된 항목이 없습니다.")
        st.caption("소프트 삭제를 사용하면 여기에서 복구할 수 있습니다.")
        return

    st.write(f"**숨김 처리된 항목: {len(hidden_items)}개**")

    # 항목 목록
    for i, item in enumerate(hidden_items):
        col1, col2, col3 = st.columns([3, 1, 1])

        with col1:
            icon = "📁" if item['type'] == 'directory' else "📄"
            st.text(f"{icon} {item['name']}")
            st.caption(f"숨김 일시: {item['hidden_at'][:19] if item['hidden_at'] else 'N/A'}")

        with col2:
            st.caption(manager.format_size(item['size']))

        with col3:
            if st.button("복구", key=f"restore_{i}", use_container_width=True):
                original_path = Path(item['original_path'])
                if manager.restore_hidden(original_path):
                    st.success(f"✅ '{item['name']}' 복구됨!")
                    st.rerun()
                else:
                    st.error("복구 실패")

    # 전체 복구
    st.markdown("---")

    if st.button("🔄 모두 복구", key="restore_all", use_container_width=True):
        result = manager.restore_all_hidden()

        if result['restored']:
            st.success(f"✅ {len(result['restored'])}개 항목 복구됨!")
            st.rerun()

        if result['errors']:
            st.error("일부 항목 복구 실패:")
            for err in result['errors']:
                st.text(f"  • {err}")


def render_status_tab():
    """상태 확인 탭"""
    st.markdown("### 📊 프로젝트 현황")
    st.caption("현재 프로젝트 구조와 사용량을 확인합니다.")

    manager = get_reset_manager()

    # 전체 요약
    projects = manager.get_all_projects()
    channels = manager.get_all_channels()

    col1, col2, col3, col4 = st.columns(4)

    total_size = sum(p.get('size', 0) for p in projects)
    total_files = sum(p.get('file_count', 0) for p in projects)
    total_videos = sum(len(p.get('videos', [])) for p in projects)

    with col1:
        st.metric("채널 수", f"{len(channels)}개")
    with col2:
        st.metric("프로젝트 수", f"{len(projects)}개")
    with col3:
        st.metric("총 영상 수", f"{total_videos}개")
    with col4:
        st.metric("총 사용량", manager.format_size(total_size))

    st.markdown("---")

    # 채널별 상세
    st.markdown("##### 채널별 현황")

    for channel in channels:
        channel_projects = [p for p in projects if p.get('channel') == channel]

        with st.expander(f"📺 {channel} ({len(channel_projects)}개 프로젝트)", expanded=False):
            for project in channel_projects:
                col1, col2, col3 = st.columns([3, 1, 1])

                with col1:
                    st.text(f"📁 {project['project_id']}")
                    if project.get('created'):
                        st.caption(f"생성: {project['created']}")

                with col2:
                    videos = project.get('videos', [])
                    st.caption(f"{len(videos)}개 영상")

                with col3:
                    st.caption(manager.format_size(project.get('size', 0)))

                # 영상별 에셋 현황
                for video in manager.get_project_videos(project['project_id']):
                    assets = video.get('assets', {})
                    asset_summary = ", ".join([
                        f"{k}:{v}" for k, v in assets.items() if v > 0
                    ])
                    if asset_summary:
                        st.caption(f"  └ {video['video_id']}: {asset_summary}")


def render_folder_delete_tab():
    """영상/채널 폴더 삭제 탭"""
    st.markdown("### 🗑️ 영상/채널 폴더 삭제")
    st.caption("영상 또는 채널 폴더 전체를 삭제합니다. (휴지통 이동 또는 영구 삭제)")

    st.error("""
    ⚠️ **경고**: 이 작업은 선택한 영상 또는 채널의 **모든 데이터**를 삭제합니다.
    - 이미지, TTS 오디오, 스크립트, 분석 결과, 설정 등 **모든 파일**이 삭제됩니다.
    - 휴지통으로 이동 옵션을 선택하면 '휴지통' 섹션에서 복원할 수 있습니다.
    """)

    st.markdown("---")

    manager = get_reset_manager()

    # 현재 작업 중인 프로젝트/영상
    current_project = st.session_state.get("current_project", "")
    current_video = st.session_state.get("current_video", "")

    # ========================
    # 영상 삭제 섹션
    # ========================
    st.markdown("#### 📹 영상 삭제")

    # 프로젝트 선택
    projects = manager.get_project_list_for_delete()

    if not projects:
        st.info("삭제할 프로젝트가 없습니다.")
    else:
        project_options = {p["name"]: p for p in projects}
        selected_project_name = st.selectbox(
            "프로젝트 선택",
            options=list(project_options.keys()),
            format_func=lambda x: f"{project_options[x]['display_name']} ({project_options[x]['video_count']}개 영상)",
            key="delete_video_project_select"
        )

        if selected_project_name:
            selected_project = project_options[selected_project_name]

            # 영상 목록 조회
            videos = manager.get_video_list_for_delete(selected_project_name)

            if not videos:
                st.info("이 프로젝트에 삭제할 영상이 없습니다.")
            else:
                st.write("**삭제할 영상 선택:**")

                # 세션 상태 초기화
                if "selected_videos_for_delete" not in st.session_state:
                    st.session_state["selected_videos_for_delete"] = set()

                selected_videos = []

                for video in videos:
                    is_current = (video["name"] == current_video and selected_project_name == current_project)

                    col1, col2, col3, col4 = st.columns([0.5, 2.5, 1.5, 1.5])

                    with col1:
                        is_selected = st.checkbox(
                            video["name"],
                            key=f"delete_video_{video['name']}",
                            disabled=is_current,
                            label_visibility="collapsed"
                        )
                        if is_selected:
                            selected_videos.append(video)

                    with col2:
                        status = " 🔴 (현재 작업 중)" if is_current else ""
                        st.write(f"**{video['name']}**{status}")

                    with col3:
                        st.caption(f"{video['file_count']}개 파일")

                    with col4:
                        st.caption(video['size_display'])

                st.markdown("---")

                # 삭제 옵션
                col1, col2 = st.columns(2)

                with col1:
                    use_trash = st.checkbox(
                        "🗑️ 휴지통으로 이동 (복구 가능)",
                        value=True,
                        key="video_delete_use_trash"
                    )

                with col2:
                    if selected_videos:
                        total_size = sum(v["size_bytes"] for v in selected_videos)
                        st.write(f"선택: **{len(selected_videos)}개** ({manager.format_size(total_size)})")

                # 삭제 버튼
                if selected_videos:
                    st.write("")

                    # 확인 입력
                    confirm_text = st.text_input(
                        "삭제를 확인하려면 '삭제'를 입력하세요:",
                        key="video_delete_confirm"
                    )

                    col1, col2 = st.columns([1, 3])

                    with col1:
                        delete_btn = st.button(
                            f"🗑️ {len(selected_videos)}개 영상 삭제",
                            type="primary",
                            disabled=confirm_text != "삭제",
                            key="video_delete_btn"
                        )

                    if delete_btn and confirm_text == "삭제":
                        success_count = 0
                        fail_count = 0

                        for video in selected_videos:
                            result = manager.delete_video_folder(video["path"], use_trash=use_trash)

                            if result["success"]:
                                st.success(f"✅ {video['name']}: {result['message']}")
                                success_count += 1
                            else:
                                st.error(f"❌ {video['name']}: {result['message']}")
                                fail_count += 1

                        if success_count > 0:
                            st.balloons()
                            st.rerun()
                else:
                    st.info("삭제할 영상을 선택해주세요.")

    st.markdown("---")

    # ========================
    # 채널/프로젝트 삭제 섹션
    # ========================
    st.markdown("#### 📁 채널(프로젝트) 삭제")

    st.warning("""
    🚨 **주의**: 채널 전체가 삭제됩니다!
    - 해당 채널의 **모든 영상, 이미지, TTS, 스크립트, 설정** 등이 삭제됩니다.
    """)

    if not projects:
        st.info("삭제할 채널이 없습니다.")
    else:
        st.write("**삭제할 채널 선택:**")

        selected_projects = []

        for project in projects:
            is_current = project["name"] == current_project

            col1, col2, col3, col4 = st.columns([0.5, 3, 2, 1.5])

            with col1:
                is_selected = st.checkbox(
                    project["name"],
                    key=f"delete_project_{project['name']}",
                    disabled=is_current,
                    label_visibility="collapsed"
                )
                if is_selected:
                    selected_projects.append(project)

            with col2:
                status = " 🔴 (현재 작업 중)" if is_current else ""
                st.write(f"**{project['display_name']}**{status}")
                st.caption(project["name"])

            with col3:
                st.caption(f"{project['video_count']}개 영상, {project['file_count']}개 파일")

            with col4:
                st.caption(project['size_display'])

        st.markdown("---")

        # 삭제 옵션
        col1, col2 = st.columns(2)

        with col1:
            project_use_trash = st.checkbox(
                "🗑️ 휴지통으로 이동 (복구 가능)",
                value=True,
                key="project_delete_use_trash"
            )

        with col2:
            if selected_projects:
                total_size = sum(p["size_bytes"] for p in selected_projects)
                total_videos = sum(p["video_count"] for p in selected_projects)
                st.write(f"선택: **{len(selected_projects)}개 채널** ({total_videos}개 영상, {manager.format_size(total_size)})")

        # 삭제 버튼
        if selected_projects:
            st.write("")

            # 이중 확인 (채널명 입력)
            channel_names = ", ".join([p["display_name"] for p in selected_projects])
            st.warning(f"🚨 다음 채널이 삭제됩니다: **{channel_names}**")

            confirm_text = st.text_input(
                "삭제를 확인하려면 '영구삭제'를 입력하세요:",
                key="project_delete_confirm"
            )

            col1, col2 = st.columns([1, 3])

            with col1:
                delete_btn = st.button(
                    f"🗑️ {len(selected_projects)}개 채널 삭제",
                    type="primary",
                    disabled=confirm_text != "영구삭제",
                    key="project_delete_btn"
                )

            if delete_btn and confirm_text == "영구삭제":
                success_count = 0
                fail_count = 0

                for project in selected_projects:
                    result = manager.delete_project_folder(project["path"], use_trash=project_use_trash)

                    if result["success"]:
                        st.success(f"✅ {project['display_name']}: {result['message']}")
                        success_count += 1
                    else:
                        st.error(f"❌ {project['display_name']}: {result['message']}")
                        fail_count += 1

                if success_count > 0:
                    # session_state 초기화 (현재 채널이 삭제된 경우)
                    if current_project in [p["name"] for p in selected_projects]:
                        st.session_state.pop("current_project", None)
                        st.session_state.pop("project_path", None)

                    st.balloons()
                    st.rerun()
        else:
            st.info("삭제할 채널을 선택해주세요.")

    st.markdown("---")

    # ========================
    # 휴지통 섹션
    # ========================
    st.markdown("#### 🗑️ 휴지통")

    trash_contents = manager.get_trash_contents()

    if trash_contents["total_size"] == 0:
        st.info("휴지통이 비어 있습니다.")
    else:
        st.write(f"**휴지통 사용량**: {trash_contents['total_size_display']}")

        col1, col2 = st.columns(2)

        with col1:
            st.write(f"- 채널: {len(trash_contents['projects'])}개")

        with col2:
            st.write(f"- 영상: {len(trash_contents['videos'])}개")

        # 삭제된 프로젝트 목록
        if trash_contents["projects"]:
            with st.expander(f"📁 삭제된 채널 ({len(trash_contents['projects'])}개)", expanded=True):
                for project in trash_contents["projects"]:
                    col1, col2, col3 = st.columns([3, 1, 1])

                    with col1:
                        st.write(f"**{project['name']}** ({project['size_display']})")
                        if project.get("deleted_at"):
                            st.caption(f"삭제: {project['deleted_at']}")

                    with col2:
                        if st.button("🔄 복구", key=f"restore_project_{project['name']}", use_container_width=True):
                            result = manager.restore_from_trash(project["path"], "project")
                            if result["success"]:
                                st.success(result["message"])
                                st.rerun()
                            else:
                                st.error(result["message"])

                    with col3:
                        if st.button("🗑️ 영구삭제", key=f"perm_delete_project_{project['name']}", use_container_width=True):
                            result = manager.permanently_delete_from_trash(project["path"])
                            if result["success"]:
                                st.success(result["message"])
                                st.rerun()
                            else:
                                st.error(result["message"])

        # 삭제된 영상 목록
        if trash_contents["videos"]:
            with st.expander(f"📹 삭제된 영상 ({len(trash_contents['videos'])}개)", expanded=True):
                for video in trash_contents["videos"]:
                    col1, col2, col3 = st.columns([3, 1, 1])

                    with col1:
                        st.write(f"**{video['name']}** ({video['size_display']})")
                        if video.get("deleted_at"):
                            st.caption(f"삭제: {video['deleted_at']}")

                    with col2:
                        if st.button("🔄 복구", key=f"restore_video_{video['name']}", use_container_width=True):
                            result = manager.restore_from_trash(video["path"], "video")
                            if result["success"]:
                                st.success(result["message"])
                                st.rerun()
                            else:
                                st.error(result["message"])

                    with col3:
                        if st.button("🗑️ 영구삭제", key=f"perm_delete_video_{video['name']}", use_container_width=True):
                            result = manager.permanently_delete_from_trash(video["path"])
                            if result["success"]:
                                st.success(result["message"])
                                st.rerun()
                            else:
                                st.error(result["message"])

        # 휴지통 비우기 버튼
        st.markdown("---")

        col1, col2 = st.columns([1, 3])

        with col1:
            if st.button("🗑️ 휴지통 비우기", key="empty_trash", type="secondary"):
                result = manager.empty_trash()
                if result["success"]:
                    st.success(result["message"])
                    st.rerun()
                else:
                    st.error(result["message"])


def main():
    """메인 함수"""
    st.title("🗑️ 프로젝트 초기화")
    st.caption("프로젝트, 채널, 영상 단위로 데이터를 초기화합니다.")

    # 탭
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "🎬 영상 초기화",
        "📺 채널 초기화",
        "🌐 전체 초기화",
        "♻️ 복구",
        "📊 현황",
        "🗑️ 폴더 삭제"
    ])

    with tab1:
        render_video_reset_tab()

    with tab2:
        render_channel_reset_tab()

    with tab3:
        render_all_reset_tab()

    with tab4:
        render_restore_tab()

    with tab5:
        render_status_tab()

    with tab6:
        render_folder_delete_tab()


if __name__ == "__main__":
    main()
