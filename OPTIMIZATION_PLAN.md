# Longform 프로젝트 최적화 실행 계획

**프로젝트**: AI 롱폼 유튜브 생성 Tool
**작성 일시**: 2026-01-18
**총 예상 성능 개선**: 60-80%

---

## Phase 1: Quick Wins (즉시 적용 가능)

**예상 성능 개선: 35-45%**

| 순서 | 작업 | 대상 파일 | 구체적 변경 내용 | 예상 효과 |
|------|------|-----------|------------------|-----------|
| 1.1 | 데이터 로더 캐싱 | `utils/data_loader.py` | load_json, load_excel, load_text에 @st.cache_data 추가 | 15-20% |
| 1.2 | 프로젝트 설정 캐싱 | `utils/project_manager.py` | 채널/영상 설정 로드 함수 캐싱 | 5-10% |
| 1.3 | 이미지 바이트 저장 제거 | `utils/memory_manager.py` | 세션 상태에 경로만 저장 | 메모리 50% 절감 |
| 1.4 | 세션 정리 함수 호출 | `pages/6_🎨_이미지_생성.py` | 페이지 전환 시 cleanup_session_images() 자동 호출 | 메모리 누수 방지 |

### 항목 1.1: 데이터 로더 캐싱 추가

**현재 코드** (`utils/data_loader.py:45-78`):
```python
def load_json(filepath: Path) -> dict:
    """JSON 파일 로드"""
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

def load_excel(filepath: Path, sheet_name: str = None) -> pd.DataFrame:
    """Excel 파일 로드"""
    return pd.read_excel(filepath, sheet_name=sheet_name)

def load_text(filepath: Path) -> str:
    """텍스트 파일 로드"""
    return filepath.read_text(encoding='utf-8')
```

**개선 코드**:
```python
import streamlit as st
from pathlib import Path
import json
import pandas as pd

@st.cache_data(ttl=300, show_spinner=False, max_entries=100)
def load_json_cached(filepath_str: str, _mtime: float = None) -> dict:
    """JSON 파일 로드 (캐싱 적용)

    Args:
        filepath_str: 파일 경로 (문자열)
        _mtime: 파일 수정 시간 (캐시 무효화용, 언더스코어로 해시 제외)
    """
    filepath = Path(filepath_str)
    with open(filepath, 'r', encoding='utf-8') as f:
        return json.load(f)

@st.cache_data(ttl=300, show_spinner=False, max_entries=50)
def load_excel_cached(filepath_str: str, sheet_name: str = None, _mtime: float = None) -> pd.DataFrame:
    """Excel 파일 로드 (캐싱 적용)"""
    return pd.read_excel(filepath_str, sheet_name=sheet_name)

@st.cache_data(ttl=300, show_spinner=False, max_entries=100)
def load_text_cached(filepath_str: str, _mtime: float = None) -> str:
    """텍스트 파일 로드 (캐싱 적용)"""
    return Path(filepath_str).read_text(encoding='utf-8')

# 래퍼 함수 (기존 인터페이스 유지)
def load_json(filepath: Path) -> dict:
    """JSON 파일 로드 (자동 캐싱)"""
    mtime = filepath.stat().st_mtime if filepath.exists() else 0
    return load_json_cached(str(filepath), _mtime=mtime)

def load_excel(filepath: Path, sheet_name: str = None) -> pd.DataFrame:
    """Excel 파일 로드 (자동 캐싱)"""
    mtime = filepath.stat().st_mtime if filepath.exists() else 0
    return load_excel_cached(str(filepath), sheet_name, _mtime=mtime)

def load_text(filepath: Path) -> str:
    """텍스트 파일 로드 (자동 캐싱)"""
    mtime = filepath.stat().st_mtime if filepath.exists() else 0
    return load_text_cached(str(filepath), _mtime=mtime)
```

**적용 방법**:
1. `utils/data_loader.py` 상단에 `import streamlit as st` 추가
2. 기존 함수 위에 캐싱 버전 추가
3. 기존 함수를 래퍼로 변경 (하위 호환성 유지)

