"""
utils/timeline_composite.py

타임라인 뷰 이미지 합성 유틸리티
- 이미지 실시간 동기화
- 배경 + 실사이미지 합성
- 묶음 대체 기능

v1.0: 2025-01 초기 구현
"""

import os
import glob
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
from PIL import Image, ImageFilter, ImageEnhance
import tempfile


# ═══════════════════════════════════════════════════════════════════════════════
# 이미지 검색 함수
# ═══════════════════════════════════════════════════════════════════════════════

def get_latest_scene_image(scene: Dict, project_path: str) -> Optional[str]:
    """
    씬의 최신 이미지 경로 반환 (카드뷰와 동기화)

    검색 우선순위 (v2.2: 인포그래픽 이미지 추가):
    0. 인포그래픽 이미지 (infographic_image_path - Step5에서 설정, 최우선)
    1. 실사 대체 이미지 (real_image_path - Step3에서 설정)
    2. 합성 이미지 (composited_image_path - Step3에서 설정)
    3. 기존 합성 이미지 (composite_image_path, nano_composite_image, composite_path)
    4. 실사 합성 이미지 (composite_realshot)
    5. 실사 이미지 (realshot)
    6. 비디오 배경 썸네일 (video_thumbnails)
    7. 인포그래픽 디렉토리 이미지 (infographics/images/)
    8. 씬 이미지 (scenes/scene_XXX.png)
    9. 배경 이미지 (backgrounds)

    Args:
        scene: 씬 딕셔너리
        project_path: 프로젝트 경로

    Returns:
        최신 이미지 경로 또는 None
    """
    scene_id = scene.get('scene_id') or scene.get('scene_number') or scene.get('id', 0)
    scene_num_str = f"{scene_id:03d}"

    # 1. 씬 데이터에서 직접 경로 확인 (v2.3: 타임라인 대체 최우선)
    direct_paths = [
        scene.get('replaced_image_path'),      # v2.3: 타임라인 드래그앤드롭 대체 (최우선)
        scene.get('infographic_image_path'),   # v2.2: Step5 인포그래픽 이미지
        scene.get('real_image_path'),          # v2.0: Step3 실사 대체 이미지
        scene.get('composited_image_path'),    # v2.0: Step3 합성 이미지
        scene.get('composite_image_path'),
        scene.get('nano_composite_image'),
        scene.get('composite_path'),
        scene.get('image_path'),
        scene.get('background_image'),
    ]

    for path in direct_paths:
        if path and os.path.exists(path):
            return str(path)

    # 2. 파일 시스템 검색
    project = Path(project_path) if isinstance(project_path, str) else project_path

    search_patterns = [
        # v2.3: 타임라인 대체 이미지 (최우선)
        f"images/replaced/scene_{scene_num_str}_replaced.*",
        # v2.2: 인포그래픽 이미지
        f"infographics/images/infographic_scene_{scene_num_str}*.png",
        # v2.0: 실사 대체 이미지 (Step3에서 생성, 타임스탬프 포함)
        f"images/composited/composited_{scene_num_str}_*.png",
        f"images/composited/composited_{scene_num_str}_*.jpg",
        # 합성 이미지
        f"images/composite_realshot/scene_{scene_num_str}_composite.png",
        f"images/nano_composite/composite_scene_{scene_num_str}_*.png",
        f"images/nano_composite/composite_scene_{scene_num_str}.png",
        f"images/composites/composite_{scene_num_str}.png",
        # 실사 이미지
        f"images/realshot/scene_{scene_num_str}_realshot.*",
        f"images/realshot/scene_{scene_num_str}.*",
        # 비디오 배경 썸네일 (v2.1)
        f"images/video_thumbnails/scene_{scene_num_str}_video_thumb.*",
        # 한글 텍스트 이미지 (Step 1에서 생성)
        f"images/korean_text/korean_text_scene_{scene_num_str}_*.png",
        # 씬 이미지
        f"images/scenes/scene_{scene_num_str}.png",
        f"images/scenes/scene_{scene_num_str}.*",
        f"images/scenes/real_scene_{scene_num_str}.*",
        f"images/scenes/{scene_num_str}_scene.*",
        # 배경 이미지
        f"images/backgrounds/bg_scene_{scene_num_str}_*.png",
        f"images/backgrounds/scene_{scene_num_str}_*.png",
    ]

    for pattern in search_patterns:
        full_pattern = str(project / pattern)
        matches = glob.glob(full_pattern)

        if matches:
            # 가장 최근 수정된 파일 반환
            latest = max(matches, key=os.path.getmtime)
            return latest

    return None


