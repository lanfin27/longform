"""
2단계: 영상 리서치 (고도화 버전)

YouTube API를 사용하여 키워드 기반 영상 검색 및 분석
- 롱폼/쇼츠 구분 검색
- 영상 길이 수동 입력
- 상세 데이터 (채널 정보, 구독자, 좋아요 등)
- 필터 및 정렬 기능
- 엑셀 추출 기능
"""
import streamlit as st
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
import sys

# 루트 디렉토리 설정
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from utils.project_manager import (
    ensure_project_selected,
    get_current_project,
    render_project_sidebar,
    update_project_step
)
from utils.data_loader import (
    save_video_research,
    load_video_research,
    save_selected_videos,
    load_selected_videos
)
from core.youtube.cache import get_cache
from config.settings import YOUTUBE_API_KEY
from utils.api_helper import (
    require_api_key,
    show_api_status_sidebar
)
# v2.0: 새로운 모듈 추가
from utils.bookmark_storage import BookmarkStorage
from utils.thumbnail_downloader import ThumbnailDownloader
from utils.excel_export import export_with_metrics, get_excel_filename
from utils.youtube_service import (
    YouTubeService,
    SEARCH_SCOPE_OPTIONS,
    filter_videos_by_search_scope,
    get_search_scope_description
)

# 페이지 설정
st.set_page_config(
    page_title="영상 리서치",
    page_icon="🔍",
    layout="wide"
)

# CSS 스타일
st.markdown("""
<style>
/* 섹션 헤더 */
.section-header {
    background: linear-gradient(90deg, #f0f2f6 0%, transparent 100%);
    padding: 10px 15px;
    border-left: 4px solid #667eea;
    margin: 15px 0 10px 0;
    font-weight: 600;
}

/* 메트릭 카드 */
div[data-testid="metric-container"] {
    background: #f8f9fa;
    padding: 10px;
    border-radius: 8px;
}

/* 비디오 카드 */
.video-card {
    background: #f8f9fa;
    border: 1px solid #dee2e6;
    border-radius: 8px;
    padding: 15px;
    margin: 10px 0;
}
</style>
""", unsafe_allow_html=True)

# 사이드바
render_project_sidebar()
show_api_status_sidebar()

# 프로젝트 선택 확인
if not ensure_project_selected():
    st.stop()

project_path = get_current_project()

# === 메인 콘텐츠 ===
st.title("🔍 2단계: 영상 리서치")
st.caption("YouTube API로 키워드 기반 영상 검색 및 분석 (고도화 버전)")

# API 키 확인
if not require_api_key("YOUTUBE_API_KEY", "YouTube Data API"):
    st.stop()

# === 사이드바: API 할당량 표시 ===
with st.sidebar:
    st.divider()
    st.subheader("📊 API 할당량")

    cache = get_cache()
    quota_stats = cache.get_quota_stats()

    # 프로그레스 바
    usage_percent = quota_stats["usage_percent"] / 100
    st.progress(min(usage_percent, 1.0))

    # 수치 표시
    col1, col2 = st.columns(2)
    with col1:
        st.metric("사용량", f"{quota_stats['used_today']:,}")
    with col2:
        st.metric("남은량", f"{quota_stats['remaining']:,}")

    if quota_stats["remaining"] < 1000:
        st.warning("⚠️ 할당량이 부족합니다!")

    # 캐시 통계
    cache_stats = cache.get_cache_stats()
    with st.expander("캐시 통계"):
        for cache_type, count in cache_stats.items():
            st.caption(f"{cache_type}: {count}개")

        if st.button("캐시 초기화", key="clear_cache"):
            cache.clear_all()
            st.success("캐시가 초기화되었습니다.")
            st.rerun()

    # 🔴 v3.12: API 테스트 기능
    with st.expander("🧪 API 테스트"):
        if st.button("YouTube API 테스트", key="test_api"):
            try:
                from googleapiclient.discovery import build
                youtube = build("youtube", "v3", developerKey=YOUTUBE_API_KEY)

                # 간단한 검색 테스트
                test_response = youtube.search().list(
                    part="snippet",
                    q="test",
                    type="video",
                    maxResults=1
                ).execute()

                if test_response.get("items"):
                    st.success("✅ API 정상 작동!")
                    st.caption(f"테스트 결과: {test_response['items'][0]['snippet']['title'][:30]}...")
                else:
                    st.warning("⚠️ API 응답은 있으나 결과 없음")
            except Exception as e:
                st.error(f"❌ API 오류: {e}")

# v2.0: 보관함 초기화
bookmark_storage = BookmarkStorage()

# === 탭 구성 ===
tab_search, tab_results, tab_selected, tab_bookmarks = st.tabs([
    "🔎 검색",
    "📊 검색 결과",
    "✅ 선택된 영상",
    "📁 보관함"
])