**주의사항**:
- Path 객체는 직렬화 불가 → 문자열로 변환 필수
- `_mtime` 파라미터는 언더스코어로 시작하여 해시에서 제외됨
- 파일 수정 시 자동으로 캐시 무효화

---

### 항목 1.2: 프로젝트 설정 캐싱

**현재 코드** (`utils/project_manager.py:100-102` 추정):
```python
def get_channel_config(channel_name: str) -> dict:
    config_path = CHANNELS_DIR / channel_name / "config.json"
    if config_path.exists():
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}
```

**개선 코드**:
```python
@st.cache_data(ttl=600, show_spinner=False)
def _get_channel_config_cached(channel_name: str, config_path_str: str, _mtime: float) -> dict:
    """채널 설정 로드 (캐싱 적용)"""
    with open(config_path_str, 'r', encoding='utf-8') as f:
        return json.load(f)

def get_channel_config(channel_name: str) -> dict:
    """채널 설정 로드 (자동 캐싱)"""
    config_path = CHANNELS_DIR / channel_name / "config.json"
    if config_path.exists():
        mtime = config_path.stat().st_mtime
        return _get_channel_config_cached(channel_name, str(config_path), _mtime=mtime)
    return {}
```

---

### 항목 1.3: 이미지 바이트 저장 제거

**현재 코드** (`utils/memory_manager.py:32-40`):
```python
IMAGE_SESSION_PATTERNS = [
    "composite_result_",      # 합성된 이미지 바이트
    "bg_result_",             # 배경 이미지 바이트
    "char_image_",            # 캐릭터 이미지 바이트
    # ...
]
```

**개선 코드**:
```python
# 이미지는 바이트 대신 경로만 저장
def save_composite_result(scene_id: str, image: Image.Image, output_path: Path) -> str:
    """합성 이미지 저장 후 경로 반환"""
    # 파일로 저장
    image.save(output_path, "PNG")

    # 세션에는 경로만 저장
    st.session_state[f"composite_path_{scene_id}"] = str(output_path)

    return str(output_path)

def get_composite_result(scene_id: str) -> Optional[Image.Image]:
    """합성 이미지 로드 (파일에서)"""
    path = st.session_state.get(f"composite_path_{scene_id}")
    if path and Path(path).exists():
        return Image.open(path)
    return None
```

---

### 항목 1.4: 세션 정리 함수 자동 호출

**추가 코드** (`pages/6_🎨_이미지_생성.py` 상단):
```python
from utils.memory_manager import cleanup_session_images, get_memory_usage

# 페이지 진입 시 메모리 체크
def check_and_cleanup_memory():
    """메모리 사용량 체크 및 필요시 정리"""
    usage = get_memory_usage()
    if usage.get('session_image_count', 0) > 100:  # 100개 이상 이미지
        cleanup_session_images(keep_recent=20)  # 최근 20개만 유지

# 페이지 상단에서 호출
check_and_cleanup_memory()
```

---

## Phase 2: 중요 개선사항

**예상 성능 개선: 20-30%**

| 순서 | 작업 | 대상 파일 | 구체적 변경 내용 | 예상 효과 |
|------|------|-----------|------------------|-----------|
| 2.1 | @st.fragment 도입 | `pages/2_🔍_영상_리서치.py` | 검색/필터/다운로드 섹션 분리 | 30-40% |
| 2.2 | 루프 내 위젯 최적화 | `pages/2_🔍_영상_리서치.py` | 페이지네이션 + lazy loading | 20-30% |
| 2.3 | 썸네일 캐싱 개선 | `utils/memory_manager.py` | st.cache_data로 변경 | 10-15% |
| 2.4 | 네트워크 I/O 캐싱 | `components/interactive_canvas.py` | 이미지 다운로드 캐싱 | 15-20% |

### 항목 2.1: @st.fragment 도입

**현재 코드** (`pages/2_🔍_영상_리서치.py`):
```python
# 전체 페이지가 단일 스크립트로 실행됨
tab1, tab2, tab3 = st.tabs(["검색", "보관함", "추천"])

with tab1:
    # 검색 폼
    # 필터/정렬
    # 결과 표시
    # 다운로드 버튼
```

