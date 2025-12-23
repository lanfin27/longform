# -*- coding: utf-8 -*-
"""
캐릭터-인포그래픽 동영상 합성 모듈

기능:
1. 캐릭터 PNG 이미지를 인포그래픽 동영상 위에 오버레이
2. 위치/크기/투명도 조절
3. 일괄 합성 처리
4. FFmpeg 기반 합성

변경사항 (v1.0):
- 초기 버전
- FFmpeg overlay 필터 사용
- CharacterPosition, CompositionConfig 데이터클래스
- CharacterCompositor 클래스

작성: 2025-12
"""

import os
import subprocess
import json
from pathlib import Path
from dataclasses import dataclass, asdict, field
from typing import List, Dict, Optional, Callable, Tuple
from enum import Enum


class PositionPreset(Enum):
    """캐릭터 위치 프리셋"""
    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"
    BOTTOM_LEFT = "bottom_left"
    BOTTOM_CENTER = "bottom_center"
    BOTTOM_RIGHT = "bottom_right"
    CUSTOM = "custom"


@dataclass
class CharacterPosition:
    """캐릭터 위치 및 크기 설정"""
    x: int = 0              # X 좌표 (픽셀 또는 비율)
    y: int = 0              # Y 좌표 (픽셀 또는 비율)
    scale: float = 1.0      # 크기 비율 (1.0 = 원본)
    opacity: float = 1.0    # 투명도 (1.0 = 불투명)
    preset: str = "right"   # 위치 프리셋
    anchor: str = "bottom"  # 앵커 포인트 (bottom, center, top)

    def to_ffmpeg_position(self, video_width: int, video_height: int, char_width: int, char_height: int) -> Tuple[str, str]:
        """FFmpeg overlay 좌표 계산"""
        # 스케일 적용된 캐릭터 크기
        scaled_w = int(char_width * self.scale)
        scaled_h = int(char_height * self.scale)

        # 프리셋별 좌표 계산
        preset = self.preset.lower()

        if preset == "left":
            x = int(video_width * 0.05)
            y = video_height - scaled_h - int(video_height * 0.05)
        elif preset == "center":
            x = (video_width - scaled_w) // 2
            y = video_height - scaled_h - int(video_height * 0.05)
        elif preset == "right":
            x = video_width - scaled_w - int(video_width * 0.05)
            y = video_height - scaled_h - int(video_height * 0.05)
        elif preset == "bottom_left":
            x = int(video_width * 0.02)
            y = video_height - scaled_h
        elif preset == "bottom_center":
            x = (video_width - scaled_w) // 2
            y = video_height - scaled_h
        elif preset == "bottom_right":
            x = video_width - scaled_w - int(video_width * 0.02)
            y = video_height - scaled_h
        elif preset == "custom":
            x = self.x
            y = self.y
        else:
            # 기본값: 오른쪽 하단
            x = video_width - scaled_w - int(video_width * 0.05)
            y = video_height - scaled_h - int(video_height * 0.05)

        return str(x), str(y)


@dataclass
class CompositionConfig:
    """합성 설정"""
    character_image_path: str           # 캐릭터 PNG 경로
    video_path: str                     # 인포그래픽 비디오 경로
    output_path: str                    # 출력 경로
    position: CharacterPosition = None  # 위치 설정
    fade_in_duration: float = 0.0       # 페이드인 (초)
    fade_out_duration: float = 0.0      # 페이드아웃 (초)
    start_time: float = 0.0             # 캐릭터 등장 시작 시간

    def __post_init__(self):
        if self.position is None:
            self.position = CharacterPosition()


