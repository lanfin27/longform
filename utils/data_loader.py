"""
데이터 로드/저장 유틸리티

각 단계별 데이터의 자동 로드/저장을 담당합니다.

사용법:
    from utils.data_loader import save_video_research, load_video_research

    # 저장
    save_video_research(project_path, videos)

    # 로드
    videos = load_video_research(project_path)
"""
import json
import pandas as pd
from pathlib import Path
from typing import Optional, Any, List, Dict

# Streamlit 캐싱 (조건부 import)
try:
    import streamlit as st
    _HAS_STREAMLIT = True
except ImportError:
    _HAS_STREAMLIT = False


# === 단계별 폴더 매핑 ===
STEP_FOLDERS = {
    "research": "research",
    "transcripts": "research/transcripts",
    "comments": "research/comments",
    "thumbnails": "research/thumbnails",
    "scripts": "scripts",
    "audio": "audio",
    "prompts": "prompts",
    "images": "images/content",
    "thumbnail_images": "images/thumbnail",
    "export": "export"
}


# === 캐싱된 로드 함수 (Streamlit 환경) ===

def _load_json_impl(filepath_str: str) -> Optional[Any]:
    """JSON 파일 로드 구현 (내부용)"""
    filepath = Path(filepath_str)
    if filepath.exists():
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def _load_excel_impl(filepath_str: str) -> Optional[pd.DataFrame]:
    """Excel 파일 로드 구현 (내부용)"""
    filepath = Path(filepath_str)
    if filepath.exists():
        return pd.read_excel(filepath)
    return None


def _load_text_impl(filepath_str: str) -> Optional[str]:
    """텍스트 파일 로드 구현 (내부용)"""
    filepath = Path(filepath_str)
    if filepath.exists():
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    return None


# Streamlit 캐싱 적용 (조건부)
if _HAS_STREAMLIT:
    @st.cache_data(ttl=300, show_spinner=False, max_entries=100)
    def _load_json_cached(filepath_str: str, _mtime: float) -> Optional[Any]:
        """JSON 파일 로드 (캐싱 적용) - mtime으로 자동 무효화"""
        return _load_json_impl(filepath_str)

    @st.cache_data(ttl=300, show_spinner=False, max_entries=50)
    def _load_excel_cached(filepath_str: str, _mtime: float) -> Optional[pd.DataFrame]:
        """Excel 파일 로드 (캐싱 적용) - mtime으로 자동 무효화"""
        return _load_excel_impl(filepath_str)

    @st.cache_data(ttl=300, show_spinner=False, max_entries=100)
    def _load_text_cached(filepath_str: str, _mtime: float) -> Optional[str]:
        """텍스트 파일 로드 (캐싱 적용) - mtime으로 자동 무효화"""
        return _load_text_impl(filepath_str)


# === 기본 유틸리티 함수 ===

def save_json(data: Any, filepath: Path):
    """JSON 파일 저장"""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_json(filepath: Path) -> Optional[Any]:
    """
    JSON 파일 로드 (자동 캐싱)

    Streamlit 환경에서는 @st.cache_data로 캐싱됨.
    파일 수정 시 자동으로 캐시 무효화.
    """
    filepath = Path(filepath)
    if not filepath.exists():
        return None

    if _HAS_STREAMLIT:
        mtime = filepath.stat().st_mtime
        return _load_json_cached(str(filepath), _mtime=mtime)
    else:
        return _load_json_impl(str(filepath))


def save_excel(df: pd.DataFrame, filepath: Path):
    """Excel 파일 저장"""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(filepath, index=False)


def load_excel(filepath: Path) -> Optional[pd.DataFrame]:
    """
    Excel 파일 로드 (자동 캐싱)

    Streamlit 환경에서는 @st.cache_data로 캐싱됨.
    파일 수정 시 자동으로 캐시 무효화.
    """
    filepath = Path(filepath)
    if not filepath.exists():
        return None

    if _HAS_STREAMLIT:
        mtime = filepath.stat().st_mtime
        return _load_excel_cached(str(filepath), _mtime=mtime)
    else:
        return _load_excel_impl(str(filepath))