# ============================================================
# 검색 탭
# ============================================================
with tab_search:
    st.subheader("🔎 검색 설정")

    # === 기본 검색 ===
    col1, col2 = st.columns([3, 1])

    with col1:
        search_query = st.text_input(
            "검색 키워드",
            placeholder="검색어를 입력하세요... (예: 1인 창업 아이디어)",
            key="search_query"
        )

    with col2:
        region = st.selectbox(
            "🌍 지역",
            options=["KR", "US", "JP", "GB", "DE", "FR"],
            format_func=lambda x: {
                "KR": "🇰🇷 한국",
                "US": "🇺🇸 미국",
                "JP": "🇯🇵 일본",
                "GB": "🇬🇧 영국",
                "DE": "🇩🇪 독일",
                "FR": "🇫🇷 프랑스"
            }.get(x, x),
            key="region"
        )
        # v3.13: 한국어 필터링 옵션
        if region == "KR":
            korean_only = st.checkbox(
                "🇰🇷 한국어 콘텐츠만",
                value=True,
                key="korean_only",
                help="제목/채널명/설명에 한국어가 포함된 영상만 표시"
            )
        else:
            korean_only = False

    # v3.14: 검색 범위 필터링 (채널명 포함 문제 해결)
    st.markdown('<div class="section-header">🎯 검색 범위</div>', unsafe_allow_html=True)

    search_scope = st.radio(
        "검색 범위 선택",
        options=list(SEARCH_SCOPE_OPTIONS.keys()),
        format_func=lambda x: x,
        horizontal=True,
        key="search_scope",
        index=0,  # "제목만 검색" 기본값
        help=get_search_scope_description(SEARCH_SCOPE_OPTIONS.get(list(SEARCH_SCOPE_OPTIONS.keys())[0], "title_only"))
    )

    # 검색 범위 설명 표시
    selected_scope = SEARCH_SCOPE_OPTIONS.get(search_scope, "title_only")
    st.caption(f"ℹ️ {get_search_scope_description(selected_scope)}")

    st.markdown("---")

    # === 영상 유형 선택 (롱폼/쇼츠) ===
    st.markdown('<div class="section-header">📹 영상 유형</div>', unsafe_allow_html=True)

    video_type = st.radio(
        "영상 유형 선택",
        options=["all", "long_form", "shorts"],
        format_func=lambda x: {
            "all": "📺 전체",
            "long_form": "🎬 롱폼 (1분 이상)",
            "shorts": "📱 쇼츠 (1분 이하)"
        }.get(x),
        horizontal=True,
        key="video_type"
    )

    st.markdown("---")

    # === 영상 길이 설정 ===
    st.markdown('<div class="section-header">⏱️ 영상 길이</div>', unsafe_allow_html=True)

    duration_mode = st.radio(
        "길이 설정 방식",
        options=["preset", "custom"],
        format_func=lambda x: {
            "preset": "📋 프리셋 선택",
            "custom": "✏️ 수동 입력"
        }.get(x),
        horizontal=True,
        key="duration_mode"
    )

    if duration_mode == "preset":
        duration_preset = st.selectbox(
            "영상 길이 프리셋",
            options=["any", "short", "medium", "long"],
            format_func=lambda x: {
                "any": "전체",
                "short": "짧은 영상 (4분 미만)",
                "medium": "중간 영상 (4~20분)",
                "long": "긴 영상 (20분 이상)"
            }.get(x),
            key="duration_preset"
        )

        # 프리셋을 초로 변환
        duration_map = {
            "any": (None, None),
            "short": (None, 240),
            "medium": (240, 1200),
            "long": (1200, None)
        }
        min_duration, max_duration = duration_map.get(duration_preset, (None, None))

    else:  # custom
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**최소 길이**")
            col_min1, col_min2 = st.columns(2)
            with col_min1:
                min_min = st.number_input("분", min_value=0, max_value=999, value=0, key="min_min")
            with col_min2:
                min_sec = st.number_input("초", min_value=0, max_value=59, value=0, key="min_sec")
            min_duration = min_min * 60 + min_sec if (min_min > 0 or min_sec > 0) else None

        with col2:
            st.markdown("**최대 길이**")
            col_max1, col_max2 = st.columns(2)
            with col_max1:
                max_min = st.number_input("분", min_value=0, max_value=999, value=0, key="max_min")
            with col_max2:
                max_sec = st.number_input("초", min_value=0, max_value=59, value=0, key="max_sec")
            max_duration = max_min * 60 + max_sec if (max_min > 0 or max_sec > 0) else None

        if min_duration and max_duration and min_duration > max_duration:
            st.warning("⚠️ 최소 길이가 최대 길이보다 큽니다.")

    st.markdown("---")

    # === 조회수/구독자 필터 ===
    col1, col2 = st.columns(2)

    with col1:
        st.markdown('<div class="section-header">👀 조회수 필터</div>', unsafe_allow_html=True)
        col_v1, col_v2 = st.columns(2)
        with col_v1:
            min_views = st.number_input(
                "최소 조회수",
                min_value=0,
                value=0,
                step=1000,
                format="%d",
                key="min_views"
            )
            min_views = min_views if min_views > 0 else None
        with col_v2:
            max_views = st.number_input(
                "최대 조회수",
                min_value=0,
                value=0,
                step=10000,
                format="%d",
                help="0 = 무제한",
                key="max_views"
            )
            max_views = max_views if max_views > 0 else None

    with col2:
        st.markdown('<div class="section-header">👥 구독자 필터</div>', unsafe_allow_html=True)
        col_s1, col_s2 = st.columns(2)
        with col_s1:
            min_subs = st.number_input(
                "최소 구독자",
                min_value=0,
                value=0,
                step=1000,
                format="%d",
                key="min_subs"
            )
            min_subs = min_subs if min_subs > 0 else None
        with col_s2:
            max_subs = st.number_input(
                "최대 구독자",
                min_value=0,
                value=0,
                step=10000,
                format="%d",
                help="0 = 무제한",
                key="max_subs"
            )
            max_subs = max_subs if max_subs > 0 else None

    st.markdown("---")

    # === 기간 필터 ===
    st.markdown('<div class="section-header">📅 업로드 기간</div>', unsafe_allow_html=True)

    col1, col2 = st.columns(2)

    with col1:
        period_preset = st.selectbox(
            "기간 프리셋",
            options=["all", "hour", "today", "week", "month", "3months", "year", "custom"],
            format_func=lambda x: {
                "all": "전체 기간",
                "hour": "1시간 이내",
                "today": "오늘",
                "week": "이번 주 (7일)",
                "month": "이번 달 (30일)",
                "3months": "3개월",
                "year": "올해 (365일)",
                "custom": "직접 입력"
            }.get(x),
            index=4,  # month 기본
            key="period_preset"
        )

    # 기간 계산
    now = datetime.utcnow()
    published_after = None
    published_before = None

    if period_preset == "hour":
        published_after = (now - timedelta(hours=1)).isoformat() + "Z"
    elif period_preset == "today":
        published_after = now.replace(hour=0, minute=0, second=0).isoformat() + "Z"
    elif period_preset == "week":
        published_after = (now - timedelta(days=7)).isoformat() + "Z"
    elif period_preset == "month":
        published_after = (now - timedelta(days=30)).isoformat() + "Z"
    elif period_preset == "3months":
        published_after = (now - timedelta(days=90)).isoformat() + "Z"
    elif period_preset == "year":
        published_after = (now - timedelta(days=365)).isoformat() + "Z"
    elif period_preset == "custom":
        with col2:
            date_range = st.date_input(
                "기간 선택",
                value=(now.date() - timedelta(days=30), now.date()),
                key="date_range"
            )
            if len(date_range) == 2:
                published_after = datetime.combine(date_range[0], datetime.min.time()).isoformat() + "Z"
                published_before = datetime.combine(date_range[1], datetime.max.time()).isoformat() + "Z"

    st.markdown("---")

    # === 정렬 및 결과 수 ===
    st.markdown('<div class="section-header">⚙️ 정렬 및 결과</div>', unsafe_allow_html=True)

    col1, col2 = st.columns(2)

    with col1:
        sort_by = st.selectbox(
            "정렬 기준",
            options=["viewCount", "date", "relevance", "rating"],
            format_func=lambda x: {
                "relevance": "관련성",
                "viewCount": "조회수",
                "date": "업로드일",
                "rating": "평점"
            }.get(x),
            key="sort_by"
        )

    with col2:
        max_results = st.slider(
            "최대 결과 수",
            min_value=10,
            max_value=50,
            value=30,
            step=5,
            key="max_results"
        )

    st.markdown("---")

    # === 검색 실행 ===
    if st.button("🔍 검색 시작", type="primary", use_container_width=True, disabled=not search_query):
        try:
            from core.youtube.enhanced_search import EnhancedYouTubeSearcher
            from core.youtube.data_models import SearchFilters

            # 필터 구성
            filters = SearchFilters(
                query=search_query,
                video_type=video_type,
                min_duration=min_duration,
                max_duration=max_duration,
                min_views=min_views,
                max_views=max_views,
                min_subscribers=min_subs,
                max_subscribers=max_subs,
                published_after=published_after,
                published_before=published_before,
                sort_by=sort_by,
                region_code=region,
                korean_only=korean_only,  # v3.13: 한국어 필터
                max_results=max_results
            )

            # 검색 실행
            searcher = EnhancedYouTubeSearcher()

            with st.spinner("검색 중... (캐시 확인 후 API 호출)"):
                progress_bar = st.progress(0)
                status_text = st.empty()

                def update_progress(current, total):
                    progress_bar.progress(current / total)
                    status_text.text(f"영상 분석 중... {current}/{total}")

                videos, api_calls = searcher.search_videos_enhanced(filters, update_progress)

            if videos:
                # v3.14: 검색 범위 필터링 적용
                original_count = len(videos)
                video_dicts_for_filter = [v.to_dict() for v in videos]
                filtered_dicts = filter_videos_by_search_scope(
                    video_dicts_for_filter,
                    search_query,
                    selected_scope
                )

                # 필터링된 video_id 목록
                filtered_ids = {v.get('video_id') for v in filtered_dicts}
                videos = [v for v in videos if v.video_id in filtered_ids]

                # 세션에 저장 (VideoInfo 객체 리스트)
                st.session_state["search_results"] = videos
                st.session_state["last_search_query"] = search_query
                st.session_state["last_search_scope"] = selected_scope

                # 파일로 저장 (딕셔너리로 변환)
                video_dicts = [v.to_dict() for v in videos]
                save_video_research(project_path, video_dicts)

                # 필터링 결과 표시
                if original_count != len(videos):
                    st.success(f"✅ {len(videos)}개 영상 검색 완료! (총 {original_count}개 중 {original_count - len(videos)}개 제외, API 호출: {api_calls}회)")
                    st.caption(f"🎯 검색 범위: {search_scope} - 채널명만 일치하는 {original_count - len(videos)}개 영상이 제외되었습니다.")
                else:
                    st.success(f"✅ {len(videos)}개 영상 검색 완료! (API 호출: {api_calls}회)")
                st.info("📊 '검색 결과' 탭에서 결과를 확인하세요.")

                # 할당량 표시
                quota_info = searcher.get_quota_info()
                st.caption(f"현재 할당량: {quota_info['used_today']:,} / {quota_info['daily_limit']:,}")

            else:
                st.warning("검색 결과가 없습니다. 다른 키워드나 필터를 시도해보세요.")

                # 🔴 v3.12: 진단 정보 표시
                with st.expander("🔍 문제 진단"):
                    st.markdown("""
                    **검색 결과가 없는 이유:**

                    1. **필터가 너무 엄격함**: 조회수/구독자 필터를 낮추거나 0으로 설정
                    2. **캐시된 빈 결과**: 아래 '캐시 초기화' 버튼 클릭
                    3. **API 할당량 초과**: 사이드바에서 남은 할당량 확인
                    4. **키워드 문제**: 다른 키워드로 시도

                    **현재 설정:**
                    """)
                    st.write(f"- 키워드: `{search_query}`")
                    st.write(f"- 영상 유형: `{video_type}`")
                    st.write(f"- 지역: `{region}`")
                    st.write(f"- 한국어 필터: `{korean_only}`")
                    st.write(f"- 검색 범위: `{search_scope}` ({selected_scope})")
                    st.write(f"- 기간: `{period_preset}`")

                    if st.button("🗑️ 이 검색의 캐시 초기화", key="clear_search_cache"):
                        try:
                            cache.clear_all()
                            st.success("캐시가 초기화되었습니다. 다시 검색해보세요.")
                        except Exception as ce:
                            st.error(f"캐시 초기화 실패: {ce}")

        except Exception as e:
            st.error(f"검색 오류: {str(e)}")
            import traceback

            # 🔴 v3.12: 상세 오류 정보
            with st.expander("🔧 오류 상세 정보"):
                st.code(traceback.format_exc())

                # API 키 확인
                if "API" in str(e).upper() or "KEY" in str(e).upper():
                    st.warning("⚠️ API 키 관련 오류일 수 있습니다. API 키 설정을 확인하세요.")
                elif "QUOTA" in str(e).upper():
                    st.warning("⚠️ API 할당량이 초과되었을 수 있습니다.")