def check_ffmpeg_available() -> Tuple[bool, str]:
    """FFmpeg 사용 가능 여부 확인"""
    try:
        result = subprocess.run(
            ["ffmpeg", "-version"],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='ignore',
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        if result.returncode == 0:
            version_line = result.stdout.split('\n')[0]
            return True, version_line
        return False, "FFmpeg 실행 실패"
    except FileNotFoundError:
        return False, "FFmpeg이 설치되지 않았습니다"
    except Exception as e:
        return False, str(e)


def check_ffprobe_available() -> Tuple[bool, str]:
    """FFprobe 사용 가능 여부 확인"""
    try:
        result = subprocess.run(
            ["ffprobe", "-version"],
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='ignore',
            timeout=10,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
        )
        if result.returncode == 0:
            return True, "OK"
        return False, "FFprobe 실행 실패"
    except FileNotFoundError:
        return False, "FFprobe가 설치되지 않았습니다"
    except Exception as e:
        return False, str(e)


class CharacterCompositor:
    """캐릭터-인포그래픽 동영상 합성기"""

    def __init__(self, output_dir: str = "outputs/composed_videos"):
        """
        Args:
            output_dir: 합성된 비디오 출력 디렉토리
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # FFmpeg 확인
        ok, msg = check_ffmpeg_available()
        if not ok:
            raise RuntimeError(f"FFmpeg 필요: {msg}")

        print(f"[CharacterCompositor] 초기화 완료 - 출력 디렉토리: {self.output_dir}")

    def get_video_info(self, video_path: str) -> Dict:
        """
        비디오 정보 가져오기 (FFprobe 사용)

        Returns:
            {"width": 1920, "height": 1080, "duration": 10.0, "fps": 30}
        """
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            video_path
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore',
                timeout=30,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )

            if result.returncode != 0:
                return {"width": 1920, "height": 1080, "duration": 10.0, "fps": 30}

            data = json.loads(result.stdout)

            # 비디오 스트림 찾기
            video_stream = None
            for stream in data.get("streams", []):
                if stream.get("codec_type") == "video":
                    video_stream = stream
                    break

            if not video_stream:
                return {"width": 1920, "height": 1080, "duration": 10.0, "fps": 30}

            # FPS 파싱
            fps_str = video_stream.get("r_frame_rate", "30/1")
            try:
                if "/" in fps_str:
                    num, den = map(int, fps_str.split("/"))
                    fps = num / den if den > 0 else 30
                else:
                    fps = float(fps_str)
            except:
                fps = 30

            return {
                "width": int(video_stream.get("width", 1920)),
                "height": int(video_stream.get("height", 1080)),
                "duration": float(data.get("format", {}).get("duration", 10.0)),
                "fps": fps
            }
        except Exception as e:
            print(f"[CharacterCompositor] 비디오 정보 조회 실패: {e}")
            return {"width": 1920, "height": 1080, "duration": 10.0, "fps": 30}

    def get_image_info(self, image_path: str) -> Dict:
        """
        이미지 정보 가져오기 (FFprobe 사용)

        Returns:
            {"width": 500, "height": 800}
        """
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_streams",
            image_path
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore',
                timeout=10,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )

            if result.returncode != 0:
                return {"width": 500, "height": 800}

            data = json.loads(result.stdout)

            for stream in data.get("streams", []):
                if stream.get("codec_type") == "video":
                    return {
                        "width": int(stream.get("width", 500)),
                        "height": int(stream.get("height", 800))
                    }

            return {"width": 500, "height": 800}
        except Exception as e:
            print(f"[CharacterCompositor] 이미지 정보 조회 실패: {e}")
            return {"width": 500, "height": 800}

    def compose_single(
        self,
        video_path: str,
        character_image_path: str,
        output_path: str = None,
        position: CharacterPosition = None,
        fade_in: float = 0.5,
        fade_out: float = 0.5
    ) -> Tuple[bool, str]:
        """
        단일 비디오에 캐릭터 합성

        Args:
            video_path: 인포그래픽 비디오 경로
            character_image_path: 캐릭터 PNG 이미지 경로
            output_path: 출력 경로 (None이면 자동 생성)
            position: 위치 설정 (None이면 기본값)
            fade_in: 페이드인 시간 (초)
            fade_out: 페이드아웃 시간 (초)

        Returns:
            (success, output_path or error_message)
        """
        # 파일 존재 확인
        if not os.path.exists(video_path):
            return False, f"비디오 파일 없음: {video_path}"

        if not os.path.exists(character_image_path):
            return False, f"캐릭터 이미지 없음: {character_image_path}"

        # 기본값 설정
        if position is None:
            position = CharacterPosition(preset="right", scale=0.35)

        if output_path is None:
            video_name = Path(video_path).stem
            char_name = Path(character_image_path).stem
            output_path = str(self.output_dir / f"{video_name}_with_{char_name}.mp4")

        # 비디오 및 이미지 정보
        video_info = self.get_video_info(video_path)
        image_info = self.get_image_info(character_image_path)

        vw, vh = video_info["width"], video_info["height"]
        iw, ih = image_info["width"], image_info["height"]
        duration = video_info["duration"]

        # 스케일된 이미지 크기
        scaled_w = int(iw * position.scale)
        scaled_h = int(ih * position.scale)

        # 위치 계산
        x_pos, y_pos = position.to_ffmpeg_position(vw, vh, iw, ih)

        print(f"[CharacterCompositor] 합성 시작:")
        print(f"  비디오: {vw}x{vh}, {duration:.1f}초")
        print(f"  캐릭터: {iw}x{ih} → {scaled_w}x{scaled_h}")
        print(f"  위치: ({x_pos}, {y_pos})")

        # FFmpeg 필터 구성
        # 1. 캐릭터 이미지 스케일 조정
        # 2. 알파 채널로 오버레이
        # 3. 페이드인/아웃 효과

        filter_parts = []

        # 이미지 스케일
        filter_parts.append(f"[1:v]scale={scaled_w}:{scaled_h}[scaled]")

        # 페이드 효과
        if fade_in > 0 or fade_out > 0:
            fade_filter = "[scaled]"
            if fade_in > 0:
                fade_filter += f"fade=t=in:st=0:d={fade_in}:alpha=1"
                if fade_out > 0:
                    fade_out_start = max(0, duration - fade_out)
                    fade_filter += f",fade=t=out:st={fade_out_start}:d={fade_out}:alpha=1"
            elif fade_out > 0:
                fade_out_start = max(0, duration - fade_out)
                fade_filter += f"fade=t=out:st={fade_out_start}:d={fade_out}:alpha=1"
            fade_filter += "[faded]"
            filter_parts.append(fade_filter)
            overlay_input = "[faded]"
        else:
            overlay_input = "[scaled]"

        # 오버레이
        filter_parts.append(f"[0:v]{overlay_input}overlay={x_pos}:{y_pos}:format=auto[out]")

        filter_complex = ";".join(filter_parts)

        # FFmpeg 명령
        cmd = [
            "ffmpeg",
            "-y",
            "-i", video_path,
            "-i", character_image_path,
            "-filter_complex", filter_complex,
            "-map", "[out]",
            "-map", "0:a?",  # 오디오가 있으면 복사
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            output_path
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='ignore',
                timeout=120,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )

            if result.returncode != 0:
                print(f"[CharacterCompositor] FFmpeg 오류: {result.stderr}")
                return False, result.stderr

            if os.path.exists(output_path):
                print(f"[CharacterCompositor] 합성 완료: {output_path}")
                return True, output_path
            else:
                return False, "출력 파일 생성 실패"

        except subprocess.TimeoutExpired:
            return False, "합성 시간 초과 (120초)"
        except Exception as e:
            return False, str(e)

    def compose_batch(
        self,
        configs: List[CompositionConfig],
        progress_callback: Callable[[int, int, str], None] = None
    ) -> Dict[str, Tuple[bool, str]]:
        """
        여러 비디오 일괄 합성

        Args:
            configs: 합성 설정 리스트
            progress_callback: 진행 콜백 (current, total, message)

        Returns:
            {video_path: (success, output_path or error), ...}
        """
        results = {}
        total = len(configs)

        for i, config in enumerate(configs):
            if progress_callback:
                progress_callback(i + 1, total, f"합성 중: {Path(config.video_path).name}")

            success, result = self.compose_single(
                video_path=config.video_path,
                character_image_path=config.character_image_path,
                output_path=config.output_path,
                position=config.position,
                fade_in=config.fade_in_duration,
                fade_out=config.fade_out_duration
            )

            results[config.video_path] = (success, result)

        if progress_callback:
            success_count = sum(1 for s, _ in results.values() if s)
            progress_callback(total, total, f"완료: {success_count}/{total} 성공")

        return results

    def compose_all_with_default(
        self,
        video_dir: str,
        character_image_path: str,
        position: CharacterPosition = None,
        fade_in: float = 0.5,
        fade_out: float = 0.5,
        progress_callback: Callable[[int, int, str], None] = None
    ) -> Dict[str, Tuple[bool, str]]:
        """
        디렉토리 내 모든 비디오에 동일 캐릭터 합성

        Args:
            video_dir: 비디오 디렉토리
            character_image_path: 캐릭터 이미지 경로
            position: 위치 설정
            fade_in: 페이드인 시간
            fade_out: 페이드아웃 시간
            progress_callback: 진행 콜백

        Returns:
            {video_path: (success, output_path or error), ...}
        """
        video_dir = Path(video_dir)
        if not video_dir.exists():
            return {}

        # MP4 파일 목록
        video_files = list(video_dir.glob("*.mp4"))

        if not video_files:
            print(f"[CharacterCompositor] {video_dir}에 비디오 없음")
            return {}

        # 기본 위치 설정
        if position is None:
            position = CharacterPosition(preset="right", scale=0.35)

        # 설정 생성
        configs = []
        for video_path in video_files:
            output_name = f"{video_path.stem}_composed.mp4"
            output_path = str(self.output_dir / output_name)

            config = CompositionConfig(
                character_image_path=character_image_path,
                video_path=str(video_path),
                output_path=output_path,
                position=position,
                fade_in_duration=fade_in,
                fade_out_duration=fade_out
            )
            configs.append(config)

        return self.compose_batch(configs, progress_callback)

    def compose_scene_with_character(
        self,
        scene_id: int,
        scene_video_path: str,
        character_name: str,
        character_image_path: str,
        position_preset: str = "right",
        scale: float = 0.35
    ) -> Tuple[bool, str]:
        """
        특정 씬에 캐릭터 합성 (편의 메서드)

        Args:
            scene_id: 씬 번호
            scene_video_path: 씬 비디오 경로
            character_name: 캐릭터 이름 (파일명용)
            character_image_path: 캐릭터 PNG 경로
            position_preset: 위치 프리셋
            scale: 크기 비율

        Returns:
            (success, output_path or error)
        """
        position = CharacterPosition(preset=position_preset, scale=scale)

        output_name = f"scene_{scene_id:02d}_{character_name}_composed.mp4"
        output_path = str(self.output_dir / output_name)

        return self.compose_single(
            video_path=scene_video_path,
            character_image_path=character_image_path,
            output_path=output_path,
            position=position
        )


# ============================================
# 유틸리티 함수
# ============================================

def get_position_presets() -> Dict[str, Dict]:
    """위치 프리셋 목록 반환"""
    return {
        "left": {"name": "왼쪽 하단", "desc": "화면 왼쪽 하단에 배치"},
        "center": {"name": "가운데 하단", "desc": "화면 가운데 하단에 배치"},
        "right": {"name": "오른쪽 하단", "desc": "화면 오른쪽 하단에 배치 (기본)"},
        "bottom_left": {"name": "좌측 끝", "desc": "화면 좌측 끝에 배치"},
        "bottom_center": {"name": "중앙 끝", "desc": "화면 중앙 끝에 배치"},
        "bottom_right": {"name": "우측 끝", "desc": "화면 우측 끝에 배치"},
    }


def get_scale_presets() -> Dict[str, float]:
    """크기 프리셋 목록 반환"""
    return {
        "작게": 0.25,
        "보통": 0.35,
        "크게": 0.45,
        "아주 크게": 0.55,
    }


if __name__ == "__main__":
    # 테스트
    ok, msg = check_ffmpeg_available()
    print(f"FFmpeg: {'OK' if ok else 'FAIL'} - {msg}")

    ok, msg = check_ffprobe_available()
    print(f"FFprobe: {'OK' if ok else 'FAIL'} - {msg}")

    print("\n위치 프리셋:")
    for key, value in get_position_presets().items():
        print(f"  {key}: {value['name']}")
