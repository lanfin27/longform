# -*- coding: utf-8 -*-
"""
인포그래픽 렌더러

HTML 씬을 이미지로 렌더링

지원 기능:
- Playwright를 사용한 HTML 렌더링
- 씬별 이미지 생성
- 썸네일 생성
- 배치 렌더링
"""

import os
import asyncio
import base64
from typing import Dict, List, Optional, Tuple, Callable
from pathlib import Path
from PIL import Image
import io
import tempfile

from utils.models.infographic import InfographicScene, InfographicData


class InfographicRenderer:
    """인포그래픽 HTML 렌더러"""

    # 기본 설정
    DEFAULT_WIDTH = 1920
    DEFAULT_HEIGHT = 1080
    THUMBNAIL_WIDTH = 320
    THUMBNAIL_HEIGHT = 180

    # HTML 템플릿
    HTML_TEMPLATE = """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width={width}, height={height}">
        <style>
            * {{
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }}
            html, body {{
                width: {width}px;
                height: {height}px;
                overflow: hidden;
                font-family: 'Pretendard', 'Apple SD Gothic Neo', 'Malgun Gothic', sans-serif;
                background: {background};
            }}
            .scene-container {{
                width: 100%;
                height: 100%;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 40px;
            }}
            .scene-content {{
                width: 100%;
                height: 100%;
            }}
            {custom_css}
        </style>
        {head_extra}
    </head>
    <body>
        <div class="scene-container">
            <div class="scene-content">
                {content}
            </div>
        </div>
        {scripts}
    </body>
    </html>
    """

    def __init__(
        self,
        width: int = None,
        height: int = None,
        background: str = "#ffffff",
        custom_css: str = "",
        head_extra: str = "",
        scripts: str = ""
    ):
        """
        Args:
            width: 렌더링 너비 (기본 1920)
            height: 렌더링 높이 (기본 1080)
            background: 배경색
            custom_css: 추가 CSS
            head_extra: 추가 head 콘텐츠 (폰트, 스크립트 등)
            scripts: 추가 스크립트
        """
        self.width = width or self.DEFAULT_WIDTH
        self.height = height or self.DEFAULT_HEIGHT
        self.background = background
        self.custom_css = custom_css
        self.head_extra = head_extra
        self.scripts = scripts

        self.browser = None
        self.context = None
        self.last_error: Optional[str] = None

    async def _ensure_browser(self):
        """브라우저 인스턴스 확보"""
        if self.browser is None:
            try:
                from playwright.async_api import async_playwright
                self._playwright = await async_playwright().start()
                self.browser = await self._playwright.chromium.launch(
                    headless=True,
                    args=['--disable-web-security', '--disable-features=VizDisplayCompositor']
                )
                self.context = await self.browser.new_context(
                    viewport={'width': self.width, 'height': self.height},
                    device_scale_factor=2  # 고해상도
                )
            except Exception as e:
                self.last_error = f"Playwright 초기화 실패: {e}"
                raise

    async def _close_browser(self):
        """브라우저 종료"""
        if self.context:
            await self.context.close()
            self.context = None
        if self.browser:
            await self.browser.close()
            self.browser = None
        if hasattr(self, '_playwright') and self._playwright:
            await self._playwright.stop()
            self._playwright = None

    def _create_full_html(self, scene_html: str) -> str:
        """씬 HTML을 완전한 HTML 문서로 변환"""
        return self.HTML_TEMPLATE.format(
            width=self.width,
            height=self.height,
            background=self.background,
            custom_css=self.custom_css,
            head_extra=self.head_extra,
            content=scene_html,
            scripts=self.scripts
        )

    async def render_scene(
        self,
        scene: InfographicScene,
        output_path: str,
        create_thumbnail: bool = True
    ) -> Tuple[bool, Optional[str]]:
        """
        단일 씬 렌더링

        Args:
            scene: 렌더링할 씬
            output_path: 출력 이미지 경로
            create_thumbnail: 썸네일 생성 여부

        Returns:
            (성공 여부, 오류 메시지)
        """
        try:
            await self._ensure_browser()

            # HTML 생성
            full_html = self._create_full_html(scene.html_content)

            # 페이지 생성 및 렌더링
            page = await self.context.new_page()

            try:
                await page.set_content(full_html, wait_until='networkidle')

                # 스크립트 실행 대기 (차트 등)
                await asyncio.sleep(0.5)

                # 스크린샷 캡처
                await page.screenshot(
                    path=output_path,
                    type='png',
                    full_page=False
                )

                # 썸네일 생성
                if create_thumbnail:
                    thumb_path = self._get_thumbnail_path(output_path)
                    await self._create_thumbnail(output_path, thumb_path)
                    scene.thumbnail_path = thumb_path

                scene.image_path = output_path
                scene.is_rendered = True
                scene.render_error = None

                return True, None

            finally:
                await page.close()

        except Exception as e:
            error_msg = f"렌더링 실패: {e}"
            scene.render_error = error_msg
            scene.is_rendered = False
            return False, error_msg

    async def render_all_scenes(
        self,
        infographic_data: InfographicData,
        output_dir: str,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> Tuple[int, int]:
        """
        모든 씬 렌더링

        Args:
            infographic_data: 인포그래픽 데이터
            output_dir: 출력 디렉토리
            progress_callback: 진행 콜백 (current, total, message)

        Returns:
            (성공 수, 실패 수)
        """
        os.makedirs(output_dir, exist_ok=True)

        success_count = 0
        fail_count = 0
        total = len(infographic_data.scenes)

        try:
            await self._ensure_browser()

            for i, scene in enumerate(infographic_data.scenes):
                if progress_callback:
                    progress_callback(i + 1, total, f"씬 {scene.scene_number} 렌더링 중...")

                output_path = os.path.join(
                    output_dir,
                    f"infographic_scene_{scene.scene_number:03d}.png"
                )

                success, error = await self.render_scene(scene, output_path)

                if success:
                    success_count += 1
                else:
                    fail_count += 1
                    print(f"[InfographicRenderer] 씬 {scene.scene_number} 실패: {error}")

        finally:
            await self._close_browser()

        return success_count, fail_count

    async def render_html_string(
        self,
        html_content: str,
        output_path: str
    ) -> Tuple[bool, Optional[str]]:
        """
        HTML 문자열을 이미지로 렌더링

        Args:
            html_content: HTML 콘텐츠
            output_path: 출력 경로

        Returns:
            (성공 여부, 오류 메시지)
        """
        try:
            await self._ensure_browser()

            full_html = self._create_full_html(html_content)
            page = await self.context.new_page()

            try:
                await page.set_content(full_html, wait_until='networkidle')
                await asyncio.sleep(0.5)
                await page.screenshot(path=output_path, type='png')
                return True, None
            finally:
                await page.close()

        except Exception as e:
            return False, str(e)
        finally:
            await self._close_browser()

    async def render_to_base64(
        self,
        html_content: str
    ) -> Tuple[Optional[str], Optional[str]]:
        """
        HTML을 Base64 이미지로 렌더링

        Args:
            html_content: HTML 콘텐츠

        Returns:
            (base64 문자열, 오류 메시지)
        """
        try:
            await self._ensure_browser()

            full_html = self._create_full_html(html_content)
            page = await self.context.new_page()

            try:
                await page.set_content(full_html, wait_until='networkidle')
                await asyncio.sleep(0.5)
                screenshot_bytes = await page.screenshot(type='png')
                base64_str = base64.b64encode(screenshot_bytes).decode('utf-8')
                return base64_str, None
            finally:
                await page.close()

        except Exception as e:
            return None, str(e)
        finally:
            await self._close_browser()

    def _get_thumbnail_path(self, image_path: str) -> str:
        """썸네일 경로 생성"""
        path = Path(image_path)
        return str(path.parent / f"{path.stem}_thumb{path.suffix}")

    async def _create_thumbnail(self, source_path: str, thumb_path: str):
        """썸네일 생성"""
        try:
            with Image.open(source_path) as img:
                img.thumbnail((self.THUMBNAIL_WIDTH, self.THUMBNAIL_HEIGHT), Image.Resampling.LANCZOS)
                img.save(thumb_path, 'PNG')
        except Exception as e:
            print(f"[InfographicRenderer] 썸네일 생성 실패: {e}")


# 동기 래퍼 클래스
class SyncInfographicRenderer:
    """동기 API를 위한 래퍼"""

    def __init__(self, **kwargs):
        self.renderer = InfographicRenderer(**kwargs)

    def render_scene(
        self,
        scene: InfographicScene,
        output_path: str,
        create_thumbnail: bool = True
    ) -> Tuple[bool, Optional[str]]:
        """씬 렌더링 (동기)"""
        return asyncio.run(
            self.renderer.render_scene(scene, output_path, create_thumbnail)
        )

    def render_all_scenes(
        self,
        infographic_data: InfographicData,
        output_dir: str,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> Tuple[int, int]:
        """모든 씬 렌더링 (동기)"""
        return asyncio.run(
            self.renderer.render_all_scenes(infographic_data, output_dir, progress_callback)
        )

    def render_html_string(
        self,
        html_content: str,
        output_path: str
    ) -> Tuple[bool, Optional[str]]:
        """HTML 렌더링 (동기)"""
        return asyncio.run(
            self.renderer.render_html_string(html_content, output_path)
        )

    def render_to_base64(
        self,
        html_content: str
    ) -> Tuple[Optional[str], Optional[str]]:
        """Base64 렌더링 (동기)"""
        return asyncio.run(
            self.renderer.render_to_base64(html_content)
        )


def render_infographic_scenes(
    infographic_data: InfographicData,
    output_dir: str,
    progress_callback: Optional[Callable[[int, int, str], None]] = None,
    **renderer_kwargs
) -> Tuple[int, int]:
    """
    인포그래픽 씬 렌더링 (헬퍼 함수)

    Args:
        infographic_data: 인포그래픽 데이터
        output_dir: 출력 디렉토리
        progress_callback: 진행 콜백
        **renderer_kwargs: 렌더러 설정

    Returns:
        (성공 수, 실패 수)
    """
    renderer = SyncInfographicRenderer(**renderer_kwargs)
    return renderer.render_all_scenes(infographic_data, output_dir, progress_callback)


def get_infographic_renderer(**kwargs) -> SyncInfographicRenderer:
    """렌더러 인스턴스 생성"""
    return SyncInfographicRenderer(**kwargs)
