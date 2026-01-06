# -*- coding: utf-8 -*-
"""
채널 트렌드 분석 페이지

특정 키워드 분야의 신규 채널 탐지 및 시장 진입 강도 분석
- AI 키워드 확장 기능 추가
- 그래프 수정 (X축 날짜 형식, Y축 정수 형식)
- 채널 검색 기능 추가
- 트랜스크립트 일괄 다운로드 기능 추가
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import time
import os
import sys
import zipfile
import io
import json

# 경로 설정
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.youtube.channel_trend_analyzer import (
    ChannelTrendAnalyzer,
    TrendAnalysisResult,
    create_channel_trend_analyzer
)

# AI 키워드 확장 및 차트 모듈
try:
    from utils.ai_keyword_suggester import AIKeywordSuggester, get_ai_keyword_suggester
    AI_KEYWORD_AVAILABLE = True
except ImportError:
    AI_KEYWORD_AVAILABLE = False

try:
    from utils.trend_chart import create_monthly_channel_chart, get_trend_interpretation
    TREND_CHART_AVAILABLE = True
except ImportError:
    TREND_CHART_AVAILABLE = False

# 채널 검색 모듈
try:
    from utils.channel_searcher import YouTubeChannelSearcher, get_channel_searcher
    CHANNEL_SEARCHER_AVAILABLE = True
except ImportError:
    CHANNEL_SEARCHER_AVAILABLE = False

# 트랜스크립트 다운로더 모듈
try:
    from utils.transcript_downloader import (
        YouTubeTranscriptDownloader,
        get_transcript_downloader,
        TranscriptResult,
        DownloadProgress,
        DownloadMethod,  # ⭐ 다운로드 방식 추가
        check_cookies_status,  # ⭐ 쿠키 상태 확인
        create_cookies_guide,  # ⭐ 쿠키 가이드
        TranscriptFormatter  # ⭐ v4.4: 다중 형식 저장
    )
    TRANSCRIPT_DOWNLOADER_AVAILABLE = True
except ImportError:
    TRANSCRIPT_DOWNLOADER_AVAILABLE = False

# ⭐ v4.2: 쿠키 검증 모듈
try:
    from utils.cookie_validator import validate_cookies_file, get_cookie_status_summary
    COOKIE_VALIDATOR_AVAILABLE = True
except ImportError:
    COOKIE_VALIDATOR_AVAILABLE = False

# v2.0: 보관함 및 YouTube 서비스 모듈
try:
    from utils.bookmark_storage import BookmarkStorage
    from utils.youtube_service import YouTubeService
    BOOKMARK_AVAILABLE = True
except ImportError:
    BOOKMARK_AVAILABLE = False

# 페이지 설정
st.set_page_config(
    page_title="채널 트렌드 분석",
    page_icon="📊",
    layout="wide"
)

# CSS 스타일
st.markdown("""
<style>
.trend-header {
    background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
    color: white;
    padding: 20px;
    border-radius: 12px;
    margin-bottom: 20px;
}

.metric-card {
    background: white;
    padding: 20px;
    border-radius: 12px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.1);
    text-align: center;
}

.metric-value {
    font-size: 32px;
    font-weight: bold;
    color: #667eea;
}

.metric-label {
    color: #666;
    font-size: 14px;
}

.channel-card {
    background: white;
    padding: 15px;
    border-radius: 10px;
    border-left: 4px solid #667eea;
    margin-bottom: 10px;
    box-shadow: 0 2px 5px rgba(0,0,0,0.05);
}

.growth-badge {
    display: inline-block;
    padding: 4px 12px;
    border-radius: 20px;
    font-size: 12px;
    font-weight: bold;
}

