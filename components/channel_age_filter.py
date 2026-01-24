# -*- coding: utf-8 -*-
"""
components/channel_age_filter.py
채널 생성일 필터 UI 컴포넌트

프리셋 및 수동 입력으로 채널 나이 기준 필터링 제공

작성: 2025-01
"""

import streamlit as st
from datetime import datetime, timedelta
from typing import Dict, Optional

# dateutil이 없을 경우 대비
try:
    from dateutil.relativedelta import relativedelta
    DATEUTIL_AVAILABLE = True
except ImportError:
    DATEUTIL_AVAILABLE = False


# 프리셋 정의
CHANNEL_AGE_PRESETS = {
    "new_6m": {
        "label": "🌱 신생 채널 (6개월 이내)",
        "min_months": 0,
        "max_months": 6,
        "description": "최근 6개월 내 생성된 신규 채널"
    },
    "new_1y": {
        "label": "🌿 신생 채널 (1년 이내)",
        "min_months": 0,
        "max_months": 12,
        "description": "최근 1년 내 생성된 채널"
    },
    "growing_1_3y": {
        "label": "📈 성장 채널 (1-3년)",
        "min_months": 12,
        "max_months": 36,
        "description": "1년~3년 사이 생성된 성장 중인 채널"
    },
    "established_3y": {
        "label": "🏢 기존 채널 (3년 이상)",
        "min_months": 36,
        "max_months": None,
        "description": "3년 이상된 안정적인 채널"
    },
    "new_2y": {
        "label": "📊 2년 이내",
        "min_months": 0,
        "max_months": 24,
        "description": "최근 2년 내 생성된 채널"
    },
    "old_5y": {
        "label": "🏛️ 5년 이상",
        "min_months": 60,
        "max_months": None,
        "description": "5년 이상된 오래된 채널"
    }
}


def _months_ago(months: int) -> datetime:
    """N개월 전 날짜 계산"""
    if DATEUTIL_AVAILABLE:
        return datetime.now() - relativedelta(months=months)
    else:
        # dateutil 없을 경우 대략적 계산
        return datetime.now() - timedelta(days=months * 30)


def render_channel_age_filter(key_prefix: str = "channel_age") -> Dict:
    """
    채널 생성일 필터 UI 렌더링

    Args:
        key_prefix: 위젯 키 프리픽스

    Returns:
        {
            "enabled": bool,
            "min_date": datetime or None,  # 채널 최소 생성일 (이후 생성)
            "max_date": datetime or None,  # 채널 최대 생성일 (이전 생성)
            "preset": str or None
        }
    """
    st.markdown('<div class="section-header">📅 채널 생성일 필터</div>', unsafe_allow_html=True)

    # 필터 모드 선택
    filter_mode = st.radio(
        "필터 모드",
        options=["disabled", "preset", "manual"],
        format_func=lambda x: {
            "disabled": "비활성화",
            "preset": "📋 프리셋 선택",
            "manual": "✏️ 수동 입력"
        }[x],
        horizontal=True,
        key=f"{key_prefix}_mode"
    )

    result = {
        "enabled": filter_mode != "disabled",
        "min_date": None,
        "max_date": None,
        "preset": None
    }

    if filter_mode == "disabled":
        st.caption("채널 생성일 필터를 사용하지 않습니다.")
        return result

    if filter_mode == "preset":
        result = _render_preset_selection(key_prefix)

    elif filter_mode == "manual":
        result = _render_manual_input(key_prefix)

    # 필터 요약 표시
    if result["enabled"]:
        _render_filter_summary(result)

    return result


def _render_preset_selection(key_prefix: str) -> Dict:
    """프리셋 선택 UI"""
    st.caption("자주 사용하는 채널 나이 필터를 선택하세요.")

    # 프리셋 선택
    preset_options = list(CHANNEL_AGE_PRESETS.keys())

    # 기본값 설정
    default_preset = st.session_state.get(f"{key_prefix}_selected_preset", "new_1y")
    if default_preset not in preset_options:
        default_preset = "new_1y"

    # 프리셋 버튼 그리드
    cols = st.columns(3)

    for idx, preset_key in enumerate(preset_options):
        preset = CHANNEL_AGE_PRESETS[preset_key]
        col_idx = idx % 3

        with cols[col_idx]:
            is_selected = (default_preset == preset_key)
            btn_type = "primary" if is_selected else "secondary"

            if st.button(
                preset["label"],
                key=f"{key_prefix}_preset_{preset_key}",
                use_container_width=True,
                type=btn_type
            ):
                st.session_state[f"{key_prefix}_selected_preset"] = preset_key
                st.rerun()

    # 선택된 프리셋 정보
    selected_preset = st.session_state.get(f"{key_prefix}_selected_preset", "new_1y")
    preset = CHANNEL_AGE_PRESETS.get(selected_preset, CHANNEL_AGE_PRESETS["new_1y"])

    st.info(f"📌 **{preset['label']}**: {preset['description']}")

    # 날짜 계산
    now = datetime.now()
    min_date = None
    max_date = None

    max_months = preset.get("max_months")
    min_months = preset.get("min_months", 0)

    if max_months is not None:
        # 최대 나이 → 최소 생성일 (이 날짜 이후 생성된 채널)
        min_date = _months_ago(max_months)

    if min_months > 0:
        # 최소 나이 → 최대 생성일 (이 날짜 이전 생성된 채널)
        max_date = _months_ago(min_months)

    return {
        "enabled": True,
        "min_date": min_date,
        "max_date": max_date,
        "preset": selected_preset
    }


