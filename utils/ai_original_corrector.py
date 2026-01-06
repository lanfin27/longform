# -*- coding: utf-8 -*-
"""
AI 원문 교정기 (AIOriginalCorrector) v4.0

⭐ v4.0 변경사항 (속도 최적화):
1. 배치 크기 150 (2번 API 호출로 297씬 처리!)
2. 성공 시 대기 시간 0초 (Rate Limit 발생 시만 대기)
3. Claude API 기본 사용 (Rate Limit 없음)
4. 프롬프트 최적화 (응답 속도 향상)

⭐ 핵심 원칙:
1. 타임스탬프는 절대 변경하지 않음!
2. 텍스트만 원문과 일치시킴
3. AI가 원문과 Whisper를 비교해서 교정
"""

import json
import re
import os
import time
import copy
from typing import List, Dict, Tuple, Optional


class RateLimitError(Exception):
    """Rate Limit 예외"""
    def __init__(self, message: str, retry_delay: float = 10.0):
        super().__init__(message)
        self.retry_delay = retry_delay


class AIOriginalCorrector:
    """AI 기반 원문 교정기 v4.0 (속도 최적화)"""

    # Provider별 기본 모델
    DEFAULT_MODELS = {
        'google': 'gemini-2.0-flash-exp',
        'anthropic': 'claude-3-5-sonnet-20241022'
    }

    def __init__(self, provider: str = 'anthropic', model: str = None):
        """
        ⭐ v4.0: 기본값을 Claude로 변경! (Rate Limit 없음)

        Args:
            provider: AI 제공자 ('anthropic', 'google')
            model: 모델명 (None이면 기본값 사용)
        """
        self.provider = provider
        self.model = model if model else self.DEFAULT_MODELS.get(provider, 'claude-3-5-sonnet-20241022')
        self.client = None
        self.claude_client = None  # 폴백용

        # ⭐ v4.0 속도 최적화 설정
        self.batch_size = 150          # 50 → 150 (2번 API 호출로 충분!)
        self.rate_limit_delay = 0.5    # 7.0 → 0.5 (성공 시 거의 대기 없음)
        self.max_retries = 3           # 최대 재시도 횟수
        self.retry_base_delay = 10.0   # 재시도 기본 대기 시간

        print(f"\n{'='*60}")
        print(f"[AIOriginalCorrector] v4.0 초기화 (속도 최적화)")
        print(f"{'='*60}")
        print(f"[AIOriginalCorrector]   Provider: {provider}")
        print(f"[AIOriginalCorrector]   Model: {self.model}")
        print(f"[AIOriginalCorrector]   배치 크기: {self.batch_size} (대용량)")
        print(f"[AIOriginalCorrector]   최대 재시도: {self.max_retries}회")

        self._init_client()

        # Gemini 사용 시에만 폴백 준비
        if self.provider == 'google':
            self._init_fallback_client()
            print(f"[AIOriginalCorrector] ⚠️ Gemini는 Rate Limit 있음. Claude 권장!")

    def _init_client(self):
        """AI 클라이언트 초기화"""
        try:
            if self.provider == 'google':
                self._init_google_client()
            elif self.provider == 'anthropic':
                self._init_anthropic_client()
            else:
                print(f"[AIOriginalCorrector] ⚠️ 알 수 없는 provider: {self.provider}")
        except ImportError as e:
            print(f"[AIOriginalCorrector] ❌ 라이브러리 없음: {e}")
            self.client = None
        except Exception as e:
            print(f"[AIOriginalCorrector] ❌ 클라이언트 초기화 실패: {e}")
            self.client = None

    def _init_google_client(self):
        """Google Gemini 클라이언트 초기화"""
        # 새로운 google-genai SDK 시도
        try:
            from google import genai
            api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
            if api_key:
                self.client = genai.Client(api_key=api_key)
                self._google_sdk = 'genai'
                print(f"[AIOriginalCorrector] ✅ Gemini 클라이언트 초기화 완료 (google-genai SDK)")
                return
        except ImportError:
            pass

        # 기존 google-generativeai SDK 시도
        try:
            import google.generativeai as genai
            api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
            if api_key:
                genai.configure(api_key=api_key)
                self.client = genai
                self._google_sdk = 'generativeai'
                print(f"[AIOriginalCorrector] ✅ Gemini 클라이언트 초기화 완료 (google-generativeai SDK)")
                return
        except ImportError:
            pass

        print(f"[AIOriginalCorrector] ⚠️ Google SDK 없음")

    def _init_anthropic_client(self):
        """Anthropic Claude 클라이언트 초기화"""
        import anthropic
        self.client = anthropic.Anthropic()
        print(f"[AIOriginalCorrector] ✅ Claude 클라이언트 초기화 완료")

    def _init_fallback_client(self):
        """폴백용 Claude 클라이언트 초기화"""
        if self.provider != 'anthropic':
            try:
                import anthropic
                self.claude_client = anthropic.Anthropic()
                print(f"[AIOriginalCorrector] ✅ 폴백용 Claude 클라이언트 준비됨")
            except Exception as e:
                print(f"[AIOriginalCorrector] ⚠️ 폴백 클라이언트 없음: {e}")
                self.claude_client = None

    def correct_with_original(self,
                               scenes: List[Dict],
                               original_script: str,
                               batch_size: int = None,
                               progress_callback=None) -> Tuple[List[Dict], List[Dict]]:
        """
        Whisper SRT를 원문과 비교해서 교정

        ⭐ v4.0: 속도 최적화 - 2번 API 호출로 297씬 처리!

        Args:
            scenes: Whisper 씬 리스트 (직접 수정됨!)
            original_script: 원문 스크립트
            batch_size: 배치 크기 (기본값: self.batch_size)
            progress_callback: 진행률 콜백 (progress, message)

        Returns:
            (수정된 scenes, 교정 내역 리스트)
        """
        if not scenes or not original_script:
            print(f"[AIOriginalCorrector] ⚠️ 입력 데이터 없음")
            return scenes, []

        if not self.client:
            print(f"[AIOriginalCorrector] ⚠️ AI 클라이언트 없음")
            return scenes, []

        # 배치 크기 설정
        if batch_size is None:
            batch_size = self.batch_size

        print(f"\n{'='*60}")
        print(f"[AIOriginalCorrector] AI 원문 교정 시작 (v4.0 속도 최적화)")
        print(f"{'='*60}")
        print(f"[AIOriginalCorrector]   입력 씬: {len(scenes)}개")
        print(f"[AIOriginalCorrector]   원문 길이: {len(original_script)}자")
        print(f"[AIOriginalCorrector]   배치 크기: {batch_size}")

        # 배치 계산
        total_batches = (len(scenes) + batch_size - 1) // batch_size
        print(f"[AIOriginalCorrector]   총 배치: {total_batches}개")

        # ⭐ v4.0: 예상 시간 (현실적으로)
        if self.provider == 'anthropic':
            est_time = total_batches * 20  # Claude는 빠름
        else:
            est_time = total_batches * 30  # Gemini는 Rate Limit 대기 포함
        print(f"[AIOriginalCorrector]   예상 시간: {est_time}초 ({est_time/60:.1f}분)")

        # ⭐ 씬 ID → 인덱스 매핑 (결과 반영용)
        scene_id_to_idx = {s.get('scene_id'): i for i, s in enumerate(scenes)}

        all_corrections = []
        failed_batches = []
        start_time = time.time()

        for batch_idx in range(total_batches):
            batch_start = time.time()

            start_idx = batch_idx * batch_size
            end_idx = min(start_idx + batch_size, len(scenes))

            # ⭐ 배치 씬 정보 추출 (scene_id와 text만)
            batch_info = []
            for i in range(start_idx, end_idx):
                batch_info.append({
                    'scene_id': scenes[i].get('scene_id'),
                    'text': scenes[i].get('text', ''),
                    'original_idx': i  # 원본 인덱스 저장!
                })

            print(f"\n[AIOriginalCorrector] 📦 배치 {batch_idx + 1}/{total_batches} 처리 중 ({len(batch_info)}씬)...")

            # 진행률 콜백
            if progress_callback:
                progress = (batch_idx + 0.5) / total_batches
                progress_callback(progress, f"배치 {batch_idx + 1}/{total_batches} 처리 중...")

            # ⭐ v4.0: 간소화된 재시도 로직
            success = False
            last_error = None

            for retry in range(self.max_retries):
                try:
                    corrections = self._process_batch(batch_info, original_script, scenes)
                    all_corrections.extend(corrections)
                    success = True

                    batch_time = time.time() - batch_start
                    print(f"[AIOriginalCorrector] ✅ 배치 {batch_idx + 1} 완료: {len(corrections)}개 교정 ({batch_time:.1f}초)")
                    break

                except RateLimitError as e:
                    last_error = e
                    wait_time = e.retry_delay
                    print(f"[AIOriginalCorrector] ⏳ Rate Limit! {wait_time:.0f}초 대기 후 재시도 ({retry + 1}/{self.max_retries})...")
                    time.sleep(wait_time)

                except Exception as e:
                    last_error = e
                    print(f"[AIOriginalCorrector] ❌ 배치 {batch_idx + 1} 오류 ({retry + 1}/{self.max_retries}): {e}")
                    if retry < self.max_retries - 1:
                        time.sleep(2)

            if not success:
                failed_batches.append({
                    'batch_idx': batch_idx,
                    'batch_info': batch_info,
                    'error': str(last_error)
                })
                print(f"[AIOriginalCorrector] ⚠️ 배치 {batch_idx + 1} 실패")

                # ⭐ Gemini 실패 시 Claude 폴백 즉시 시도
                if self.provider == 'google' and self.claude_client:
                    print(f"[AIOriginalCorrector] 🔄 Claude 폴백 시도...")
                    try:
                        corrections = self._process_batch_with_claude(batch_info, original_script, scenes)
                        all_corrections.extend(corrections)
                        failed_batches.pop()  # 성공했으므로 실패 목록에서 제거
                        print(f"[AIOriginalCorrector] ✅ 폴백 성공: {len(corrections)}개 교정")
                    except Exception as e:
                        print(f"[AIOriginalCorrector] ❌ 폴백 실패: {e}")

            # ⭐ v4.0: 성공 시 대기 거의 없음! (Gemini만 짧은 대기)
            if batch_idx < total_batches - 1:
                if self.provider == 'google':
                    time.sleep(self.rate_limit_delay)  # 0.5초만 대기
                # Claude는 대기 없음!

        # ⭐ 최종 검증: 교정이 실제로 적용됐는지 확인
        applied_count = 0
        force_applied_count = 0
        for c in all_corrections:
            scene_id = c['scene_id']
            idx = scene_id_to_idx.get(scene_id)
            if idx is not None:
                current_text = scenes[idx].get('text', '')
                expected_text = c['after']
                if current_text == expected_text:
                    applied_count += 1
                else:
                    # 적용 안 됐으면 강제 적용
                    scenes[idx]['text'] = expected_text
                    force_applied_count += 1

        # ⭐ 결과 요약
        total_time = time.time() - start_time

        print(f"\n{'='*60}")
        print(f"[AIOriginalCorrector] ✅ AI 원문 교정 완료")
        print(f"{'='*60}")
        print(f"[AIOriginalCorrector]   총 교정: {len(all_corrections)}개")
        print(f"[AIOriginalCorrector]   소요 시간: {total_time:.1f}초 ({total_time/60:.1f}분)")
        print(f"[AIOriginalCorrector]   처리 속도: {len(scenes)/total_time:.1f} 씬/초")
        if force_applied_count > 0:
            print(f"[AIOriginalCorrector]   강제 적용: {force_applied_count}개")
        if failed_batches:
            print(f"[AIOriginalCorrector]   실패 배치: {len(failed_batches)}개")

        # 교정 내역 출력 (최대 10개)
        for i, c in enumerate(all_corrections[:10]):
            print(f"[AIOriginalCorrector]   씬 {c['scene_id']}: {c['before'][:20]}... → {c['after'][:20]}...")

        if len(all_corrections) > 10:
            print(f"[AIOriginalCorrector]   ... 외 {len(all_corrections) - 10}개")

        # 진행률 완료
        if progress_callback:
            progress_callback(1.0, "교정 완료!")

        return scenes, all_corrections

    def _process_batch(self, batch_info: List[Dict],
                        original_script: str,
                        scenes: List[Dict]) -> List[Dict]:
        """배치 처리"""

        # Whisper 텍스트 추출
        whisper_texts = []
        for info in batch_info:
            scene_id = info['scene_id']
            text = info['text']
            whisper_texts.append(f"[{scene_id}] {text}")

        whisper_combined = '\n'.join(whisper_texts)

        # ⭐ v4.0: 간결한 프롬프트 (응답 속도 향상)
        prompt = self._create_fast_prompt(whisper_combined, original_script)

        # AI 호출
        if self.provider == 'google':
            response = self._call_gemini(prompt)
        else:
            response = self._call_claude(prompt)

        if not response:
            return []

        # 응답 파싱 및 적용
        return self._parse_and_apply_corrections(response, batch_info, scenes)

    def _process_batch_with_claude(self, batch_info: List[Dict],
                                    original_script: str,
                                    scenes: List[Dict]) -> List[Dict]:
        """폴백: Claude로 배치 처리"""

        if not self.claude_client:
            raise Exception("Claude 폴백 클라이언트 없음")

        whisper_texts = []
        for info in batch_info:
            whisper_texts.append(f"[{info['scene_id']}] {info['text']}")

        whisper_combined = '\n'.join(whisper_texts)
        prompt = self._create_fast_prompt(whisper_combined, original_script)

        try:
            response = self.claude_client.messages.create(
                model='claude-3-5-sonnet-20241022',
                max_tokens=8192,
                messages=[{"role": "user", "content": prompt}]
            )
            response_text = response.content[0].text
            return self._parse_and_apply_corrections(response_text, batch_info, scenes)

        except Exception as e:
            raise Exception(f"Claude API 오류: {e}")

    def _call_gemini(self, prompt: str) -> Optional[str]:
        """Gemini API 호출 (Rate Limit 감지)"""

        try:
            if hasattr(self, '_google_sdk') and self._google_sdk == 'genai':
                # 새로운 google-genai SDK
                response = self.client.models.generate_content(
                    model=self.model,
                    contents=prompt
                )
                return response.text
            else:
                # 기존 google-generativeai SDK
                model = self.client.GenerativeModel(self.model)
                response = model.generate_content(
                    prompt,
                    generation_config={
                        "temperature": 0.1,
                        "max_output_tokens": 8192
                    }
                )
                return response.text

        except Exception as e:
            error_str = str(e)

            # Rate Limit 감지
            if '429' in error_str or 'quota' in error_str.lower() or 'rate' in error_str.lower():
                # retry_delay 추출
                retry_delay = 30
                match = re.search(r'seconds[:\s]*(\d+)', error_str)
                if match:
                    retry_delay = int(match.group(1)) + 2  # 여유 2초 추가

                raise RateLimitError(f"Gemini Rate Limit", retry_delay)

            raise

    def _call_claude(self, prompt: str) -> Optional[str]:
        """Claude API 호출"""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=8192,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.content[0].text
        except Exception as e:
            print(f"[AIOriginalCorrector] ❌ Claude 오류: {e}")
            raise

    def _create_fast_prompt(self, whisper_text: str, original_script: str) -> str:
        """⭐ v4.0: 간결한 프롬프트 (응답 속도 향상)"""

        # 원문 길이 제한 (너무 길면 느려짐)
        script_excerpt = original_script[:6000]

        prompt = f"""자막 교정. Whisper 인식 오류를 원문 기준으로 수정.

규칙:
- 오타/발음 오류만 수정 (예: "계기판되신"→"계기판 대신", "콕피시"→"콕핏")
- 줄바꿈(\\n) 유지
- 변경 없으면 포함 안 함

원문:
{script_excerpt}

자막:
{whisper_text}

JSON으로만 응답:
[{{"scene_id": 1, "corrected": "수정된 텍스트"}}, ...]

수정할 것 없으면: []"""

        return prompt

    def _parse_and_apply_corrections(self, response: str,
                                      batch_info: List[Dict],
                                      scenes: List[Dict]) -> List[Dict]:
        """AI 응답 파싱 및 교정 적용"""

        corrections = []

        try:
            # JSON 추출
            json_match = re.search(r'```json\s*([\s\S]*?)\s*```', response)
            if json_match:
                json_str = json_match.group(1)
            else:
                # JSON 배열 직접 찾기
                json_match = re.search(r'\[\s*\{[\s\S]*?\}\s*\]|\[\s*\]', response)
                if json_match:
                    json_str = json_match.group(0)
                else:
                    # 빈 배열 처리
                    if '[]' in response:
                        return []
                    print(f"[AIOriginalCorrector] ⚠️ JSON 형식 없음")
                    return []

            correction_list = json.loads(json_str)

        except (json.JSONDecodeError, AttributeError) as e:
            print(f"[AIOriginalCorrector] ⚠️ JSON 파싱 오류: {e}")
            return []

        # ⭐ scene_id → original_idx 매핑 생성
        scene_id_to_info = {info['scene_id']: info for info in batch_info}

        # 교정 적용
        for correction in correction_list:
            scene_id = correction.get('scene_id')
            corrected_text = correction.get('corrected', '').strip()

            if not scene_id or not corrected_text:
                continue

            info = scene_id_to_info.get(scene_id)
            if not info:
                continue

            original_idx = info['original_idx']
            original_text = info['text']

            # 변경된 경우만 처리
            if corrected_text != original_text:
                corrections.append({
                    'scene_id': scene_id,
                    'before': original_text,
                    'after': corrected_text
                })

                # ⭐ 원본 scenes 리스트에 직접 적용!
                scenes[original_idx]['text'] = corrected_text

        return corrections


# ============================================================
# 팩토리 함수
# ============================================================

_corrector_instance: Optional[AIOriginalCorrector] = None


def get_ai_original_corrector(provider: str = 'anthropic',
                               model: str = None) -> AIOriginalCorrector:
    """AIOriginalCorrector 싱글톤 인스턴스 (기본값: Claude)"""
    global _corrector_instance

    if _corrector_instance is None:
        _corrector_instance = AIOriginalCorrector(provider=provider, model=model)

    return _corrector_instance


def create_ai_original_corrector(provider: str = 'anthropic',
                                  model: str = None) -> AIOriginalCorrector:
    """AIOriginalCorrector 새 인스턴스 생성 (기본값: Claude)"""
    return AIOriginalCorrector(provider=provider, model=model)
