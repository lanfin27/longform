# -*- coding: utf-8 -*-
"""
채널 트렌드 차트 모듈

문제점 해결:
1. X축 날짜 형식 수정 (시간 → 년-월)
2. Y축 정수로 표시 (소수점 제거)
3. 데이터 매핑 정확히 처리
"""

import plotly.graph_objects as go
from datetime import datetime
from typing import Dict, List, Optional


def create_monthly_channel_chart(
    monthly_data: Dict[str, int],
    title: str = "월별 신규 채널 생성 추이"
) -> go.Figure:
    """
    월별 신규 채널 생성 추이 차트

    Args:
        monthly_data: {"2024-10": 3, "2024-11": 5, "2024-12": 2}

    Returns:
        Plotly Figure 객체
    """

    if not monthly_data:
        # 빈 차트 반환
        fig = go.Figure()
        fig.add_annotation(
            text="데이터가 없습니다",
            xref="paper", yref="paper",
            x=0.5, y=0.5, showarrow=False,
            font=dict(size=16, color="gray")
        )
        fig.update_layout(
            title=title,
            height=300
        )
        return fig

    # 데이터 정렬 (날짜순)
    sorted_months = sorted(monthly_data.keys())

    # X축 레이블 변환 (2024-10 → 2024년 10월)
    x_labels = []
    for month in sorted_months:
        try:
            dt = datetime.strptime(month, "%Y-%m")
            x_labels.append(dt.strftime("%Y년 %m월"))
        except ValueError:
            # 파싱 실패시 원본 사용
            x_labels.append(month)

    # Y축 값 (정수)
    y_values = [monthly_data[m] for m in sorted_months]

    # 최대값 계산 (Y축 범위용)
    max_value = max(y_values) if y_values else 1

    # 차트 생성
    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=x_labels,
        y=y_values,
        marker_color='#667eea',
        text=y_values,  # 막대 위에 숫자 표시
        textposition='outside',
        textfont=dict(size=14, color='#333'),
        hovertemplate='%{x}<br>신규 채널: %{y}개<extra></extra>'
    ))

    # 레이아웃 설정
    fig.update_layout(
        title=dict(
            text=title,
            font=dict(size=18, color='#333')
        ) if title else None,
        xaxis=dict(
            title="",
            tickfont=dict(size=12),
            tickangle=-45 if len(x_labels) > 6 else 0,
            type='category'  # 카테고리로 설정 (시간 축 아님!)
        ),
        yaxis=dict(
            title="신규 채널 수",
            tickfont=dict(size=12),
            dtick=max(1, max_value // 5) if max_value > 5 else 1,  # 적절한 눈금 간격
            rangemode='tozero',
            tickformat='d',  # 정수 형식
            range=[0, max_value * 1.2]  # 상단 여백
        ),
        height=350,
        margin=dict(l=50, r=30, t=50 if title else 20, b=80),
        showlegend=False,
        plot_bgcolor='rgba(0,0,0,0)',
        paper_bgcolor='rgba(0,0,0,0)'
    )

    # 그리드 스타일
    fig.update_xaxes(showgrid=False)
    fig.update_yaxes(showgrid=True, gridwidth=1, gridcolor='rgba(0,0,0,0.1)')

    return fig


def create_opportunity_gauge(
    score: float,
    title: str = "기회 지수"
) -> go.Figure:
    """
    기회 지수 게이지 차트

    Args:
        score: 기회 지수 (0-100+)
    """

    # 색상 결정
    if score >= 100:
        color = "#FFD700"  # 황금
        level = "황금 기회!"
    elif score >= 50:
        color = "#2ecc71"  # 녹색
        level = "좋은 기회"
    elif score >= 10:
        color = "#f39c12"  # 주황
        level = "보통"
    else:
        color = "#e74c3c"  # 빨강
        level = "포화"

    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=min(score, 150),  # 최대 150으로 제한 (표시용)
        domain={'x': [0, 1], 'y': [0, 1]},
        title={'text': f"{title}<br><span style='font-size:14px;color:{color}'>{level}</span>"},
        number={'font': {'size': 40, 'color': color}},
        gauge={
            'axis': {'range': [0, 150], 'tickwidth': 1},
            'bar': {'color': color},
            'bgcolor': "white",
            'borderwidth': 2,
            'bordercolor': "gray",
            'steps': [
                {'range': [0, 10], 'color': '#ffebee'},
                {'range': [10, 50], 'color': '#fff3e0'},
                {'range': [50, 100], 'color': '#e8f5e9'},
                {'range': [100, 150], 'color': '#fffde7'}
            ],
            'threshold': {
                'line': {'color': "red", 'width': 4},
                'thickness': 0.75,
                'value': score
            }
        }
    ))

    fig.update_layout(
        height=250,
        margin=dict(l=20, r=20, t=50, b=20)
    )

    return fig