def save_text(text: str, filepath: Path):
    """텍스트 파일 저장"""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(text)


def load_text(filepath: Path) -> Optional[str]:
    """
    텍스트 파일 로드 (자동 캐싱)

    Streamlit 환경에서는 @st.cache_data로 캐싱됨.
    파일 수정 시 자동으로 캐시 무효화.
    """
    filepath = Path(filepath)
    if not filepath.exists():
        return None

    if _HAS_STREAMLIT:
        mtime = filepath.stat().st_mtime
        return _load_text_cached(str(filepath), _mtime=mtime)
    else:
        return _load_text_impl(str(filepath))


# === 2단계: 영상 리서치 ===

def save_video_research(project_path: Path, videos: List[Dict]):
    """
    영상 리서치 결과 저장

    저장 파일:
    - research/video_list.xlsx (Excel 버전)
    - research/video_list.json (JSON 버전)
    """
    project_path = Path(project_path)

    # Excel 저장
    df = pd.DataFrame(videos)
    save_excel(df, project_path / "research" / "video_list.xlsx")

    # JSON 저장
    save_json(videos, project_path / "research" / "video_list.json")


def load_video_research(project_path: Path) -> Optional[List[Dict]]:
    """영상 리서치 결과 로드"""
    return load_json(Path(project_path) / "research" / "video_list.json")


def save_selected_videos(project_path: Path, videos: List[Dict]):
    """선택된 영상 저장"""
    save_json(videos, Path(project_path) / "research" / "selected_videos.json")


def load_selected_videos(project_path: Path) -> Optional[List[Dict]]:
    """선택된 영상 로드"""
    return load_json(Path(project_path) / "research" / "selected_videos.json")


# === 2.5단계: 스크립트 추출 ===

def save_transcript(project_path: Path, video_id: str, transcript: str, lang: str = "original"):
    """
    추출된 스크립트 저장

    Args:
        project_path: 프로젝트 경로
        video_id: 영상 ID
        transcript: 스크립트 내용
        lang: 언어 ("original", "ko", "en" 등)
    """
    filepath = Path(project_path) / "research" / "transcripts" / f"{video_id}_{lang}.txt"
    save_text(transcript, filepath)


def load_transcript(project_path: Path, video_id: str, lang: str = "original") -> Optional[str]:
    """추출된 스크립트 로드"""
    filepath = Path(project_path) / "research" / "transcripts" / f"{video_id}_{lang}.txt"
    return load_text(filepath)


def list_transcripts(project_path: Path) -> List[str]:
    """저장된 스크립트 파일 목록"""
    transcript_dir = Path(project_path) / "research" / "transcripts"
    if transcript_dir.exists():
        return [f.stem for f in transcript_dir.glob("*.txt")]
    return []


# === 3단계: 스크립트 생성 ===

def save_script(project_path: Path, script: str, language: str, script_type: str = "draft"):
    """
    생성된 스크립트 저장

    Args:
        project_path: 프로젝트 경로
        script: 스크립트 내용
        language: 언어 ("ko" 또는 "ja")
        script_type: 타입 ("draft" 또는 "final")
    """
    filepath = Path(project_path) / "scripts" / f"{script_type}_{language}.txt"
    save_text(script, filepath)


def load_script(project_path: Path, language: str, script_type: str = "draft") -> Optional[str]:
    """스크립트 로드"""
    filepath = Path(project_path) / "scripts" / f"{script_type}_{language}.txt"
    return load_text(filepath)


def save_script_metadata(project_path: Path, metadata: Dict):
    """스크립트 메타데이터 저장 (토큰 사용량 등)"""
    save_json(metadata, Path(project_path) / "scripts" / "metadata.json")


def load_script_metadata(project_path: Path) -> Optional[Dict]:
    """스크립트 메타데이터 로드"""
    return load_json(Path(project_path) / "scripts" / "metadata.json")


# === 4단계: TTS ===

def get_audio_path(project_path: Path, language: str) -> Path:
    """오디오 파일 경로 반환"""
    return Path(project_path) / "audio" / f"voice_{language}.mp3"