**개선 코드**:
```python
import streamlit as st

# 검색 결과 섹션을 fragment로 분리
@st.fragment
def render_search_results_section(filtered_videos: list):
    """검색 결과 표시 - 독립적으로 리렌더링"""

    # 정렬 옵션
    sort_by = st.selectbox("정렬 기준", ["조회수", "좋아요", "날짜"])

    # 결과 표시
    for video in filtered_videos[:20]:  # 페이지당 20개
        render_video_card(video)

# 다운로드 버튼 섹션을 fragment로 분리
@st.fragment
def render_download_section(videos: list):
    """다운로드 버튼 영역 - 독립적으로 리렌더링"""

    if st.button("엑셀 생성"):
        excel_file = generate_excel(videos)
        st.download_button("다운로드", excel_file)

# 메인 페이지
def main():
    tab1, tab2, tab3 = st.tabs(["검색", "보관함", "추천"])

    with tab1:
        # 검색 폼 (fragment 아님 - 전체 페이지 영향)
        query = st.text_input("검색어")
        if st.button("검색"):
            videos = search_videos(query)
            st.session_state.search_results = videos

        # Fragment: 결과 표시 (독립 리렌더링)
        if "search_results" in st.session_state:
            render_search_results_section(st.session_state.search_results)
            render_download_section(st.session_state.search_results)
```

**적용 방법**:
1. Streamlit 1.33+ 확인 (`pip install streamlit>=1.33.0`)
2. 독립적으로 업데이트되는 섹션 식별
3. `@st.fragment` 데코레이터 적용
4. 상태 공유는 st.session_state 활용

---

### 항목 2.2: 루프 내 위젯 최적화

**현재 코드** (`pages/2_🔍_영상_리서치.py:1004-1054`):
```python
for video in page_videos:  # 30개
    with st.expander(f"{video.title}"):
        col1, col2 = st.columns([1, 2])
        with col1:
            st.image(video.thumbnail_url)  # 30회 이미지 로드
        with col2:
            metric_col1, metric_col2, metric_col3 = st.columns(3)
            with metric_col1:
                st.metric("조회수", video.views)
            # ... 더 많은 metric
```

**개선 코드**:
```python
# 방법 1: 페이지네이션 적용
ITEMS_PER_PAGE = 10

if "video_page" not in st.session_state:
    st.session_state.video_page = 0

total_pages = (len(page_videos) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE

# 페이지네이션 컨트롤
col_prev, col_info, col_next = st.columns([1, 2, 1])
with col_prev:
    if st.button("◀ 이전", disabled=st.session_state.video_page == 0):
        st.session_state.video_page -= 1
        st.rerun()
with col_info:
    st.write(f"페이지 {st.session_state.video_page + 1} / {total_pages}")
with col_next:
    if st.button("다음 ▶", disabled=st.session_state.video_page >= total_pages - 1):
        st.session_state.video_page += 1
        st.rerun()

# 현재 페이지 항목만 렌더링
start_idx = st.session_state.video_page * ITEMS_PER_PAGE
end_idx = start_idx + ITEMS_PER_PAGE
current_page_videos = page_videos[start_idx:end_idx]

for video in current_page_videos:  # 최대 10개만
    render_video_card(video)

# 방법 2: Lazy Loading (expander 내부 최적화)
def render_video_card(video):
    with st.expander(f"{video.title[:50]}..."):
        # 이미지는 expander 펼칠 때만 로드
        if st.session_state.get(f"show_thumb_{video.id}", False):
            st.image(video.thumbnail_url)
        else:
            if st.button("썸네일 보기", key=f"load_{video.id}"):
                st.session_state[f"show_thumb_{video.id}"] = True
                st.rerun()

        # 간단한 정보는 markdown으로 (metric 대신)
        st.markdown(f"""
        **조회수**: {video.views:,} | **좋아요**: {video.likes:,} | **댓글**: {video.comments:,}
        """)
```

---

### 항목 2.3: 썸네일 캐싱 개선

