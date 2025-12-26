# -*- coding: utf-8 -*-
"""
썸네일 다운로드 모듈 v1.0

기능:
- 단일/다중 썸네일 다운로드
- ZIP 압축 다운로드
- 파일명 안전 처리
"""

import requests
import zipfile
import io
import re
from typing import List, Dict, Optional
from pathlib import Path
from datetime import datetime


class ThumbnailDownloader:
    """썸네일 다운로더"""

    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        self.session = requests.Session()

    def download_single(self, url: str) -> Optional[bytes]:
        """단일 썸네일 다운로드"""
        try:
            response = self.session.get(url, timeout=self.timeout)
            response.raise_for_status()
            return response.content
        except Exception as e:
            print(f"[ThumbnailDownloader] 다운로드 실패: {e}")
            return None

    def download_thumbnails_zip(
        self,
        videos: List[Dict],
        progress_callback=None
    ) -> bytes:
        """여러 썸네일을 ZIP으로 다운로드"""

        zip_buffer = io.BytesIO()
        successful = 0
        failed = 0

        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            total = len(videos)

            for i, video in enumerate(videos):
                try:
                    thumbnail_url = video.get('thumbnail_url', '')
                    if not thumbnail_url:
                        failed += 1
                        continue

                    response = self.session.get(thumbnail_url, timeout=self.timeout)
                    response.raise_for_status()

                    # 파일명 생성
                    filename = self._generate_filename(video, i + 1)
                    zip_file.writestr(filename, response.content)
                    successful += 1

                    if progress_callback:
                        progress_callback(i + 1, total, f"다운로드 중... {i + 1}/{total}")

                except Exception as e:
                    print(f"[ThumbnailDownloader] 썸네일 다운로드 실패 ({video.get('video_id', 'unknown')}): {e}")
                    failed += 1
                    continue

        print(f"[ThumbnailDownloader] 다운로드 완료: 성공 {successful}개, 실패 {failed}개")

        zip_buffer.seek(0)
        return zip_buffer.getvalue()

    def _generate_filename(self, video: Dict, index: int) -> str:
        """안전한 파일명 생성"""
        # 채널명
        channel = self._sanitize_filename(video.get('channel_title', 'channel'))[:20]

        # 제목 (30자 제한)
        title = self._sanitize_filename(video.get('title', 'video'))[:30]

        # 영상 ID
        video_id = video.get('video_id', f'video_{index}')

        return f"{index:03d}_{channel}_{title}_{video_id}.jpg"

    @staticmethod
    def _sanitize_filename(name: str) -> str:
        """파일명에서 특수문자 제거"""
        # Windows 파일명 금지 문자 제거
        sanitized = re.sub(r'[<>:"/\\|?*\[\]{}()\'`~!@#$%^&+=]', '', name)
        # 연속 공백을 단일 공백으로
        sanitized = re.sub(r'\s+', ' ', sanitized)
        return sanitized.strip()

    @staticmethod
    def get_zip_filename(keyword: str = "thumbnails") -> str:
        """ZIP 파일명 생성"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        safe_keyword = re.sub(r'[^a-zA-Z0-9가-힣]', '_', keyword)[:20]
        return f"thumbnails_{safe_keyword}_{timestamp}.zip"

    def download_to_folder(
        self,
        videos: List[Dict],
        output_dir: str,
        progress_callback=None
    ) -> Dict:
        """썸네일을 폴더에 저장"""

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        successful = 0
        failed = 0
        total = len(videos)

        for i, video in enumerate(videos):
            try:
                thumbnail_url = video.get('thumbnail_url', '')
                if not thumbnail_url:
                    failed += 1
                    continue

                response = self.session.get(thumbnail_url, timeout=self.timeout)
                response.raise_for_status()

                filename = self._generate_filename(video, i + 1)
                filepath = output_path / filename

                with open(filepath, 'wb') as f:
                    f.write(response.content)

                successful += 1

                if progress_callback:
                    progress_callback(i + 1, total, f"저장 중... {i + 1}/{total}")

            except Exception as e:
                print(f"[ThumbnailDownloader] 저장 실패: {e}")
                failed += 1

        return {
            'successful': successful,
            'failed': failed,
            'output_dir': str(output_path)
        }

    def get_best_thumbnail_url(self, video: Dict) -> str:
        """최고 화질 썸네일 URL 반환"""
        # YouTube 썸네일 우선순위: maxres > standard > high > medium > default
        thumbnails = video.get('thumbnails', {})

        for quality in ['maxres', 'standard', 'high', 'medium', 'default']:
            if quality in thumbnails and thumbnails[quality].get('url'):
                return thumbnails[quality]['url']

        # 직접 URL이 있는 경우
        if video.get('thumbnail_url'):
            return video['thumbnail_url']

        # video_id로 URL 생성
        video_id = video.get('video_id', '')
        if video_id:
            return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"

        return ''
