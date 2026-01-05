# -*- coding: utf-8 -*-
"""
TTS 오디오 다운로드 컴포넌트

다운로드 옵션:
1. 씬별 다운로드 (ZIP) - 1.mp3, 2.mp3, ...
2. 전체 합산 다운로드 - 단일 파일
3. 씬별+전체합산 (ZIP) - 씬별/ 폴더 + 전체합산.mp3

사용:
    from components.tts_audio_downloader import render_tts_download_section, create_scenes_zip
"""

import io
import zipfile
from pathlib import Path
from typing import List, Dict, Tuple, Optional, Union
from datetime import datetime


class TTSAudioDownloader:
    """TTS 오디오 다운로드 관리자"""

    # 다운로드 옵션
    OPTION_SCENES_ONLY = "씬별 다운로드 (ZIP)"
    OPTION_COMBINED_ONLY = "전체 합산 다운로드"
    OPTION_SCENES_AND_COMBINED = "씬별+전체합산 (ZIP)"

    ALL_OPTIONS = [OPTION_SCENES_ONLY, OPTION_COMBINED_ONLY, OPTION_SCENES_AND_COMBINED]

    def __init__(self, project_name: str = "tts_output"):
        """
        Args:
            project_name: 프로젝트명 (파일명 접두사)
        """
        self.project_name = project_name

    @staticmethod
    def get_simple_filename(scene_index: int, extension: str = "mp3") -> str:
        """
        단순화된 씬 파일명 생성

        Args:
            scene_index: 씬 인덱스 (1부터 시작)
            extension: 파일 확장자 (mp3, wav 등)

        Returns:
            단순화된 파일명 (예: "1.mp3", "2.mp3")
        """
        # 확장자에서 점 제거
        ext = extension.lstrip('.')
        return f"{scene_index}.{ext}"

    def create_scenes_only_zip(
        self,
        audio_files: List[Dict],
        extension: str = "mp3"
    ) -> Tuple[bytes, str]:
        """
        씬별 파일만 ZIP으로 생성

        Args:
            audio_files: [{"scene_id": 1, "data": bytes, "path": str}, ...]
                        - data: 오디오 바이트 데이터 (우선)
                        - path: 오디오 파일 경로 (data 없을 때 사용)
            extension: 파일 확장자

        Returns:
            (ZIP 바이트 데이터, 파일명)
        """
        zip_buffer = io.BytesIO()

        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            for item in sorted(audio_files, key=lambda x: x.get("scene_id", 0)):
                scene_id = item.get("scene_id", 1)
                filename = self.get_simple_filename(scene_id, extension)

                # 바이트 데이터 또는 파일 경로에서 읽기
                audio_data = item.get("data") or item.get("audio_data")
                if audio_data:
                    zf.writestr(filename, audio_data)
                elif item.get("path"):
                    path = Path(item["path"])
                    if path.exists():
                        zf.write(str(path), filename)

        zip_buffer.seek(0)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_filename = f"{self.project_name}_씬별_{timestamp}.zip"

        return zip_buffer.getvalue(), zip_filename

    def create_combined_audio(
        self,
        audio_files: List[Dict],
        output_format: str = "mp3"
    ) -> Tuple[Optional[bytes], str]:
        """
        전체 합산 오디오 생성

        Args:
            audio_files: [{"scene_id": 1, "data": bytes, "path": str}, ...]
            output_format: 출력 형식 (mp3, wav)

        Returns:
            (오디오 바이트 데이터, 파일명)
        """
        try:
            from pydub import AudioSegment
        except ImportError:
            print("[TTSDownloader] pydub 모듈이 없습니다. pip install pydub")
            return None, ""

        combined_audio = None

        # 씬 ID 순으로 정렬하여 합산
        for item in sorted(audio_files, key=lambda x: x.get("scene_id", 0)):
            audio_data = item.get("data") or item.get("audio_data")
            audio_path = item.get("path")

            try:
                if audio_data:
                    # 바이트 데이터에서 로드
                    # 형식 추측
                    fmt = item.get("format", output_format)
                    segment = AudioSegment.from_file(io.BytesIO(audio_data), format=fmt)
                elif audio_path and Path(audio_path).exists():
                    # 파일에서 로드
                    segment = AudioSegment.from_file(audio_path)
                else:
                    continue

                if combined_audio is None:
                    combined_audio = segment
                else:
                    combined_audio += segment

            except Exception as e:
                print(f"[TTSDownloader] 오디오 로드 실패: {e}")
                continue

        if combined_audio is None:
            return None, ""

        # 출력 형식으로 내보내기
        output_buffer = io.BytesIO()
        combined_audio.export(output_buffer, format=output_format)
        output_buffer.seek(0)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{self.project_name}_전체합산_{timestamp}.{output_format}"

        return output_buffer.getvalue(), filename

    def create_scenes_and_combined_zip(
        self,
        audio_files: List[Dict],
        extension: str = "mp3"
    ) -> Tuple[bytes, str]:
        """
        씬별 ZIP + 전체 합산 파일을 하나의 ZIP으로 생성

        Args:
            audio_files: [{"scene_id": 1, "data": bytes, "path": str}, ...]
            extension: 파일 확장자

        Returns:
            (ZIP 바이트 데이터, 파일명)
        """
        try:
            from pydub import AudioSegment
        except ImportError:
            print("[TTSDownloader] pydub 모듈이 없습니다.")
            # pydub 없으면 씬별만 반환
            return self.create_scenes_only_zip(audio_files, extension)

        zip_buffer = io.BytesIO()
        combined_audio = None

        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
            # 1. 씬별 폴더에 파일 추가
            for item in sorted(audio_files, key=lambda x: x.get("scene_id", 0)):
                scene_id = item.get("scene_id", 1)
                filename = self.get_simple_filename(scene_id, extension)
                arcname = f"씬별/{filename}"  # 씬별/ 폴더 안에 저장

                audio_data = item.get("data") or item.get("audio_data")
                audio_path = item.get("path")

                if audio_data:
                    zf.writestr(arcname, audio_data)

                    # 합산용 오디오 누적
                    try:
                        fmt = item.get("format", extension)
                        segment = AudioSegment.from_file(io.BytesIO(audio_data), format=fmt)
                        if combined_audio is None:
                            combined_audio = segment
                        else:
                            combined_audio += segment
                    except Exception as e:
                        print(f"[TTSDownloader] 합산 실패 (scene {scene_id}): {e}")

                elif audio_path and Path(audio_path).exists():
                    zf.write(str(audio_path), arcname)

                    try:
                        segment = AudioSegment.from_file(audio_path)
                        if combined_audio is None:
                            combined_audio = segment
                        else:
                            combined_audio += segment
                    except Exception as e:
                        print(f"[TTSDownloader] 합산 실패 (scene {scene_id}): {e}")

            # 2. 전체 합산 파일 추가
            if combined_audio:
                combined_buffer = io.BytesIO()
                combined_audio.export(combined_buffer, format=extension)
                combined_buffer.seek(0)

                # 루트에 전체합산 파일 저장
                zf.writestr(f"전체합산.{extension}", combined_buffer.getvalue())

        zip_buffer.seek(0)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        zip_filename = f"{self.project_name}_씬별+전체합산_{timestamp}.zip"

        return zip_buffer.getvalue(), zip_filename

    def create_download(
        self,
        audio_files: List[Dict],
        option: str,
        extension: str = "mp3"
    ) -> Tuple[Optional[bytes], str, str]:
        """
        선택된 옵션에 따라 다운로드 데이터 생성

        Args:
            audio_files: 오디오 파일 정보 리스트
            option: 다운로드 옵션 (OPTION_* 상수)
            extension: 파일 확장자

        Returns:
            (데이터, 파일명, MIME 타입)
        """
        if option == self.OPTION_SCENES_ONLY:
            data, filename = self.create_scenes_only_zip(audio_files, extension)
            return data, filename, "application/zip"

        elif option == self.OPTION_COMBINED_ONLY:
            data, filename = self.create_combined_audio(audio_files, extension)
            if data:
                mime = "audio/mpeg" if extension == "mp3" else f"audio/{extension}"
                return data, filename, mime
            return None, "", ""

        elif option == self.OPTION_SCENES_AND_COMBINED:
            data, filename = self.create_scenes_and_combined_zip(audio_files, extension)
            return data, filename, "application/zip"

        return None, "", ""