def get_existing_scene_background(scene_num: int, project_path: str) -> Optional[str]:
    """기존 씬 배경 이미지 경로 찾기"""

    scene_num_str = f"{scene_num:03d}"
    project = Path(project_path) if isinstance(project_path, str) else project_path

    patterns = [
        f"images/backgrounds/bg_scene_{scene_num_str}_*.png",
        f"images/scenes/scene_{scene_num_str}.*",
        f"images/composite/scene_{scene_num_str}_composite.png",
    ]

    for pattern in patterns:
        full_pattern = str(project / pattern)
        matches = glob.glob(full_pattern)

        if matches:
            return max(matches, key=os.path.getmtime)

    return None


# ═══════════════════════════════════════════════════════════════════════════════
# 이미지 처리 함수
# ═══════════════════════════════════════════════════════════════════════════════

def resize_with_aspect(img: Image.Image, max_width: int, max_height: int) -> Image.Image:
    """비율 유지하며 리사이즈"""

    original_w, original_h = img.size
    ratio = min(max_width / original_w, max_height / original_h)

    new_w = int(original_w * ratio)
    new_h = int(original_h * ratio)

    return img.resize((new_w, new_h), Image.LANCZOS)


def adjust_opacity(img: Image.Image, opacity: float) -> Image.Image:
    """이미지 투명도 조절 (0~1)"""

    if img.mode != 'RGBA':
        img = img.convert('RGBA')

    # 알파 채널 조절
    r, g, b, a = img.split()
    a = a.point(lambda x: int(x * opacity))

    return Image.merge('RGBA', (r, g, b, a))


def darken_image(img: Image.Image, amount: float) -> Image.Image:
    """이미지 어둡게 처리 (amount: 0~1)"""

    enhancer = ImageEnhance.Brightness(img)
    return enhancer.enhance(1 - amount)


def hex_to_rgb(hex_color: str) -> Tuple[int, int, int]:
    """HEX 색상을 RGB 튜플로 변환"""

    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))