**현재 코드** (`utils/memory_manager.py:257-273`):
```python
# 캐시 확인 (세션 상태)
if cache_key and _HAS_STREAMLIT:
    cached = st.session_state.get(f"_thumb_{cache_key}")
    if cached:
        return cached

# 캐시 저장 (세션 상태)
if cache_key and _HAS_STREAMLIT:
    st.session_state[f"_thumb_{cache_key}"] = thumb_bytes
```

**개선 코드**:
```python
@st.cache_data(ttl=600, max_entries=200, show_spinner=False)
def get_thumbnail_cached(image_path: str, max_size: tuple = (200, 200)) -> Optional[bytes]:
    """
    썸네일 생성 및 캐싱 (st.cache_data 사용)

    세션 상태 대신 전역 캐시 사용으로:
    - 여러 세션 간 공유 가능
    - 자동 LRU 관리 (max_entries)
    - TTL 기반 자동 만료
    """
    try:
        from PIL import Image
        import io

        with Image.open(image_path) as img:
            img.thumbnail(max_size, Image.Resampling.LANCZOS)

            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=85)
            return buffer.getvalue()
    except Exception:
        return None

# 사용법
def get_thumbnail(image_path: str, max_size: tuple = (200, 200)) -> Optional[bytes]:
    """썸네일 가져오기 (캐싱 적용)"""
    return get_thumbnail_cached(image_path, max_size)
```

---

### 항목 2.4: 네트워크 I/O 캐싱

**현재 코드** (`components/interactive_canvas.py:641-665`):
```python
def load_image_from_url(url: str) -> Image.Image:
    response = requests.get(url, timeout=10)
    return Image.open(io.BytesIO(response.content))
```

**개선 코드**:
```python
import hashlib

@st.cache_data(ttl=3600, max_entries=100, show_spinner=False)
def _download_image_cached(url: str) -> Optional[bytes]:
    """URL에서 이미지 다운로드 (캐싱)"""
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        return response.content
    except Exception:
        return None

def load_image_from_url(url: str) -> Optional[Image.Image]:
    """URL에서 이미지 로드 (캐싱 적용)"""
    image_bytes = _download_image_cached(url)
    if image_bytes:
        return Image.open(io.BytesIO(image_bytes))
    return None
```

---

## Phase 3: 구조적 개선

**예상 성능 개선: 10-20%**

| 순서 | 작업 | 대상 파일 | 구체적 변경 내용 | 예상 효과 |
|------|------|-----------|------------------|-----------|
| 3.1 | Import 최적화 | `pages/6_🎨_이미지_생성.py` | 지연 로딩 패턴 적용 | 500ms 로드 시간 단축 |
| 3.2 | Import 최적화 | `pages/2_🔍_영상_리서치.py` | 탭별 동적 import | 200ms 단축 |
| 3.3 | 초기화 패턴 통일 | `pages/3_🎬_SRT_생성.py` | 중앙화된 init 함수 | 유지보수성 향상 |
| 3.4 | config.toml 추가 | `.streamlit/config.toml` | 최적화 설정 추가 | 안정성 향상 |

### 항목 3.1: pages/6 Import 최적화

**현재 코드** (`pages/6_🎨_이미지_생성.py:1-50`):
```python
import gc
import streamlit as st
from PIL import Image
import numpy as np
from selenium import webdriver
from utils.image_composer import ImageComposer
from utils.background_remover import remove_background
# ... 20개 이상의 import
```

**개선 코드**:
```python
import streamlit as st
import gc
from pathlib import Path
import sys

# 필수 import만 상단에
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from utils.project_manager import get_current_project, ensure_project_selected

# 지연 로드 헬퍼
_LAZY_IMPORTS = {}

def lazy_import(module_name: str, from_module: str = None):
    """지연 import 헬퍼"""
    key = f"{from_module}.{module_name}" if from_module else module_name
    if key not in _LAZY_IMPORTS:
        if from_module:
            mod = __import__(from_module, fromlist=[module_name])
            _LAZY_IMPORTS[key] = getattr(mod, module_name)
        else:
            _LAZY_IMPORTS[key] = __import__(module_name)
    return _LAZY_IMPORTS[key]

# 탭 진입 시에만 import
with tab_batch:
    # PIL은 이미지 배치 탭에서만 필요
    Image = lazy_import('Image', 'PIL')
    ImageComposer = lazy_import('ImageComposer', 'utils.image_composer')

    # 배치 이미지 생성 로직...

with tab_background:
    # 배경 제거는 배경 탭에서만 필요
    remove_background = lazy_import('remove_background', 'utils.background_remover')

    # 배경 제거 로직...
```