# ============================================================
# Streamlit UI 렌더링 함수
# ============================================================

def render_tts_download_section(
    audio_files: List[Dict],
    project_name: str = "tts_output",
    extension: str = "mp3",
    key_prefix: str = "tts_dl"
):
    """
    TTS 다운로드 섹션 렌더링

    Args:
        audio_files: [{"scene_id": 1, "data": bytes, "path": str}, ...]
        project_name: 프로젝트명
        extension: 파일 확장자 (mp3, wav)
        key_prefix: Streamlit 키 접두사

    Usage:
        generated_files = [
            {"scene_id": 1, "data": audio_bytes_1},
            {"scene_id": 2, "data": audio_bytes_2},
        ]
        render_tts_download_section(generated_files, "my_project", "mp3")
    """
    import streamlit as st

    st.markdown("### 📦 일괄 다운로드")

    if not audio_files:
        st.warning("다운로드할 오디오 파일이 없습니다.")
        return

    # 다운로드 옵션 선택
    downloader = TTSAudioDownloader(project_name)

    selected_option = st.radio(
        "다운로드 옵션 선택",
        options=downloader.ALL_OPTIONS,
        key=f"{key_prefix}_option",
        horizontal=True
    )

    # 옵션별 설명
    descriptions = {
        downloader.OPTION_SCENES_ONLY: f"각 씬의 오디오 파일을 개별적으로 압축 (1.{extension}, 2.{extension}, ...)",
        downloader.OPTION_COMBINED_ONLY: "모든 씬을 하나의 오디오 파일로 합침",
        downloader.OPTION_SCENES_AND_COMBINED: f"씬별 파일 + 전체 합산 파일을 함께 압축 (씬별/ + 전체합산.{extension})"
    }
    st.caption(f"ℹ️ {descriptions.get(selected_option, '')}")

    # ZIP 구조 미리보기
    if selected_option == downloader.OPTION_SCENES_AND_COMBINED:
        with st.expander("📁 ZIP 파일 구조 미리보기"):
            preview_lines = [
                f"{project_name}_씬별+전체합산_[timestamp].zip",
                "├── 씬별/"
            ]

            # 처음 3개 + ... + 마지막 1개 표시
            scene_ids = sorted([f.get("scene_id", i+1) for i, f in enumerate(audio_files)])
            if len(scene_ids) <= 5:
                for sid in scene_ids:
                    preview_lines.append(f"│   ├── {sid}.{extension}")
            else:
                for sid in scene_ids[:3]:
                    preview_lines.append(f"│   ├── {sid}.{extension}")
                preview_lines.append("│   ├── ...")
                preview_lines.append(f"│   └── {scene_ids[-1]}.{extension}")

            preview_lines.append(f"└── 전체합산.{extension}")
            st.code("\n".join(preview_lines), language=None)

    # 다운로드 생성 버튼
    col1, col2 = st.columns([1, 2])

    with col1:
        if st.button("📦 다운로드 생성", type="primary", use_container_width=True, key=f"{key_prefix}_create"):
            with st.spinner("다운로드 파일 생성 중..."):
                try:
                    data, filename, mime = downloader.create_download(
                        audio_files, selected_option, extension
                    )

                    if data:
                        st.session_state[f"{key_prefix}_data"] = data
                        st.session_state[f"{key_prefix}_filename"] = filename
                        st.session_state[f"{key_prefix}_mime"] = mime
                        st.success(f"✅ '{filename}' 생성 완료!")
                    else:
                        st.error("다운로드 파일 생성 실패")

                except Exception as e:
                    st.error(f"오류: {e}")

    # 다운로드 버튼 표시
    if st.session_state.get(f"{key_prefix}_data"):
        with col2:
            st.download_button(
                label=f"⬇️ {st.session_state.get(f'{key_prefix}_filename', 'download')} 다운로드",
                data=st.session_state[f"{key_prefix}_data"],
                file_name=st.session_state.get(f"{key_prefix}_filename", "download.zip"),
                mime=st.session_state.get(f"{key_prefix}_mime", "application/zip"),
                use_container_width=True,
                key=f"{key_prefix}_download_btn"
            )


