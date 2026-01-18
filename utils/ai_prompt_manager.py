# -*- coding: utf-8 -*-
"""
utils/ai_prompt_manager.py
AI 프롬프트 다중 관리 유틸리티 (v1.0)

주요 기능:
1. 여러 개의 AI 프롬프트 저장/관리
2. 프롬프트 선택, 추가, 수정, 삭제
3. 내장 프롬프트 (삭제 불가) + 사용자 프롬프트
4. JSON 파일로 저장/로드
"""

import json
import uuid
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any


# ============================================================
# 내장 프롬프트 정의
# ============================================================

BUILTIN_PROMPTS = {
    "default": {
        "name": "기본 프롬프트",
        "description": "일반적인 한글 텍스트 씬 추천용 프롬프트",
        "content": """당신은 한글 텍스트 오버레이 전문가입니다.

## 작업
아래 씬들의 프롬프트를 분석하고, 한글 텍스트 오버레이가 효과적일 씬을 선택하세요.

## 선택 기준 (우선순위)
1. 📊 **숫자/통계**: 금액(원), 퍼센트(%), 순위, 연도 등
2. 🏢 **기업/브랜드명**: 삼성, 현대, 테슬라, 애플 등
3. 📝 **핵심 키워드**: 기술 용어, 중요 개념
4. ⚡ **강조 문구**: 시청자 주의를 끌 내용
5. 🎯 **전환점**: 스토리의 중요한 포인트

## 제외 기준
1. 설명이 길고 복잡한 씬
2. 시각적 묘사만 있는 씬
3. 특별한 강조점이 없는 씬

## 출력 형식 (JSON만 출력, 다른 텍스트 없이)
{
    "selected_scenes": [
        {"scene_number": 1, "reason": "선택 이유", "suggested_korean_text": "추천 한글 문구"}
    ],
    "total_selected": N,
    "selection_summary": "전체 선택 요약 (50자 이내)"
}
""",
        "is_builtin": True
    },

    "strict": {
        "name": "엄격한 기준",
        "description": "텍스트 키워드가 명시적인 경우만 추천 (최소 선택)",
        "content": """당신은 한글 텍스트 오버레이 전문가입니다.
매우 엄격한 기준으로 한글 텍스트가 **반드시** 필요한 씬만 선택하세요.

## 선택 기준 (엄격 - 최소 2개 이상 충족 필요)
1. 프롬프트에 "text", "title", "sign", "banner", "UI", "screen" 등 텍스트 관련 키워드가 명시적으로 있는 경우
2. 화면, 인터페이스 등 텍스트가 핵심 요소인 경우
3. 간판, 표지판이 주요 피사체인 경우
4. 숫자/금액/퍼센트가 핵심인 경우

## 제외 대상 (많이 제외)
1. 텍스트가 있을 수도 있지만 없어도 되는 장면
2. 배경에 텍스트가 있을 법한 장면 (명시되지 않은 경우)
3. 일반적인 설명 씬
4. 감정/분위기 위주 씬

## 출력 형식 (JSON만)
{"selected_scenes": [{"scene_number": N, "reason": "이유", "suggested_korean_text": "문구"}], "total_selected": N, "selection_summary": "요약"}
""",
        "is_builtin": True
    },

    "lenient": {
        "name": "관대한 기준",
        "description": "텍스트가 있으면 더 좋을 씬도 포함 (넓은 선택)",
        "content": """당신은 한글 텍스트 오버레이 전문가입니다.
한글 텍스트가 있으면 더 좋을 것 같은 씬도 포함하여 넓게 추천해주세요.

## 선택 기준 (관대 - 1개만 충족해도 선택)
1. 텍스트가 있으면 의미가 더 명확해질 장면
2. 정보 전달이 필요하거나 도움이 될 장면
3. 사람이 보는 화면, 문서, 책 등이 있는 장면
4. 환경에 간판, 표지판, 포스터 등이 있을 법한 장면
5. 제품, 패키지, 브랜드가 등장하는 장면
6. 뉴스, 방송, 발표 등 미디어 장면
7. 숫자, 이름, 용어가 언급되는 장면

적극적으로 추천해주세요!

## 제외 기준 (최소한으로)
1. 순수 자연 풍경만 있는 씬
2. 추상적인 이미지 씬

## 출력 형식 (JSON만)
{"selected_scenes": [{"scene_number": N, "reason": "이유", "suggested_korean_text": "문구"}], "total_selected": N, "selection_summary": "요약"}
""",
        "is_builtin": True
    },

    "ui_focused": {
        "name": "UI/UX 특화",
        "description": "앱, 웹사이트 인터페이스 중심 분석",
        "content": """당신은 UI/UX 전문가입니다.
주어진 씬들 중에서 앱, 웹사이트, 소프트웨어 인터페이스가 포함된 씬을 찾아주세요.

## 선택 기준 (UI/UX 특화)
다음 요소가 있는 씬을 추천합니다:
1. 스마트폰, 태블릿, 컴퓨터 화면이 보이는 장면
2. 앱 인터페이스, 웹사이트가 등장하는 장면
3. 대시보드, 관리 화면, 설정 화면 등
4. 버튼, 메뉴, 네비게이션 등 UI 요소가 있는 장면
5. 알림, 메시지, 팝업 등이 표시되는 장면
6. 로그인, 회원가입 등 폼 화면
7. 차트, 그래프, 데이터 시각화 화면

이런 장면에는 한글 UI 텍스트가 필수입니다!

## 출력 형식 (JSON만)
{"selected_scenes": [{"scene_number": N, "reason": "이유", "suggested_korean_text": "문구"}], "total_selected": N, "selection_summary": "요약"}
""",
        "is_builtin": True
    },

    "signage_focused": {
        "name": "간판/표지판 특화",
        "description": "거리, 건물, 상점 간판 중심 분석",
        "content": """당신은 환경 디자인 전문가입니다.
주어진 씬들 중에서 간판, 표지판, 안내문 등이 포함될 장면을 찾아주세요.

## 선택 기준 (간판/표지판 특화)
다음 요소가 있는 씬을 추천합니다:
1. 상점, 가게, 레스토랑이 배경에 있는 장면
2. 거리, 도시, 쇼핑몰 등 상업 지역 장면
3. 병원, 학교, 관공서 등 공공시설 장면
4. 도로, 교차로, 역 등 교통 관련 장면
5. 공원, 관광지 등 안내판이 있을 법한 장면
6. 건물 외관, 입구가 보이는 장면
7. 주차장, 화장실 등 시설 안내가 필요한 장면

이런 장면에는 한글 간판/표지판이 필요합니다!

## 출력 형식 (JSON만)
{"selected_scenes": [{"scene_number": N, "reason": "이유", "suggested_korean_text": "문구"}], "total_selected": N, "selection_summary": "요약"}
""",
        "is_builtin": True
    }
}