---

### 항목 3.2: pages/2 탭별 동적 Import

**현재 코드** (`pages/2_🔍_영상_리서치.py:175-182`):
```python
# 상단에서 모든 모듈 import
from utils.channel_identity import get_identity_manager, ChannelIdentity
from utils.topic_recommender import (
    get_topic_recommender,
    recommend_topics,
    VideoData,
    TopicRecommendation,
    RecommendationResult,
    check_api_availability
)
```

**개선 코드**:
```python
# 상단에서 제거하고 탭 내부로 이동

# "채널 정체성" 탭
with tab_identity:
    # 탭 진입 시에만 import
    from utils.channel_identity import get_identity_manager, ChannelIdentity

    identity_manager = get_identity_manager()
    # ... 채널 정체성 로직

# "AI 주제 추천" 탭
with tab_recommend:
    # 탭 진입 시에만 import
    from utils.topic_recommender import (
        get_topic_recommender,
        recommend_topics,
        VideoData,
        TopicRecommendation,
        RecommendationResult,
        check_api_availability
    )

    if check_api_availability():
        recommender = get_topic_recommender()
        # ... 추천 로직
```

---

### 항목 3.3: 초기화 패턴 통일

**현재 코드** (`pages/3_🎬_SRT_생성.py:80-102, 242-250`):
```python
# 분산된 초기화
if "whisper_srt_result" not in st.session_state:
    st.session_state.whisper_srt_result = None
if "ai_corrected_result" not in st.session_state:
    st.session_state.ai_corrected_result = None
# ... 여러 위치에 분산

# 라인 242
if "vad_threshold" not in st.session_state:
    st.session_state.vad_threshold = 0.5
```

**개선 코드**:
```python
def init_srt_page_state():
    """
    SRT 생성 페이지 세션 상태 초기화

    모든 초기화를 한 곳에서 관리하여:
    - 누락 방지
    - 기본값 일괄 확인
    - 디버깅 용이
    """
    defaults = {
        # Whisper 결과
        "whisper_srt_result": None,
        "ai_corrected_result": None,
        "original_script": None,
        "original_scenes_backup": None,

        # VAD 설정
        "vad_threshold": 0.5,
        "vad_min_speech_duration_ms": 250,
        "vad_max_speech_duration_s": 30.0,

        # UI 상태
        "srt_current_tab": 0,
        "srt_edit_mode": False,
    }

    for key, default_value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default_value

# 페이지 최상단에서 한 번만 호출
init_srt_page_state()
```

---

### 항목 3.4: .streamlit/config.toml 추가

**새 파일** (`.streamlit/config.toml`):
```toml
[theme]
primaryColor = "#667eea"
backgroundColor = "#ffffff"
secondaryBackgroundColor = "#f8f9fa"
textColor = "#262730"
font = "sans serif"

[server]
# 최대 업로드 크기 (MB)
maxUploadSize = 200

# 최대 메시지 크기 (MB)
maxMessageSize = 200

# XSRF 보호 활성화
enableXsrfProtection = true

# 파일 감시 모드 (개발 시 "auto", 프로덕션 시 false)
fileWatcherType = "auto"

# 헤드리스 모드
headless = true

[client]
# 에러 상세 정보 표시
showErrorDetails = true

# 툴바 모드
toolbarMode = "auto"

[browser]
# 사용량 통계 수집 비활성화
gatherUsageStats = false

[runner]
# 페이지 캐싱 활성화
fastReruns = true
```

**적용 방법**:
1. 프로젝트 루트에 `.streamlit` 폴더 생성
2. `config.toml` 파일 생성 및 내용 입력
3. 앱 재시작

---

## Phase 4: 고급 최적화 (선택)

