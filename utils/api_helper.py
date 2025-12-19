"""
API 키 관련 유틸리티

API 키 상태 확인, 설정 가이드 표시
"""
import streamlit as st
from pathlib import Path
from typing import List

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.settings import (
    ROOT_DIR,
    ENV_PATH,
    check_api_keys,
    get_missing_keys,
    is_env_file_exists,
    YOUTUBE_API_KEY,
    ANTHROPIC_API_KEY,
    TOGETHER_API_KEY,
    GEMINI_API_KEY
)


# 페이지별 필요한 API 키 매핑
PAGE_REQUIRED_KEYS = {
    "video_research": ["YOUTUBE_API_KEY"],
    "script_generation": ["ANTHROPIC_API_KEY"],
    "tts_generation": [],  # Edge TTS는 API 키 불필요
    "image_prompt": ["ANTHROPIC_API_KEY"],
    "image_generation": ["TOGETHER_API_KEY"],
    "keyword_research": ["GEMINI_API_KEY"],  # 선택적
}


def show_api_key_setup_guide(missing_keys: List[str] = None):
    """
    API 키 설정 가이드 표시

    Args:
        missing_keys: 누락된 키 목록 (None이면 자동 감지)
    """
    if missing_keys is None:
        missing_keys = get_missing_keys()

    st.error("⚠️ API 키가 설정되지 않았습니다.")

    with st.expander("🔑 API 키 설정 방법", expanded=True):
        st.markdown(f"""
### 1단계: .env 파일 생성

프로젝트 폴더에 `.env` 파일을 생성하세요.

```
📁 {ROOT_DIR}
└── .env  ← 이 파일 생성
```

### 2단계: API 키 발급

| API | 발급 링크 | 용도 | 비용 |
|-----|----------|------|------|
| YouTube | [Google Cloud Console](https://console.cloud.google.com/) | 영상 검색 | 무료 (일 10,000 포인트) |
| Anthropic | [Anthropic Console](https://console.anthropic.com/) | 스크립트 생성 | 사용량 기반 |
| Together.ai | [Together.ai](https://api.together.ai/) | 이미지 생성 | $25 무료 크레딧 |
| Gemini | [Google AI Studio](https://aistudio.google.com/) | 키워드 분석 (선택) | 무료 |

### 3단계: .env 파일 작성

```env
YOUTUBE_API_KEY=AIza...your_youtube_key
ANTHROPIC_API_KEY=sk-ant-...your_anthropic_key
TOGETHER_API_KEY=...your_together_key
GEMINI_API_KEY=...your_gemini_key
```

### 4단계: 앱 재시작

`.env` 파일 저장 후 **앱을 재시작**하세요.
        """)

        # 현재 상태 표시
        st.divider()
        st.markdown("### 현재 API 키 상태")

        status = check_api_keys()
        for key, is_set in status.items():
            if is_set:
                st.success(f"✅ {key}: 설정됨")
            else:
                required = key in ["YOUTUBE_API_KEY", "ANTHROPIC_API_KEY", "TOGETHER_API_KEY"]
                if required:
                    st.error(f"❌ {key}: 미설정 (필수)")
                else:
                    st.warning(f"⚠️ {key}: 미설정 (선택)")


def check_page_api_keys(page_name: str) -> bool:
    """
    페이지에 필요한 API 키 확인

    Args:
        page_name: 페이지 이름 (PAGE_REQUIRED_KEYS의 키)

    Returns:
        필요한 모든 API 키가 설정되었으면 True
    """
    required_keys = PAGE_REQUIRED_KEYS.get(page_name, [])

    if not required_keys:
        return True

    missing = get_missing_keys(required_keys)
    return len(missing) == 0