# ============================================================
# AIPromptManager 클래스
# ============================================================

class AIPromptManager:
    """AI 프롬프트 다중 관리 클래스"""

    def __init__(self, config_path: str = None):
        """
        Args:
            config_path: 설정 파일 경로 (None이면 기본 경로 사용)
        """
        if config_path is None:
            root_dir = Path(__file__).parent.parent
            config_path = root_dir / "data" / "config" / "ai_prompts.json"

        self.config_path = Path(config_path)
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self._load_config()

    def _load_config(self):
        """설정 파일 로드"""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)

                # 내장 프롬프트 동기화 (새로 추가된 내장 프롬프트 반영)
                self._sync_builtin_prompts()

            except Exception as e:
                print(f"[AIPromptManager] 설정 로드 실패: {e}")
                self.config = self._get_default_config()
        else:
            self.config = self._get_default_config()
            self._save_config()

    def _sync_builtin_prompts(self):
        """내장 프롬프트 동기화 (새로 추가된 것 반영)"""
        now = datetime.now().isoformat()

        for prompt_id, builtin in BUILTIN_PROMPTS.items():
            if prompt_id not in self.config.get("prompts", {}):
                # 새로 추가된 내장 프롬프트
                self.config["prompts"][prompt_id] = {
                    **builtin,
                    "is_default": False,
                    "created_at": now,
                    "updated_at": now
                }

    def _get_default_config(self) -> dict:
        """기본 설정 생성"""
        prompts = {}
        now = datetime.now().isoformat()

        for prompt_id, prompt_data in BUILTIN_PROMPTS.items():
            prompts[prompt_id] = {
                **prompt_data,
                "is_default": prompt_id == "default",
                "created_at": now,
                "updated_at": now
            }

        return {
            "prompts": prompts,
            "selected_prompt_id": "default",
            "last_updated": now
        }

    def _save_config(self):
        """설정 파일 저장"""
        self.config["last_updated"] = datetime.now().isoformat()

        try:
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            print(f"[AIPromptManager] 설정 저장 실패: {e}")
            return False

    # ============================================================
    # 프롬프트 조회
    # ============================================================

    def get_all_prompts(self) -> Dict[str, dict]:
        """모든 프롬프트 목록 반환"""
        return self.config.get("prompts", {})

    def get_prompt(self, prompt_id: str) -> Optional[dict]:
        """특정 프롬프트 반환"""
        return self.config.get("prompts", {}).get(prompt_id)

    def get_selected_prompt(self) -> dict:
        """현재 선택된 프롬프트 반환"""
        selected_id = self.config.get("selected_prompt_id", "default")
        prompt = self.get_prompt(selected_id)

        if not prompt:
            # 선택된 프롬프트가 없으면 기본값 반환
            return self.get_prompt("default") or {}

        return prompt

    def get_selected_prompt_id(self) -> str:
        """현재 선택된 프롬프트 ID 반환"""
        return self.config.get("selected_prompt_id", "default")

    def get_selected_prompt_content(self) -> str:
        """현재 선택된 프롬프트 내용 반환"""
        return self.get_selected_prompt().get("content", "")

    def get_prompt_list(self) -> List[dict]:
        """프롬프트 목록 (UI 표시용)"""
        prompts = self.get_all_prompts()
        result = []

        # 내장 프롬프트 먼저
        for pid in ["default", "strict", "lenient", "ui_focused", "signage_focused"]:
            if pid in prompts:
                result.append({
                    "id": pid,
                    **prompts[pid]
                })

        # 사용자 프롬프트
        for pid, pdata in prompts.items():
            if not pdata.get("is_builtin", False):
                result.append({
                    "id": pid,
                    **pdata
                })

        return result

    # ============================================================
    # 프롬프트 선택
    # ============================================================

    def select_prompt(self, prompt_id: str) -> bool:
        """프롬프트 선택"""
        if prompt_id in self.config.get("prompts", {}):
            self.config["selected_prompt_id"] = prompt_id
            self._save_config()
            return True
        return False

    # ============================================================
    # 프롬프트 추가/수정/삭제
    # ============================================================

    def add_prompt(self, name: str, description: str, content: str) -> str:
        """새 프롬프트 추가

        Returns:
            생성된 프롬프트 ID
        """
        prompt_id = f"custom_{uuid.uuid4().hex[:8]}"
        now = datetime.now().isoformat()

        self.config["prompts"][prompt_id] = {
            "name": name,
            "description": description,
            "content": content,
            "is_default": False,
            "is_builtin": False,
            "created_at": now,
            "updated_at": now
        }

        self._save_config()
        return prompt_id

    def update_prompt(
        self,
        prompt_id: str,
        name: str = None,
        description: str = None,
        content: str = None
    ) -> bool:
        """프롬프트 수정"""
        if prompt_id not in self.config.get("prompts", {}):
            return False

        prompt = self.config["prompts"][prompt_id]

        if name is not None:
            prompt["name"] = name
        if description is not None:
            prompt["description"] = description
        if content is not None:
            prompt["content"] = content

        prompt["updated_at"] = datetime.now().isoformat()

        self._save_config()
        return True

    def delete_prompt(self, prompt_id: str) -> bool:
        """프롬프트 삭제 (내장 프롬프트는 삭제 불가)"""
        if prompt_id not in self.config.get("prompts", {}):
            return False

        prompt = self.config["prompts"][prompt_id]

        # 내장 프롬프트는 삭제 불가
        if prompt.get("is_builtin", False):
            return False

        # 현재 선택된 프롬프트면 기본값으로 변경
        if self.config.get("selected_prompt_id") == prompt_id:
            self.config["selected_prompt_id"] = "default"

        del self.config["prompts"][prompt_id]
        self._save_config()
        return True

    def duplicate_prompt(self, prompt_id: str, new_name: str = None) -> Optional[str]:
        """프롬프트 복제

        Returns:
            새로 생성된 프롬프트 ID (실패 시 None)
        """
        original = self.get_prompt(prompt_id)
        if not original:
            return None

        name = new_name or f"{original['name']} (복사본)"

        return self.add_prompt(
            name=name,
            description=original.get("description", ""),
            content=original.get("content", "")
        )

    def reset_to_default(self, prompt_id: str) -> bool:
        """내장 프롬프트를 원본으로 리셋"""
        if prompt_id not in BUILTIN_PROMPTS:
            return False

        original = BUILTIN_PROMPTS[prompt_id]
        self.config["prompts"][prompt_id]["content"] = original["content"]
        self.config["prompts"][prompt_id]["updated_at"] = datetime.now().isoformat()

        self._save_config()
        return True

    # ============================================================
    # 내보내기/가져오기
    # ============================================================

    def export_prompt(self, prompt_id: str) -> Optional[str]:
        """프롬프트를 JSON 문자열로 내보내기"""
        prompt = self.get_prompt(prompt_id)
        if not prompt:
            return None

        export_data = {
            "name": prompt["name"],
            "description": prompt.get("description", ""),
            "content": prompt.get("content", ""),
            "exported_at": datetime.now().isoformat()
        }

        return json.dumps(export_data, ensure_ascii=False, indent=2)

    def import_prompt(self, json_str: str) -> Optional[str]:
        """JSON 문자열에서 프롬프트 가져오기

        Returns:
            생성된 프롬프트 ID (실패 시 None)
        """
        try:
            data = json.loads(json_str)

            return self.add_prompt(
                name=data.get("name", "가져온 프롬프트"),
                description=data.get("description", ""),
                content=data.get("content", "")
            )
        except Exception as e:
            print(f"[AIPromptManager] 프롬프트 가져오기 실패: {e}")
            return None

    # ============================================================
    # 유틸리티
    # ============================================================

    def get_builtin_prompt_ids(self) -> List[str]:
        """내장 프롬프트 ID 목록"""
        return list(BUILTIN_PROMPTS.keys())

    def is_builtin(self, prompt_id: str) -> bool:
        """내장 프롬프트 여부"""
        prompt = self.get_prompt(prompt_id)
        return prompt.get("is_builtin", False) if prompt else False

    def get_custom_prompt_count(self) -> int:
        """사용자 프롬프트 개수"""
        count = 0
        for prompt in self.config.get("prompts", {}).values():
            if not prompt.get("is_builtin", False):
                count += 1
        return count


# ============================================================
# 싱글톤 인스턴스
# ============================================================

_prompt_manager_instance = None


def get_prompt_manager() -> AIPromptManager:
    """AIPromptManager 싱글톤 인스턴스 반환"""
    global _prompt_manager_instance

    if _prompt_manager_instance is None:
        _prompt_manager_instance = AIPromptManager()

    return _prompt_manager_instance


def reset_prompt_manager():
    """프롬프트 매니저 리셋 (테스트용)"""
    global _prompt_manager_instance
    _prompt_manager_instance = None