def render_inline_download_buttons(
    audio_files: List[Dict],
    project_name: str = "tts_output",
    extension: str = "mp3",
    key_prefix: str = "tts_inline"
):
    """
    인라인 다운로드 버튼 렌더링 (3개 옵션을 버튼으로 표시)

    Args:
        audio_files: 오디오 파일 정보 리스트
        project_name: 프로젝트명
        extension: 파일 확장자
        key_prefix: Streamlit 키 접두사
    """
    import streamlit as st

    if not audio_files:
        return

    downloader = TTSAudioDownloader(project_name)

    st.markdown("### 📦 다운로드")

    col1, col2, col3 = st.columns(3)

    with col1:
        if st.button(f"📁 씬별 ZIP", use_container_width=True, key=f"{key_prefix}_scenes"):
            with st.spinner("생성 중..."):
                data, filename = downloader.create_scenes_only_zip(audio_files, extension)
                st.session_state[f"{key_prefix}_ready"] = {
                    "data": data, "filename": filename, "mime": "application/zip"
                }

    with col2:
        if st.button(f"🎵 전체 합산", use_container_width=True, key=f"{key_prefix}_combined"):
            with st.spinner("생성 중..."):
                data, filename = downloader.create_combined_audio(audio_files, extension)
                if data:
                    mime = "audio/mpeg" if extension == "mp3" else f"audio/{extension}"
                    st.session_state[f"{key_prefix}_ready"] = {
                        "data": data, "filename": filename, "mime": mime
                    }

    with col3:
        if st.button(f"📦 씬별+합산", use_container_width=True, key=f"{key_prefix}_both"):
            with st.spinner("생성 중..."):
                data, filename = downloader.create_scenes_and_combined_zip(audio_files, extension)
                st.session_state[f"{key_prefix}_ready"] = {
                    "data": data, "filename": filename, "mime": "application/zip"
                }

    # 생성된 파일 다운로드 버튼
    if st.session_state.get(f"{key_prefix}_ready"):
        ready = st.session_state[f"{key_prefix}_ready"]
        st.download_button(
            label=f"⬇️ {ready['filename']} 다운로드",
            data=ready["data"],
            file_name=ready["filename"],
            mime=ready["mime"],
            use_container_width=True,
            key=f"{key_prefix}_final_download"
        )