def require_api_key(key_name: str, friendly_name: str = None) -> bool:
    """
    특정 API 키 필수 확인 및 안내

    Args:
        key_name: API 키 이름 (예: "YOUTUBE_API_KEY")
        friendly_name: 표시할 이름 (예: "YouTube API")

    Returns:
        API 키가 설정되었으면 True

    사용법:
        if not require_api_key("YOUTUBE_API_KEY", "YouTube API"):
            st.stop()
    """
    status = check_api_keys()
    friendly_name = friendly_name or key_name

    if not status.get(key_name, False):
        st.error(f"⚠️ {friendly_name} 키가 설정되지 않았습니다.")

        with st.expander("🔑 설정 방법"):
            _show_single_key_guide(key_name)

        return False

    return True


def _show_single_key_guide(key_name: str):
    """단일 API 키 설정 가이드"""
    guides = {
        "YOUTUBE_API_KEY": {
            "name": "YouTube Data API v3",
            "url": "https://console.cloud.google.com/",
            "steps": [
                "Google Cloud Console 접속",
                "새 프로젝트 생성 또는 기존 프로젝트 선택",
                "API 및 서비스 > 라이브러리 > 'YouTube Data API v3' 검색 후 사용 설정",
                "API 및 서비스 > 사용자 인증 정보 > API 키 만들기",
                "생성된 키를 .env 파일에 추가"
            ],
            "env_example": "YOUTUBE_API_KEY=AIzaSy..."
        },
        "ANTHROPIC_API_KEY": {
            "name": "Anthropic Claude API",
            "url": "https://console.anthropic.com/",
            "steps": [
                "Anthropic Console 접속 및 로그인",
                "API Keys 메뉴에서 새 키 생성",
                "생성된 키를 .env 파일에 추가"
            ],
            "env_example": "ANTHROPIC_API_KEY=sk-ant-..."
        },
        "TOGETHER_API_KEY": {
            "name": "Together.ai API",
            "url": "https://api.together.ai/",
            "steps": [
                "Together.ai 회원가입 ($25 무료 크레딧 제공)",
                "Settings > API Keys에서 키 생성",
                "생성된 키를 .env 파일에 추가"
            ],
            "env_example": "TOGETHER_API_KEY=..."
        },
        "GEMINI_API_KEY": {
            "name": "Google Gemini API",
            "url": "https://aistudio.google.com/",
            "steps": [
                "Google AI Studio 접속",
                "Get API Key 클릭",
                "생성된 키를 .env 파일에 추가"
            ],
            "env_example": "GEMINI_API_KEY=..."
        }
    }

    guide = guides.get(key_name, {})

    if guide:
        st.markdown(f"**{guide['name']}**")
        st.markdown(f"[🔗 발급 페이지]({guide['url']})")

        st.markdown("**설정 단계:**")
        for i, step in enumerate(guide["steps"], 1):
            st.markdown(f"{i}. {step}")

        st.code(guide["env_example"], language="env")


def show_api_status_sidebar():
    """
    사이드바에 API 키 상태 표시
    """
    with st.sidebar:
        with st.expander("🔑 API 상태"):
            status = check_api_keys()

            for key, is_set in status.items():
                short_name = key.replace("_API_KEY", "")
                if is_set:
                    st.caption(f"✅ {short_name}")
                else:
                    st.caption(f"❌ {short_name}")

            if not is_env_file_exists():
                st.warning("`.env` 파일 없음")


def get_api_key_display_status() -> dict:
    """
    API 키 상태를 사용자 친화적으로 반환

    Returns:
        {
            "youtube": {"status": "ok", "label": "YouTube", "message": "설정됨"},
            ...
        }
    """
    status = check_api_keys()

    result = {}
    key_info = {
        "YOUTUBE_API_KEY": ("youtube", "YouTube"),
        "ANTHROPIC_API_KEY": ("anthropic", "Anthropic"),
        "TOGETHER_API_KEY": ("together", "Together.ai"),
        "GEMINI_API_KEY": ("gemini", "Gemini"),
    }

    for key, (short, label) in key_info.items():
        is_set = status.get(key, False)
        result[short] = {
            "status": "ok" if is_set else "missing",
            "label": label,
            "message": "설정됨" if is_set else "미설정"
        }

    return result