def get_srt_path(project_path: Path, language: str) -> Path:
    """SRT 파일 경로 반환"""
    return Path(project_path) / "audio" / f"voice_{language}.srt"


def save_tts_settings(project_path: Path, settings: Dict):
    """TTS 설정 저장"""
    save_json(settings, Path(project_path) / "audio" / "tts_settings.json")


def load_tts_settings(project_path: Path) -> Optional[Dict]:
    """TTS 설정 로드"""
    return load_json(Path(project_path) / "audio" / "tts_settings.json")


def save_paragraph_breaks(project_path: Path, breaks: Dict):
    """문단 구분 정보 저장"""
    save_json(breaks, Path(project_path) / "audio" / "paragraph_breaks.json")


def load_paragraph_breaks(project_path: Path) -> Optional[Dict]:
    """문단 구분 정보 로드"""
    return load_json(Path(project_path) / "audio" / "paragraph_breaks.json")


# === 5단계: 이미지 프롬프트 ===

def save_thumbnail_prompts(project_path: Path, prompts: Dict):
    """
    썸네일 프롬프트 저장

    구조:
    {
        "thumbnail_prompts": [
            {
                "version": "A",
                "image_prompt": "...",
                "overlay_text": {"main": "...", "sub": "..."}
            }
        ]
    }
    """
    save_json(prompts, Path(project_path) / "prompts" / "thumbnail_prompts.json")


def load_thumbnail_prompts(project_path: Path) -> Optional[Dict]:
    """썸네일 프롬프트 로드"""
    return load_json(Path(project_path) / "prompts" / "thumbnail_prompts.json")


def save_image_prompts(project_path: Path, prompts: List[Dict]):
    """
    본문 이미지 프롬프트 저장

    저장 파일:
    - prompts/image_prompts.xlsx (Excel 버전)
    - prompts/image_prompts.json (JSON 버전)
    """
    project_path = Path(project_path)

    # Excel 저장
    df = pd.DataFrame(prompts)
    save_excel(df, project_path / "prompts" / "image_prompts.xlsx")

    # JSON 저장
    save_json(prompts, project_path / "prompts" / "image_prompts.json")


def load_image_prompts(project_path: Path) -> Optional[List[Dict]]:
    """본문 이미지 프롬프트 로드"""
    return load_json(Path(project_path) / "prompts" / "image_prompts.json")


def save_segment_groups(project_path: Path, groups: List[Dict]):
    """세그먼트 그룹 정보 저장"""
    save_json(groups, Path(project_path) / "prompts" / "segment_groups.json")


def load_segment_groups(project_path: Path) -> Optional[List[Dict]]:
    """세그먼트 그룹 정보 로드"""
    return load_json(Path(project_path) / "prompts" / "segment_groups.json")


def save_style_guide(project_path: Path, style_guide: Dict):
    """이미지 스타일 가이드 저장"""
    save_json(style_guide, Path(project_path) / "prompts" / "style_guide.json")


def load_style_guide(project_path: Path) -> Optional[Dict]:
    """이미지 스타일 가이드 로드"""
    return load_json(Path(project_path) / "prompts" / "style_guide.json")


# === 6단계: 이미지 생성 ===

def get_content_images_dir(project_path: Path) -> Path:
    """본문 이미지 폴더 경로"""
    path = Path(project_path) / "images" / "content"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_thumbnail_images_dir(project_path: Path) -> Path:
    """썸네일 이미지 폴더 경로"""
    path = Path(project_path) / "images" / "thumbnail"
    path.mkdir(parents=True, exist_ok=True)
    return path


def list_content_images(project_path: Path) -> List[Path]:
    """생성된 본문 이미지 목록"""
    images_dir = get_content_images_dir(project_path)
    return sorted(images_dir.glob("*.png"))


def save_image_generation_log(project_path: Path, log: List[Dict]):
    """이미지 생성 로그 저장"""
    save_json(log, Path(project_path) / "images" / "content" / "generation_log.json")