.growth-rapid { background: #d4edda; color: #155724; }
.growth-good { background: #cce5ff; color: #004085; }
.growth-normal { background: #fff3cd; color: #856404; }
.growth-slow { background: #f8d7da; color: #721c24; }

.insight-box {
    background: linear-gradient(135deg, #f5f7fa 0%, #c3cfe2 100%);
    padding: 20px;
    border-radius: 12px;
    border-left: 4px solid #667eea;
}

.search-result-card {
    background: white;
    padding: 20px;
    border-radius: 12px;
    border-left: 4px solid #28a745;
    margin-bottom: 15px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
}

.queue-item {
    background: #f8f9fa;
    padding: 10px 15px;
    border-radius: 8px;
    margin: 5px 0;
    display: flex;
    justify-content: space-between;
    align-items: center;
}

.transcript-stats {
    background: linear-gradient(135deg, #e3f2fd 0%, #bbdefb 100%);
    padding: 15px;
    border-radius: 10px;
    text-align: center;
}

.download-complete {
    background: #d4edda;
    border: 1px solid #c3e6cb;
    padding: 15px;
    border-radius: 10px;
}
</style>
""", unsafe_allow_html=True)


def get_api_key():
    """API 키 가져오기"""
    # 세션에서 먼저 확인
    if "youtube_api_key" in st.session_state and st.session_state.youtube_api_key:
        return st.session_state.youtube_api_key

    # 환경변수 확인
    from config.settings import YOUTUBE_API_KEY
    if YOUTUBE_API_KEY:
        return YOUTUBE_API_KEY

    return None


def render_header():
    """헤더 렌더링"""
    st.markdown("""
    <div class="trend-header">
        <h1>📊 채널 트렌드 분석</h1>
        <p>특정 키워드 분야에서 최근 생성된 신규 채널들을 발굴하고 시장 진입 강도를 분석합니다.</p>
    </div>
    """, unsafe_allow_html=True)


def render_search_form():
    """검색 폼 렌더링"""
    st.markdown("### 🔍 분석 설정")

    # ═══════════════════════════════════════════════════════
    # Row 1: 키워드 + AI 확장 옵션
    # ═══════════════════════════════════════════════════════
    col1, col2, col3 = st.columns([3, 1, 1])

    with col1:
        keyword = st.text_input(
            "키워드",
            placeholder="예: 일본 시니어 브이로그, 은퇴 후 이민, 연금",
            help="분석할 주제 키워드를 입력하세요"
        )

    with col2:
        region = st.selectbox(
            "국가",
            options=["KR", "JP", "US", "GB", "AU"],
            format_func=lambda x: {
                "KR": "🇰🇷 한국",
                "JP": "🇯🇵 일본",
                "US": "🇺🇸 미국",
                "GB": "🇬🇧 영국",
                "AU": "🇦🇺 호주"
            }.get(x, x)
        )

    with col3:
        months = st.selectbox(
            "분석 기간",
            options=[1, 3, 6, 12],
            index=2,
            format_func=lambda x: f"최근 {x}개월"
        )

    # ═══════════════════════════════════════════════════════
    # Row 2: AI 키워드 확장 설정
    # ═══════════════════════════════════════════════════════
    expanded_keywords = []

    if AI_KEYWORD_AVAILABLE:
        with st.expander("🤖 AI 키워드 확장 (클릭하여 펼치기)", expanded=False):
            st.caption("AI가 관련 키워드를 자동으로 추천하여 더 넓은 범위의 채널을 분석합니다.")

            col_ai1, col_ai2, col_ai3 = st.columns([1, 1, 1])

            with col_ai1:
                use_ai_expansion = st.checkbox(
                    "AI 키워드 확장 사용",
                    value=False,
                    key="use_ai_expansion",
                    help="체크하면 AI가 관련 키워드를 추천합니다"
                )

            with col_ai2:
                ai_provider = st.selectbox(
                    "AI API",
                    options=["gemini", "claude"],
                    format_func=lambda x: {
                        "gemini": "🔷 Google Gemini",
                        "claude": "🟣 Anthropic Claude"
                    }.get(x, x),
                    disabled=not use_ai_expansion,
                    key="ai_provider"
                )

            with col_ai3:
                keyword_count = st.slider(
                    "추천 키워드 수",
                    min_value=5,
                    max_value=25,
                    value=15,
                    disabled=not use_ai_expansion,
                    key="keyword_count"
                )

            # AI 키워드 추천 실행
            if use_ai_expansion and keyword:
                if st.button("🔍 관련 키워드 추천받기", type="secondary"):
                    with st.spinner(f"{ai_provider}로 키워드 분석 중..."):
                        suggester = get_ai_keyword_suggester(api_provider=ai_provider)

                        if not suggester.check_api_key():
                            st.error(f"❌ {ai_provider.upper()} API 키가 설정되지 않았습니다.")
                        else:
                            result = suggester.suggest_keywords(
                                keyword=keyword,
                                count=keyword_count
                            )

                            if result.get("success"):
                                st.session_state.ai_keywords = result
                                st.success(f"✅ {result['total_count']}개 키워드 추천 완료! (API: {result['api_used']})")
                            else:
                                st.warning("키워드 추천에 실패했습니다. 폴백 모드로 전환합니다.")
                                st.session_state.ai_keywords = result

                # 추천된 키워드 표시 및 선택
                if "ai_keywords" in st.session_state and st.session_state.ai_keywords.get("success"):
                    ai_result = st.session_state.ai_keywords
                    categories = ai_result.get("categories", {})

                    if categories:
                        st.markdown("#### 📋 추천 키워드 (분석에 포함할 키워드 선택)")

                        # 카테고리 표시 이름
                        cat_display_map = {
                            "직접_관련": "🎯 직접 관련",
                            "동의어_유사어": "🔄 동의어/유사어",
                            "관련_주제": "📚 관련 주제",
                            "롱테일_키워드": "🔍 롱테일 키워드",
                            "트렌드_키워드": "📈 트렌드 키워드"
                        }

                        # 카테고리별 표시
                        for cat_name, keywords in categories.items():
                            if not keywords or not isinstance(keywords, list):
                                continue

                            cat_display = cat_display_map.get(cat_name, cat_name)
                            st.markdown(f"**{cat_display}**")

                            # 키워드 칩 형태로 표시 (한 줄에 최대 4개)
                            cols = st.columns(min(len(keywords), 4))
                            for i, kw in enumerate(keywords):
                                if isinstance(kw, str):
                                    with cols[i % 4]:
                                        # 기본값은 직접 관련만 체크
                                        default_checked = cat_name == "직접_관련"
                                        if st.checkbox(kw, value=default_checked, key=f"kw_{cat_name}_{i}"):
                                            if kw not in expanded_keywords:
                                                expanded_keywords.append(kw)

                        # 선택된 키워드 수 표시
                        st.info(f"📊 선택된 확장 키워드: {len(expanded_keywords)}개")

        # 세션에 확장 키워드 저장
        st.session_state.expanded_keywords = expanded_keywords

    # ═══════════════════════════════════════════════════════
    # Row 3: 기존 설정 (영상 수, 캐시)
    # ═══════════════════════════════════════════════════════
    col1, col2, col3 = st.columns([1, 1, 3])

    with col1:
        max_videos = st.number_input(
            "검색 영상 수",
            min_value=50,
            max_value=200,
            value=100,
            step=50,
            help="더 많은 영상을 검색하면 더 많은 채널을 발견할 수 있지만, API 할당량이 더 소모됩니다."
        )

    with col2:
        use_cache = st.checkbox("캐시 사용", value=True, help="7일 이내 동일 검색 결과를 재사용합니다.")

    return keyword, region, months, max_videos, use_cache, expanded_keywords


def render_metrics(result: TrendAnalysisResult):
    """주요 지표 렌더링"""
    col1, col2, col3, col4, col5 = st.columns(5)

    with col1:
        st.metric(
            "검색된 영상",
            f"{result.total_videos_searched:,}개"
        )

    with col2:
        st.metric(
            "고유 채널",
            f"{result.unique_channels_found:,}개"
        )

    with col3:
        st.metric(
            "🆕 신규 채널",
            f"{result.new_channels_count:,}개",
            help=f"최근 {result.period_months}개월 내 생성된 채널"
        )

    with col4:
        # 키워드 관련 채널 수
        relevant_count = len([c for c in result.new_channels if c.keyword_relevant])
        st.metric(
            "🎯 키워드 관련",
            f"{relevant_count}개",
            help="채널명/설명에 키워드가 포함된 채널"
        )

    with col5:
        # 시장 판정 (Market Verdict)
        if result.market_verdict_label:
            st.metric(
                "시장 판정",
                result.market_verdict_label,
                help="기회지수 + 경쟁강도 기반 시장 판정"
            )
        else:
            # 진입 강도 계산 (fallback)
            monthly_avg = result.new_channels_count / result.period_months if result.period_months > 0 else 0
            if monthly_avg >= 5:
                intensity = "🔴 높음"
            elif monthly_avg >= 2:
                intensity = "🟡 중간"
            else:
                intensity = "🟢 낮음"
            st.metric(
                "진입 강도",
                intensity,
                help="월 평균 신규 채널 수 기준"
            )


def render_market_opportunity(result: TrendAnalysisResult):
    """시장 기회 분석 섹션"""
    st.markdown("### ⭐ 시장 기회 분석")

    # 기회 지수 설명
    with st.expander("ℹ️ 기회 지수란?", expanded=False):
        st.markdown("""
        **기회 지수 (Opportunity Score)** = 평균 조회수 / 구독자 수

        - 🌟 **황금 기회 (100+)**: 구독자 대비 조회수가 매우 높음 = 알고리즘이 밀어주는 키워드
        - ✅ **좋은 기회 (50-100)**: 성장 가능성이 높은 분야
        - 🟡 **보통 (10-50)**: 일반적인 경쟁 수준
        - 🔴 **포화 (<10)**: 구독자 대비 조회수가 낮음 = 레드오션
        """)

    # 주요 지표 카드
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        score = result.avg_opportunity_score
        if score >= 100:
            score_emoji = "🌟"
        elif score >= 50:
            score_emoji = "✅"
        elif score >= 10:
            score_emoji = "🟡"
        else:
            score_emoji = "🔴"
        st.metric(
            "평균 기회지수",
            f"{score_emoji} {score:.1f}",
            help="관련 채널들의 평균 기회 지수"
        )

    with col2:
        st.metric(
            "경쟁 강도",
            f"{result.supply_index:.1f}",
            help="월 평균 신규 채널 수"
        )

    with col3:
        st.metric(
            "수요 지수",
            f"{result.demand_index:.1f}",
            help="평균 조회수 기반 (로그 스케일)"
        )

    with col4:
        st.metric(
            "시장 판정",
            result.market_verdict_label or "분석 중",
            help="기회지수 + 경쟁강도 기반 종합 판정"
        )

    # 시장 판정 상세 설명
    if result.market_verdict == "blue_ocean":
        st.success("🔵 **블루오션**: 기회지수가 높고 경쟁이 적습니다. 지금이 진입 적기!")
    elif result.market_verdict == "growing":
        st.info("🟢 **성장시장**: 수요가 증가하고 있으며 아직 기회가 있습니다.")
    elif result.market_verdict == "competitive":
        st.warning("🟡 **경쟁시장**: 적절한 차별화 전략이 필요합니다.")
    elif result.market_verdict == "red_ocean":
        st.error("🔴 **레드오션**: 경쟁이 치열합니다. 틈새 시장을 공략하세요.")

    # 라이징 스타 (황금 기회 채널)
    golden = result.get_golden_opportunities()
    if golden:
        st.markdown("#### 🌟 황금 기회 채널")
        st.caption("구독자 대비 조회수가 매우 높은 채널들 (기회지수 100+)")

        for ch in golden[:3]:
            col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
            with col1:
                st.markdown(f"**[{ch.title}]({ch.channel_url})**")
            with col2:
                st.caption(f"구독자: {ch.subscribers:,}")
            with col3:
                st.caption(f"평균조회: {ch.avg_views_per_video:,.0f}")
            with col4:
                st.markdown(f"**{ch.opportunity_label}**")
    else:
        # 황금 기회가 없으면 라이징 스타 표시
        rising = result.get_rising_stars(3)
        if rising:
            st.markdown("#### 📈 주목할 채널 (라이징 스타)")
            st.caption("기회 지수가 높은 상위 채널")

            for ch in rising:
                col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
                with col1:
                    st.markdown(f"**[{ch.title}]({ch.channel_url})**")
                with col2:
                    st.caption(f"구독자: {ch.subscribers:,}")
                with col3:
                    st.caption(f"평균조회: {ch.avg_views_per_video:,.0f}")
                with col4:
                    st.markdown(f"**{ch.opportunity_label}**")


def render_monthly_trend(result: TrendAnalysisResult):
    """월별 트렌드 차트"""
    st.markdown("### 📈 월별 신규 채널 생성 추이")

    if not result.monthly_trend:
        st.info("데이터가 없습니다.")
        return

    # 수정된 차트 함수 사용 (X축 날짜 형식, Y축 정수 형식)
    if TREND_CHART_AVAILABLE:
        fig = create_monthly_channel_chart(
            monthly_data=result.monthly_trend,
            title=""
        )
        st.plotly_chart(fig, use_container_width=True)

        # 트렌드 해석 문구
        interpretation = get_trend_interpretation(result.monthly_trend)
        if interpretation:
            st.markdown(interpretation)
    else:
        # 폴백: 기존 차트 (수정된 버전)
        sorted_months = sorted(result.monthly_trend.keys())

        # X축 레이블 변환 (2024-10 → 2024년 10월)
        x_labels = []
        for month in sorted_months:
            try:
                dt = datetime.strptime(month, "%Y-%m")
                x_labels.append(dt.strftime("%Y년 %m월"))
            except ValueError:
                x_labels.append(month)

        y_values = [result.monthly_trend[m] for m in sorted_months]
        max_value = max(y_values) if y_values else 1

        # Plotly Graph Objects로 직접 생성
        fig = go.Figure()

        fig.add_trace(go.Bar(
            x=x_labels,
            y=y_values,
            marker_color='#667eea',
            text=y_values,
            textposition='outside',
            textfont=dict(size=14, color='#333'),
            hovertemplate='%{x}<br>신규 채널: %{y}개<extra></extra>'
        ))

        fig.update_layout(
            xaxis=dict(
                title="",
                tickfont=dict(size=12),
                tickangle=-45 if len(x_labels) > 6 else 0,
                type='category'  # 카테고리로 설정 (시간 축 아님!)
            ),
            yaxis=dict(
                title="채널 수",
                tickfont=dict(size=12),
                dtick=max(1, max_value // 5) if max_value > 5 else 1,
                rangemode='tozero',
                tickformat='d',  # 정수 형식
                range=[0, max_value * 1.2]
            ),
            height=350,
            showlegend=False,
            plot_bgcolor='rgba(0,0,0,0)',
            paper_bgcolor='rgba(0,0,0,0)'
        )

        fig.update_xaxes(showgrid=False)
        fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='rgba(0,0,0,0.1)')

        st.plotly_chart(fig, use_container_width=True)

        # 트렌드 분석 메시지
        if len(result.monthly_trend) >= 2:
            values = list(result.monthly_trend.values())

            recent_avg = sum(values[-2:]) / 2 if len(values) >= 2 else values[-1]
            older_avg = sum(values[:-2]) / max(1, len(values) - 2) if len(values) > 2 else values[0]

            if recent_avg > older_avg * 1.5:
                st.warning("⚠️ 최근 신규 채널 생성이 급증하고 있습니다. 경쟁이 심화되는 추세입니다.")
            elif recent_avg < older_avg * 0.5:
                st.success("✅ 최근 신규 채널 생성이 감소하고 있습니다. 진입 기회가 있을 수 있습니다.")


def render_channel_list(result: TrendAnalysisResult):
    """신규 채널 리스트"""
    st.markdown("### 🏆 주목할 만한 신규 채널")

    if not result.new_channels:
        st.info("발견된 신규 채널이 없습니다.")
        return

    # 관련 채널과 기타 채널 분리
    relevant_channels = [c for c in result.new_channels if c.keyword_relevant]
    other_channels = [c for c in result.new_channels if not c.keyword_relevant]

    # 필터 및 정렬 옵션
    col1, col2 = st.columns(2)

    with col1:
        filter_option = st.selectbox(
            "표시 필터",
            options=["all", "relevant", "other"],
            format_func=lambda x: {
                "all": f"🔎 전체 ({len(result.new_channels)}개)",
                "relevant": f"🎯 키워드 관련 ({len(relevant_channels)}개)",
                "other": f"📋 기타 ({len(other_channels)}개)"
            }.get(x)
        )

    with col2:
        sort_option = st.selectbox(
            "정렬 기준",
            options=["opportunity", "relevance", "created_at", "subscribers", "avg_views", "efficiency"],
            format_func=lambda x: {
                "opportunity": "⭐ 기회지수순",
                "relevance": "🎯 관련성순",
                "created_at": "📅 최신순",
                "subscribers": "👥 구독자순",
                "avg_views": "👁️ 평균조회수순",
                "efficiency": "📈 성장효율순"
            }.get(x)
        )

    # 필터링
    if filter_option == "relevant":
        channels = relevant_channels.copy()
    elif filter_option == "other":
        channels = other_channels.copy()
    else:
        channels = result.new_channels.copy()

    # 정렬
    if sort_option == "opportunity":
        channels.sort(key=lambda x: x.opportunity_score, reverse=True)
    elif sort_option == "relevance":
        channels.sort(key=lambda x: (-x.relevance_score, -x.subscribers))
    elif sort_option == "subscribers":
        channels.sort(key=lambda x: x.subscribers, reverse=True)
    elif sort_option == "avg_views":
        channels.sort(key=lambda x: x.avg_views_per_video, reverse=True)
    elif sort_option == "efficiency":
        channels.sort(key=lambda x: x.subscribers_per_video, reverse=True)
    elif sort_option == "created_at":
        channels.sort(key=lambda x: x.created_at_dt, reverse=True)

    if not channels:
        st.info("해당 조건에 맞는 채널이 없습니다.")
        return

    # 채널 카드 표시
    for i, channel in enumerate(channels[:20]):  # 최대 20개
        with st.container():
            col1, col2, col3, col4, col5, col6 = st.columns([3, 1, 1, 1, 1, 1])

            with col1:
                # 관련성 배지 + 채널명
                relevance_badge = ""
                if channel.keyword_relevant:
                    relevance_badge = "🎯 "
                elif channel.relevance_score > 0:
                    relevance_badge = "🔸 "

                st.markdown(f"**{relevance_badge}[{channel.title}]({channel.channel_url})**")
                st.caption(f"📅 {channel.created_at} 생성 ({channel.days_since_creation}일 전)")

                # 관련성 이유 표시 (있으면)
                if channel.relevance_reason and channel.relevance_reason != "관련성 낮음":
                    st.caption(f"💡 {channel.relevance_reason}")

            with col2:
                st.metric("구독자", f"{channel.subscribers:,}")

            with col3:
                st.metric("영상", f"{channel.video_count}")

            with col4:
                st.metric("평균조회", f"{channel.avg_views_per_video:,.0f}")

            with col5:
                # 기회 지수 (핵심 지표!)
                opp_score = channel.opportunity_score
                if opp_score >= 100:
                    opp_display = f"🌟 {opp_score:.0f}"
                elif opp_score >= 50:
                    opp_display = f"✅ {opp_score:.0f}"
                elif opp_score >= 10:
                    opp_display = f"🟡 {opp_score:.1f}"
                else:
                    opp_display = f"🔴 {opp_score:.1f}"
                st.markdown(f"**기회지수**\n{opp_display}")

            with col6:
                # 관련성 점수
                score = channel.relevance_score
                if score >= 5:
                    score_display = f"🟢 {score}/10"
                elif score >= 3:
                    score_display = f"🟡 {score}/10"
                else:
                    score_display = f"⚪ {score}/10"
                st.markdown(f"**관련성**\n{score_display}")

            st.divider()


def render_ai_insight(result: TrendAnalysisResult):
    """AI 인사이트"""
    st.markdown("### 🤖 AI 분석 리포트")

    if result.ai_insight:
        st.markdown(f"""
        <div class="insight-box">
            {result.ai_insight}
        </div>
        """, unsafe_allow_html=True)
    else:
        if st.button("🧠 AI 인사이트 생성", type="secondary"):
            with st.spinner("AI가 분석 중..."):
                try:
                    analyzer = create_channel_trend_analyzer()

                    # Gemini 클라이언트 가져오기
                    ai_client = None
                    try:
                        import google.generativeai as genai
                        gemini_key = os.getenv("GEMINI_API_KEY")
                        if gemini_key:
                            genai.configure(api_key=gemini_key)
                            ai_client = genai.GenerativeModel('gemini-pro')
                    except ImportError:
                        pass

                    insight = analyzer.generate_ai_insight(result, ai_client)
                    result.ai_insight = insight
                    st.session_state["trend_result"] = result

                    st.markdown(f"""
                    <div class="insight-box">
                        {insight}
                    </div>
                    """, unsafe_allow_html=True)
                except Exception as e:
                    st.error(f"AI 분석 오류: {e}")


def render_download(result: TrendAnalysisResult):
    """다운로드 버튼"""
    st.markdown("### 📥 데이터 다운로드")

    if not result.new_channels:
        return

    # DataFrame 생성
    df = pd.DataFrame([
        {
            "채널명": ch.title,
            "채널 URL": ch.channel_url,
            "생성일": ch.created_at,
            "구독자": ch.subscribers,
            "영상 수": ch.video_count,
            "총 조회수": ch.view_count,
            "평균 조회수": round(ch.avg_views_per_video),
            "기회 지수": round(ch.opportunity_score, 1),
            "기회 레벨": ch.opportunity_label,
            "영상당 구독자": round(ch.subscribers_per_video, 1),
            "성장 등급": ch.growth_rate,
            "관련성 점수": ch.relevance_score,
            "키워드 관련": "O" if ch.keyword_relevant else "",
            "관련성 이유": ch.relevance_reason
        }
        for ch in result.new_channels
    ])

    col1, col2 = st.columns(2)

    with col1:
        # CSV
        csv = df.to_csv(index=False).encode('utf-8-sig')
        st.download_button(
            "📄 CSV 다운로드",
            data=csv,
            file_name=f"channel_trend_{result.keyword}_{result.analysis_date[:10]}.csv",
            mime="text/csv",
            use_container_width=True
        )

    with col2:
        # Excel
        try:
            import io
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
                df.to_excel(writer, index=False, sheet_name='신규채널')

            st.download_button(
                "📊 Excel 다운로드",
                data=buffer.getvalue(),
                file_name=f"channel_trend_{result.keyword}_{result.analysis_date[:10]}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        except ImportError:
            st.caption("Excel 다운로드를 위해 openpyxl 설치가 필요합니다.")


def _merge_trend_results(
    results: list,
    main_keyword: str,
    expanded_keywords: list
) -> TrendAnalysisResult:
    """
    여러 키워드의 분석 결과를 통합

    Args:
        results: TrendAnalysisResult 목록
        main_keyword: 원본 키워드
        expanded_keywords: 확장 키워드 목록

    Returns:
        통합된 TrendAnalysisResult
    """
    from collections import Counter

    if not results:
        return None

    # 기본 정보는 첫 번째 결과에서 가져옴
    first = results[0]

    # 채널 통합 (중복 제거)
    all_channels = {}
    total_videos = 0
    unique_channel_ids = set()

    for r in results:
        total_videos += r.total_videos_searched
        for ch in r.new_channels:
            if ch.channel_id not in all_channels:
                all_channels[ch.channel_id] = ch
            unique_channel_ids.add(ch.channel_id)

    # 월별 트렌드 통합
    monthly_counter = Counter()
    for r in results:
        for month, count in r.monthly_trend.items():
            # 중복 채널이 있을 수 있으므로 최대값 사용
            monthly_counter[month] = max(monthly_counter.get(month, 0), count)

    # 통합 결과 생성
    merged = TrendAnalysisResult(
        keyword=main_keyword,
        region=first.region,
        period_months=first.period_months,
        analysis_date=first.analysis_date,
        total_videos_searched=total_videos,
        unique_channels_found=len(unique_channel_ids),
        new_channels_count=len(all_channels),
        new_channels=list(all_channels.values()),
        monthly_trend=dict(sorted(monthly_counter.items()))
    )

    # 요약 통계 및 시장 기회 지표 계산
    merged.calculate_summary()

    return merged


# ═══════════════════════════════════════════════════════════════════════════════
# 채널 검색 탭
# ═══════════════════════════════════════════════════════════════════════════════

def render_channel_search_tab():
    """채널 검색 탭 렌더링"""
    st.markdown("### 📺 채널 검색")
    st.caption("YouTube 채널을 URL, @handle, 채널 ID, 또는 이름으로 검색합니다.")

    if not CHANNEL_SEARCHER_AVAILABLE:
        st.error("❌ 채널 검색 모듈이 설치되지 않았습니다.")
        return

    api_key = get_api_key()
    if not api_key:
        st.warning("⚠️ YouTube API 키가 필요합니다. 상단에서 설정하세요.")
        return

    # 검색 입력
    col1, col2 = st.columns([4, 1])

    with col1:
        search_query = st.text_input(
            "채널 검색",
            placeholder="예: https://youtube.com/@채널명, UC채널ID, 채널이름",
            help="URL, @handle, 채널 ID(UC로 시작), 또는 채널 이름을 입력하세요"
        )

    with col2:
        search_type = st.selectbox(
            "검색 타입",
            options=["auto", "url", "id", "name"],
            format_func=lambda x: {
                "auto": "🔄 자동 감지",
                "url": "🔗 URL",
                "id": "🆔 채널 ID",
                "name": "📝 채널명"
            }.get(x, x)
        )

    # 검색 실행
    if st.button("🔍 채널 검색", type="primary", disabled=not search_query):
        with st.spinner("채널 검색 중..."):
            try:
                searcher = get_channel_searcher(api_key)
                result = searcher.search_channel(search_query, search_type)

                if result:
                    st.session_state["channel_search_result"] = result
                    st.success(f"✅ 채널을 찾았습니다: {result['channel_name']}")
                else:
                    st.warning("채널을 찾을 수 없습니다. 다른 검색어를 시도해보세요.")
            except Exception as e:
                st.error(f"검색 오류: {e}")

    # 검색 결과 표시
    if "channel_search_result" in st.session_state:
        result = st.session_state["channel_search_result"]
        render_channel_info_card(result)

        # 다운로드 대기열에 추가 버튼
        st.markdown("---")
        col1, col2, col3 = st.columns([2, 2, 2])

        with col1:
            if st.button("📥 트랜스크립트 대기열에 추가", use_container_width=True):
                add_to_transcript_queue(result)

        with col2:
            max_videos = st.number_input(
                "영상 수 제한",
                min_value=10,
                max_value=500,
                value=50,
                step=10,
                help="가져올 최대 영상 수"
            )

        with col3:
            if st.button("📋 영상 목록 보기", use_container_width=True):
                with st.spinner(f"영상 목록 로딩 중... (최대 {max_videos}개)"):
                    try:
                        searcher = get_channel_searcher(api_key)
                        videos = searcher.get_channel_videos(
                            result["channel_id"],
                            max_results=max_videos
                        )
                        st.session_state["channel_videos"] = videos
                        st.success(f"✅ {len(videos)}개 영상을 불러왔습니다.")
                    except Exception as e:
                        st.error(f"영상 목록 로딩 오류: {e}")

        # 영상 목록 표시
        if "channel_videos" in st.session_state:
            videos = st.session_state["channel_videos"]
            render_video_list(videos)


def render_channel_info_card(channel: dict):
    """채널 정보 카드 렌더링"""
    st.markdown(f"""
    <div class="search-result-card">
        <h3>📺 {channel.get('channel_name', 'Unknown')}</h3>
        <p><a href="{channel.get('channel_url', '#')}" target="_blank">{channel.get('custom_url', channel.get('channel_url', ''))}</a></p>
    </div>
    """, unsafe_allow_html=True)

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        subs = channel.get('subscriber_count', 0)
        if isinstance(subs, str):
            st.metric("👥 구독자", subs)
        else:
            st.metric("👥 구독자", f"{subs:,}")

    with col2:
        st.metric("🎬 영상 수", f"{channel.get('video_count', 0):,}")

    with col3:
        st.metric("👁️ 총 조회수", f"{channel.get('view_count', 0):,}")

    with col4:
        created = channel.get('created_at', '')[:10] if channel.get('created_at') else 'N/A'
        st.metric("📅 생성일", created)

    # 설명
    if channel.get('description'):
        with st.expander("📝 채널 설명"):
            st.write(channel['description'][:500] + "..." if len(channel.get('description', '')) > 500 else channel['description'])


def render_video_list(videos: list):
    """영상 목록 렌더링"""
    st.markdown("#### 📋 영상 목록")

    if not videos:
        st.info("영상이 없습니다.")
        return

    # 데이터프레임 생성
    df = pd.DataFrame([
        {
            "제목": v.get("title", "")[:50] + "..." if len(v.get("title", "")) > 50 else v.get("title", ""),
            "게시일": v.get("published_at", "")[:10],
            "영상 ID": v.get("video_id", "")
        }
        for v in videos[:50]  # 최대 50개만 표시
    ])

    st.dataframe(df, use_container_width=True, height=300)

    st.caption(f"총 {len(videos)}개 영상 중 상위 50개 표시")


def add_to_transcript_queue(channel: dict):
    """채널을 트랜스크립트 다운로드 대기열에 추가"""
    if "transcript_queue" not in st.session_state:
        st.session_state["transcript_queue"] = []

    # 중복 확인
    existing_ids = [c["channel_id"] for c in st.session_state["transcript_queue"]]
    if channel["channel_id"] in existing_ids:
        st.warning("이미 대기열에 있는 채널입니다.")
        return

    st.session_state["transcript_queue"].append({
        "channel_id": channel["channel_id"],
        "channel_name": channel["channel_name"],
        "video_count": channel.get("video_count", 0),
        "added_at": datetime.now().isoformat()
    })

    st.success(f"✅ '{channel['channel_name']}' 채널이 대기열에 추가되었습니다.")


# ═══════════════════════════════════════════════════════════════════════════════
# 시스템 상태 표시 (쿠키, API, yt-dlp)
# ═══════════════════════════════════════════════════════════════════════════════

def render_system_status():
    """시스템 상태 표시 (쿠키 파일, API, yt-dlp 상태)"""

    try:
        status = check_cookies_status()
    except Exception:
        status = {
            "cookies_file_found": False,
            "cookies_file_path": None,
            "yt_dlp_available": False,
            "api_available": True
        }

    # ⭐ v4.2: 쿠키 검증 모듈 사용
    cookie_validation = None
    if COOKIE_VALIDATOR_AVAILABLE:
        try:
            cookie_validation = get_cookie_status_summary("data/cookies.txt")
        except Exception:
            cookie_validation = None

    # 상태 표시 (접힌 상태로 시작)
    with st.expander("🔧 시스템 상태", expanded=False):
        col1, col2, col3 = st.columns(3)

        with col1:
            if status.get("api_available"):
                st.success("✅ youtube-transcript-api")
            else:
                st.error("❌ youtube-transcript-api 미설치")

        with col2:
            if status.get("yt_dlp_available"):
                st.success("✅ yt-dlp")
            else:
                st.warning("⚠️ yt-dlp 미설치")

        with col3:
            # ⭐ v4.2: 상세 쿠키 검증 결과 표시
            if cookie_validation:
                if cookie_validation['status'] == 'ok':
                    st.success(cookie_validation['message'])
                elif cookie_validation['status'] == 'warning':
                    st.warning(cookie_validation['message'])
                else:
                    st.error(cookie_validation['message'])
            elif status.get("cookies_file_found"):
                st.success("✅ 쿠키 파일")
            else:
                st.warning("⚠️ 쿠키 파일 없음")

        # ⭐ v4.2: 상세 쿠키 정보 표시
        if cookie_validation and cookie_validation.get('details'):
            details = cookie_validation['details']
            info = details.get('info', {})

            if info:
                st.markdown("---")
                st.markdown("**🍪 쿠키 상세 정보**")

                info_col1, info_col2 = st.columns(2)
                with info_col1:
                    st.caption(f"YouTube 쿠키: {info.get('youtube_cookies', 0)}개")
                    st.caption(f"Google 쿠키: {info.get('google_cookies', 0)}개")

                with info_col2:
                    found_cookies = info.get('important_cookies_found', [])
                    if found_cookies:
                        st.caption(f"인증 쿠키: {', '.join(found_cookies[:3])}...")

                # 경고 표시
                if details.get('warnings'):
                    for warn in details['warnings']:
                        st.warning(f"⚠️ {warn}")

                # 에러 표시
                if details.get('errors'):
                    for err in details['errors']:
                        st.error(f"❌ {err}")

        # 쿠키 파일이 없거나 무효한 경우 가이드 표시
        show_guide = not status.get("cookies_file_found")
        if cookie_validation and cookie_validation['status'] == 'error':
            show_guide = True

        if show_guide:
            st.markdown("---")
            st.markdown("""
            #### 🍪 쿠키 파일 설정 가이드 (Rate Limit 방지)

            쿠키 파일을 설정하면 Rate Limit(429 에러) 발생률을 **대폭 줄일 수 있습니다**.

            **1단계: Chrome 확장 프로그램 설치**
            - Chrome 웹스토어에서 **"Get cookies.txt LOCALLY"** 검색 후 설치

            **2단계: YouTube 쿠키 내보내기**
            - YouTube.com에 로그인한 상태에서 확장 프로그램 아이콘 클릭
            - "Export" 클릭하여 cookies.txt 다운로드

            **3단계: 파일 저장**
            - 다운로드된 파일을 아래 경로에 저장:
            """)

            st.code("data/cookies.txt", language="text")

            # 폴더 열기 버튼 (Windows 전용)
            if st.button("📁 data 폴더 열기", key="open_data_folder"):
                import subprocess
                import os
                data_path = os.path.join(os.getcwd(), "data")
                try:
                    subprocess.Popen(f'explorer "{data_path}"', shell=True)
                    st.info(f"📂 폴더 열기: {data_path}")
                except Exception as e:
                    st.warning(f"폴더 열기 실패: {e}")

            st.markdown("""
            **⚠️ 주의사항**
            - 쿠키 파일은 2-4주마다 갱신 필요
            - YouTube에서 로그아웃하면 쿠키 무효화됨
            - 쿠키 파일을 다른 사람과 공유하지 마세요
            """)
        elif status.get("cookies_file_found") and not cookie_validation:
            # 쿠키 검증 모듈 없이 기본 정보만 표시
            st.info(f"📄 쿠키 파일: `{status.get('cookies_file_path', 'N/A')}`")


# ═══════════════════════════════════════════════════════════════════════════════
# 트랜스크립트 다운로드 탭
# ═══════════════════════════════════════════════════════════════════════════════

def render_transcript_tab():
    """트랜스크립트 다운로드 탭 렌더링"""
    st.markdown("### 📥 트랜스크립트 다운로드")
    st.caption("채널의 모든 영상에서 자막을 일괄 다운로드합니다.")

    if not TRANSCRIPT_DOWNLOADER_AVAILABLE:
        st.error("❌ 트랜스크립트 다운로더 모듈이 설치되지 않았습니다.")
        st.code("pip install youtube-transcript-api")
        return

    api_key = get_api_key()
    if not api_key:
        st.warning("⚠️ YouTube API 키가 필요합니다. 상단에서 설정하세요.")
        return

    # ═══════════════════════════════════════════════════════
    # ⭐ v4.5: 기존 다운로드 결과 표시 (페이지 리셋 방지)
    # ═══════════════════════════════════════════════════════
    existing_results = st.session_state.get("transcript_download_results")
    if existing_results and existing_results.get("files"):
        st.success("### ✅ 이전 다운로드 완료!")

        stats = existing_results.get("stats", {})
        st.markdown(f"""
        - 📺 처리된 채널: {stats.get('channels', 0)}개
        - 📺 처리된 영상: {stats.get('videos_downloaded', 0)}개
        - ✅ 성공: {stats.get('success', 0)}개
        - ⚠️ 자막 없음: {stats.get('no_caption', 0)}개
        - ❌ 실패: {stats.get('failed', 0)}개
        - 📁 형식: {stats.get('formats_summary', 'N/A')}
        """)

        # 다운로드 버튼 표시
        _render_download_results(existing_results)

        st.markdown("---")

        # 새 다운로드 시작 버튼
        if st.button("🔄 새 다운로드 시작", type="secondary", use_container_width=True):
            st.session_state["transcript_download_results"] = None
            st.rerun()

        return  # 기존 결과가 있으면 여기서 종료

    # ═══════════════════════════════════════════════════════
    # ⭐ 시스템 상태 표시 (쿠키, API, yt-dlp)
    # ═══════════════════════════════════════════════════════
    render_system_status()

    # 대기열 표시
    render_transcript_queue()

    queue = st.session_state.get("transcript_queue", [])
    if not queue:
        return

    st.markdown("---")

    # ═══════════════════════════════════════════════════════
    # 다운로드 설정
    # ═══════════════════════════════════════════════════════
    st.markdown("#### ⚙️ 다운로드 설정")

    col1, col2, col3 = st.columns(3)

    with col1:
        # ⭐ 언어 설정 개선 - auto를 기본값으로
        language = st.selectbox(
            "자막 언어",
            options=["auto", "en", "ko", "ja", "zh-Hans", "es"],
            index=0,  # auto가 기본값
            format_func=lambda x: {
                "auto": "🌐 자동 감지 (권장)",
                "en": "🇺🇸 영어",
                "ko": "🇰🇷 한국어",
                "ja": "🇯🇵 일본어",
                "zh-Hans": "🇨🇳 중국어 (간체)",
                "es": "🇪🇸 스페인어"
            }.get(x, x),
            help="'자동 감지'를 선택하면 영상에서 가장 적합한 자막을 자동으로 찾습니다."
        )

        # 자동 감지 설명
        if language == "auto":
            st.caption("💡 수동 자막 우선 → 자동생성 자막 순으로 탐색")

    with col2:
        # ⭐ v4.4: 다중 형식 선택 (체크박스)
        st.write("**📁 저장 형식**")
        format_col1, format_col2 = st.columns(2)
        with format_col1:
            save_json = st.checkbox("JSON", value=True, help="세그먼트 데이터 포함", key="fmt_json")
            save_srt = st.checkbox("SRT", value=True, help="자막 파일 형식", key="fmt_srt")
        with format_col2:
            save_txt = st.checkbox("TXT", value=False, help="순수 텍스트만", key="fmt_txt")
            save_vtt = st.checkbox("VTT", value=False, help="웹 자막 형식", key="fmt_vtt")

        # 선택된 형식 리스트
        selected_formats = []
        if save_json:
            selected_formats.append('json')
        if save_srt:
            selected_formats.append('srt')
        if save_txt:
            selected_formats.append('txt')
        if save_vtt:
            selected_formats.append('vtt')

        # 최소 하나 선택 필수
        if not selected_formats:
            st.warning("⚠️ 최소 하나 선택 필요")
            selected_formats = ['json']

        st.caption(f"선택: {', '.join(f.upper() for f in selected_formats)}")

    with col3:
        include_auto = st.checkbox(
            "자동생성 자막 포함",
            value=True,
            help="자동생성 자막도 다운로드합니다"
        )

    # ═══════════════════════════════════════════════════════
    # 다운로드 방식 선택 (v4.3 적응형)
    # ═══════════════════════════════════════════════════════
    st.markdown("#### 📡 다운로드 방식 (v4.3 적응형)")

    download_method = st.radio(
        "방식 선택",
        options=["auto", "api", "yt-dlp"],
        format_func=lambda x: {
            "auto": "🚀 자동 (적응형 최적화) - 권장",
            "api": "⚡ API (빠름, Rate Limit 취약)",
            "yt-dlp": "🛡️ yt-dlp (안정적)"
        }[x],
        index=0,
        horizontal=True,
        help="자동: 성공한 방식을 기억하고 우선 사용, Rate Limit 시 즉시 스킵"
    )

    # 방식별 안내 + 쿠키 상태 체크
    try:
        cookies_status = check_cookies_status()
        has_cookies = cookies_status.get("cookies_file_found", False)
    except Exception:
        has_cookies = False

    if download_method == "auto":
        st.info("""💡 **적응형 자동 모드 (v4.3)**
- 성공한 방식을 기억하고 다음에 우선 시도
- Rate Limit 발생 시 즉시 스킵 (긴 대기 없음)
- 연속 3회 실패한 방식 자동 비활성화
- 영상 1개 평균 3-5초 (기존 20초 대비 4배 빠름)""")
        if not has_cookies:
            st.caption("💡 쿠키 파일 설정 시 Rate Limit 발생률이 줄어듭니다.")
    elif download_method == "api":
        if not has_cookies:
            st.error("🚨 **API 모드 + 쿠키 없음**: Rate Limit 발생 위험이 높습니다! '자동' 모드를 권장합니다.")
        else:
            st.warning("⚠️ **API 모드**: 빠르지만 YouTube Rate Limit에 취약합니다.")
    else:
        st.success("✅ **yt-dlp 모드**: 안정적입니다. Rate Limit 걱정 없이 다운로드할 수 있습니다.")

    st.markdown("---")

    col1, col2 = st.columns(2)

    with col1:
        # ⭐ 최대 영상 수
        max_videos_per_channel = st.number_input(
            "채널당 최대 영상 수",
            min_value=10,
            max_value=2000,
            value=100,  # ⭐ 기본값 낮춤
            step=10,
            help="채널당 다운로드할 최대 영상 수 (많으면 Rate Limit 위험)"
        )

    with col2:
        # ⭐ v4.3: 요청 간격 최적화 (1-3초)
        request_delay = st.slider(
            "요청 간격 (초)",
            min_value=1.0,  # ⭐ 최소 1초
            max_value=3.0,  # ⭐ 최대 3초 (5→3)
            value=1.5,      # ⭐ 기본값 1.5초 (2→1.5)
            step=0.5,
            help="v4.3: 적응형 최적화로 짧은 딜레이도 안정적. Rate Limit 시 즉시 스킵됨."
        )

    # ⭐ 배치 설정 추가
    col3, col4 = st.columns(2)

    with col3:
        batch_size = st.number_input(
            "배치 크기",
            min_value=5,
            max_value=50,
            value=10,
            step=5,
            help="N개 영상마다 배치 대기 시간만큼 추가 대기합니다."
        )

    with col4:
        # ⭐ v4.3: 배치 대기 시간 최적화
        batch_delay = st.number_input(
            "배치 대기 시간 (초)",
            min_value=5,
            max_value=60,
            value=10,  # 30 → 10
            step=5,
            help="v4.3: Rate Limit 시 즉시 스킵하므로 짧은 대기도 안정적"
        )

    st.markdown("---")

    # ═══════════════════════════════════════════════════════
    # ✅ 글로벌 필터 옵션 (새로 추가)
    # ═══════════════════════════════════════════════════════
    st.markdown("#### 🔍 필터 및 정렬 옵션")
    st.caption("다운로드 대상 영상을 필터링하고 정렬합니다. (전체 다운로드/수동 선택 모두 적용)")

    filter_col1, filter_col2, filter_col3 = st.columns(3)

    with filter_col1:
        global_sort_by = st.selectbox(
            "정렬 기준",
            options=["latest", "oldest", "popular", "unpopular"],
            format_func=lambda x: {
                "latest": "📅 최신순",
                "oldest": "📅 오래된순",
                "popular": "🔥 조회수 높은순",
                "unpopular": "📉 조회수 낮은순"
            }.get(x, x),
            index=0,
            key="global_sort_by"
        )

    with filter_col2:
        global_video_count = st.selectbox(
            "다운로드 개수",
            options=[10, 20, 50, 100, 200, 500, "전체"],
            format_func=lambda x: f"{x}개" if isinstance(x, int) else x,
            index=2,  # 기본값 50개
            key="global_video_count"
        )

    with filter_col3:
        global_period = st.selectbox(
            "업로드 기간",
            options=["all", "1week", "1month", "3months", "6months", "1year"],
            format_func=lambda x: {
                "all": "전체 기간",
                "1week": "최근 1주일",
                "1month": "최근 1개월",
                "3months": "최근 3개월",
                "6months": "최근 6개월",
                "1year": "최근 1년"
            }.get(x, x),
            index=0,
            key="global_period"
        )

    # 추가 필터
    with st.expander("🔧 추가 필터 옵션", expanded=False):
        adv_col1, adv_col2 = st.columns(2)

        with adv_col1:
            min_views = st.number_input(
                "최소 조회수",
                min_value=0,
                value=0,
                step=1000,
                key="global_min_views",
                help="이 조회수 이상의 영상만 다운로드"
            )

        with adv_col2:
            filter_keyword = st.text_input(
                "제목 키워드 필터",
                placeholder="포함할 키워드 (선택사항)",
                key="global_filter_keyword",
                help="특정 키워드가 제목에 포함된 영상만 다운로드"
            )

    st.markdown("---")

    # ═══════════════════════════════════════════════════════
    # 영상 선택 모드
    # ═══════════════════════════════════════════════════════
    st.markdown("#### 📺 영상 선택")

    selection_mode = st.radio(
        "선택 모드",
        options=["all", "manual"],
        format_func=lambda x: {
            "all": "📋 전체 다운로드 (설정된 최대 영상 수까지)",
            "manual": "☑️ 수동 선택 (영상 목록에서 선택)"
        }[x],
        horizontal=True,
        key="transcript_selection_mode"
    )

    selected_videos_by_channel = {}

    if selection_mode == "manual":
        # 채널별 영상 선택 UI
        for channel in queue:
            channel_id = channel["channel_id"]
            channel_name = channel["channel_name"]

            with st.expander(f"📺 {channel_name}", expanded=True):
                selected = render_video_selection_section(
                    channel=channel,
                    max_videos=max_videos_per_channel,
                    api_key=api_key
                )
                selected_videos_by_channel[channel_id] = selected
    else:
        # 전체 다운로드 모드 - None은 전체를 의미
        for channel in queue:
            selected_videos_by_channel[channel["channel_id"]] = None

    st.markdown("---")

    # ═══════════════════════════════════════════════════════
    # 다운로드 실행
    # ═══════════════════════════════════════════════════════
    st.markdown("#### 🚀 다운로드 실행")

    # 예상 영상 수 계산
    total_estimated = 0
    for channel in queue:
        cid = channel["channel_id"]
        if selection_mode == "manual" and selected_videos_by_channel.get(cid):
            total_estimated += len(selected_videos_by_channel[cid])
        else:
            channel_videos = min(channel.get("video_count", 0), max_videos_per_channel)
            total_estimated += channel_videos

    # ⭐ 예상 시간 계산 (배치 대기 포함)
    request_time = total_estimated * request_delay
    batch_count = max(0, (total_estimated - 1) // batch_size)
    batch_wait_time = batch_count * batch_delay
    total_time = request_time + batch_wait_time

    col1, col2, col3 = st.columns(3)
    col1.metric("📊 예상 다운로드", f"{total_estimated:,}개 영상")
    col2.metric("⏱️ 요청 시간", f"약 {request_time/60:.1f}분")
    col3.metric("⏱️ 총 예상 시간", f"약 {total_time/60:.1f}분")

    st.caption(f"💡 배치 대기: {batch_count}회 × {batch_delay}초 = {batch_wait_time/60:.1f}분")

    # 다운로드 시작 버튼
    if st.button("📥 트랜스크립트 다운로드 시작", type="primary", use_container_width=True, disabled=total_estimated == 0):
        # ✅ 글로벌 필터 옵션 수집
        global_filter_options = {
            "sort_by": global_sort_by,
            "period": global_period,
            "max_count": global_video_count if global_video_count != "전체" else None,
            "min_views": min_views,
            "keyword": filter_keyword
        }

        run_transcript_download_v2(
            queue=queue,
            language=language,
            output_formats=selected_formats,  # ⭐ v4.4: 다중 형식 지원
            include_auto=include_auto,
            max_videos=max_videos_per_channel,
            delay=request_delay,
            batch_size=batch_size,
            batch_delay=batch_delay,
            download_method=download_method,  # ⭐ 방식 추가
            api_key=api_key,
            selection_mode=selection_mode,
            selected_videos_by_channel=selected_videos_by_channel,
            global_filter_options=global_filter_options  # ✅ 글로벌 필터 추가
        )


def render_video_selection_section(channel: dict, max_videos: int, api_key: str) -> list:
    """영상 선택 UI 섹션"""
    channel_id = channel["channel_id"]
    channel_name = channel["channel_name"]

    # 영상 목록 로드 (캐시)
    cache_key = f"channel_videos_{channel_id}"

    if cache_key not in st.session_state:
        with st.spinner(f"'{channel_name}' 영상 목록 로딩 중..."):
            try:
                searcher = get_channel_searcher(api_key)
                videos = searcher.get_channel_videos(channel_id, max_results=max_videos)

                # 영상 상세 정보 추가 (조회수)
                if videos:
                    video_ids = [v["video_id"] for v in videos[:100]]  # 처음 100개만
                    details = searcher.get_video_details(video_ids)
                    details_map = {d["video_id"]: d for d in details}
                    for v in videos:
                        if v["video_id"] in details_map:
                            v.update(details_map[v["video_id"]])

                st.session_state[cache_key] = videos
            except Exception as e:
                st.error(f"영상 목록 로딩 실패: {e}")
                return []

    videos = st.session_state.get(cache_key, [])

    if not videos:
        st.warning("영상 목록을 불러올 수 없습니다.")
        return []

    st.info(f"📺 총 {len(videos)}개 영상")

    # ═══════════════════════════════════════════════════════
    # 필터 옵션
    # ═══════════════════════════════════════════════════════
    with st.expander("🔍 필터 옵션", expanded=False):
        col1, col2, col3 = st.columns(3)

        with col1:
            sort_by = st.selectbox(
                "정렬",
                options=["latest", "oldest", "popular"],
                format_func=lambda x: {
                    "latest": "📅 최신순",
                    "oldest": "📅 오래된순",
                    "popular": "🔥 조회수순"
                }[x],
                key=f"sort_{channel_id}"
            )

        with col2:
            filter_keyword = st.text_input(
                "제목 필터",
                placeholder="키워드로 필터링",
                key=f"filter_{channel_id}"
            )

        with col3:
            date_range = st.selectbox(
                "기간",
                options=["all", "1month", "3months", "6months", "1year"],
                format_func=lambda x: {
                    "all": "전체 기간",
                    "1month": "최근 1개월",
                    "3months": "최근 3개월",
                    "6months": "최근 6개월",
                    "1year": "최근 1년"
                }[x],
                key=f"date_{channel_id}"
            )

    # 필터 적용
    filtered_videos = apply_video_filters(videos, sort_by, filter_keyword, date_range)

    st.write(f"📋 필터 적용 후: {len(filtered_videos)}개")

    # ═══════════════════════════════════════════════════════
    # 전체 선택/해제 버튼
    # ═══════════════════════════════════════════════════════
    col1, col2, col3 = st.columns([1, 1, 2])

    with col1:
        if st.button("✅ 전체 선택", key=f"select_all_{channel_id}"):
            for i in range(len(filtered_videos)):
                st.session_state[f"video_sel_{channel_id}_{i}"] = True
            st.rerun()

    with col2:
        if st.button("❎ 전체 해제", key=f"deselect_all_{channel_id}"):
            for i in range(len(filtered_videos)):
                st.session_state[f"video_sel_{channel_id}_{i}"] = False
            st.rerun()

    # 선택된 영상 수 계산
    selected_count = sum(
        1 for i in range(len(filtered_videos))
        if st.session_state.get(f"video_sel_{channel_id}_{i}", True)
    )

    with col3:
        st.markdown(f"**선택됨: {selected_count}개** / {len(filtered_videos)}개")

    st.divider()

    # ═══════════════════════════════════════════════════════
    # 영상 목록 (페이지네이션)
    # ═══════════════════════════════════════════════════════
    videos_per_page = 50
    total_pages = max(1, (len(filtered_videos) - 1) // videos_per_page + 1)

    if total_pages > 1:
        current_page = st.selectbox(
            "페이지",
            options=list(range(1, total_pages + 1)),
            format_func=lambda x: f"페이지 {x}/{total_pages}",
            key=f"page_{channel_id}"
        )
    else:
        current_page = 1

    start_idx = (current_page - 1) * videos_per_page
    end_idx = min(start_idx + videos_per_page, len(filtered_videos))
    page_videos = filtered_videos[start_idx:end_idx]

    # 영상 목록 테이블
    for i, video in enumerate(page_videos):
        idx = start_idx + i
        cols = st.columns([0.5, 4, 1.5, 1.5])

        with cols[0]:
            is_selected = st.checkbox(
                label="선택",
                value=st.session_state.get(f"video_sel_{channel_id}_{idx}", True),
                key=f"video_sel_{channel_id}_{idx}",
                label_visibility="collapsed"
            )

        with cols[1]:
            title = video.get("title", "제목 없음")
            display_title = title[:55] + "..." if len(title) > 55 else title
            if is_selected:
                st.markdown(f"**{display_title}**")
            else:
                st.caption(display_title)

        with cols[2]:
            published = video.get("published_at", "")[:10]
            st.caption(published)

        with cols[3]:
            views = video.get("view_count", 0)
            if views >= 1000000:
                st.caption(f"{views/1000000:.1f}M")
            elif views >= 1000:
                st.caption(f"{views/1000:.1f}K")
            elif views > 0:
                st.caption(str(views))
            else:
                st.caption("-")

    # 선택된 영상 목록 반환
    selected_videos = [
        filtered_videos[i] for i in range(len(filtered_videos))
        if st.session_state.get(f"video_sel_{channel_id}_{i}", True)
    ]

    return selected_videos


def apply_video_filters(videos: list, sort_by: str, keyword: str, date_range: str) -> list:
    """영상 필터 적용"""
    from datetime import timedelta

    filtered = videos.copy()

    # 키워드 필터
    if keyword:
        keyword_lower = keyword.lower()
        filtered = [v for v in filtered if keyword_lower in v.get("title", "").lower()]

    # 기간 필터
    if date_range != "all":
        days_map = {"1month": 30, "3months": 90, "6months": 180, "1year": 365}
        days = days_map.get(date_range, 0)

        if days > 0:
            cutoff = datetime.now() - timedelta(days=days)
            cutoff_str = cutoff.isoformat()
            filtered = [v for v in filtered if v.get("published_at", "") >= cutoff_str]

    # 정렬
    if sort_by == "latest":
        filtered.sort(key=lambda x: x.get("published_at", ""), reverse=True)
    elif sort_by == "oldest":
        filtered.sort(key=lambda x: x.get("published_at", ""))
    elif sort_by == "popular":
        filtered.sort(key=lambda x: x.get("view_count", 0), reverse=True)

    return filtered


def apply_global_video_filters(
    videos: list,
    sort_by: str = "latest",
    period: str = "all",
    max_count: int = None,
    min_views: int = 0,
    keyword: str = ""
) -> list:
    """
    글로벌 필터 적용 (전체 다운로드 모드에서 사용)

    Args:
        videos: 영상 목록
        sort_by: 정렬 기준 (latest, oldest, popular, unpopular)
        period: 기간 필터 (all, 1week, 1month, 3months, 6months, 1year)
        max_count: 최대 영상 수 (None이면 제한 없음)
        min_views: 최소 조회수
        keyword: 제목 키워드 필터

    Returns:
        필터링된 영상 목록
    """
    from datetime import timedelta

    if not videos:
        return []

    filtered = videos.copy()

    # 1. 키워드 필터
    if keyword and keyword.strip():
        keyword_lower = keyword.lower().strip()
        filtered = [v for v in filtered if keyword_lower in v.get("title", "").lower()]

    # 2. 기간 필터
    if period != "all":
        days_map = {
            "1week": 7,
            "1month": 30,
            "3months": 90,
            "6months": 180,
            "1year": 365
        }
        days = days_map.get(period, 0)

        if days > 0:
            cutoff = datetime.now() - timedelta(days=days)
            cutoff_str = cutoff.isoformat()

            def is_within_period(v):
                pub_date = v.get("published_at", "")
                if not pub_date:
                    return True  # 날짜 없으면 포함
                return pub_date >= cutoff_str

            filtered = [v for v in filtered if is_within_period(v)]

    # 3. 최소 조회수 필터
    if min_views > 0:
        def has_min_views(v):
            views = v.get("view_count", 0)
            if isinstance(views, str):
                try:
                    views = int(views.replace(",", ""))
                except:
                    views = 0
            return views >= min_views

        filtered = [v for v in filtered if has_min_views(v)]

    # 4. 정렬
    if sort_by == "latest":
        filtered.sort(key=lambda x: x.get("published_at", ""), reverse=True)
    elif sort_by == "oldest":
        filtered.sort(key=lambda x: x.get("published_at", ""))
    elif sort_by == "popular":
        filtered.sort(key=lambda x: x.get("view_count", 0) if isinstance(x.get("view_count", 0), int) else 0, reverse=True)
    elif sort_by == "unpopular":
        filtered.sort(key=lambda x: x.get("view_count", 0) if isinstance(x.get("view_count", 0), int) else 0)

    # 5. 개수 제한
    if max_count is not None and isinstance(max_count, int) and max_count > 0:
        filtered = filtered[:max_count]

    return filtered


def render_transcript_queue():
    """트랜스크립트 다운로드 대기열 표시"""
    st.markdown("#### 📋 다운로드 대기열")

    queue = st.session_state.get("transcript_queue", [])

    if not queue:
        st.info("대기열이 비어 있습니다. '채널 검색' 탭에서 채널을 추가하세요.")
        return

    for i, item in enumerate(queue):
        col1, col2, col3 = st.columns([3, 1, 1])

        with col1:
            st.markdown(f"**{i+1}. {item['channel_name']}**")
            st.caption(f"영상 수: {item.get('video_count', 'N/A')}")

        with col2:
            st.caption(f"추가: {item['added_at'][:10]}")

        with col3:
            if st.button("❌", key=f"remove_queue_{i}", help="대기열에서 제거"):
                st.session_state["transcript_queue"].pop(i)
                st.rerun()

    # 전체 삭제
    if st.button("🗑️ 대기열 비우기", type="secondary"):
        st.session_state["transcript_queue"] = []
        st.rerun()


def run_transcript_download(
    queue: list,
    language: str,
    output_format: str,
    include_auto: bool,
    max_videos: int,
    delay: float,
    api_key: str
):
    """트랜스크립트 다운로드 실행"""
    st.markdown("---")
    st.markdown("### 📥 다운로드 진행 중...")

    total_channels = len(queue)
    overall_progress = st.progress(0)
    overall_status = st.empty()

    # 채널 검색기
    searcher = get_channel_searcher(api_key)

    # 트랜스크립트 다운로더
    downloader = get_transcript_downloader("data/transcripts")

    all_results = []
    total_stats = {
        "channels": 0,
        "videos_processed": 0,
        "success": 0,
        "no_captions": 0,
        "failed": 0,
        "total_words": 0
    }

    for ch_idx, channel_info in enumerate(queue):
        channel_name = channel_info["channel_name"]
        channel_id = channel_info["channel_id"]

        overall_status.markdown(f"**[{ch_idx+1}/{total_channels}]** 채널: {channel_name}")

        # 영상 목록 가져오기
        st.caption(f"📋 '{channel_name}' 영상 목록 로딩 중...")
        try:
            videos = searcher.get_channel_videos(channel_id, max_results=max_videos)
        except Exception as e:
            st.error(f"영상 목록 로딩 실패: {e}")
            continue

        if not videos:
            st.warning(f"'{channel_name}' 채널에 영상이 없습니다.")
            continue

        st.caption(f"🎬 {len(videos)}개 영상 발견")

        # 진행률 표시
        channel_progress = st.progress(0)
        channel_status = st.empty()

        def progress_callback(progress: DownloadProgress):
            pct = progress.completed / progress.total if progress.total > 0 else 0
            channel_progress.progress(pct)
            channel_status.caption(
                f"📥 {progress.completed}/{progress.total} | "
                f"✅ {progress.success} | ❌ {progress.no_captions} | "
                f"현재: {progress.current_video[:30]}..."
            )

        # 다운로드 실행
        results, stats = downloader.download_batch(
            videos=videos,
            language=language,
            include_auto_generated=include_auto,
            delay=delay,
            progress_callback=progress_callback
        )

        # 결과 저장
        if results:
            saved_path = downloader.save_results(
                results=results,
                channel_name=channel_name,
                output_format=output_format
            )
            st.success(f"✅ '{channel_name}' 저장 완료: {saved_path}")

        # 통계 업데이트
        total_stats["channels"] += 1
        total_stats["videos_processed"] += stats.get("total", 0)
        total_stats["success"] += stats.get("success", 0)
        total_stats["no_captions"] += stats.get("no_captions", 0)
        total_stats["failed"] += stats.get("failed", 0)
        total_stats["total_words"] += stats.get("total_words", 0)

        all_results.extend(results)

        # 전체 진행률 업데이트
        overall_progress.progress((ch_idx + 1) / total_channels)

    # 완료 메시지
    st.markdown("---")
    st.markdown(f"""
    <div class="download-complete">
        <h3>✅ 다운로드 완료!</h3>
        <p>
            📺 처리된 채널: {total_stats['channels']}개<br>
            🎬 처리된 영상: {total_stats['videos_processed']}개<br>
            ✅ 성공: {total_stats['success']}개<br>
            ❌ 자막 없음: {total_stats['no_captions']}개<br>
            ⚠️ 실패: {total_stats['failed']}개<br>
            📝 총 단어 수: {total_stats['total_words']:,}개
        </p>
    </div>
    """, unsafe_allow_html=True)

    # 대기열 비우기
    st.session_state["transcript_queue"] = []


def run_transcript_download_v2(
    queue: list,
    language: str,
    output_formats: list,  # ⭐ v4.4: 다중 형식 리스트
    include_auto: bool,
    max_videos: int,
    delay: float,
    batch_size: int,
    batch_delay: float,
    download_method: str,  # ⭐ 다운로드 방식 추가
    api_key: str,
    selection_mode: str,
    selected_videos_by_channel: dict,
    global_filter_options: dict = None  # ✅ 글로벌 필터 옵션 추가
):
    """트랜스크립트 다운로드 실행 (하이브리드 버전 + 다중 형식 지원)"""
    st.markdown("---")
    st.markdown("### 📊 다운로드 진행 중...")

    # 프로그레스 UI
    overall_progress = st.progress(0)

    status_cols = st.columns(4)
    total_metric = status_cols[0].empty()
    success_metric = status_cols[1].empty()
    no_caption_metric = status_cols[2].empty()
    failed_metric = status_cols[3].empty()

    current_status = st.empty()
    log_expander = st.expander("📋 상세 로그", expanded=False)
    log_area = log_expander.empty()

    logs = []
    output_files = []

    searcher = get_channel_searcher(api_key)
    downloader = get_transcript_downloader("data/transcripts")

    # ⭐ 다운로드 방식 변환
    method_map = {
        "auto": DownloadMethod.AUTO,
        "api": DownloadMethod.API,
        "yt-dlp": DownloadMethod.YTDLP
    }
    method = method_map.get(download_method, DownloadMethod.AUTO)

    # 방식 표시
    method_name = {"auto": "자동", "api": "API", "yt-dlp": "yt-dlp"}.get(download_method, download_method)
    logs.append(f"[설정] 다운로드 방식: {method_name}")

    # ✅ 글로벌 필터 옵션 표시
    if global_filter_options:
        filter_info = []
        if global_filter_options.get("sort_by") and global_filter_options["sort_by"] != "latest":
            filter_info.append(f"정렬: {global_filter_options['sort_by']}")
        if global_filter_options.get("period") and global_filter_options["period"] != "all":
            filter_info.append(f"기간: {global_filter_options['period']}")
        if global_filter_options.get("max_count"):
            filter_info.append(f"개수: {global_filter_options['max_count']}개")
        if global_filter_options.get("min_views") and global_filter_options["min_views"] > 0:
            filter_info.append(f"최소조회수: {global_filter_options['min_views']}")
        if global_filter_options.get("keyword"):
            filter_info.append(f"키워드: {global_filter_options['keyword']}")

        if filter_info:
            logs.append(f"[설정] 필터: {', '.join(filter_info)}")

    total_videos_to_download = 0
    videos_downloaded = 0
    total_success = 0
    total_no_caption = 0
    total_failed = 0
    method_api_count = 0
    method_ytdlp_count = 0

    # 먼저 총 다운로드 영상 수 계산
    for channel in queue:
        cid = channel["channel_id"]
        if selection_mode == "manual" and selected_videos_by_channel.get(cid):
            total_videos_to_download += len(selected_videos_by_channel[cid])
        else:
            total_videos_to_download += min(channel.get("video_count", 0), max_videos)

    total_metric.metric("📊 총 영상", f"0/{total_videos_to_download}")
    success_metric.metric("✅ 성공", 0)
    no_caption_metric.metric("⚠️ 자막없음", 0)
    failed_metric.metric("❌ 실패", 0)

    # 채널별 다운로드
    for ch_idx, channel in enumerate(queue):
        channel_name = channel["channel_name"]
        channel_id = channel["channel_id"]

        logs.append(f"[{channel_name}] 처리 시작...")
        log_area.code("\n".join(logs[-20:]))

        # 다운로드할 영상 목록 결정
        if selection_mode == "manual" and selected_videos_by_channel.get(channel_id):
            # 수동 선택된 영상
            videos_to_download = selected_videos_by_channel[channel_id]
            logs.append(f"[{channel_name}] 선택된 {len(videos_to_download)}개 영상 다운로드")

            # ✅ 수동 선택 모드에서도 글로벌 필터 적용 (정렬, 개수 제한)
            if global_filter_options:
                original_count = len(videos_to_download)
                videos_to_download = apply_global_video_filters(
                    videos=videos_to_download,
                    sort_by=global_filter_options.get("sort_by", "latest"),
                    period=global_filter_options.get("period", "all"),
                    max_count=global_filter_options.get("max_count"),
                    min_views=global_filter_options.get("min_views", 0),
                    keyword=global_filter_options.get("keyword", "")
                )
                if len(videos_to_download) != original_count:
                    logs.append(f"[{channel_name}] 필터 적용 후: {len(videos_to_download)}개")
        else:
            # 전체 다운로드 (최대 영상 수 제한 적용)
            logs.append(f"[{channel_name}] 영상 목록 조회 중...")
            log_area.code("\n".join(logs[-20:]))

            # 캐시된 영상 목록 확인
            cache_key = f"channel_videos_{channel_id}"
            if cache_key in st.session_state:
                videos_to_download = st.session_state[cache_key][:max_videos]
            else:
                videos_to_download = searcher.get_channel_videos(
                    channel_id=channel_id,
                    max_results=max_videos
                )
            logs.append(f"[{channel_name}] {len(videos_to_download)}개 영상 발견")

            # ✅ 글로벌 필터 적용
            if global_filter_options and videos_to_download:
                original_count = len(videos_to_download)
                videos_to_download = apply_global_video_filters(
                    videos=videos_to_download,
                    sort_by=global_filter_options.get("sort_by", "latest"),
                    period=global_filter_options.get("period", "all"),
                    max_count=global_filter_options.get("max_count"),
                    min_views=global_filter_options.get("min_views", 0),
                    keyword=global_filter_options.get("keyword", "")
                )
                if len(videos_to_download) != original_count:
                    logs.append(f"[{channel_name}] 필터 적용 후: {original_count} → {len(videos_to_download)}개")

        if not videos_to_download:
            logs.append(f"[{channel_name}] ⚠️ 다운로드할 영상이 없습니다.")
            log_area.code("\n".join(logs[-20:]))
            continue

        # 영상별 다운로드
        channel_results = []

        for vid_idx, video in enumerate(videos_to_download):
            video_id = video.get("video_id")
            video_title = video.get("title", video_id)

            current_status.text(f"📺 [{channel_name}] {video_title[:50]}...")

            # ⭐ 다운로드 실행 (하이브리드 방식)
            result = downloader.download_single(
                video_id=video_id,
                video_title=video_title,
                language=language,
                include_auto_generated=include_auto,
                method=method  # ⭐ 선택한 방식 전달
            )

            channel_results.append(result)
            videos_downloaded += 1

            # 통계 업데이트
            if result.success:
                total_success += 1
            elif result.error_type == "no_caption" or "자막" in result.error:
                total_no_caption += 1
            elif result.error_type == "rate_limit":
                total_failed += 1
                logs.append(f"⚠️ Rate Limit 감지: {video_title[:30]}...")
                log_area.code("\n".join(logs[-20:]))

                # ⭐ 글로벌 Rate Limit 초과 시 조기 종료
                if "글로벌 Rate Limit 초과" in result.error or result.method_used == "blocked":
                    logs.append("🚨 글로벌 Rate Limit 초과! 다운로드 중단...")
                    logs.append("💡 쿠키 파일(data/cookies.txt) 설정을 권장합니다.")
                    log_area.code("\n".join(logs[-20:]))
                    st.warning("""
                    ### 🚨 Rate Limit 초과

                    YouTube가 너무 많은 요청을 차단했습니다.

                    **해결 방법:**
                    1. **쿠키 파일 설정** (권장): 시스템 상태에서 가이드 확인
                    2. **5분 후 재시도**: 잠시 후 다시 시도하세요
                    3. **yt-dlp 모드 사용**: 다운로드 방식을 'yt-dlp'로 변경

                    쿠키 파일 경로: `data/cookies.txt`
                    """)
                    break  # 현재 채널 다운로드 중단
            else:
                total_failed += 1

            # ⭐ 방식별 카운트
            if result.method_used == "api":
                method_api_count += 1
            elif result.method_used == "yt-dlp":
                method_ytdlp_count += 1

            # UI 업데이트
            progress = videos_downloaded / total_videos_to_download if total_videos_to_download > 0 else 0
            overall_progress.progress(progress)

            total_metric.metric("📊 총 영상", f"{videos_downloaded}/{total_videos_to_download}")
            success_metric.metric("✅ 성공", total_success)
            no_caption_metric.metric("⚠️ 자막없음", total_no_caption)
            failed_metric.metric("❌ 실패", total_failed)

            # 로그 (10개마다)
            if (vid_idx + 1) % 10 == 0:
                logs.append(f"[{channel_name}] {vid_idx+1}/{len(videos_to_download)} 완료")
                log_area.code("\n".join(logs[-20:]))

            # ⭐ Rate limit 대기 (배치 처리 포함)
            if vid_idx < len(videos_to_download) - 1:  # 마지막이 아닌 경우
                time.sleep(delay)

                # 배치 대기 (N개마다 추가 대기)
                if (vid_idx + 1) % batch_size == 0:
                    logs.append(f"[{channel_name}] 배치 완료, {batch_delay}초 대기...")
                    log_area.code("\n".join(logs[-20:]))
                    current_status.text(f"⏳ Rate Limit 방지 대기 중... ({batch_delay}초)")
                    time.sleep(batch_delay)

        # ⭐ v4.5: 채널별 결과 저장 (개별 파일 + ZIP 지원)
        if channel_results:
            try:
                # 기본 파일 경로 생성
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                safe_channel = "".join(c for c in channel_name if c.isalnum() or c in (' ', '-', '_')).strip()[:50]

                # 성공한 결과만 추출
                successful_results = [r for r in channel_results if r.success and r.transcript]

                if successful_results:
                    # ⭐ 개별 파일들을 담을 딕셔너리 (형식별로 구분)
                    individual_files = {fmt: [] for fmt in output_formats}

                    # 각 영상별로 개별 파일 생성
                    for result in successful_results:
                        video_id = result.video_id
                        video_title = result.video_title or video_id

                        # 안전한 파일명 생성
                        safe_title = "".join(c for c in video_title if c.isalnum() or c in (' ', '-', '_', '(', ')')).strip()[:50]
                        base_filename = f"{safe_channel}_{safe_title}_{video_id}"

                        # 각 형식별로 개별 파일 내용 생성
                        for fmt in output_formats:
                            if fmt == 'json':
                                # JSON 형식
                                content = json.dumps({
                                    "video_id": video_id,
                                    "video_title": video_title,
                                    "channel_name": channel_name,
                                    "transcript": result.transcript,
                                    "language": result.language,
                                    "downloaded_at": datetime.now().isoformat()
                                }, ensure_ascii=False, indent=2)
                            else:
                                # SRT/VTT/TXT 형식
                                content = TranscriptFormatter.convert(result.transcript, fmt)

                            individual_files[fmt].append({
                                "filename": f"{base_filename}.{fmt}",
                                "content": content
                            })

                    # ⭐ ZIP 파일 생성 (형식별로)
                    for fmt in output_formats:
                        if individual_files[fmt]:
                            zip_path = f"data/transcripts/{safe_channel}_{timestamp}_{fmt.upper()}.zip"

                            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                                for file_info in individual_files[fmt]:
                                    zf.writestr(file_info["filename"], file_info["content"])

                            output_files.append(zip_path)

                    logs.append(f"[{channel_name}] ✅ {len(successful_results)}개 영상 저장 (개별 파일 ZIP)")
                else:
                    logs.append(f"[{channel_name}] ⚠️ 저장할 성공 결과 없음")

            except Exception as e:
                logs.append(f"[{channel_name}] ❌ 저장 실패: {e}")

        logs.append(f"[{channel_name}] 완료!")
        log_area.code("\n".join(logs[-20:]))

    # 완료
    overall_progress.progress(1.0)
    current_status.empty()

    st.divider()

    # 결과 요약
    method_summary = f"API {method_api_count}개, yt-dlp {method_ytdlp_count}개" if (method_api_count + method_ytdlp_count) > 0 else "N/A"
    formats_summary = ', '.join(f.upper() for f in output_formats)

    st.success(f"""
    ### ✅ 다운로드 완료!

    - 📺 처리된 채널: {len(queue)}개
    - 📺 처리된 영상: {videos_downloaded}개
    - ✅ 성공: {total_success}개
    - ⚠️ 자막 없음: {total_no_caption}개
    - ❌ 실패: {total_failed}개
    - 📡 방식: {method_summary}
    - 📁 형식: {formats_summary}
    """)

    # ⭐ v4.5: 다운로드 결과를 session state에 저장 (페이지 리셋 방지)
    download_result = {
        "timestamp": datetime.now().isoformat(),
        "stats": {
            "channels": len(queue),
            "videos_downloaded": videos_downloaded,
            "success": total_success,
            "no_caption": total_no_caption,
            "failed": total_failed,
            "method_summary": method_summary,
            "formats_summary": formats_summary
        },
        "files": []
    }

    # 파일 데이터를 미리 로드하여 session state에 저장
    if output_files:
        for filepath in output_files:
            filename = os.path.basename(filepath)
            try:
                with open(filepath, "rb") as f:
                    file_data = f.read()
                download_result["files"].append({
                    "filename": filename,
                    "filepath": filepath,
                    "data": file_data
                })
            except Exception as e:
                download_result["files"].append({
                    "filename": filename,
                    "filepath": filepath,
                    "data": None,
                    "error": str(e)
                })

    st.session_state["transcript_download_results"] = download_result

    # 다운로드 파일 목록 표시
    _render_download_results(download_result)

    # 대기열 비우기 (결과는 session state에 유지)
    st.session_state["transcript_queue"] = []


def _render_download_results(result: dict):
    """다운로드 결과 표시 (session state에서 호출)"""
    if not result:
        return

    st.markdown("### 📁 저장된 파일")

    files = result.get("files", [])
    if not files:
        st.info("저장된 파일이 없습니다.")
        return

    for file_info in files:
        filename = file_info["filename"]
        file_data = file_info.get("data")

        if file_data:
            st.download_button(
                label=f"📥 {filename}",
                data=file_data,
                file_name=filename,
                mime="application/zip" if filename.endswith('.zip') else "application/octet-stream",
                key=f"dl_{filename}_{result.get('timestamp', '')}"
            )
        else:
            error = file_info.get("error", "알 수 없는 오류")
            st.caption(f"📄 {filename} (로드 실패: {error})")


def main():
    """메인 함수"""
    render_header()

    # API 키 확인
    api_key = get_api_key()

    if not api_key:
        st.error("⚠️ YouTube API 키가 설정되지 않았습니다.")

        # API 키 입력
        with st.expander("API 키 설정", expanded=True):
            input_key = st.text_input("YouTube API 키 입력", type="password")
            if st.button("저장"):
                if input_key:
                    st.session_state["youtube_api_key"] = input_key
                    st.success("API 키가 저장되었습니다!")
                    st.rerun()
        return

    # ═══════════════════════════════════════════════════════════════════════════════
    # 탭 구조
    # ═══════════════════════════════════════════════════════════════════════════════
    tab1, tab2, tab3 = st.tabs([
        "🔍 키워드 분석",
        "📺 채널 검색",
        "📥 트랜스크립트"
    ])

    # ═══════════════════════════════════════════════════════════════════════════════
    # Tab 1: 키워드 분석 (기존 기능)
    # ═══════════════════════════════════════════════════════════════════════════════
    with tab1:
        render_keyword_analysis_tab()

    # ═══════════════════════════════════════════════════════════════════════════════
    # Tab 2: 채널 검색
    # ═══════════════════════════════════════════════════════════════════════════════
    with tab2:
        render_channel_search_tab()

    # ═══════════════════════════════════════════════════════════════════════════════
    # Tab 3: 트랜스크립트 다운로드
    # ═══════════════════════════════════════════════════════════════════════════════
    with tab3:
        render_transcript_tab()


def render_keyword_analysis_tab():
    """키워드 분석 탭 (기존 기능)"""
    api_key = get_api_key()

    # 검색 폼
    keyword, region, months, max_videos, use_cache, expanded_keywords = render_search_form()

    st.markdown("---")

    # 분석 실행 버튼
    if st.button("🚀 트렌드 분석 시작", type="primary", use_container_width=True, disabled=not keyword):
        if not keyword:
            st.warning("키워드를 입력해주세요.")
            return

        # 분석 실행
        progress_text = st.empty()
        progress_bar = st.progress(0)

        def update_progress(msg):
            progress_text.text(msg)

        try:
            analyzer = create_channel_trend_analyzer(api_key=api_key)

            # ═══════════════════════════════════════════════════════
            # 확장 키워드를 포함한 분석
            # ═══════════════════════════════════════════════════════
            all_keywords = [keyword]
            if expanded_keywords:
                all_keywords.extend(expanded_keywords)
                all_keywords = list(set(all_keywords))  # 중복 제거

            # 확장 키워드가 있으면 각 키워드로 검색 후 통합
            all_results = []

            if len(all_keywords) > 1:
                progress_text.text(f"🔍 {len(all_keywords)}개 키워드로 확장 분석 중...")

                # 키워드당 영상 수 할당
                videos_per_keyword = max(20, max_videos // len(all_keywords))

                for i, kw in enumerate(all_keywords):
                    progress_bar.progress(int(20 + (i / len(all_keywords)) * 60))
                    progress_text.text(f"분석 중: {kw} ({i+1}/{len(all_keywords)})")

                    try:
                        partial_result = analyzer.analyze_channel_trend(
                            keyword=kw,
                            region=region,
                            months=months,
                            max_videos=videos_per_keyword,
                            use_cache=use_cache,
                            progress_callback=None  # 개별 진행 콜백 비활성화
                        )
                        all_results.append(partial_result)
                    except Exception as e:
                        print(f"[TrendAnalysis] 키워드 '{kw}' 분석 오류: {e}")
                        continue

                # 결과 통합
                if all_results:
                    result = _merge_trend_results(all_results, keyword, expanded_keywords)
                else:
                    result = analyzer.analyze_channel_trend(
                        keyword=keyword,
                        region=region,
                        months=months,
                        max_videos=max_videos,
                        use_cache=use_cache,
                        progress_callback=update_progress
                    )
            else:
                # 단일 키워드 분석
                progress_bar.progress(20)
                result = analyzer.analyze_channel_trend(
                    keyword=keyword,
                    region=region,
                    months=months,
                    max_videos=max_videos,
                    use_cache=use_cache,
                    progress_callback=update_progress
                )

            progress_bar.progress(100)
            progress_text.empty()

            # 사용된 키워드 정보 저장
            result.keywords_used = all_keywords if len(all_keywords) > 1 else [keyword]

            st.session_state["trend_result"] = result

        except Exception as e:
            st.error(f"분석 중 오류 발생: {e}")
            import traceback
            with st.expander("상세 오류"):
                st.code(traceback.format_exc())
            return

    # 결과 표시
    if "trend_result" in st.session_state:
        result = st.session_state["trend_result"]

        st.markdown("---")

        # 요약 메시지
        # 사용된 키워드 정보 확인
        keywords_used = getattr(result, 'keywords_used', [result.keyword])

        if len(keywords_used) > 1:
            st.success(f"""
            ✅ **확장 분석 완료!**
            **{len(keywords_used)}개 키워드**로 최근 {result.period_months}개월간 총 {result.total_videos_searched:,}개의 영상을 분석하여
            **{result.new_channels_count}개의 신규 채널**을 발견했습니다.
            """)
        else:
            st.success(f"""
            ✅ **분석 완료!**
            최근 {result.period_months}개월간 총 {result.total_videos_searched:,}개의 영상을 분석하여
            **{result.new_channels_count}개의 신규 채널**을 발견했습니다.
            """)

        # 사용된 키워드 표시 (확장 키워드가 있는 경우)
        if len(keywords_used) > 1:
            with st.expander(f"🔍 분석에 사용된 키워드 ({len(keywords_used)}개)", expanded=False):
                # 칩 형태로 표시
                keyword_html = " ".join([
                    f'<span style="background:#667eea20;color:#667eea;padding:4px 12px;border-radius:16px;margin:2px;display:inline-block;">{kw}</span>'
                    for kw in keywords_used
                ])
                st.markdown(keyword_html, unsafe_allow_html=True)

        # 키워드 관련성 분석에 사용된 변형 표시
        with st.expander("🔍 관련성 분석에 사용된 키워드 변형", expanded=False):
            # 분석기에서 키워드 변형 가져오기
            try:
                from core.youtube.channel_trend_analyzer import ChannelTrendAnalyzer
                temp_analyzer = ChannelTrendAnalyzer.__new__(ChannelTrendAnalyzer)
                variants = temp_analyzer._get_keyword_variants(result.keyword)
                st.caption(f"'{result.keyword}' 검색 시 다음 키워드들이 관련성 판단에 사용됩니다:")
                st.code(", ".join(variants[:20]))  # 상위 20개만 표시
                if len(variants) > 20:
                    st.caption(f"... 외 {len(variants) - 20}개 더")
            except:
                st.caption("키워드 변형 정보를 가져올 수 없습니다.")

        # 지표
        render_metrics(result)

        st.markdown("---")

        # ⭐ 시장 기회 분석 (핵심 섹션!)
        render_market_opportunity(result)

        st.markdown("---")

        # 월별 트렌드
        render_monthly_trend(result)

        st.markdown("---")

        # 채널 리스트
        render_channel_list(result)

        st.markdown("---")

        # AI 인사이트
        render_ai_insight(result)

        st.markdown("---")

        # 다운로드
        render_download(result)


if __name__ == "__main__":
    main()