def create_competition_vs_demand_chart(
    supply_score: float,
    demand_score: float
) -> go.Figure:
    """
    경쟁 강도 vs 수요 비교 차트
    """

    categories = ['경쟁 강도<br>(낮을수록 좋음)', '수요 지수<br>(높을수록 좋음)']
    values = [supply_score, demand_score]
    colors = ['#e74c3c', '#2ecc71']

    fig = go.Figure()

    fig.add_trace(go.Bar(
        x=categories,
        y=values,
        marker_color=colors,
        text=[f'{v:.1f}' for v in values],
        textposition='outside',
        textfont=dict(size=16, color='#333')
    ))

    fig.update_layout(
        title="경쟁 vs 수요 분석",
        xaxis=dict(title=""),
        yaxis=dict(
            title="점수",
            rangemode='tozero',
            tickformat='d'
        ),
        height=300,
        showlegend=False
    )

    return fig


def create_keyword_distribution_chart(
    keywords_used: List[str],
    keyword_stats: Optional[Dict[str, int]] = None
) -> go.Figure:
    """
    사용된 키워드 분포 차트

    Args:
        keywords_used: 사용된 키워드 목록
        keyword_stats: 키워드별 검색 결과 수 (옵션)
    """

    if not keywords_used:
        fig = go.Figure()
        fig.add_annotation(text="키워드 데이터 없음", x=0.5, y=0.5, showarrow=False)
        return fig

    if keyword_stats:
        # 키워드별 통계가 있으면 막대 그래프
        sorted_keywords = sorted(keyword_stats.items(), key=lambda x: x[1], reverse=True)[:15]
        labels = [k for k, v in sorted_keywords]
        values = [v for k, v in sorted_keywords]

        fig = go.Figure()
        fig.add_trace(go.Bar(
            y=labels,
            x=values,
            orientation='h',
            marker_color='#667eea',
            text=values,
            textposition='outside'
        ))

        fig.update_layout(
            title="키워드별 검색 결과",
            xaxis=dict(title="결과 수"),
            yaxis=dict(title="", autorange="reversed"),
            height=400,
            margin=dict(l=150)
        )
    else:
        # 통계가 없으면 카테고리별 개수
        category_counts = {}
        for kw in keywords_used:
            # 카테고리 추정 (간단한 휴리스틱)
            if any(x in kw for x in ["추천", "방법", "비교", "후기"]):
                cat = "직접 관련"
            elif any(x in kw for x in ["시작", "초보", "가이드"]):
                cat = "롱테일"
            else:
                cat = "관련 주제"
            category_counts[cat] = category_counts.get(cat, 0) + 1

        labels = list(category_counts.keys())
        values = list(category_counts.values())

        fig = go.Figure(data=[go.Pie(
            labels=labels,
            values=values,
            hole=0.4,
            marker_colors=['#667eea', '#764ba2', '#f39c12']
        )])

        fig.update_layout(
            title=f"분석 키워드 분포 (총 {len(keywords_used)}개)",
            height=300
        )

    return fig


def get_trend_interpretation(monthly_data: Dict[str, int]) -> str:
    """
    월별 트렌드 해석 문구 생성

    Args:
        monthly_data: {"2024-10": 3, "2024-11": 5, "2024-12": 2}

    Returns:
        해석 문구
    """

    if not monthly_data:
        return "데이터가 부족하여 트렌드를 분석할 수 없습니다."

    sorted_months = sorted(monthly_data.keys())
    values = [monthly_data[m] for m in sorted_months]

    if len(values) < 2:
        return f"현재까지 {values[0]}개의 신규 채널이 생성되었습니다."

    # 최근 2개월과 이전 비교
    recent_avg = sum(values[-2:]) / 2
    total_avg = sum(values) / len(values)

    # 트렌드 판단
    if len(values) >= 3:
        older_avg = sum(values[:-2]) / max(1, len(values) - 2)

        if recent_avg > older_avg * 1.5:
            trend_icon = "📈"
            trend_text = "급증"
            advice = "경쟁이 심화되는 추세입니다. 차별화 전략이 필요합니다."
        elif recent_avg > older_avg * 1.2:
            trend_icon = "📈"
            trend_text = "증가"
            advice = "신규 채널이 늘어나고 있습니다. 시장 관심이 높아지고 있습니다."
        elif recent_avg < older_avg * 0.5:
            trend_icon = "📉"
            trend_text = "급감"
            advice = "신규 진입이 줄어들고 있습니다. 진입 기회가 있을 수 있습니다."
        elif recent_avg < older_avg * 0.8:
            trend_icon = "📉"
            trend_text = "감소"
            advice = "신규 채널 유입이 줄어드는 추세입니다."
        else:
            trend_icon = "➡️"
            trend_text = "유지"
            advice = "안정적인 시장 상태입니다."
    else:
        recent = values[-1]
        prev = values[-2]
        if recent > prev:
            trend_icon = "📈"
            trend_text = "증가"
            advice = f"이전 달 대비 신규 채널이 증가했습니다 ({prev}개 → {recent}개)."
        elif recent < prev:
            trend_icon = "📉"
            trend_text = "감소"
            advice = f"이전 달 대비 신규 채널이 감소했습니다 ({prev}개 → {recent}개)."
        else:
            trend_icon = "➡️"
            trend_text = "유지"
            advice = f"이전 달과 동일한 수준입니다 ({recent}개)."

    return f"{trend_icon} **트렌드: {trend_text}** - {advice}"