def load_image_generation_log(project_path: Path) -> Optional[List[Dict]]:
    """이미지 생성 로그 로드"""
    return load_json(Path(project_path) / "images" / "content" / "generation_log.json")


# === 7단계: Export ===

def get_export_dir(project_path: Path) -> Path:
    """Export 폴더 경로"""
    path = Path(project_path) / "export"
    path.mkdir(parents=True, exist_ok=True)
    return path


# === 유틸리티: 프로젝트 상태 확인 ===

def check_step_completed(project_path: Path, step: int) -> bool:
    """
    특정 단계가 완료되었는지 확인

    Args:
        project_path: 프로젝트 경로
        step: 단계 번호 (1-7)

    Returns:
        완료 여부
    """
    project_path = Path(project_path)

    if step == 2:
        return (project_path / "research" / "video_list.json").exists()
    elif step == 3:
        # 한국어 또는 일본어 스크립트 존재 확인
        return any([
            (project_path / "scripts" / "draft_ko.txt").exists(),
            (project_path / "scripts" / "draft_ja.txt").exists(),
            (project_path / "scripts" / "final_ko.txt").exists(),
            (project_path / "scripts" / "final_ja.txt").exists(),
        ])
    elif step == 4:
        return any((project_path / "audio").glob("voice_*.mp3"))
    elif step == 5:
        return (project_path / "prompts" / "segment_groups.json").exists()
    elif step == 6:
        return len(list_content_images(project_path)) > 0
    elif step == 7:
        return (project_path / "export" / "README.txt").exists()

    return False


def get_project_progress(project_path: Path) -> Dict:
    """
    프로젝트 진행 상황 반환

    Returns:
        {
            "completed_steps": [1, 2, 3],
            "current_step": 4,
            "total_steps": 7
        }
    """
    completed = []
    for step in range(1, 8):
        if check_step_completed(project_path, step):
            completed.append(step)

    current = max(completed) + 1 if completed else 1
    current = min(current, 7)

    return {
        "completed_steps": completed,
        "current_step": current,
        "total_steps": 7
    }


# === 씬/캐릭터 관련 함수 ===

def load_scenes(project_path: Path, auto_sync: bool = True) -> List[Dict]:
    """씬 분석 결과 로드 (character_prompt -> characters 자동 동기화 포함)"""
    scenes_path = Path(project_path) / "analysis" / "scenes.json"
    if not scenes_path.exists():
        return []

    with open(scenes_path, "r", encoding="utf-8") as f:
        scenes = json.load(f)

    if auto_sync and scenes:
        try:
            from utils.character_sync import get_sync_status, sync_all_scenes_characters, update_characters_json
            status = get_sync_status(scenes)
            if status["needs_sync"] > 0:
                print(f"[자동 동기화] {status['needs_sync']}개 씬 character_prompt -> characters 동기화")
                scenes, synced_count = sync_all_scenes_characters(scenes)
                if synced_count > 0:
                    with open(scenes_path, "w", encoding="utf-8") as f:
                        json.dump(scenes, f, ensure_ascii=False, indent=2)
                    characters_path = scenes_path.parent / "characters.json"
                    update_characters_json(scenes, characters_path)
                    print(f"[자동 동기화] {synced_count}개 씬 업데이트 완료")
        except Exception as e:
            print(f"[자동 동기화] 오류 (무시): {e}")

    return scenes


def save_scenes(project_path: Path, scenes: List[Dict]):
    """씬 분석 결과 저장 (character_prompt -> characters 후처리 동기화 포함)"""
    if scenes:
        try:
            from utils.character_sync import sync_all_scenes_characters, update_characters_json
            scenes, synced_count = sync_all_scenes_characters(scenes)
            if synced_count > 0:
                print(f"[후처리] {synced_count}개 씬의 characters 배열 자동 동기화됨")
            # characters.json 업데이트
            characters_path = Path(project_path) / "analysis" / "characters.json"
            update_characters_json(scenes, characters_path)
        except Exception as e:
            print(f"[후처리] 동기화 오류 (무시): {e}")

    save_json(scenes, Path(project_path) / "analysis" / "scenes.json")


