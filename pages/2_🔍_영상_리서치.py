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
from datetime import datetime, timedelta, timezone
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


# Helper function for safe attribute access (dict or object)
def safe_get(obj, key, default=None):
    """dict와 object 모두에서 안전하게 속성/키 접근"""
    if isinstance(obj, dict):
        return obj.get(key, default)
    else:
        return getattr(obj, key, default)


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

# v3.0: 채널 정체성 및 주제 추천 모듈
from utils.channel_identity import get_identity_manager, ChannelIdentity
from utils.topic_recommender import (
    get_topic_recommender,
    recommend_topics,
    VideoData,
    TopicRecommendation,
    RecommendationResult,
    check_api_availability
)

# === 탭 구성 ===
tab_search, tab_results, tab_selected, tab_bookmarks, tab_identity, tab_recommend = st.tabs([
    "🔎 검색",
    "📊 검색 결과",
    "✅ 선택된 영상",
    "📁 보관함",
    "📋 채널 정체성",
    "🎯 AI 주제 추천"
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

    # 기간 계산 (timezone-aware datetime 사용)
    now = datetime.now(timezone.utc)
    published_after = None
    published_before = None

    if period_preset == "hour":
        published_after = (now - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    elif period_preset == "today":
        published_after = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat().replace("+00:00", "Z")
    elif period_preset == "week":
        published_after = (now - timedelta(days=7)).isoformat().replace("+00:00", "Z")
    elif period_preset == "month":
        published_after = (now - timedelta(days=30)).isoformat().replace("+00:00", "Z")
    elif period_preset == "3months":
        published_after = (now - timedelta(days=90)).isoformat().replace("+00:00", "Z")
    elif period_preset == "year":
        published_after = (now - timedelta(days=365)).isoformat().replace("+00:00", "Z")
    elif period_preset == "custom":
        with col2:
            date_range = st.date_input(
                "기간 선택",
                value=(now.date() - timedelta(days=30), now.date()),
                key="date_range"
            )
            if len(date_range) == 2:
                published_after = datetime.combine(date_range[0], datetime.min.time(), tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")
                published_before = datetime.combine(date_range[1], datetime.max.time(), tzinfo=timezone.utc).isoformat().replace("+00:00", "Z")

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

    # ✅ 정렬 (단일 소스 - 한 번만 정렬하고 세션에 저장)
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

    # ✅ 정렬된 결과를 세션에 저장 (상세 보기와 동기화용) - 즉시 저장
    # 중요: 여기서 저장한 데이터를 상세 보기에서 동일하게 사용
    st.session_state["_sorted_filtered_videos"] = filtered_videos  # copy 제거 - 동일 참조 사용
    st.session_state["_current_sort"] = result_sort
    st.session_state["_current_sort_label"] = {
        "viral_score_desc": "🔥 급등점수 높은순",
        "view_count_desc": "👀 조회수 높은순",
        "view_count_asc": "👀 조회수 낮은순",
        "like_count_desc": "👍 좋아요 높은순",
        "subscriber_desc": "👥 구독자 높은순",
        "views_per_sub_desc": "📈 구독자 대비 조회수",
        "engagement_desc": "💬 참여율 높은순",
        "date_desc": "📅 최신순",
        "date_asc": "📅 오래된순"
    }.get(result_sort, result_sort)

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

    # ✅ 현재 정렬 상태 표시
    current_sort_label = st.session_state.get("_current_sort_label", "기본 정렬")
    st.caption(f"📊 정렬: {current_sort_label} (위 드롭다운에서 정렬 기준 변경)")

    # ✅ DataFrame으로 표시 (이미 정렬된 filtered_videos 사용)
    # 정렬은 위에서 한 번만 수행됨 - df 재정렬 불필요
    df_data = []
    for idx, v in enumerate(filtered_videos):
        df_data.append({
            "_video_idx": idx,  # ✅ 정렬된 순서의 인덱스 (동기화용)
            "선택": False,
            "유형": "🎬" if v.video_type == "long_form" else "📱",
            "제목": v.title[:50] + ("..." if len(v.title) > 50 else ""),
            "길이": v.duration_formatted,
            "조회수": f"{v.view_count:,}",
            "좋아요": f"{v.like_count:,}",
            "채널": v.channel_name[:20] + ("..." if len(v.channel_name) > 20 else ""),
            "구독자": f"{v.subscriber_count:,}",
            "구독자 대비": f"{v.views_per_subscriber:.1f}x",
            "일평균": f"{v.views_per_day:,.0f}",
            "참여율": f"{v.engagement_rate:.1f}%",
            "급등점수": f"{v.viral_score:.1f}",
            "업로드일": v.published_at[:10] if v.published_at else "",
        })

    df = pd.DataFrame(df_data)

    # ✅ 표시할 컬럼만 선택 (숨김 컬럼 제외)
    display_columns = [col for col in df.columns if not col.startswith("_")]

    # 편집 가능한 테이블
    edited_df = st.data_editor(
        df[display_columns],
        column_config={
            "선택": st.column_config.CheckboxColumn("선택", default=False),
            "조회수": st.column_config.TextColumn("조회수"),
            "좋아요": st.column_config.TextColumn("좋아요"),
            "구독자": st.column_config.TextColumn("구독자"),
            "일평균": st.column_config.TextColumn("일평균", help="일일 평균 조회수"),
            "구독자 대비": st.column_config.TextColumn("구독자 대비", help="구독자 대비 조회수 배율"),
        },
        hide_index=True,
        use_container_width=True,
        key="result_table"
    )

    # ✅ 선택된 영상 처리 (정렬 후에도 올바르게 매핑)
    # filtered_videos가 이미 df와 동기화되어 있으므로 인덱스로 직접 접근
    selected_rows = edited_df[edited_df["선택"] == True]
    selected_videos = []

    for idx in selected_rows.index:
        # filtered_videos가 df와 동일한 순서이므로 직접 인덱스 사용
        if idx < len(filtered_videos):
            selected_videos.append(filtered_videos[idx])

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

    # ✅ 핵심 수정: filtered_videos를 직접 사용 (이미 위에서 정렬됨)
    # 세션 상태 대신 동일 스코프의 변수 사용으로 동기화 보장
    sorted_videos_for_detail = filtered_videos  # 영상 목록 테이블과 동일한 데이터

    # ✅ 현재 정렬 상태 표시 (동기화 확인용)
    current_sort_label = st.session_state.get("_current_sort_label", "기본 정렬")
    st.info(f"📊 **현재 정렬:** {current_sort_label} | 총 {len(sorted_videos_for_detail)}개 영상")

    # ✅ 표시 모드 선택
    detail_col1, detail_col2 = st.columns([2, 1])

    with detail_col1:
        display_mode = st.radio(
            "표시 모드",
            options=["all", "pagination"],
            format_func=lambda x: {
                "all": f"📋 전체 표시 ({len(sorted_videos_for_detail)}개)",
                "pagination": "📄 페이지 단위"
            }.get(x, x),
            horizontal=True,
            key="detail_display_mode"
        )

    with detail_col2:
        if display_mode == "pagination":
            items_per_page = st.selectbox(
                "페이지당 영상 수",
                options=[5, 10, 20, 50],
                index=1,  # 기본값 10개
                key="items_per_page_select"
            )
        else:
            items_per_page = len(sorted_videos_for_detail)  # 전체 표시

    # ✅ 페이지네이션 (세션에 저장된 정렬 순서 사용)
    if display_mode == "pagination" and items_per_page < len(sorted_videos_for_detail):
        total_pages = max(1, (len(sorted_videos_for_detail) + items_per_page - 1) // items_per_page)

        current_page = st.number_input(
            "페이지",
            min_value=1,
            max_value=total_pages,
            value=1,
            key="result_page"
        )

        start_idx = (current_page - 1) * items_per_page
        end_idx = start_idx + items_per_page
        page_videos = sorted_videos_for_detail[start_idx:end_idx]
        st.caption(f"📍 {start_idx + 1} ~ {min(end_idx, len(sorted_videos_for_detail))} / 총 {len(sorted_videos_for_detail)}개")
    else:
        # 전체 표시
        page_videos = sorted_videos_for_detail
        if len(sorted_videos_for_detail) > 0:
            st.caption(f"📍 총 {len(sorted_videos_for_detail)}개 영상 표시")

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

# ============================================================
# 채널 정체성 탭 (v3.0)
# ============================================================
with tab_identity:
    st.subheader("📋 채널 정체성 설정")
    st.caption("채널의 정체성을 정의하면 AI가 더 적합한 주제를 추천합니다")

    # 현재 프로젝트
    project_name = project_path.name if project_path else "기본 프로젝트"

    # 정체성 로드
    identity_manager = get_identity_manager()
    identity = identity_manager.load(project_name)

    with st.expander("🎯 채널 정체성 편집", expanded=True):

        col1, col2 = st.columns(2)

        with col1:
            # 채널명
            identity_channel_name = st.text_input(
                "채널명",
                value=identity.channel_name or project_name,
                key="identity_channel_name"
            )

            # 주요 주제
            identity_main_topics_text = st.text_area(
                "주요 주제 (줄바꿈으로 구분)",
                value="\n".join(identity.main_topics) if identity.main_topics else "",
                height=100,
                placeholder="IT/테크\n재테크/투자\n건강/의료",
                key="identity_main_topics"
            )

            # 타겟 시청자
            identity_target_audience = st.text_input(
                "타겟 시청자",
                value=identity.target_audience,
                placeholder="50-70대 시니어, IT에 관심있는 중장년층",
                key="identity_target"
            )

        with col2:
            # 콘텐츠 스타일
            identity_content_style = st.text_area(
                "콘텐츠 스타일",
                value=identity.content_style,
                height=68,
                placeholder="쉽고 친근한 설명, 실용적인 정보 제공, 자막 필수",
                key="identity_style"
            )

            # 톤앤매너
            identity_tone_voice = st.text_input(
                "톤앤매너",
                value=identity.tone_voice,
                placeholder="친근하고 따뜻한 말투, 존댓말 사용",
                key="identity_tone"
            )

            # 참고 채널
            identity_reference_channels_text = st.text_area(
                "참고 채널 (줄바꿈으로 구분)",
                value="\n".join(identity.reference_channels) if identity.reference_channels else "",
                height=68,
                placeholder="신사임당\n슈카월드\n세상의모든지식",
                key="identity_reference"
            )

        # 제외 주제
        identity_exclude_topics_text = st.text_area(
            "제외 주제 (줄바꿈으로 구분)",
            value="\n".join(identity.exclude_topics) if identity.exclude_topics else "",
            height=68,
            placeholder="정치\n종교\n자극적인 낚시성 콘텐츠",
            key="identity_exclude"
        )

        # 핵심 키워드
        identity_keywords_text = st.text_input(
            "핵심 키워드 (쉼표로 구분)",
            value=", ".join(identity.keywords) if identity.keywords else "",
            placeholder="시니어, 실버, 노후, 연금, 건강",
            key="identity_keywords"
        )

        # 상세 설명
        identity_description = st.text_area(
            "상세 설명 (선택)",
            value=identity.description,
            height=100,
            placeholder="채널에 대한 추가 설명...",
            key="identity_description"
        )

        # 저장 버튼
        if st.button("저장", key="save_identity", type="primary"):
            # 데이터 파싱
            main_topics = [t.strip() for t in identity_main_topics_text.split("\n") if t.strip()]
            reference_channels = [c.strip() for c in identity_reference_channels_text.split("\n") if c.strip()]
            exclude_topics = [t.strip() for t in identity_exclude_topics_text.split("\n") if t.strip()]
            keywords = [k.strip() for k in identity_keywords_text.split(",") if k.strip()]

            # 정체성 업데이트
            new_identity = ChannelIdentity(
                project_name=project_name,
                channel_name=identity_channel_name,
                main_topics=main_topics,
                target_audience=identity_target_audience,
                content_style=identity_content_style,
                tone_voice=identity_tone_voice,
                reference_channels=reference_channels,
                exclude_topics=exclude_topics,
                keywords=keywords,
                description=identity_description,
                created_at=identity.created_at
            )

            if identity_manager.save(new_identity):
                st.success("채널 정체성이 저장되었습니다!")
                st.rerun()
            else:
                st.error("저장 실패")

    # 미리보기
    if identity.is_configured():
        with st.expander("미리보기 (AI 프롬프트 컨텍스트)", expanded=False):
            st.code(identity.to_prompt_context(), language="markdown")


# ============================================================
# AI 주제 추천 탭 (v3.0)
# ============================================================
with tab_recommend:
    st.subheader("🎯 AI 영상 주제 추천")
    st.caption("급등 영상을 분석하여 채널에 맞는 주제를 추천합니다")

    # 프로젝트 확인
    project_name = project_path.name if project_path else "기본 프로젝트"

    # 채널 정체성 로드
    identity_manager = get_identity_manager()
    identity = identity_manager.load(project_name)

    # 정체성 요약 표시
    with st.expander("현재 채널 정체성", expanded=False):
        if identity.is_configured():
            st.markdown(identity.to_prompt_context())
        else:
            st.warning("채널 정체성이 정의되지 않았습니다. '채널 정체성' 탭에서 먼저 설정해주세요.")

    st.divider()

    # 검색 결과 확인
    search_results = st.session_state.get("search_results", [])

    if not search_results:
        st.warning("검색 결과가 없습니다. '검색' 탭에서 먼저 영상을 검색해주세요.")
    else:
        # AI 설정 (3가지 제공자 지원)
        col1, col2, col3 = st.columns(3)

        with col1:
            api_availability = check_api_availability()

            # 제공자 옵션 (v4.0: anthropic 제거, Max Plan + Gemini 폴백)
            all_providers = ["claude_code_agent", "google"]

            def format_provider(x):
                status = ""
                if x == "google":
                    status = " (API 키 없음)" if not api_availability.get("google") else ""
                    return f"Gemini API{status}"
                else:  # claude_code_agent
                    cli_status = " (CLI 없음)" if not api_availability.get("claude_code_agent") else ""
                    fallback_status = " + Gemini 폴백" if api_availability.get("gemini_fallback") else ""
                    return f"Claude Max Plan{cli_status}{fallback_status}"

            topic_ai_provider = st.selectbox(
                "AI 제공자",
                all_providers,
                format_func=format_provider,
                key="topic_ai_provider",
                help="""
                - Claude Max Plan: Claude CLI (Max Plan) + Gemini 자동 폴백
                - Gemini API: Google API 직접 호출 (GOOGLE_API_KEY 필요)
                """
            )

            # 제공자별 상태 표시
            if topic_ai_provider == "claude_code_agent":
                if api_availability.get("claude_code_agent"):
                    st.caption("Claude CLI 사용 가능")
                else:
                    st.warning("Claude CLI가 설치되지 않았습니다")

        with col2:
            if topic_ai_provider == "google":
                model_options = ["gemini-2.0-flash-exp", "gemini-1.5-flash", "gemini-1.5-pro"]
            else:  # claude_code_agent
                model_options = ["Max Plan (자동)"]

            topic_ai_model = st.selectbox(
                "AI 모델",
                model_options,
                key="topic_ai_model",
                disabled=(topic_ai_provider == "claude_code_agent"),
                help="Claude Max Plan은 자동으로 최적 모델 선택 + Gemini 폴백"
            )

        with col3:
            topic_top_n = st.number_input(
                "분석할 영상 수",
                min_value=5,
                max_value=50,
                value=min(20, len(search_results)),
                key="topic_top_n"
            )

        # 추가 지시사항
        topic_custom_instructions = st.text_area(
            "추가 지시사항 (선택)",
            placeholder="예: 최근 AI 관련 주제에 집중해주세요\n예: 10분 이내 숏폼 콘텐츠로 제작 가능한 주제만",
            height=80,
            key="topic_custom_instructions"
        )

        # 프롬프트 편집 (고급)
        with st.expander("AI 프롬프트 편집 (고급)", expanded=False):
            recommender = get_topic_recommender(topic_ai_provider, topic_ai_model)
            template = recommender.get_prompt_template()

            st.caption("시스템 프롬프트")
            new_system_prompt = st.text_area(
                "시스템 프롬프트",
                value=template.system_prompt,
                height=200,
                key="topic_system_prompt",
                label_visibility="collapsed"
            )

            st.caption("사용자 프롬프트 템플릿")
            st.info("변수: {channel_identity}, {video_list}")
            new_user_prompt = st.text_area(
                "사용자 프롬프트 템플릿",
                value=template.user_prompt_template,
                height=300,
                key="topic_user_prompt",
                label_visibility="collapsed"
            )

            if st.button("프롬프트 저장", key="save_prompt"):
                recommender.update_prompt_template(new_system_prompt, new_user_prompt)
                st.success("프롬프트가 저장되었습니다!")

        st.divider()

        # 분석 대상 영상 미리보기
        st.markdown(f"### 분석 대상: 상위 {min(topic_top_n, len(search_results))}개 영상")

        # 급등점수 순 정렬
        sorted_videos = sorted(
            search_results,
            key=lambda x: safe_get(x, "surge_score", 0),
            reverse=True
        )[:topic_top_n]

        # 미리보기 테이블
        preview_data = []
        for v in sorted_videos[:10]:
            title = safe_get(v, "title", "")
            preview_data.append({
                "제목": title[:50] + ("..." if len(title) > 50 else ""),
                "채널": safe_get(v, "channel_name", "") or safe_get(v, "channel", ""),
                "조회수": f"{safe_get(v, 'view_count', 0) or safe_get(v, 'views', 0):,}",
                "급등점수": f"{safe_get(v, 'surge_score', 0):.1f}"
            })

        if preview_data:
            st.dataframe(preview_data, use_container_width=True, hide_index=True)

            if len(sorted_videos) > 10:
                st.caption(f"... 외 {len(sorted_videos) - 10}개 영상")

        st.divider()

        # 추천 실행 버튼
        if st.button("AI 주제 추천 시작", key="run_topic_recommendation", type="primary"):

            if not identity.is_configured():
                st.error("채널 정체성이 정의되지 않았습니다. 먼저 정체성을 설정해주세요.")
            else:
                # 제공자별 메시지
                provider_msgs = {
                    "google": "Gemini API로 영상을 분석하는 중...",
                    "claude_code_agent": "Claude Max Plan으로 영상을 분석하는 중 (+ Gemini 폴백 대기)..."
                }
                spinner_msg = provider_msgs.get(topic_ai_provider, "AI가 영상을 분석하는 중...")

                with st.spinner(spinner_msg):
                    try:
                        # 영상 데이터 변환
                        videos_for_ai = []
                        for v in sorted_videos:
                            videos_for_ai.append({
                                "title": safe_get(v, "title", ""),
                                "channel": safe_get(v, "channel_name", "") or safe_get(v, "channel", ""),
                                "views": safe_get(v, "view_count", 0) or safe_get(v, "views", 0),
                                "likes": safe_get(v, "like_count", 0) or safe_get(v, "likes", 0),
                                "subscribers": safe_get(v, "subscriber_count", 0),
                                "surge_score": safe_get(v, "surge_score", 0),
                                "published_date": safe_get(v, "published_at", "") or safe_get(v, "published_date", ""),
                                "video_id": safe_get(v, "video_id", "")
                            })

                        # Claude Code Agent는 모델이 None
                        model_to_use = None if topic_ai_provider == "claude_code_agent" else topic_ai_model

                        result = recommend_topics(
                            project_name=project_name,
                            videos=videos_for_ai,
                            provider=topic_ai_provider,
                            model=model_to_use,
                            custom_instructions=topic_custom_instructions
                        )

                        # 결과 저장
                        st.session_state["topic_recommendations"] = result

                    except Exception as e:
                        st.error(f"오류: {e}")
                        import traceback
                        st.code(traceback.format_exc())

        # 추천 결과 표시
        if "topic_recommendations" in st.session_state:
            result = st.session_state["topic_recommendations"]

            st.markdown("---")
            st.markdown("## AI 추천 결과")

            # 트렌드 분석
            st.markdown("### 트렌드 분석")
            st.info(result.trend_analysis)

            # 공통 키워드
            if result.common_keywords:
                st.markdown("**공통 키워드:**")
                st.write(" | ".join([f"`{kw}`" for kw in result.common_keywords]))

            st.divider()

            # 추천 주제 목록
            st.markdown("### 추천 주제")

            for i, rec in enumerate(result.recommendations, 1):
                priority_stars = "*" * rec.priority

                with st.expander(f"{i}. {rec.topic} (우선순위: {rec.priority}/5)", expanded=(i <= 3)):

                    col1, col2 = st.columns([3, 1])

                    with col1:
                        st.markdown(f"**설명:** {rec.description}")
                        st.markdown(f"**추천 이유:** {rec.reason}")
                        st.markdown(f"**타겟 시청자:** {rec.target_audience}")

                    with col2:
                        st.metric("예상 조회수", rec.estimated_views)
                        st.metric("우선순위", f"{rec.priority}/5")

                    if rec.keywords:
                        st.markdown("**키워드:** " + ", ".join([f"`{k}`" for k in rec.keywords]))

                    if rec.reference_videos:
                        st.markdown("**참고 영상:**")
                        for ref in rec.reference_videos:
                            st.caption(f"- {ref}")

            # 메타 정보
            st.divider()
            model_name = getattr(result, 'model_used', '') or getattr(result, 'provider_used', 'unknown')
            tokens = getattr(result, 'tokens_used', 0)
            st.caption(f"AI: {model_name} | 토큰 사용: {tokens:,}")

            # 내보내기
            col1, col2 = st.columns(2)
            with col1:
                if st.button("결과 복사 (텍스트)", key="copy_recommendations"):
                    # 텍스트 형식으로 변환
                    text_output = f"# AI 주제 추천 결과\n\n"
                    text_output += f"## 트렌드 분석\n{result.trend_analysis}\n\n"
                    text_output += f"## 추천 주제\n"
                    for i, rec in enumerate(result.recommendations, 1):
                        text_output += f"\n### {i}. {rec.topic}\n"
                        text_output += f"- 설명: {rec.description}\n"
                        text_output += f"- 추천 이유: {rec.reason}\n"
                        text_output += f"- 타겟: {rec.target_audience}\n"
                        text_output += f"- 예상 조회수: {rec.estimated_views}\n"

                    st.code(text_output)

            with col2:
                import json as json_module
                recommendations_json = json_module.dumps({
                    "trend_analysis": result.trend_analysis,
                    "common_keywords": result.common_keywords,
                    "recommendations": [
                        {
                            "topic": r.topic,
                            "description": r.description,
                            "reason": r.reason,
                            "target_audience": r.target_audience,
                            "estimated_views": r.estimated_views,
                            "keywords": r.keywords,
                            "priority": r.priority
                        }
                        for r in result.recommendations
                    ]
                }, ensure_ascii=False, indent=2)

                st.download_button(
                    "JSON 다운로드",
                    data=recommendations_json,
                    file_name="topic_recommendations.json",
                    mime="application/json",
                    key="download_recommendations"
                )