# ============================================================
# 헬퍼 함수 (호환성)
# ============================================================

def create_scenes_zip(
    audio_files: List[Dict],
    project_name: str = "tts_output",
    extension: str = "mp3"
) -> Tuple[bytes, str]:
    """
    씬별 ZIP 생성 (간편 함수)

    Args:
        audio_files: [{"scene_id": 1, "data": bytes}, ...]
        project_name: 프로젝트명
        extension: 파일 확장자

    Returns:
        (ZIP 바이트 데이터, 파일명)
    """
    downloader = TTSAudioDownloader(project_name)
    return downloader.create_scenes_only_zip(audio_files, extension)


def create_combined_audio(
    audio_files: List[Dict],
    project_name: str = "tts_output",
    extension: str = "mp3"
) -> Tuple[Optional[bytes], str]:
    """
    전체 합산 오디오 생성 (간편 함수)
    """
    downloader = TTSAudioDownloader(project_name)
    return downloader.create_combined_audio(audio_files, extension)


def create_scenes_and_combined_zip(
    audio_files: List[Dict],
    project_name: str = "tts_output",
    extension: str = "mp3"
) -> Tuple[bytes, str]:
    """
    씬별+전체합산 ZIP 생성 (간편 함수)
    """
    downloader = TTSAudioDownloader(project_name)
    return downloader.create_scenes_and_combined_zip(audio_files, extension)


def get_simple_filename(scene_index: int, extension: str = "mp3") -> str:
    """
    단순화된 파일명 생성 (간편 함수)

    Args:
        scene_index: 씬 인덱스 (1부터 시작)
        extension: 확장자

    Returns:
        "1.mp3", "2.mp3" 형식의 파일명
    """
    return TTSAudioDownloader.get_simple_filename(scene_index, extension)


# ============================================================
# 테스트
# ============================================================

if __name__ == "__main__":
    # 테스트 데이터 생성
    test_files = [
        {"scene_id": 1, "data": b"audio_data_1"},
        {"scene_id": 2, "data": b"audio_data_2"},
        {"scene_id": 3, "data": b"audio_data_3"},
    ]

    # 파일명 테스트
    for i in range(1, 121):
        filename = get_simple_filename(i, "mp3")
        assert filename == f"{i}.mp3", f"Expected {i}.mp3, got {filename}"
        assert not filename.startswith("scene_"), f"Filename should not start with scene_: {filename}"

    print("[OK] Filename format test passed")

    # ZIP 생성 테스트
    downloader = TTSAudioDownloader("test_project")

    zip_data, zip_name = downloader.create_scenes_only_zip(test_files, "mp3")
    assert zip_data, "ZIP data should not be empty"
    assert "씬별" in zip_name, f"ZIP name should contain '씬별': {zip_name}"

    # ZIP 내용 확인
    import zipfile
    with zipfile.ZipFile(io.BytesIO(zip_data), 'r') as zf:
        names = zf.namelist()
        assert "1.mp3" in names, f"1.mp3 should be in ZIP: {names}"
        assert "2.mp3" in names, f"2.mp3 should be in ZIP: {names}"
        assert "3.mp3" in names, f"3.mp3 should be in ZIP: {names}"

        # scene_ 형식이 없는지 확인
        for name in names:
            assert not name.startswith("scene_"), f"Should not have scene_ prefix: {name}"

    print("[OK] ZIP creation test passed")
    print("[OK] All tests passed!")
