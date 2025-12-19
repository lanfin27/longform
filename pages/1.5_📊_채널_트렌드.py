# -*- coding: utf-8 -*-
"""
채널 트렌드 분석 페이지

특정 키워드 분야의 신규 채널 탐지 및 시장 진입 강도 분석
"""
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
import time
import os
import sys

# 경로 설정
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.youtube.channel_trend_analyzer import (
    ChannelTrendAnalyzer,
    TrendAnalysisResult,
    create_channel_trend_analyzer
)

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

    col1, col2, col3 = st.columns([3, 1, 1])

    with col1:
        keyword = st.text_input(
            "키워드",
            placeholder="예: 일본 시니어 브이로그, 은퇴 후 이민",
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

    return keyword, region, months, max_videos, use_cache


def render_metrics(result: TrendAnalysisResult):
    """주요 지표 렌더링"""
    col1, col2, col3, col4 = st.columns(4)

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
        # 진입 강도 계산
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


def render_monthly_trend(result: TrendAnalysisResult):
    """월별 트렌드 차트"""
    st.markdown("### 📈 월별 신규 채널 생성 추이")

    if not result.monthly_trend:
        st.info("데이터가 없습니다.")
        return

    # 데이터 준비
    df = pd.DataFrame([
        {"월": month, "신규 채널 수": count}
        for month, count in result.monthly_trend.items()
    ])

    # 차트 생성
    fig = px.bar(
        df,
        x="월",
        y="신규 채널 수",
        color="신규 채널 수",
        color_continuous_scale="Blues",
        title=""
    )

    fig.update_layout(
        xaxis_title="",
        yaxis_title="채널 수",
        showlegend=False,
        height=300
    )

    st.plotly_chart(fig, use_container_width=True)

    # 트렌드 분석 메시지
    if len(result.monthly_trend) >= 2:
        months = list(result.monthly_trend.keys())
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

    # 정렬 옵션
    sort_option = st.selectbox(
        "정렬 기준",
        options=["created_at", "subscribers", "avg_views", "efficiency"],
        format_func=lambda x: {
            "created_at": "📅 최신순",
            "subscribers": "👥 구독자순",
            "avg_views": "👁️ 평균조회수순",
            "efficiency": "📈 성장효율순"
        }.get(x)
    )

    # 정렬
    channels = result.new_channels.copy()
    if sort_option == "subscribers":
        channels.sort(key=lambda x: x.subscribers, reverse=True)
    elif sort_option == "avg_views":
        channels.sort(key=lambda x: x.avg_views_per_video, reverse=True)
    elif sort_option == "efficiency":
        channels.sort(key=lambda x: x.subscribers_per_video, reverse=True)

    # 채널 카드 표시
    for i, channel in enumerate(channels[:20]):  # 최대 20개
        with st.container():
            col1, col2, col3, col4, col5 = st.columns([3, 1, 1, 1, 1])

            with col1:
                st.markdown(f"**[{channel.title}]({channel.channel_url})**")
                st.caption(f"📅 {channel.created_at} 생성 ({channel.days_since_creation}일 전)")

            with col2:
                st.metric("구독자", f"{channel.subscribers:,}")

            with col3:
                st.metric("영상", f"{channel.video_count}")

            with col4:
                st.metric("평균조회", f"{channel.avg_views_per_video:,.0f}")

            with col5:
                # 성장 배지
                badge_color = {
                    "🚀 급성장": "🟢",
                    "📈 양호": "🔵",
                    "➡️ 보통": "🟡",
                    "📉 저조": "🔴"
                }.get(channel.growth_rate, "⚪")
                st.markdown(f"{badge_color} {channel.growth_rate}")

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
            "영상당 구독자": round(ch.subscribers_per_video, 1),
            "성장 등급": ch.growth_rate
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

    # 검색 폼
    keyword, region, months, max_videos, use_cache = render_search_form()

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
        st.success(f"""
        ✅ **분석 완료!**
        최근 {result.period_months}개월간 총 {result.total_videos_searched:,}개의 영상을 분석하여
        **{result.new_channels_count}개의 신규 채널**을 발견했습니다.
        """)

        # 지표
        render_metrics(result)

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
