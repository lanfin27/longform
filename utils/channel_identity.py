# -*- coding: utf-8 -*-
"""
채널 정체성 관리 모듈

기능:
1. 프로젝트(채널)별 정체성 저장/로드
2. 정체성 편집 UI 헬퍼
3. AI 프롬프트 생성
"""

import os
import json
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict, field
from datetime import datetime


@dataclass
class ChannelIdentity:
    """채널 정체성 데이터"""

    # 기본 정보
    project_name: str = ""
    channel_name: str = ""

    # 채널 정체성
    main_topics: List[str] = field(default_factory=list)  # 주요 주제
    target_audience: str = ""  # 타겟 시청자
    content_style: str = ""  # 콘텐츠 스타일
    tone_voice: str = ""  # 톤앤매너

    # 참고/제외
    reference_channels: List[str] = field(default_factory=list)  # 참고 채널
    exclude_topics: List[str] = field(default_factory=list)  # 제외 주제

    # 추가 정보
    keywords: List[str] = field(default_factory=list)  # 핵심 키워드
    description: str = ""  # 상세 설명

    # 메타데이터
    created_at: str = ""
    updated_at: str = ""

    def to_prompt_context(self) -> str:
        """AI 프롬프트용 컨텍스트 생성"""

        lines = [
            f"## 채널 정체성: {self.channel_name or self.project_name}",
            "",
            f"**주요 주제**: {', '.join(self.main_topics) if self.main_topics else '미정의'}",
            f"**타겟 시청자**: {self.target_audience or '미정의'}",
            f"**콘텐츠 스타일**: {self.content_style or '미정의'}",
            f"**톤앤매너**: {self.tone_voice or '미정의'}",
        ]

        if self.reference_channels:
            lines.append(f"**참고 채널**: {', '.join(self.reference_channels)}")

        if self.exclude_topics:
            lines.append(f"**제외 주제**: {', '.join(self.exclude_topics)}")

        if self.keywords:
            lines.append(f"**핵심 키워드**: {', '.join(self.keywords)}")

        if self.description:
            lines.append(f"\n**상세 설명**:\n{self.description}")

        return "\n".join(lines)

    def is_configured(self) -> bool:
        """정체성이 설정되었는지 확인"""
        return bool(self.main_topics) or bool(self.target_audience)


class ChannelIdentityManager:
    """채널 정체성 매니저"""

    CONFIG_DIR = "data/config/channel_identities"

    def __init__(self, base_path: str = "."):
        self.base_path = Path(base_path)
        self.config_dir = self.base_path / self.CONFIG_DIR
        self.config_dir.mkdir(parents=True, exist_ok=True)

    def _get_filepath(self, project_name: str) -> Path:
        """프로젝트 설정 파일 경로"""
        safe_name = project_name.replace(" ", "_").replace("/", "_")
        return self.config_dir / f"{safe_name}.json"

    def save(self, identity: ChannelIdentity) -> bool:
        """정체성 저장"""
        try:
            identity.updated_at = datetime.now().isoformat()
            if not identity.created_at:
                identity.created_at = identity.updated_at

            filepath = self._get_filepath(identity.project_name)

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(asdict(identity), f, ensure_ascii=False, indent=2)

            print(f"[ChannelIdentity] 저장됨: {filepath}")
            return True

        except Exception as e:
            print(f"[ChannelIdentity] 저장 실패: {e}")
            return False

    def load(self, project_name: str) -> ChannelIdentity:
        """정체성 로드"""
        filepath = self._get_filepath(project_name)

        if filepath.exists():
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return ChannelIdentity(**data)
            except Exception as e:
                print(f"[ChannelIdentity] 로드 실패: {e}")

        # 기본값 반환
        return ChannelIdentity(project_name=project_name)

    def list_projects(self) -> List[str]:
        """저장된 프로젝트 목록"""
        projects = []
        for f in self.config_dir.glob("*.json"):
            projects.append(f.stem.replace("_", " "))
        return projects

    def delete(self, project_name: str) -> bool:
        """정체성 삭제"""
        filepath = self._get_filepath(project_name)
        if filepath.exists():
            filepath.unlink()
            return True
        return False

    def export_to_dict(self, project_name: str) -> Dict:
        """정체성을 딕셔너리로 내보내기"""
        identity = self.load(project_name)
        return asdict(identity)

    def import_from_dict(self, data: Dict) -> bool:
        """딕셔너리에서 정체성 가져오기"""
        try:
            identity = ChannelIdentity(**data)
            return self.save(identity)
        except Exception as e:
            print(f"[ChannelIdentity] Import 실패: {e}")
            return False


# 싱글톤
_manager = None


def get_identity_manager(base_path: str = ".") -> ChannelIdentityManager:
    """ChannelIdentityManager 싱글톤 인스턴스 반환"""
    global _manager
    if _manager is None:
        _manager = ChannelIdentityManager(base_path)
    return _manager


def load_channel_identity(project_name: str) -> ChannelIdentity:
    """편의 함수: 채널 정체성 로드"""
    return get_identity_manager().load(project_name)


def save_channel_identity(identity: ChannelIdentity) -> bool:
    """편의 함수: 채널 정체성 저장"""
    return get_identity_manager().save(identity)