def calculate_paste_position(
    canvas_size: Tuple[int, int],
    image_size: Tuple[int, int],
    position: str,
    margin: int = 20
) -> Tuple[int, int]:
    """붙여넣기 위치 계산"""

    canvas_w, canvas_h = canvas_size
    img_w, img_h = image_size

    positions = {
        "center": ((canvas_w - img_w) // 2, (canvas_h - img_h) // 2),
        "top": ((canvas_w - img_w) // 2, margin),
        "bottom": ((canvas_w - img_w) // 2, canvas_h - img_h - margin),
        "left": (margin, (canvas_h - img_h) // 2),
        "right": (canvas_w - img_w - margin, (canvas_h - img_h) // 2),
        "top-left": (margin, margin),
        "top-right": (canvas_w - img_w - margin, margin),
        "bottom-left": (margin, canvas_h - img_h - margin),
        "bottom-right": (canvas_w - img_w - margin, canvas_h - img_h - margin),
    }

    return positions.get(position, positions["center"])


# ═══════════════════════════════════════════════════════════════════════════════
# 합성 이미지 생성
# ═══════════════════════════════════════════════════════════════════════════════

def create_composite_realshot(
    realshot_source: Union[str, bytes, 'UploadedFile'],
    scene_num: int,
    project_path: str,
    settings: Dict
) -> Optional[str]:
    """
    배경 + 실사 이미지 합성

    Args:
        realshot_source: 실사 이미지 (파일 경로, 바이트, 또는 UploadedFile)
        scene_num: 씬 번호
        project_path: 프로젝트 경로
        settings: 합성 설정
            - realshot_width_pct: 실사 가로 비율 (%)
            - realshot_height_pct: 실사 세로 비율 (%)
            - position: 위치 (center, top, bottom, etc.)
            - bg_source: 배경 소스 (existing, upload, color, blur)
            - bg_settings: 배경 추가 설정

    Returns:
        저장된 합성 이미지 경로 또는 None
    """

    # 출력 크기 (1920x1080 또는 프로젝트 설정)
    OUTPUT_WIDTH = settings.get('output_width', 1920)
    OUTPUT_HEIGHT = settings.get('output_height', 1080)

    try:
        # ─────────────────────────────────────────────────────────
        # 1. 실사 이미지 로드
        # ─────────────────────────────────────────────────────────

        if isinstance(realshot_source, str):
            realshot_img = Image.open(realshot_source).convert('RGBA')
        elif hasattr(realshot_source, 'read'):
            # UploadedFile 또는 file-like object
            realshot_img = Image.open(realshot_source).convert('RGBA')
        else:
            # bytes
            import io
            realshot_img = Image.open(io.BytesIO(realshot_source)).convert('RGBA')

        # 실사 이미지 목표 크기
        width_pct = settings.get('realshot_width_pct', 60)
        height_pct = settings.get('realshot_height_pct', 60)

        target_w = int(OUTPUT_WIDTH * width_pct / 100)
        target_h = int(OUTPUT_HEIGHT * height_pct / 100)

        # 비율 유지하며 리사이즈
        realshot_img = resize_with_aspect(realshot_img, target_w, target_h)

        # ─────────────────────────────────────────────────────────
        # 2. 배경 이미지 생성
        # ─────────────────────────────────────────────────────────

        bg_source = settings.get('bg_source', 'existing')
        bg_settings = settings.get('bg_settings', {})

        if bg_source == 'existing':
            # 기존 씬 이미지를 배경으로 사용
            existing_path = get_existing_scene_background(scene_num, project_path)

            if existing_path and os.path.exists(existing_path):
                bg_img = Image.open(existing_path).convert('RGBA')
                bg_img = bg_img.resize((OUTPUT_WIDTH, OUTPUT_HEIGHT), Image.LANCZOS)

                # 투명도 조절
                opacity = bg_settings.get('opacity', 0.3)
                if opacity < 1.0:
                    # 불투명 배경 위에 투명화된 이미지 합성
                    base = Image.new('RGBA', (OUTPUT_WIDTH, OUTPUT_HEIGHT), (0, 0, 0, 255))
                    bg_img = adjust_opacity(bg_img, opacity)
                    base.paste(bg_img, (0, 0), bg_img)
                    bg_img = base

                # 어둡게 처리
                darken_amt = bg_settings.get('darken', 0.2)
                if darken_amt > 0:
                    bg_img = darken_image(bg_img, darken_amt)
            else:
                # 기존 이미지 없으면 검정 배경
                bg_img = Image.new('RGBA', (OUTPUT_WIDTH, OUTPUT_HEIGHT), (0, 0, 0, 255))

        elif bg_source == 'upload':
            # 업로드된 배경 이미지
            bg_file = bg_settings.get('file')

            if bg_file:
                if hasattr(bg_file, 'read'):
                    bg_img = Image.open(bg_file).convert('RGBA')
                else:
                    bg_img = Image.open(bg_file).convert('RGBA')
                bg_img = bg_img.resize((OUTPUT_WIDTH, OUTPUT_HEIGHT), Image.LANCZOS)
            else:
                bg_img = Image.new('RGBA', (OUTPUT_WIDTH, OUTPUT_HEIGHT), (0, 0, 0, 255))

        elif bg_source == 'color':
            # 단색 배경
            color = bg_settings.get('color', '#1a1a2e')
            rgb = hex_to_rgb(color)
            bg_img = Image.new('RGBA', (OUTPUT_WIDTH, OUTPUT_HEIGHT), (*rgb, 255))

        elif bg_source == 'blur':
            # 실사 이미지 블러 처리하여 배경으로
            blur_radius = bg_settings.get('blur_radius', 20)

            # 실사 이미지를 전체 크기로 확대 후 블러
            bg_img = realshot_img.copy()
            bg_img = bg_img.resize((OUTPUT_WIDTH, OUTPUT_HEIGHT), Image.LANCZOS)
            bg_img = bg_img.filter(ImageFilter.GaussianBlur(radius=blur_radius))

            # 약간 어둡게
            bg_img = darken_image(bg_img, 0.3)

        else:
            bg_img = Image.new('RGBA', (OUTPUT_WIDTH, OUTPUT_HEIGHT), (0, 0, 0, 255))

        # ─────────────────────────────────────────────────────────
        # 3. 합성 위치 계산
        # ─────────────────────────────────────────────────────────

        position = settings.get('position', 'center')
        paste_x, paste_y = calculate_paste_position(
            canvas_size=(OUTPUT_WIDTH, OUTPUT_HEIGHT),
            image_size=realshot_img.size,
            position=position
        )

        # ─────────────────────────────────────────────────────────
        # 4. 이미지 합성
        # ─────────────────────────────────────────────────────────

        # 배경 위에 실사 이미지 붙여넣기
        composite = bg_img.copy()
        composite.paste(realshot_img, (paste_x, paste_y), realshot_img)

        # ─────────────────────────────────────────────────────────
        # 5. 저장
        # ─────────────────────────────────────────────────────────

        project = Path(project_path) if isinstance(project_path, str) else project_path
        output_dir = project / 'images' / 'composite_realshot'
        output_dir.mkdir(parents=True, exist_ok=True)

        output_path = output_dir / f'scene_{scene_num:03d}_composite.png'

        # RGB로 변환하여 저장 (PNG)
        composite_rgb = composite.convert('RGB')
        composite_rgb.save(str(output_path), 'PNG', quality=95)

        print(f"[TimelineComposite] 씬 {scene_num} 합성 완료: {output_path}")

        return str(output_path)

    except Exception as e:
        print(f"[TimelineComposite] 합성 오류 (씬 {scene_num}): {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════════
# 묶음(Bundle) 대체
# ═══════════════════════════════════════════════════════════════════════════════

def replace_bundle_scenes(
    realshot_source: Union[str, bytes, 'UploadedFile'],
    scene: Dict,
    all_scenes: List[Dict],
    project_path: str,
    settings: Dict
) -> int:
    """
    묶음 대체 실행 - 같은 bundle_id를 가진 모든 씬 대체

    Args:
        realshot_source: 실사 이미지 소스
        scene: 현재 씬
        all_scenes: 전체 씬 목록
        project_path: 프로젝트 경로
        settings: 합성 설정

    Returns:
        대체된 씬 개수
    """

    bundle_id = scene.get('bundle_id')
    scene_num = scene.get('scene_id') or scene.get('scene_number') or scene.get('id', 0)

    if not bundle_id:
        # 묶음이 없으면 단일 씬만 대체
        result = create_composite_realshot(realshot_source, scene_num, project_path, settings)
        return 1 if result else 0

    # 같은 bundle_id를 가진 모든 씬 찾기
    bundle_scenes = [
        s for s in all_scenes
        if s.get('bundle_id') == bundle_id
    ]

    replaced_count = 0

    # 파일을 메모리에 로드 (여러 번 사용하기 위해)
    if hasattr(realshot_source, 'read'):
        realshot_source.seek(0)
        img_bytes = realshot_source.read()
        realshot_source.seek(0)
    elif isinstance(realshot_source, bytes):
        img_bytes = realshot_source
    else:
        with open(realshot_source, 'rb') as f:
            img_bytes = f.read()

    for bundle_scene in bundle_scenes:
        bundle_scene_num = bundle_scene.get('scene_id') or bundle_scene.get('scene_number') or bundle_scene.get('id', 0)

        # 각 씬에 대해 합성 이미지 생성
        result = create_composite_realshot(
            realshot_source=img_bytes,
            scene_num=bundle_scene_num,
            project_path=project_path,
            settings=settings
        )

        if result:
            replaced_count += 1
            print(f"[Bundle] 씬 {bundle_scene_num} 대체 완료")

    return replaced_count


# ═══════════════════════════════════════════════════════════════════════════════
# 비디오 처리
# ═══════════════════════════════════════════════════════════════════════════════

def extract_video_thumbnail(video_source: Union[str, 'UploadedFile'], scene_num: int, project_path: str) -> Optional[str]:
    """비디오에서 첫 프레임(썸네일) 추출"""

    try:
        import cv2
    except ImportError:
        print("[TimelineComposite] cv2 not available, cannot extract video thumbnail")
        return None

    project = Path(project_path) if isinstance(project_path, str) else project_path

    try:
        # 임시 파일로 저장 (UploadedFile인 경우)
        if hasattr(video_source, 'read'):
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as tmp:
                tmp.write(video_source.read())
                tmp_path = tmp.name
                video_source.seek(0)  # 리셋
        else:
            tmp_path = video_source

        # OpenCV로 비디오 열기
        cap = cv2.VideoCapture(tmp_path)

        if not cap.isOpened():
            return None

        # 첫 프레임 읽기
        ret, frame = cap.read()
        cap.release()

        if not ret:
            return None

        # BGR to RGB
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # PIL Image로 변환
        img = Image.fromarray(frame_rgb)

        # 썸네일 저장
        output_dir = project / 'images' / 'video_thumbnails'
        output_dir.mkdir(parents=True, exist_ok=True)

        output_path = output_dir / f'scene_{scene_num:03d}_video_thumb.png'
        img.save(str(output_path), 'PNG')

        return str(output_path)

    except Exception as e:
        print(f"[TimelineComposite] 비디오 썸네일 추출 오류: {e}")
        return None
    finally:
        # 임시 파일 삭제
        if hasattr(video_source, 'read') and 'tmp_path' in locals():
            try:
                os.unlink(tmp_path)
            except:
                pass


def get_video_info_from_file(video_source: Union[str, 'UploadedFile']) -> Dict:
    """
    비디오 파일 정보 가져오기 (FFprobe 사용)

    character_compositor.py의 get_video_info 패턴을 재사용합니다.

    Args:
        video_source: 비디오 파일 경로 또는 UploadedFile

    Returns:
        {"width": int, "height": int, "duration": float, "fps": float, "temp_path": str or None}
    """
    import subprocess
    import json as json_module

    temp_path = None

    try:
        # UploadedFile인 경우 임시 파일로 저장
        if hasattr(video_source, 'read'):
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as tmp:
                tmp.write(video_source.read())
                temp_path = tmp.name
                video_source.seek(0)  # 파일 포인터 리셋
            video_path = temp_path
        else:
            video_path = str(video_source)

        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            video_path
        ]

        creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='ignore',
            timeout=30,
            creationflags=creationflags
        )

        if result.returncode != 0:
            print(f"[TimelineComposite] ffprobe 실패: {result.stderr[:200]}")
            return {"width": 1920, "height": 1080, "duration": 0, "fps": 30, "temp_path": temp_path}

        data = json_module.loads(result.stdout)

        # 비디오 스트림 찾기
        video_stream = None
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                video_stream = stream
                break

        if not video_stream:
            return {"width": 1920, "height": 1080, "duration": 0, "fps": 30, "temp_path": temp_path}

        # FPS 파싱
        fps_str = video_stream.get("r_frame_rate", "30/1")
        try:
            if "/" in fps_str:
                num, den = map(int, fps_str.split("/"))
                fps = num / den if den > 0 else 30
            else:
                fps = float(fps_str)
        except (ValueError, ZeroDivisionError):
            fps = 30

        return {
            "width": int(video_stream.get("width", 1920)),
            "height": int(video_stream.get("height", 1080)),
            "duration": float(data.get("format", {}).get("duration", 0)),
            "fps": fps,
            "temp_path": temp_path
        }

    except Exception as e:
        print(f"[TimelineComposite] 비디오 정보 추출 오류: {e}")
        return {"width": 1920, "height": 1080, "duration": 0, "fps": 30, "temp_path": temp_path}


def prepare_background_video(
    video_path: str,
    target_duration: float,
    output_path: str,
    loop: bool = False
) -> Optional[str]:
    """
    배경 비디오를 씬 duration에 맞게 트림/루프 처리

    Args:
        video_path: 원본 비디오 경로
        target_duration: 목표 길이 (초)
        output_path: 출력 경로
        loop: True면 비디오가 짧을 때 루프

    Returns:
        출력 파일 경로 또는 None
    """
    import subprocess

    creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0

    # 원본 비디오 길이 확인
    video_info = get_video_info_from_file(video_path)
    video_duration = video_info.get("duration", 0)

    # 임시 파일 정리
    if video_info.get("temp_path"):
        try:
            os.unlink(video_info["temp_path"])
        except OSError:
            pass

    try:
        if video_duration >= target_duration:
            # 비디오가 씬보다 길면 → 트림 (스트림 복사로 빠르게)
            print(f"[TimelineComposite] 비디오 트림: {video_duration:.2f}초 → {target_duration:.2f}초")
            cmd = [
                "ffmpeg", "-y",
                "-i", video_path,
                "-t", str(target_duration),
                "-c", "copy",
                "-an",  # 오디오 제거 (배경이므로)
                output_path
            ]
        elif loop:
            # 비디오가 짧고 루프 요청 → 루프 후 트림
            print(f"[TimelineComposite] 비디오 루프: {video_duration:.2f}초 → {target_duration:.2f}초")
            cmd = [
                "ffmpeg", "-y",
                "-stream_loop", "-1",
                "-i", video_path,
                "-t", str(target_duration),
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "18",
                "-pix_fmt", "yuv420p",
                "-an",
                output_path
            ]
        else:
            # 비디오가 짧고 루프 안 함 → 그대로 복사
            print(f"[TimelineComposite] 비디오 복사: {video_duration:.2f}초 (씬 {target_duration:.2f}초)")
            cmd = [
                "ffmpeg", "-y",
                "-i", video_path,
                "-c", "copy",
                "-an",
                output_path
            ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='ignore',
            timeout=300,
            creationflags=creationflags
        )

        if result.returncode == 0 and os.path.exists(output_path):
            print(f"[TimelineComposite] 배경 비디오 준비 완료: {output_path}")
            return output_path
        else:
            print(f"[TimelineComposite] 배경 비디오 준비 실패: {result.stderr[:300]}")
            return None

    except subprocess.TimeoutExpired:
        print(f"[TimelineComposite] 배경 비디오 준비 타임아웃")
        return None
    except Exception as e:
        print(f"[TimelineComposite] 배경 비디오 준비 오류: {e}")
        return None


def composite_realshot_on_video(
    realshot_source: Union[str, bytes, 'UploadedFile'],
    bg_video_path: str,
    scene_num: int,
    project_path: str,
    settings: Dict
) -> Optional[str]:
    """
    실사이미지를 배경 비디오 위에 합성 → MP4 출력

    Args:
        realshot_source: 실사 이미지 (파일 경로, 바이트, 또는 UploadedFile)
        bg_video_path: 배경 비디오 경로 (이미 트림/루프 처리됨)
        scene_num: 씬 번호
        project_path: 프로젝트 경로
        settings: 합성 설정 dict

    Returns:
        저장된 MP4 경로 또는 None
    """
    import subprocess
    import time as time_module
    import io as io_module

    OUTPUT_WIDTH = settings.get('output_width', 1920)
    OUTPUT_HEIGHT = settings.get('output_height', 1080)
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0

    temp_realshot_path = None

    try:
        # 1. 실사 이미지 로드
        if isinstance(realshot_source, str):
            realshot_img = Image.open(realshot_source).convert('RGBA')
        elif hasattr(realshot_source, 'read'):
            realshot_img = Image.open(realshot_source).convert('RGBA')
            realshot_source.seek(0)
        else:
            realshot_img = Image.open(io_module.BytesIO(realshot_source)).convert('RGBA')

        # 2. 리사이즈
        width_pct = settings.get('realshot_width_pct', 60)
        height_pct = settings.get('realshot_height_pct', 60)
        target_w = int(OUTPUT_WIDTH * width_pct / 100)
        target_h = int(OUTPUT_HEIGHT * height_pct / 100)
        realshot_img = resize_with_aspect(realshot_img, target_w, target_h)

        # 3. 임시 PNG 파일로 저장 (FFmpeg 입력용)
        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp:
            # RGBA → RGB 변환 (투명 영역은 흰색 배경 위에 합성)
            if realshot_img.mode == 'RGBA':
                bg = Image.new('RGBA', realshot_img.size, (0, 0, 0, 0))
                bg.paste(realshot_img, (0, 0), realshot_img)
                bg.save(tmp.name, 'PNG')
            else:
                realshot_img.save(tmp.name, 'PNG')
            temp_realshot_path = tmp.name

        # 4. 위치 계산
        position = settings.get('position', 'center')
        paste_x, paste_y = calculate_paste_position(
            canvas_size=(OUTPUT_WIDTH, OUTPUT_HEIGHT),
            image_size=realshot_img.size,
            position=position
        )

        # 5. 배경 투명도 (밝기 조절)
        bg_opacity = settings.get('bg_opacity', 0.3)

        # FFmpeg filter_complex 구성
        # 배경 비디오 밝기 조절 + 실사이미지 오버레이
        # eq 필터: brightness 범위 -1.0 ~ 1.0 (0 = 원본)
        brightness_adj = bg_opacity - 1.0  # opacity 0.3 → brightness -0.7

        overlay_w = realshot_img.size[0]
        overlay_h = realshot_img.size[1]

        filter_complex = (
            f"[0:v]scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT},"
            f"eq=brightness={brightness_adj:.2f}[bg];"
            f"[1:v]scale={overlay_w}:{overlay_h}[fg];"
            f"[bg][fg]overlay={paste_x}:{paste_y}:format=auto[out]"
        )

        # 6. 출력 경로
        project = Path(project_path) if isinstance(project_path, str) else project_path
        output_dir = project / 'images' / 'composite_realshot'
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = int(time_module.time() * 1000)
        output_path = str(output_dir / f'scene_{scene_num:03d}_bg_video_{timestamp}.mp4')

        # 7. FFmpeg 실행
        cmd = [
            "ffmpeg", "-y",
            "-i", bg_video_path,
            "-i", temp_realshot_path,
            "-filter_complex", filter_complex,
            "-map", "[out]",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-an",
            output_path
        ]

        print(f"[TimelineComposite] 씬 {scene_num}: 비디오 배경 합성 시작")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='ignore',
            timeout=600,
            creationflags=creationflags
        )

        if result.returncode == 0 and os.path.exists(output_path):
            print(f"[TimelineComposite] 씬 {scene_num}: 비디오 배경 합성 완료")
            return output_path
        else:
            print(f"[TimelineComposite] 씬 {scene_num}: FFmpeg 오류 - {result.stderr[:300]}")
            return None

    except subprocess.TimeoutExpired:
        print(f"[TimelineComposite] 씬 {scene_num}: 비디오 합성 타임아웃")
        return None
    except Exception as e:
        print(f"[TimelineComposite] 씬 {scene_num}: 비디오 합성 오류 - {e}")
        return None
    finally:
        # 임시 파일 정리
        if temp_realshot_path and os.path.exists(temp_realshot_path):
            try:
                os.unlink(temp_realshot_path)
            except OSError:
                pass


def composite_infographic_on_video(
    infographic_png_path: str,
    bg_video_source: Union[str, 'UploadedFile'],
    scene_num: int,
    project_path: str,
    settings: Dict
) -> Optional[str]:
    """
    인포그래픽 PNG를 배경 비디오 위에 합성하여 MP4 출력

    Args:
        infographic_png_path: 캡쳐된 인포그래픽 PNG 경로
        bg_video_source: 배경 비디오 경로 또는 UploadedFile
        scene_num: 씬 번호
        project_path: 프로젝트 경로
        settings: 합성 설정 dict
            - output_width/height: 출력 해상도
            - width_pct/height_pct: 인포그래픽 크기 비율
            - position: 위치
            - bg_opacity_pct: 배경 투명도 0-100
            - target_duration: 씬 duration (트림/루프용)
            - loop_video: 짧은 비디오 루프 여부

    Returns:
        저장된 MP4 경로 또는 None
    """
    import subprocess
    import time as time_module

    OUTPUT_WIDTH = settings.get('output_width', 1920)
    OUTPUT_HEIGHT = settings.get('output_height', 1080)
    creationflags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0

    temp_video_path = None
    temp_overlay_path = None
    prepared_video_path = None

    try:
        # 1. UploadedFile → 임시 파일 저장
        if hasattr(bg_video_source, 'read'):
            with tempfile.NamedTemporaryFile(delete=False, suffix='.mp4') as tmp:
                bg_video_source.seek(0)
                tmp.write(bg_video_source.read())
                temp_video_path = tmp.name
            bg_video_source.seek(0)
            video_path = temp_video_path
        else:
            video_path = str(bg_video_source)

        # 2. 배경 비디오 트림/루프 (씬 duration에 맞게)
        target_duration = settings.get('target_duration')
        if target_duration and target_duration > 0:
            project = Path(project_path) if isinstance(project_path, str) else project_path
            prep_dir = project / 'infographics' / 'temp'
            prep_dir.mkdir(parents=True, exist_ok=True)
            prep_output = str(prep_dir / f'bg_prep_scene_{scene_num:03d}.mp4')
            prepared = prepare_background_video(
                video_path, target_duration, prep_output,
                loop=settings.get('loop_video', True)
            )
            if prepared:
                video_path = prepared
                prepared_video_path = prepared

        # 3. 인포그래픽 PNG 로드 및 크기 조정
        infographic_img = Image.open(infographic_png_path).convert('RGBA')

        width_pct = settings.get('width_pct', 60)
        height_pct = settings.get('height_pct', 60)
        target_w = int(OUTPUT_WIDTH * width_pct / 100)
        target_h = int(OUTPUT_HEIGHT * height_pct / 100)
        infographic_img = resize_with_aspect(infographic_img, target_w, target_h)

        # 4. 임시 PNG 저장 (FFmpeg 입력용)
        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp:
            infographic_img.save(tmp.name, 'PNG')
            temp_overlay_path = tmp.name

        # 5. 위치 계산
        position = settings.get('position', 'center')
        paste_x, paste_y = calculate_paste_position(
            canvas_size=(OUTPUT_WIDTH, OUTPUT_HEIGHT),
            image_size=infographic_img.size,
            position=position
        )

        # 6. FFmpeg filter_complex 구성
        bg_opacity_pct = settings.get('bg_opacity_pct', 30)
        brightness_adj = (bg_opacity_pct / 100.0) - 1.0

        overlay_w = infographic_img.size[0]
        overlay_h = infographic_img.size[1]

        filter_complex = (
            f"[0:v]scale={OUTPUT_WIDTH}:{OUTPUT_HEIGHT},"
            f"eq=brightness={brightness_adj:.2f}[bg];"
            f"[1:v]scale={overlay_w}:{overlay_h}[fg];"
            f"[bg][fg]overlay={paste_x}:{paste_y}:format=auto[out]"
        )

        # 7. 출력 경로
        project = Path(project_path) if isinstance(project_path, str) else project_path
        output_dir = project / 'infographics' / 'videos'
        output_dir.mkdir(parents=True, exist_ok=True)

        output_path = str(output_dir / f'infographic_scene_{scene_num:03d}.mp4')

        # 8. FFmpeg 실행
        cmd = [
            "ffmpeg", "-y",
            "-i", video_path,
            "-i", temp_overlay_path,
            "-filter_complex", filter_complex,
            "-map", "[out]",
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-an",
            output_path
        ]

        print(f"[TimelineComposite] 씬 {scene_num}: 인포그래픽 비디오 합성 시작")

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='ignore',
            timeout=600,
            creationflags=creationflags
        )

        if result.returncode == 0 and os.path.exists(output_path):
            print(f"[TimelineComposite] 씬 {scene_num}: 인포그래픽 비디오 합성 완료")
            return output_path
        else:
            print(f"[TimelineComposite] 씬 {scene_num}: FFmpeg 오류 - {result.stderr[:300]}")
            return None

    except subprocess.TimeoutExpired:
        print(f"[TimelineComposite] 씬 {scene_num}: 인포그래픽 비디오 합성 타임아웃")
        return None
    except Exception as e:
        print(f"[TimelineComposite] 씬 {scene_num}: 인포그래픽 비디오 합성 오류 - {e}")
        return None
    finally:
        for p in [temp_video_path, temp_overlay_path, prepared_video_path]:
            if p and os.path.exists(p):
                try:
                    os.unlink(p)
                except OSError:
                    pass


def save_realshot_file(
    uploaded_file: 'UploadedFile',
    scene_num: int,
    project_path: str
) -> Tuple[str, bool]:
    """
    업로드된 파일 저장

    Returns:
        (저장 경로, is_video 여부)
    """

    project = Path(project_path) if isinstance(project_path, str) else project_path

    file_ext = uploaded_file.name.split('.')[-1].lower()
    is_video = file_ext in ['mp4', 'mov', 'avi', 'mkv', 'webm']

    if is_video:
        output_dir = project / 'videos' / 'realshot'
    else:
        output_dir = project / 'images' / 'realshot'

    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / f'scene_{scene_num:03d}_realshot.{file_ext}'

    with open(output_path, 'wb') as f:
        f.write(uploaded_file.getbuffer())

    return str(output_path), is_video


# ═══════════════════════════════════════════════════════════════════════════════
# 기본 설정
# ═══════════════════════════════════════════════════════════════════════════════

DEFAULT_COMPOSITE_SETTINGS = {
    'realshot_width_pct': 60,
    'realshot_height_pct': 60,
    'position': 'center',
    'bg_source': 'existing',
    'bg_settings': {
        'opacity': 0.3,
        'darken': 0.2,
    },
    'output_width': 1920,
    'output_height': 1080,
}

POSITION_OPTIONS = [
    ("center", "중앙"),
    ("top", "상단"),
    ("bottom", "하단"),
    ("left", "좌측"),
    ("right", "우측"),
    ("top-left", "좌상단"),
    ("top-right", "우상단"),
    ("bottom-left", "좌하단"),
    ("bottom-right", "우하단"),
]

BG_SOURCE_OPTIONS = [
    ("existing", "기존 씬 이미지 (투명도 조절)"),
    ("blur", "실사 이미지 블러"),
    ("color", "단색 배경"),
    ("upload", "업로드 이미지"),
    ("video", "업로드 비디오"),
]
