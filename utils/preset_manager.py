# -*- coding: utf-8 -*-
"""
TTS 설정 프리셋 관리자

기능:
- 프리셋 저장
- 프리셋 불러오기
- 프리셋 목록 조회
- 프리셋 삭제
- 프리셋 내보내기/가져오기
"""

import os
import json
import uuid
import re
from datetime import datetime
from typing import Dict, List, Optional
from pathlib import Path


class PresetManager:
    """TTS 설정 프리셋 관리자"""

    def __init__(self, presets_dir: str = None):
        """
        초기화

        Args:
            presets_dir: 프리셋 저장 디렉토리 (기본: data/presets)
        """
        if presets_dir is None:
            base_dir = Path(__file__).parent.parent
            presets_dir = base_dir / "data" / "presets"

        self.presets_dir = Path(presets_dir)
        self.presets_dir.mkdir(parents=True, exist_ok=True)

        self.index_file = self.presets_dir / "tts_presets.json"

        # 인덱스 파일 초기화
        if not self.index_file.exists():
            self._save_index({"presets": []})

        print(f"[PresetManager] 초기화")
        print(f"  경로: {self.presets_dir}")
        print(f"  프리셋 수: {len(self.list_presets())}")

    def _load_index(self) -> Dict:
        """인덱스 파일 로드"""
        try:
            with open(self.index_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[PresetManager] 인덱스 로드 오류: {e}")
            return {"presets": []}

    def _save_index(self, index: Dict):
        """인덱스 파일 저장"""
        with open(self.index_file, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)

    def save_preset(
        self,
        name: str,
        voice_reference: Dict,
        voice_parameters: Dict,
        quality_settings: Dict,
        generation_options: Dict,
        post_processing: Dict,
        description: str = ""
    ) -> str:
        """
        프리셋 저장

        Args:
            name: 프리셋 이름
            voice_reference: 참조 음성 정보
            voice_parameters: 음성 파라미터
            quality_settings: 품질 설정
            generation_options: 생성 옵션
            post_processing: 후처리 옵션
            description: 설명 (선택)

        Returns:
            저장된 프리셋 ID
        """

        preset_id = str(uuid.uuid4())[:8]
        now = datetime.now().isoformat()

        preset = {
            "preset_id": preset_id,
            "preset_name": name,
            "created_at": now,
            "updated_at": now,
            "description": description,
            "voice_reference": voice_reference,
            "voice_parameters": voice_parameters,
            "quality_settings": quality_settings,
            "generation_options": generation_options,
            "post_processing": post_processing
        }

        # 프리셋 파일 저장
        safe_name = self._safe_filename(name)
        preset_file = self.presets_dir / f"preset_{safe_name}_{preset_id}.json"

        with open(preset_file, "w", encoding="utf-8") as f:
            json.dump(preset, f, ensure_ascii=False, indent=2)

        # 인덱스 업데이트
        index = self._load_index()
        index["presets"].append({
            "preset_id": preset_id,
            "preset_name": name,
            "created_at": now,
            "file_path": str(preset_file),
            "voice_name": voice_reference.get("voice_name", "")
        })
        self._save_index(index)

        print(f"\n[PresetManager] 프리셋 저장 완료!")
        print(f"  이름: {name}")
        print(f"  ID: {preset_id}")
        print(f"  파일: {preset_file.name}")

        return preset_id

    def load_preset(self, preset_id: str) -> Optional[Dict]:
        """
        프리셋 불러오기

        Args:
            preset_id: 프리셋 ID

        Returns:
            프리셋 딕셔너리 또는 None
        """

        index = self._load_index()

        for preset_info in index["presets"]:
            if preset_info["preset_id"] == preset_id:
                preset_file = Path(preset_info["file_path"])

                if preset_file.exists():
                    with open(preset_file, "r", encoding="utf-8") as f:
                        preset = json.load(f)

                    print(f"\n[PresetManager] 프리셋 불러오기 완료!")
                    print(f"  이름: {preset['preset_name']}")
                    print(f"  음성: {preset['voice_reference'].get('voice_name', 'N/A')}")

                    return preset
                else:
                    print(f"[PresetManager] 프리셋 파일 없음: {preset_file}")
                    return None

        print(f"[PresetManager] 프리셋 ID 없음: {preset_id}")
        return None

    def list_presets(self, voice_name: str = None) -> List[Dict]:
        """
        프리셋 목록 조회

        Args:
            voice_name: 특정 음성의 프리셋만 필터링 (선택)

        Returns:
            프리셋 정보 목록
        """

        index = self._load_index()
        presets = index.get("presets", [])

        if voice_name:
            presets = [p for p in presets if p.get("voice_name") == voice_name]

        # 최신순 정렬
        presets.sort(key=lambda x: x.get("created_at", ""), reverse=True)

        return presets

    def delete_preset(self, preset_id: str) -> bool:
        """
        프리셋 삭제

        Args:
            preset_id: 프리셋 ID

        Returns:
            삭제 성공 여부
        """

        index = self._load_index()

        for i, preset_info in enumerate(index["presets"]):
            if preset_info["preset_id"] == preset_id:
                # 파일 삭제
                preset_file = Path(preset_info["file_path"])
                if preset_file.exists():
                    preset_file.unlink()

                # 인덱스에서 제거
                index["presets"].pop(i)
                self._save_index(index)

                print(f"[PresetManager] 프리셋 삭제 완료: {preset_id}")
                return True

        return False

    def update_preset(self, preset_id: str, updates: Dict) -> bool:
        """
        프리셋 업데이트

        Args:
            preset_id: 프리셋 ID
            updates: 업데이트할 항목들

        Returns:
            업데이트 성공 여부
        """

        preset = self.load_preset(preset_id)
        if not preset:
            return False

        # 업데이트 적용
        for key, value in updates.items():
            if key in preset:
                if isinstance(preset[key], dict) and isinstance(value, dict):
                    preset[key].update(value)
                else:
                    preset[key] = value

        preset["updated_at"] = datetime.now().isoformat()

        # 저장
        index = self._load_index()
        for preset_info in index["presets"]:
            if preset_info["preset_id"] == preset_id:
                preset_file = Path(preset_info["file_path"])
                with open(preset_file, "w", encoding="utf-8") as f:
                    json.dump(preset, f, ensure_ascii=False, indent=2)
                return True

        return False

    def export_preset(self, preset_id: str, export_path: str) -> bool:
        """프리셋 내보내기 (공유용)"""
        preset = self.load_preset(preset_id)
        if not preset:
            return False

        with open(export_path, "w", encoding="utf-8") as f:
            json.dump(preset, f, ensure_ascii=False, indent=2)

        print(f"[PresetManager] 프리셋 내보내기: {export_path}")
        return True

    def import_preset(self, import_path: str) -> Optional[str]:
        """프리셋 가져오기"""
        try:
            with open(import_path, "r", encoding="utf-8") as f:
                preset = json.load(f)

            # 새 ID 부여
            preset["preset_id"] = str(uuid.uuid4())[:8]
            preset["created_at"] = datetime.now().isoformat()
            preset["updated_at"] = preset["created_at"]
            preset["preset_name"] = f"{preset['preset_name']} (가져옴)"

            # 저장
            return self.save_preset(
                name=preset["preset_name"],
                voice_reference=preset.get("voice_reference", {}),
                voice_parameters=preset.get("voice_parameters", {}),
                quality_settings=preset.get("quality_settings", {}),
                generation_options=preset.get("generation_options", {}),
                post_processing=preset.get("post_processing", {}),
                description=preset.get("description", "")
            )
        except Exception as e:
            print(f"[PresetManager] 가져오기 실패: {e}")
            return None

    def _safe_filename(self, name: str) -> str:
        """안전한 파일명 생성"""
        safe = re.sub(r'[<>:"/\\|?*]', '_', name)
        safe = safe.replace(' ', '_')
        return safe[:50]  # 최대 50자


# 싱글톤 인스턴스
_preset_manager = None

def get_preset_manager() -> PresetManager:
    """PresetManager 싱글톤 인스턴스 반환"""
    global _preset_manager
    if _preset_manager is None:
        _preset_manager = PresetManager()
    return _preset_manager