def _render_manual_input(key_prefix: str) -> Dict:
    """수동 입력 UI"""
    st.caption("채널 생성일 범위를 직접 설정하세요.")

    # 입력 방식 선택
    input_type = st.radio(
        "입력 방식",
        options=["date_range", "age_range"],
        format_func=lambda x: {
            "date_range": "📅 날짜 범위",
            "age_range": "⏳ 채널 나이"
        }[x],
        horizontal=True,
        key=f"{key_prefix}_input_type"
    )

    now = datetime.now()
    min_date = None
    max_date = None

    if input_type == "date_range":
        # 날짜 범위 입력
        col1, col2 = st.columns(2)

        with col1:
            min_date_input = st.date_input(
                "채널 생성일 (최소)",
                value=now.date() - timedelta(days=365 * 2),
                max_value=now.date(),
                key=f"{key_prefix}_min_date",
                help="이 날짜 이후 생성된 채널만"
            )
            if min_date_input:
                min_date = datetime.combine(min_date_input, datetime.min.time())

        with col2:
            max_date_input = st.date_input(
                "채널 생성일 (최대)",
                value=now.date(),
                max_value=now.date(),
                key=f"{key_prefix}_max_date",
                help="이 날짜 이전 생성된 채널만"
            )
            if max_date_input:
                max_date = datetime.combine(max_date_input, datetime.max.time())

    else:
        # 채널 나이 입력
        st.markdown("**최소 채널 나이** (이보다 오래된 채널)")
        col1, col2 = st.columns(2)

        with col1:
            min_age_years = st.number_input(
                "년",
                min_value=0,
                max_value=20,
                value=0,
                key=f"{key_prefix}_min_age_years"
            )
        with col2:
            min_age_months = st.number_input(
                "개월",
                min_value=0,
                max_value=11,
                value=0,
                key=f"{key_prefix}_min_age_months"
            )

        st.markdown("**최대 채널 나이** (이보다 젊은 채널)")
        col3, col4 = st.columns(2)

        with col3:
            max_age_years = st.number_input(
                "년",
                min_value=0,
                max_value=20,
                value=2,
                key=f"{key_prefix}_max_age_years"
            )
        with col4:
            max_age_months = st.number_input(
                "개월",
                min_value=0,
                max_value=11,
                value=0,
                key=f"{key_prefix}_max_age_months"
            )

        # 나이를 날짜로 변환
        total_min_months = min_age_years * 12 + min_age_months
        total_max_months = max_age_years * 12 + max_age_months

        if total_max_months > 0:
            # 최대 나이 → 최소 생성일
            min_date = _months_ago(total_max_months)

        if total_min_months > 0:
            # 최소 나이 → 최대 생성일
            max_date = _months_ago(total_min_months)

    return {
        "enabled": True,
        "min_date": min_date,
        "max_date": max_date,
        "preset": None
    }


def _render_filter_summary(filter_result: Dict):
    """필터 요약 표시"""
    min_date = filter_result.get("min_date")
    max_date = filter_result.get("max_date")

    summary_parts = []

    if min_date:
        summary_parts.append(f"**{min_date.strftime('%Y-%m-%d')}** 이후 생성")

    if max_date:
        summary_parts.append(f"**{max_date.strftime('%Y-%m-%d')}** 이전 생성")

    if summary_parts:
        st.success(f"📅 필터 적용: {' ~ '.join(summary_parts)}")


def get_channel_age_badge(published_at: datetime) -> Dict:
    """
    채널 생성일로부터 나이 배지 정보 반환

    Args:
        published_at: 채널 생성일

    Returns:
        {
            "age_str": "2년 3개월",
            "badge_text": "🌿 신생",
            "badge_color": "#10B981"
        }
    """
    now = datetime.now()

    if published_at.tzinfo:
        now = datetime.now(published_at.tzinfo)

    # 나이 계산
    if DATEUTIL_AVAILABLE:
        from dateutil.relativedelta import relativedelta
        age = relativedelta(now, published_at)
        years = age.years
        months = age.months
    else:
        # 대략적 계산
        diff = now - published_at
        total_months = diff.days // 30
        years = total_months // 12
        months = total_months % 12

    # 나이 문자열
    age_str = ""
    if years > 0:
        age_str += f"{years}년 "
    if months > 0:
        age_str += f"{months}개월"
    if not age_str:
        age_str = "1개월 미만"

    # 배지 결정
    if years < 1:
        badge_color = "#10B981"  # 초록 - 신생
        badge_text = "🌱 신생"
    elif years < 3:
        badge_color = "#3B82F6"  # 파랑 - 성장
        badge_text = "📈 성장"
    else:
        badge_color = "#6B7280"  # 회색 - 기존
        badge_text = "🏢 기존"

    return {
        "age_str": age_str.strip(),
        "badge_text": badge_text,
        "badge_color": badge_color,
        "years": years,
        "months": months
    }


def render_channel_age_badge_html(published_at: datetime) -> str:
    """채널 나이 배지 HTML 반환"""
    badge_info = get_channel_age_badge(published_at)

    return f"""
        <span style="
            display: inline-block;
            background: {badge_info['badge_color']};
            color: white;
            padding: 2px 8px;
            border-radius: 4px;
            font-size: 11px;
            margin-right: 8px;
        ">
            {badge_info['badge_text']} ({badge_info['age_str']})
        </span>
    """


# 내보내기
__all__ = [
    'render_channel_age_filter',
    'get_channel_age_badge',
    'render_channel_age_badge_html',
    'CHANNEL_AGE_PRESETS'
]