def load_characters_analysis(project_path: Path) -> List[Dict]:
    """씬 분석에서 추출된 캐릭터 로드"""
    chars_path = Path(project_path) / "analysis" / "characters.json"
    if chars_path.exists():
        with open(chars_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def get_scene_character_names(project_path: Path, scene_id: int) -> List[str]:
    """특정 씬에 등장하는 캐릭터 이름 목록"""
    scenes = load_scenes(project_path)
    for scene in scenes:
        if scene.get("scene_id") == scene_id:
            return scene.get("characters", [])
    return []


def save_scene_prompts(project_path: Path, prompts: List[Dict]):
    """씬 기반 프롬프트 저장"""
    prompts_dir = Path(project_path) / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)

    # scene_prompts.json 저장
    save_json(prompts, prompts_dir / "scene_prompts.json")

    # content_prompts.json도 저장 (호환성)
    save_json(prompts, prompts_dir / "content_prompts.json")


def load_scene_prompts(project_path: Path) -> List[Dict]:
    """씬 기반 프롬프트 로드"""
    return load_json(Path(project_path) / "prompts" / "scene_prompts.json")


def get_scene_images_dir(project_path: Path) -> Path:
    """씬 이미지 폴더 경로"""
    path = Path(project_path) / "images" / "scenes"
    path.mkdir(parents=True, exist_ok=True)
    return path


def list_scene_images(project_path: Path) -> List[Path]:
    """생성된 씬 이미지 목록"""
    images_dir = get_scene_images_dir(project_path)
    return sorted(images_dir.glob("*.png"))


def load_project_metadata(project_path: Path) -> Dict:
    """프로젝트 메타데이터 로드"""
    metadata_path = Path(project_path) / "metadata.json"
    if metadata_path.exists():
        with open(metadata_path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "name": Path(project_path).name,
        "created_at": "",
        "language": "ko",
        "status": "draft"
    }


def get_project_list() -> List[Dict]:
    """모든 프로젝트 목록 가져오기"""
    projects_dir = Path("projects")
    if not projects_dir.exists():
        return []

    projects = []
    for p in projects_dir.iterdir():
        if p.is_dir() and (p / "metadata.json").exists():
            metadata = load_project_metadata(p)
            metadata["path"] = str(p)
            projects.append(metadata)

    return sorted(projects, key=lambda x: x.get("created_at", ""), reverse=True)


def get_project_status(project_path: Path) -> Dict:
    """프로젝트 진행 상태 확인"""
    project_path = Path(project_path)
    status = {
        "script": False,
        "scene_analysis": False,
        "characters": False,
        "character_images": False,
        "tts": False,
        "image_prompts": False,
        "scene_images": False
    }

    # 스크립트
    scripts_dir = project_path / "scripts"
    if scripts_dir.exists() and list(scripts_dir.glob("*.txt")):
        status["script"] = True

    # 씬 분석
    if (project_path / "analysis" / "scenes.json").exists():
        status["scene_analysis"] = True

    # 캐릭터
    chars_file = project_path / "characters" / "characters.json"
    if chars_file.exists():
        with open(chars_file, "r", encoding="utf-8") as f:
            chars = json.load(f)
            if chars:
                status["characters"] = True

    # 캐릭터 이미지
    char_images = project_path / "characters" / "images"
    if char_images.exists() and list(char_images.glob("*.png")):
        status["character_images"] = True

    # TTS
    audio_dir = project_path / "audio"
    if audio_dir.exists() and list(audio_dir.glob("*.mp3")):
        status["tts"] = True

    # 이미지 프롬프트
    prompts_dir = project_path / "prompts"
    if (prompts_dir / "scene_prompts.json").exists() or (prompts_dir / "image_prompts.json").exists():
        status["image_prompts"] = True

    # 씬 이미지
    scene_images = project_path / "images" / "scenes"
    content_images = project_path / "images" / "content"
    if (scene_images.exists() and list(scene_images.glob("*.png"))) or \
       (content_images.exists() and list(content_images.glob("*.png"))):
        status["scene_images"] = True

    return status
