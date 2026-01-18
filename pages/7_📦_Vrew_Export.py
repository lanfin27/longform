"""
7단계: Vrew Export

Vrew에서 바로 사용할 수 있는 폴더 구조로 Export
script_for_vrew.txt, image_mapping.xlsx 포함
"""
import streamlit as st
from pathlib import Path
import sys

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from utils.project_manager import (
    ensure_project_selected,
    get_current_project,
    get_current_project_config,
    render_project_sidebar,
    update_project_step
)
from utils.data_loader import (
    get_export_dir,
    list_content_images,
    get_audio_path,
    get_srt_path,
    load_segment_groups,
    check_step_completed
)
from utils.api_helper import show_api_status_sidebar


# ============================================================
# ⭐ 성능 최적화: 캐싱 데코레이터
# ============================================================
@st.cache_data(ttl=30, show_spinner=False)
def _cached_check_export_status(project_path_str, language):
    """Export 체크리스트 상태 확인 (캐싱 적용)"""
    from pathlib import Path
    project_path = Path(project_path_str)
    return {
        "오디오 (MP3)": get_audio_path(project_path, language).exists(),
        "자막 (SRT)": get_srt_path(project_path, language).exists(),
        "본문 이미지": len(list_content_images(project_path)) > 0,
        "세그먼트 그룹": load_segment_groups(project_path) is not None,
    }


# 페이지 설정
st.set_page_config(
    page_title="Vrew Export",
    page_icon="📦",
    layout="wide"
)

render_project_sidebar()
show_api_status_sidebar()

if not ensure_project_selected():
    st.stop()

project_path = get_current_project()
project_config = get_current_project_config()

st.title("📦 7단계: Vrew Export")
st.caption("Vrew에서 바로 사용할 수 있는 폴더 구조로 내보냅니다.")

st.divider()

# === 체크리스트 ===
st.subheader("✅ Export 전 체크리스트")

language = project_config.get("language", "ko")

# ⭐ 캐싱된 함수 사용
checks = _cached_check_export_status(str(project_path), language)

all_ready = True
for name, exists in checks.items():
    if exists:
        st.success(f"✅ {name}")
    else:
        st.warning(f"⚠️ {name} - 준비되지 않음")
        all_ready = False

st.divider()

# === 데이터 동기화 ===
st.subheader("🔄 데이터 동기화")
st.caption("이미지 생성과 TTS 결과를 Vrew Export에 동기화합니다.")

from utils.sync_manager import ProcessType
from utils.sync_ui import render_sync_buttons, render_manual_sync_panel
render_sync_buttons(ProcessType.VREW_EXPORT)
render_manual_sync_panel()

st.divider()

# === Export 설정 ===
st.subheader("⚙️ Export 설정")

col1, col2 = st.columns(2)

with col1:
    include_script = st.checkbox("script_for_vrew.txt 포함", value=True, help="원고 복사용 텍스트 파일")
    include_mapping = st.checkbox("image_mapping.xlsx 포함", value=True, help="이미지-자막 매핑 표")

with col2:
    include_thumbnail_text = st.checkbox("thumbnail_text.txt 포함", value=True, help="썸네일 텍스트 (합성용)")
    include_readme = st.checkbox("README.txt 포함", value=True, help="사용 가이드")

st.divider()

# === Export 버튼 ===
if all_ready:
    if st.button("📦 Vrew용으로 Export", type="primary", use_container_width=True):
        with st.spinner("Export 중..."):
            try:
                from utils.vrew_exporter import VrewExporter

                exporter = VrewExporter()
                export_path = exporter.export(
                    project_path,
                    include_script=include_script,
                    include_mapping=include_mapping,
                    include_thumbnail_text=include_thumbnail_text,
                    include_readme=include_readme
                )

                update_project_step(7)

                st.success("✅ Export 완료!")
                st.info(f"📂 경로: `{export_path}`")

                # 결과 표시
                st.divider()
                st.subheader("📁 Export 결과")

                export_dir = Path(export_path)

                for item in sorted(export_dir.iterdir()):
                    if item.is_file():
                        size_kb = item.stat().st_size / 1024
                        st.caption(f"📄 {item.name} ({size_kb:.1f} KB)")
                    elif item.is_dir():
                        file_count = len(list(item.iterdir()))
                        st.caption(f"📁 {item.name}/ ({file_count}개 파일)")

            except Exception as e:
                st.error(f"Export 실패: {str(e)}")

else:
    st.warning("⚠️ 먼저 모든 단계를 완료하세요.")

    st.divider()

    # 미완료 단계 안내
    st.subheader("🔄 진행이 필요한 단계")

    if not checks["오디오 (MP3)"] or not checks["자막 (SRT)"]:
        st.page_link("pages/4_🎤_TTS_생성.py", label="🎤 4단계: TTS 생성", icon="➡️")

    if not checks["세그먼트 그룹"]:
        st.page_link("pages/5_🖼️_이미지_프롬프트.py", label="🖼️ 5단계: 이미지 프롬프트", icon="➡️")

    if not checks["본문 이미지"]:
        st.page_link("pages/6_🎨_이미지_생성.py", label="🎨 6단계: 이미지 생성", icon="➡️")

st.divider()

# === Vrew Import 가이드 ===
st.subheader("📋 Vrew Import 가이드")

st.markdown("""
### 1. Vrew 실행
- Vrew 실행 → 새 프로젝트 → **"음성으로 영상 만들기"**

### 2. 오디오 Import
- `audio.mp3` 파일 선택
- 문단별 1.5초 무음이 이미 포함되어 있습니다.

### 3. 자막 설정
- **방법 A**: `subtitles.srt` 파일 직접 import
- **방법 B**: Vrew 자동 생성 후 수정

### 4. 이미지 배치 (⚠️ 중요!)
- `image_mapping.xlsx` 파일을 열어 참고하세요.
- 각 자막 구간에 맞는 이미지를 삽입합니다.

| 이미지 파일 | 자막 구간 |
|-------------|----------|
| 001_seg_001-004.png | 자막 1~4번 |
| 002_seg_005-008.png | 자막 5~8번 |
| ... | ... |

### 5. 썸네일 제작
1. 나노바나나에서 배경 이미지 생성
2. `thumbnail_text.txt`의 텍스트를 복사
3. 미리캔버스 또는 Vrew에서 텍스트 합성

### 6. 최종 편집
- 전환 효과 추가
- BGM 삽입
- 최종 Export

---

💡 **팁**
- 이미지 파일명의 숫자는 해당 자막 세그먼트 번호입니다.
- `script_for_vrew.txt`는 원고 복사용으로 활용하세요.
""")

st.divider()

# 완료 메시지
if all_ready and check_step_completed(project_path, 7):
    st.balloons()
    st.success("🎉 모든 단계가 완료되었습니다! Vrew에서 편집을 시작하세요.")