**예상 성능 개선: 5-15%**

| 순서 | 작업 | 대상 파일 | 구체적 변경 내용 | 예상 효과 |
|------|------|-----------|------------------|-----------|
| 4.1 | 병렬 이미지 로딩 | `pages/6_🎨_이미지_생성.py` | ThreadPoolExecutor 적용 | 배치 생성 30% 빠름 |
| 4.2 | DataFrame dtype 최적화 | `pages/2_🔍_영상_리서치.py` | category, int32 사용 | 메모리 20% 절감 |
| 4.3 | 중첩 레이아웃 단순화 | `pages/2_🔍_영상_리서치.py` | 4중 → 2중 레이아웃 | 렌더링 10% 빠름 |

### 항목 4.1: 병렬 이미지 로딩

**개선 코드**:
```python
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict

def load_images_parallel(image_paths: List[str], max_workers: int = 4) -> Dict[str, bytes]:
    """
    여러 이미지를 병렬로 로드

    Args:
        image_paths: 이미지 경로 목록
        max_workers: 최대 병렬 작업 수

    Returns:
        {경로: 바이트} 딕셔너리
    """
    results = {}

    def load_single(path: str) -> tuple:
        try:
            with open(path, 'rb') as f:
                return path, f.read()
        except Exception:
            return path, None

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(load_single, p): p for p in image_paths}

        for future in as_completed(futures):
            path, data = future.result()
            if data:
                results[path] = data

    return results
```

---

### 항목 4.2: DataFrame dtype 최적화

**현재 코드**:
```python
df = pd.DataFrame([{
    "제목": v.get('title', ''),
    "채널": v.get('channel_title', ''),
    "조회수": v.get('view_count', 0),
    "구독자": v.get('subscriber_count', 0),
} for v in videos])
```

**개선 코드**:
```python
df = pd.DataFrame([{
    "제목": v.get('title', ''),
    "채널": v.get('channel_title', ''),
    "조회수": v.get('view_count', 0),
    "구독자": v.get('subscriber_count', 0),
} for v in videos])

# dtype 최적화
df = df.astype({
    "제목": "string",           # object → string (메모리 효율)
    "채널": "category",         # 반복되는 채널명 → category
    "조회수": "int32",          # int64 → int32 (충분한 범위)
    "구독자": "int32",
})
```

---

## 최적화 적용 순서 요약

```
Week 1: Phase 1 (Quick Wins)
├── Day 1-2: 데이터 로더 캐싱 (1.1, 1.2)
├── Day 3-4: 이미지 바이트 저장 제거 (1.3)
└── Day 5: 세션 정리 함수 (1.4)

Week 2: Phase 2 (중요 개선)
├── Day 1-2: @st.fragment 도입 (2.1)
├── Day 3-4: 루프 내 위젯 최적화 (2.2)
└── Day 5: 썸네일/네트워크 캐싱 (2.3, 2.4)

Week 3: Phase 3 (구조적 개선)
├── Day 1-2: Import 최적화 (3.1, 3.2)
├── Day 3: 초기화 패턴 통일 (3.3)
└── Day 4: config.toml 추가 (3.4)

Week 4+: Phase 4 (선택)
├── 병렬 처리 (4.1)
├── DataFrame 최적화 (4.2)
└── 레이아웃 단순화 (4.3)
```

---

## 예상 결과

### 성능 개선 예상치

| 메트릭 | 현재 (추정) | 목표 | 개선율 |
|--------|-----------|------|--------|
| 페이지 로드 시간 | 3-5초 | 1-2초 | 60% |
| 메모리 사용량 | 500MB+ | 200MB | 60% |
| 리렌더링 시간 | 2-3초 | 0.5-1초 | 70% |
| 이미지 배치 처리 | 느림 | 빠름 | 40% |

### 사용자 경험 개선

- 페이지 전환 시 즉각적인 응답
- 대용량 갤러리에서도 부드러운 스크롤
- 이미지 배치 생성 시 메모리 부족 오류 감소
- 검색 결과 필터/정렬 시 빠른 업데이트

---

**계획서 끝**