# ============================================================
# 검색 결과 탭
# ============================================================
with tab_results:
    st.subheader("📊 검색 결과")

    # 세션에서 로드
    videos = st.session_state.get("search_results", [])

    if not videos:
        # 파일에서 로드 시도
        saved_data = load_video_research(project_path)
        if saved_data:
            # 딕셔너리를 VideoInfo로 변환
            from core.youtube.data_models import VideoInfo
            videos = []
            for v in saved_data:
                try:
                    video = VideoInfo(
                        video_id=v.get("video_id", ""),
                        title=v.get("title", ""),
                        video_url=v.get("video_url", ""),
                        thumbnail_url=v.get("thumbnail_url", ""),
                        channel_id=v.get("channel_id", ""),
                        channel_name=v.get("channel_name", v.get("channel_title", "")),
                        channel_url=v.get("channel_url", ""),
                        subscriber_count=v.get("subscriber_count", 0),
                        channel_created_at=v.get("channel_created_at", ""),
                        channel_total_videos=v.get("channel_total_videos", 0),
                        view_count=v.get("view_count", 0),
                        like_count=v.get("like_count", 0),
                        comment_count=v.get("comment_count", 0),
                        published_at=v.get("published_at", ""),
                        duration_seconds=v.get("duration_seconds", 0),
                        duration_formatted=v.get("duration_formatted", ""),
                        video_type=v.get("video_type", "long_form"),
                        description=v.get("description", ""),
                        tags=v.get("tags", [])
                    )
                    videos.append(video)
                except:
                    pass
            st.session_state["search_results"] = videos

    if not videos:
        st.info("검색 결과가 없습니다. '검색' 탭에서 검색을 실행하세요.")
        st.stop()

    # 결과 요약
    st.success(f"총 {len(videos)}개 영상")

    # === 결과 필터링/정렬 ===
    st.markdown('<div class="section-header">🔧 결과 필터링/정렬</div>', unsafe_allow_html=True)

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        result_type_filter = st.selectbox(
            "영상 유형",
            options=["all", "long_form", "shorts"],
            format_func=lambda x: {
                "all": "전체",
                "long_form": "🎬 롱폼",
                "shorts": "📱 쇼츠"
            }.get(x),
            key="result_type_filter"
        )

    with col2:
        result_sort = st.selectbox(
            "정렬",
            options=[
                "viral_score_desc", "view_count_desc", "view_count_asc",
                "like_count_desc", "subscriber_desc",
                "views_per_sub_desc", "engagement_desc",
                "date_desc", "date_asc"
            ],
            format_func=lambda x: {
                "viral_score_desc": "🔥 급등점수 높은순",
                "view_count_desc": "👀 조회수 높은순",
                "view_count_asc": "👀 조회수 낮은순",
                "like_count_desc": "👍 좋아요 높은순",
                "subscriber_desc": "👥 구독자 높은순",
                "views_per_sub_desc": "📈 구독자 대비 조회수",
                "engagement_desc": "💬 참여율 높은순",
                "date_desc": "📅 최신순",
                "date_asc": "📅 오래된순"
            }.get(x),
            key="result_sort"
        )

    with col3:
        min_view_filter = st.number_input(
            "최소 조회수",
            min_value=0,
            value=0,
            step=1000,
            key="min_view_filter"
        )

    with col4:
        min_sub_filter = st.number_input(
            "최소 구독자",
            min_value=0,
            value=0,
            step=1000,
            key="min_sub_filter"
        )

    # 필터링 적용
    filtered_videos = videos.copy()

    # 유형 필터
    if result_type_filter != "all":
        filtered_videos = [v for v in filtered_videos if v.video_type == result_type_filter]

    # 조회수 필터
    if min_view_filter > 0:
        filtered_videos = [v for v in filtered_videos if v.view_count >= min_view_filter]

    # 구독자 필터
    if min_sub_filter > 0:
        filtered_videos = [v for v in filtered_videos if v.subscriber_count >= min_sub_filter]

    # 정렬
    sort_key_map = {
        "viral_score_desc": (lambda v: v.viral_score, True),
        "view_count_desc": (lambda v: v.view_count, True),
        "view_count_asc": (lambda v: v.view_count, False),
        "like_count_desc": (lambda v: v.like_count, True),
        "subscriber_desc": (lambda v: v.subscriber_count, True),
        "views_per_sub_desc": (lambda v: v.views_per_subscriber, True),
        "engagement_desc": (lambda v: v.engagement_rate, True),
        "date_desc": (lambda v: v.published_at, True),
        "date_asc": (lambda v: v.published_at, False),
    }

    sort_func, reverse = sort_key_map.get(result_sort, (lambda v: v.viral_score, True))
    filtered_videos.sort(key=sort_func, reverse=reverse)

    st.caption(f"필터링 후: {len(filtered_videos)}개")

    st.markdown("---")

    # === 엑셀 다운로드 ===
    col1, col2, col3 = st.columns([1, 1, 2])

    with col1:
        if st.button("📥 엑셀 다운로드", type="secondary"):
            from utils.excel_export import export_videos_to_excel

            excel_data = [v.to_excel_row() for v in filtered_videos]
            excel_file = export_videos_to_excel(excel_data)

            st.download_button(
                "💾 다운로드",
                data=excel_file,
                file_name=f"영상_리서치_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    with col2:
        if st.button("📊 요약 통계"):
            # 통계 표시
            total_views = sum(v.view_count for v in filtered_videos)
            avg_views = total_views / len(filtered_videos) if filtered_videos else 0
            avg_subs = sum(v.subscriber_count for v in filtered_videos) / len(filtered_videos) if filtered_videos else 0
            shorts_count = len([v for v in filtered_videos if v.video_type == "shorts"])
            longform_count = len([v for v in filtered_videos if v.video_type == "long_form"])

            st.info(f"""
            **📊 통계 요약**
            - 총 영상: {len(filtered_videos)}개 (롱폼: {longform_count}, 쇼츠: {shorts_count})
            - 총 조회수: {total_views:,}
            - 평균 조회수: {avg_views:,.0f}
            - 평균 구독자: {avg_subs:,.0f}
            """)

    st.markdown("---")

    # === 결과 테이블 ===
    st.markdown("#### 📋 영상 목록")

    # DataFrame으로 표시
    df_data = []
    for v in filtered_videos:
        df_data.append({
            "선택": False,
            "유형": "🎬" if v.video_type == "long_form" else "📱",
            "제목": v.title[:50] + ("..." if len(v.title) > 50 else ""),
            "길이": v.duration_formatted,
            "조회수": f"{v.view_count:,}",
            "좋아요": f"{v.like_count:,}",
            "채널": v.channel_name[:20] + ("..." if len(v.channel_name) > 20 else ""),
            "구독자": f"{v.subscriber_count:,}",
            "구독자 대비": f"{v.views_per_subscriber:.1f}x",
            "일평균": f"{v.views_per_day:,.0f}",  # v3.14: 일일 평균 조회수 추가
            "참여율": f"{v.engagement_rate:.1f}%",
            "급등점수": f"{v.viral_score:.1f}",
            "업로드일": v.published_at[:10] if v.published_at else "",
        })

    df = pd.DataFrame(df_data)

    # 편집 가능한 테이블
    edited_df = st.data_editor(
        df,
        column_config={
            "선택": st.column_config.CheckboxColumn("선택", default=False),
            "조회수": st.column_config.TextColumn("조회수"),
            "좋아요": st.column_config.TextColumn("좋아요"),
            "구독자": st.column_config.TextColumn("구독자"),
            "일평균": st.column_config.TextColumn("일평균", help="일일 평균 조회수"),
        },
        hide_index=True,
        use_container_width=True,
        key="result_table"
    )

    # 선택된 영상 처리
    selected_indices = edited_df[edited_df["선택"] == True].index.tolist()
    selected_videos = [filtered_videos[i] for i in selected_indices]

    st.divider()

    col1, col2 = st.columns([1, 3])
    with col1:
        st.metric("선택된 영상", f"{len(selected_videos)}개")

    with col2:
        if st.button("✅ 선택한 영상 저장", type="primary", disabled=len(selected_videos) == 0):
            # 딕셔너리로 변환하여 저장
            selected_dicts = [v.to_dict() for v in selected_videos]
            save_selected_videos(project_path, selected_dicts)
            st.session_state["selected_videos"] = selected_videos
            update_project_step(2)
            st.success(f"✅ {len(selected_videos)}개 영상이 저장되었습니다!")

    # v2.0: 추가 액션 버튼
    action_col1, action_col2, action_col3, action_col4 = st.columns(4)

    with action_col1:
        if st.button("📁 보관함에 저장", disabled=len(selected_videos) == 0, use_container_width=True):
            video_dicts = [v.to_dict() for v in selected_videos]
            count = bookmark_storage.save_videos(video_dicts)
            st.success(f"✅ {count}개 영상이 보관함에 저장되었습니다!")

    with action_col2:
        if st.button("📺 채널 보관함 저장", disabled=len(selected_videos) == 0, use_container_width=True):
            video_dicts = [v.to_dict() for v in selected_videos]
            count = bookmark_storage.save_channels_from_videos(video_dicts)
            st.success(f"✅ {count}개 채널이 보관함에 저장되었습니다!")

    with action_col3:
        if selected_videos:
            video_dicts = [v.to_dict() for v in selected_videos]
            excel_data = export_with_metrics(video_dicts, st.session_state.get("last_search_query", "검색결과"))
            st.download_button(
                "📊 Excel 다운로드",
                data=excel_data,
                file_name=get_excel_filename(st.session_state.get("last_search_query", "검색결과")),
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        else:
            st.button("📊 Excel 다운로드", disabled=True, use_container_width=True)

    with action_col4:
        # v3.14: 세션 상태를 사용하여 다운로드 버튼 안정화
        if "thumbnail_zip_data" not in st.session_state:
            st.session_state["thumbnail_zip_data"] = None
            st.session_state["thumbnail_zip_filename"] = None

        if selected_videos:
            if st.button("🖼️ 썸네일 생성", use_container_width=True, key="create_thumbnail_zip"):
                downloader = ThumbnailDownloader()
                video_dicts = [v.to_dict() for v in selected_videos]
                with st.spinner("썸네일 다운로드 중..."):
                    st.session_state["thumbnail_zip_data"] = downloader.download_thumbnails_zip(video_dicts)
                    st.session_state["thumbnail_zip_filename"] = ThumbnailDownloader.get_zip_filename(
                        st.session_state.get("last_search_query", "검색결과")
                    )
                st.success(f"✅ {len(selected_videos)}개 썸네일 준비 완료!")
                st.rerun()

            # 다운로드 버튼 표시
            if st.session_state["thumbnail_zip_data"]:
                st.download_button(
                    "💾 ZIP 저장",
                    data=st.session_state["thumbnail_zip_data"],
                    file_name=st.session_state["thumbnail_zip_filename"],
                    mime="application/zip",
                    use_container_width=True
                )
        else:
            st.button("🖼️ 썸네일 ZIP", disabled=True, use_container_width=True)

    st.markdown("---")

    # === 상세 카드 뷰 ===
    st.markdown("#### 🎴 상세 보기")

    # 페이지네이션
    items_per_page = 5
    total_pages = max(1, (len(filtered_videos) + items_per_page - 1) // items_per_page)

    current_page = st.number_input(
        "페이지",
        min_value=1,
        max_value=total_pages,
        value=1,
        key="result_page"
    )

    start_idx = (current_page - 1) * items_per_page
    end_idx = start_idx + items_per_page
    page_videos = filtered_videos[start_idx:end_idx]

    for video in page_videos:
        type_icon = '🎬' if video.video_type == 'long_form' else '📱'
        with st.expander(f"{type_icon} {video.title[:60]}...", expanded=False):
            col1, col2 = st.columns([1, 2])

            with col1:
                if video.thumbnail_url:
                    st.image(video.thumbnail_url, use_container_width=True)
                st.markdown(f"[▶️ 영상 보기]({video.video_url})")

            with col2:
                # 영상 정보
                st.markdown("**📹 영상 정보**")
                st.markdown(f"""
                - **제목:** {video.title}
                - **유형:** {"롱폼" if video.video_type == "long_form" else "쇼츠"}
                - **길이:** {video.duration_formatted}
                - **업로드일:** {video.published_at[:10] if video.published_at else "N/A"}
                """)

                # 통계
                st.markdown("**📊 통계**")
                metric_col1, metric_col2, metric_col3 = st.columns(3)
                with metric_col1:
                    st.metric("조회수", f"{video.view_count:,}")
                with metric_col2:
                    st.metric("좋아요", f"{video.like_count:,}")
                with metric_col3:
                    st.metric("댓글", f"{video.comment_count:,}")

                # 채널 정보
                st.markdown("**📺 채널 정보**")
                st.markdown(f"""
                - **채널명:** {video.channel_name}
                - **구독자:** {video.subscriber_count:,}명
                - **채널 개설일:** {video.channel_created_at[:10] if video.channel_created_at else "N/A"}
                - **총 영상 수:** {video.channel_total_videos:,}개
                """)
                st.markdown(f"[📺 채널 방문]({video.channel_url})")

                # 효율성 지표
                st.markdown("**📈 효율성 지표**")
                eff_col1, eff_col2, eff_col3, eff_col4 = st.columns(4)
                with eff_col1:
                    st.metric("구독자 대비", f"{video.views_per_subscriber:.1f}x")
                with eff_col2:
                    st.metric("참여율", f"{video.engagement_rate:.1f}%")
                with eff_col3:
                    st.metric("일평균 조회", f"{video.views_per_day:,.0f}")
                with eff_col4:
                    st.metric("급등점수", f"{video.viral_score:.1f}")


# ============================================================
# 선택된 영상 탭
# ============================================================
with tab_selected:
    st.subheader("✅ 선택된 영상")

    # 세션 또는 파일에서 로드
    selected = st.session_state.get("selected_videos") or []

    if not selected:
        saved_selected = load_selected_videos(project_path)
        if saved_selected:
            from core.youtube.data_models import VideoInfo
            selected = []
            for v in saved_selected:
                try:
                    video = VideoInfo(
                        video_id=v.get("video_id", ""),
                        title=v.get("title", ""),
                        video_url=v.get("video_url", ""),
                        thumbnail_url=v.get("thumbnail_url", ""),
                        channel_id=v.get("channel_id", ""),
                        channel_name=v.get("channel_name", v.get("channel_title", "")),
                        channel_url=v.get("channel_url", ""),
                        subscriber_count=v.get("subscriber_count", 0),
                        channel_created_at=v.get("channel_created_at", ""),
                        channel_total_videos=v.get("channel_total_videos", 0),
                        view_count=v.get("view_count", 0),
                        like_count=v.get("like_count", 0),
                        comment_count=v.get("comment_count", 0),
                        published_at=v.get("published_at", ""),
                        duration_seconds=v.get("duration_seconds", 0),
                        duration_formatted=v.get("duration_formatted", ""),
                        video_type=v.get("video_type", "long_form"),
                        description=v.get("description", ""),
                        tags=v.get("tags", [])
                    )
                    selected.append(video)
                except:
                    pass
            st.session_state["selected_videos"] = selected

    if not selected:
        st.info("선택된 영상이 없습니다. '검색 결과' 탭에서 영상을 선택하세요.")
        st.stop()

    st.success(f"총 {len(selected)}개 선택됨")

    # 엑셀 다운로드
    if st.button("📥 선택된 영상 엑셀 다운로드"):
        from utils.excel_export import export_videos_to_excel

        excel_data = [v.to_excel_row() for v in selected]
        excel_file = export_videos_to_excel(excel_data, "선택된_영상")

        st.download_button(
            "💾 다운로드",
            data=excel_file,
            file_name=f"선택된_영상_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    st.markdown("---")

    # 목록 표시
    for i, video in enumerate(selected):
        type_icon = '🎬' if video.video_type == 'long_form' else '📱'
        with st.expander(f"{i+1}. {type_icon} {video.title[:50]}...", expanded=(i == 0)):
            col1, col2 = st.columns([1, 2])

            with col1:
                if video.thumbnail_url:
                    st.image(video.thumbnail_url, use_container_width=True)

            with col2:
                st.markdown(f"**{video.title}**")
                st.caption(f"채널: {video.channel_name}")

                metrics_col1, metrics_col2, metrics_col3, metrics_col4 = st.columns(4)
                with metrics_col1:
                    st.metric("조회수", f"{video.view_count:,}")
                with metrics_col2:
                    st.metric("구독자", f"{video.subscriber_count:,}")
                with metrics_col3:
                    st.metric("급등점수", f"{video.viral_score:.1f}")
                with metrics_col4:
                    st.metric("길이", video.duration_formatted)

                st.markdown(f"[▶️ YouTube에서 보기]({video.video_url})")

    st.divider()

    # 다음 단계 안내
    st.success("✅ 2단계 완료! 다음 단계로 진행하세요.")
    st.page_link("pages/3_📝_스크립트_생성.py", label="📝 3단계: 스크립트 생성으로 이동", icon="➡️")

# ============================================================
# 보관함 탭 (v2.0)
# ============================================================
with tab_bookmarks:
    st.subheader("📁 보관함")
    st.caption("자주 참고하는 영상과 채널을 저장하고 관리합니다.")

    # 보관함 통계
    bookmark_stats = bookmark_storage.get_stats()

    col1, col2 = st.columns(2)
    with col1:
        st.metric("📹 저장된 영상", f"{bookmark_stats['videos_count']}개")
    with col2:
        st.metric("📺 저장된 채널", f"{bookmark_stats['channels_count']}개")

    st.divider()

    # 영상 보관함
    st.markdown("### 🎬 저장된 영상")

    saved_videos = bookmark_storage.get_saved_videos()

    if saved_videos:
        # 액션 버튼
        action_col1, action_col2, action_col3 = st.columns(3)

        with action_col1:
            # Excel 내보내기
            excel_data = export_with_metrics(saved_videos, "보관함")
            st.download_button(
                "📊 Excel 다운로드",
                data=excel_data,
                file_name=get_excel_filename("보관함"),
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

        with action_col2:
            # v3.14: 썸네일 다운로드 (세션 상태 사용)
            if "bookmark_thumbnail_zip" not in st.session_state:
                st.session_state["bookmark_thumbnail_zip"] = None

            if st.button("🖼️ 썸네일 생성", use_container_width=True, key="bookmark_thumbnail"):
                downloader = ThumbnailDownloader()
                with st.spinner("썸네일 다운로드 중..."):
                    st.session_state["bookmark_thumbnail_zip"] = downloader.download_thumbnails_zip(saved_videos)
                st.success(f"✅ {len(saved_videos)}개 썸네일 준비 완료!")
                st.rerun()

            if st.session_state.get("bookmark_thumbnail_zip"):
                st.download_button(
                    "💾 ZIP 저장",
                    data=st.session_state["bookmark_thumbnail_zip"],
                    file_name=ThumbnailDownloader.get_zip_filename("보관함"),
                    mime="application/zip",
                    use_container_width=True
                )

        with action_col3:
            if st.button("🗑️ 전체 삭제", use_container_width=True, type="secondary"):
                bookmark_storage.clear_videos()
                st.success("영상 보관함이 비워졌습니다.")
                st.rerun()

        # 영상 목록 테이블
        df_bookmarks = pd.DataFrame([
            {
                "제목": v.get('title', '')[:40] + "...",
                "채널": v.get('channel_title', '')[:20],
                "조회수": f"{v.get('view_count', 0):,}",
                "구독자": f"{v.get('subscriber_count', 0):,}",
                "저장일": v.get('saved_at', '')[:10],
            }
            for v in saved_videos
        ])

        st.dataframe(
            df_bookmarks,
            column_config={
                "제목": st.column_config.TextColumn("제목", width="large"),
                "채널": st.column_config.TextColumn("채널"),
                "조회수": st.column_config.TextColumn("조회수"),
                "구독자": st.column_config.TextColumn("구독자"),
                "저장일": st.column_config.TextColumn("저장일"),
            },
            hide_index=True,
            use_container_width=True
        )

        # 개별 영상 삭제
        st.markdown("##### 개별 삭제")
        video_to_delete = st.selectbox(
            "삭제할 영상 선택",
            options=[v.get('video_id') for v in saved_videos],
            format_func=lambda x: next(
                (v.get('title', '')[:50] for v in saved_videos if v.get('video_id') == x),
                x
            ),
            key="delete_bookmark_video"
        )

        if st.button("🗑️ 선택한 영상 삭제"):
            bookmark_storage.delete_video(video_to_delete)
            st.success("영상이 삭제되었습니다.")
            st.rerun()

    else:
        st.info("저장된 영상이 없습니다. '검색 결과' 탭에서 영상을 보관함에 추가하세요.")

    st.divider()

    # 채널 보관함
    st.markdown("### 📺 저장된 채널")

    saved_channels = bookmark_storage.get_saved_channels()

    if saved_channels:
        df_channels = pd.DataFrame([
            {
                "채널명": c.get('channel_title', ''),
                "구독자": f"{c.get('subscriber_count', 0):,}",
                "저장일": c.get('saved_at', '')[:10],
            }
            for c in saved_channels
        ])

        st.dataframe(
            df_channels,
            column_config={
                "채널명": st.column_config.TextColumn("채널명", width="large"),
                "구독자": st.column_config.TextColumn("구독자"),
                "저장일": st.column_config.TextColumn("저장일"),
            },
            hide_index=True,
            use_container_width=True
        )

        if st.button("🗑️ 채널 보관함 비우기"):
            bookmark_storage.clear_channels()
            st.success("채널 보관함이 비워졌습니다.")
            st.rerun()

    else:
        st.info("저장된 채널이 없습니다.")
