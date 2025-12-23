# -*- coding: utf-8 -*-
"""
TTS 병렬 생성기 - 결과 반환 문제 완전 수정

문제: 서버에서 성공해도 클라이언트에서 0개 성공
원인:
  1. audio_data가 None이어도 success=True 반환
  2. 응답 키 불일치 (duration_seconds vs duration)
  3. 다운로드 실패 시 조용히 무시
해결: 철저한 검증 + 디버그 로깅
"""

import os
import io
import time
import threading
import traceback
import requests
from typing import List, Dict, Optional, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

CHATTERBOX_URL = "http://localhost:8100"

# 스레드 로컬 세션
_thread_local = threading.local()


def get_thread_session() -> requests.Session:
    """스레드별 세션 반환"""
    if not hasattr(_thread_local, "session"):
        session = requests.Session()
        adapter = HTTPAdapter(
            pool_connections=10,
            pool_maxsize=10,
            max_retries=Retry(total=2, backoff_factor=0.5)
        )
        session.mount("http://", adapter)
        session.headers.update({
            "Connection": "keep-alive",
            "Content-Type": "application/json"
        })
        _thread_local.session = session
    return _thread_local.session


class ParallelTTSGenerator:
    """
    수정된 병렬 TTS 생성기

    핵심 수정:
    1. audio_data 필수 검증
    2. 응답 키 호환성 처리
    3. 상세 디버그 로깅
    """

    def __init__(
        self,
        api_url: str = CHATTERBOX_URL,
        max_workers: int = 3,
        timeout: int = 300  # 5분 타임아웃
    ):
        self.api_url = api_url
        self.max_workers = max_workers
        self.timeout = timeout
        self._lock = threading.Lock()
        self._completed = 0

        print(f"\n[ParallelGen] 초기화")
        print(f"  ⚡ 동시 처리: {max_workers}개")
        print(f"  ⏱️ 타임아웃: {timeout}초")
        print(f"  🌐 API: {api_url}")

    def generate_all(
        self,
        scenes: List[Dict],
        params: Dict,
        progress_callback: Optional[Callable] = None
    ) -> List[Dict]:
        """모든 씬 병렬 생성"""

        total = len(scenes)
        self._completed = 0

        # Voice cloning 디버그
        voice_ref = params.get("voice_ref_path")
        print(f"\n[ParallelGen] 🎤 Voice: {voice_ref[-40:] if voice_ref else '기본 음성'}")

        print(f"\n{'='*60}")
        print(f"[ParallelGen] 🚀 {total}개 씬 병렬 생성 시작")
        print(f"{'='*60}")

        start_time = time.time()
        results = [None] * total
        task_times = {}

        def wrapped_generate(idx: int, scene: Dict) -> Dict:
            """래퍼 함수"""
            task_start = time.time()
            scene_id = scene.get("scene_id", idx + 1)

            print(f"[Scene {scene_id}] 🔄 시작 (t={task_start - start_time:.1f}s)")

            try:
                result = self._generate_single(scene, params)
            except Exception as e:
                print(f"[Scene {scene_id}] ❌ 예외: {e}")
                traceback.print_exc()
                result = {
                    "scene_id": scene_id,
                    "text": scene.get("text", ""),
                    "text_preview": scene.get("text", "")[:50],
                    "char_count": len(scene.get("text", "")),
                    "audio_data": None,
                    "duration": 0,
                    "success": False,
                    "status": "failed",
                    "error": f"Exception: {e}"
                }

            gen_time = time.time() - task_start
            task_times[idx] = gen_time

            # 진행률 업데이트
            with self._lock:
                self._completed += 1
                current = self._completed

            # 결과 로깅
            if result.get("success") and result.get("audio_data"):
                audio_size = len(result.get("audio_data", b""))
                duration = result.get("duration", 0)
                print(f"[Scene {scene_id}] ✅ 완료 {gen_time:.1f}초 (오디오: {duration:.1f}초, {audio_size//1024}KB)")
            else:
                error = result.get("error", "Unknown")
                has_audio = "있음" if result.get("audio_data") else "없음"
                print(f"[Scene {scene_id}] ❌ 실패: {error} (audio_data: {has_audio})")

            if progress_callback:
                try:
                    progress_callback(current, total, f"씬 {scene_id} 완료 ({current}/{total})")
                except Exception:
                    pass

            result["generation_time"] = gen_time
            return result

        # 병렬 실행
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_idx = {
                executor.submit(wrapped_generate, idx, scene): idx
                for idx, scene in enumerate(scenes)
            }

            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    result = future.result(timeout=self.timeout + 60)
                    results[idx] = result
                except Exception as e:
                    print(f"[Future {idx}] ❌ future.result() 예외: {e}")
                    scene = scenes[idx]
                    results[idx] = {
                        "scene_id": scene.get("scene_id", idx + 1),
                        "text": scene.get("text", ""),
                        "audio_data": None,
                        "success": False,
                        "status": "failed",
                        "error": f"Future error: {e}"
                    }

        total_time = time.time() - start_time

        # ⭐ 핵심: success AND audio_data 둘 다 있어야 성공
        success_count = sum(
            1 for r in results
            if r and r.get("success") == True and r.get("audio_data")
        )

        # 병렬 효율
        total_gen_time = sum(task_times.values())
        efficiency = total_gen_time / total_time if total_time > 0 else 1

        print(f"\n{'='*60}")
        print(f"[ParallelGen] ✅ 완료: {success_count}/{total}개 성공")
        print(f"[ParallelGen] ⏱️ 총 시간: {total_time:.1f}초")
        print(f"[ParallelGen] 📊 병렬 효율: {efficiency:.2f}x")

        # 개별 결과 상태 출력
        print(f"[ParallelGen] 개별 결과:")
        for idx, r in enumerate(results):
            if r:
                status = "✅" if (r.get("success") and r.get("audio_data")) else "❌"
                audio_info = f"{len(r.get('audio_data', b''))//1024}KB" if r.get("audio_data") else "None"
                print(f"  [{idx+1}] {status} success={r.get('success')}, audio={audio_info}")
            else:
                print(f"  [{idx+1}] ❌ result is None")

        print(f"{'='*60}")

        if progress_callback:
            progress_callback(total, total, f"생성 완료 ({success_count}/{total})")

        return results

    def _generate_single(self, scene: Dict, params: Dict) -> Dict:
        """단일 씬 생성"""

        text = scene.get("text", "")
        scene_id = scene.get("scene_id", 0)
        char_count = len(text.replace(" ", "").replace("\n", ""))

        # 기본 실패 결과
        fail_result = {
            "scene_id": scene_id,
            "text": text,
            "text_preview": text[:50] + "..." if len(text) > 50 else text,
            "char_count": char_count,
            "audio_data": None,
            "duration": 0,
            "chunks_count": 1,
            "status": "failed",
            "success": False
        }

        if not text.strip():
            return {**fail_result, "error": "빈 텍스트"}

        # 요청 데이터
        request_data = {
            "text": text,
            "settings": {
                "language": params.get("language", "ko"),
                "voice_ref_path": params.get("voice_ref_path"),
                "exaggeration": params.get("exaggeration", 0.5),
                "cfg_weight": params.get("cfg_weight", 0.5),
                "temperature": params.get("temperature", 0.8),
                "speed": params.get("speed", 1.0),
                "repetition_penalty": params.get("repetition_penalty", 1.4),
                "seed": params.get("seed"),
            }
        }

        try:
            session = get_thread_session()

            # 1단계: 생성 요청
            print(f"  [Scene {scene_id}] POST /generate...")
            response = session.post(
                f"{self.api_url}/generate",
                json=request_data,
                timeout=self.timeout
            )

            print(f"  [Scene {scene_id}] HTTP {response.status_code}")

            if response.status_code != 200:
                return {**fail_result, "error": f"HTTP {response.status_code}: {response.text[:100]}"}

            # 2단계: JSON 파싱
            try:
                result = response.json()
                print(f"  [Scene {scene_id}] Response keys: {list(result.keys())}")
            except Exception as e:
                return {**fail_result, "error": f"JSON 파싱 실패: {e}"}

            # 3단계: 성공 여부 확인
            if not result.get("success"):
                return {**fail_result, "error": result.get("error", "서버에서 실패 반환")}

            # 4단계: 오디오 URL 추출
            audio_url = result.get("audio_url", "")
            if not audio_url:
                # audio_path 시도
                audio_url = result.get("audio_path", "")
            if not audio_url:
                return {**fail_result, "error": f"audio_url 없음: {result}"}

            print(f"  [Scene {scene_id}] audio_url: {audio_url}")

            # 5단계: 오디오 다운로드 (필수!)
            audio_data = None
            download_url = f"{self.api_url}{audio_url}"

            try:
                print(f"  [Scene {scene_id}] GET {download_url}...")
                audio_resp = session.get(download_url, timeout=60)

                print(f"  [Scene {scene_id}] Download HTTP {audio_resp.status_code}")

                if audio_resp.status_code == 200:
                    audio_data = audio_resp.content
                    print(f"  [Scene {scene_id}] Downloaded {len(audio_data)//1024}KB")
                else:
                    return {**fail_result, "error": f"다운로드 HTTP {audio_resp.status_code}"}

            except Exception as e:
                print(f"  [Scene {scene_id}] ❌ 다운로드 예외: {e}")
                return {**fail_result, "error": f"다운로드 실패: {e}"}

            # 6단계: audio_data 검증 (필수!)
            if not audio_data or len(audio_data) < 1000:
                return {**fail_result, "error": f"오디오 데이터 없음 또는 너무 작음: {len(audio_data) if audio_data else 0} bytes"}

            # 7단계: duration 추출 (여러 키 시도)
            duration = (
                result.get("duration_seconds") or
                result.get("duration") or
                result.get("audio_duration") or
                0
            )

            # ⭐ 성공!
            return {
                "scene_id": scene_id,
                "text": text,
                "text_preview": text[:50] + "..." if len(text) > 50 else text,
                "char_count": char_count,
                "audio_data": audio_data,
                "duration": duration,
                "chunks_count": 1,
                "status": "success",
                "success": True  # ⭐ 명시적 True
            }

        except requests.exceptions.Timeout:
            return {**fail_result, "error": f"타임아웃 ({self.timeout}초)"}
        except requests.exceptions.ConnectionError as e:
            return {**fail_result, "error": f"연결 오류: {e}"}
        except Exception as e:
            print(f"  [Scene {scene_id}] ❌ 예외: {e}")
            traceback.print_exc()
            return {**fail_result, "error": f"예외: {e}"}


# ============================================================
# 순차 생성기 (GPU 1개 환경에서 최적)
# ============================================================

class SequentialTTSGenerator:
    """
    순차 TTS 생성기

    GPU가 하나일 때:
    - 병렬 처리 → 서버에서 큐잉 → 실제로는 순차 + 오버헤드
    - 순차 처리 → 오버헤드 없음 → 더 빠르고 안정적
    """

    def __init__(
        self,
        api_url: str = CHATTERBOX_URL,
        timeout: int = 300
    ):
        self.api_url = api_url
        self.timeout = timeout

        self.session = requests.Session()
        adapter = HTTPAdapter(
            pool_connections=5,
            pool_maxsize=5,
            max_retries=Retry(total=2, backoff_factor=0.5)
        )
        self.session.mount("http://", adapter)
        self.session.headers.update({
            "Connection": "keep-alive",
            "Content-Type": "application/json"
        })

        print(f"\n[SequentialGen] 초기화")
        print(f"  🎯 순차 처리 모드 (GPU 최적화)")
        print(f"  ⏱️ 타임아웃: {timeout}초")

    def generate_all(
        self,
        scenes: List[Dict],
        params: Dict,
        progress_callback: Optional[Callable] = None
    ) -> List[Dict]:
        """순차 생성"""

        total = len(scenes)
        results = []

        voice_ref = params.get("voice_ref_path")
        print(f"\n[SequentialGen] 🎤 Voice: {voice_ref[-40:] if voice_ref else '기본 음성'}")

        print(f"\n{'='*60}")
        print(f"[SequentialGen] 🎯 {total}개 씬 순차 생성 시작")
        print(f"{'='*60}")

        total_start = time.time()

        for idx, scene in enumerate(scenes):
            scene_id = scene.get("scene_id", idx + 1)

            if progress_callback:
                try:
                    progress_callback(idx, total, f"씬 {scene_id} 생성 중...")
                except:
                    pass

            gen_start = time.time()
            result = self._generate_single(scene, params)
            gen_time = time.time() - gen_start

            if result.get("success") and result.get("audio_data"):
                audio_size = len(result.get("audio_data", b"")) // 1024
                duration = result.get("duration", 0)
                print(f"[Scene {scene_id}] ✅ {gen_time:.1f}초 (오디오: {duration:.1f}초, {audio_size}KB)")
            else:
                print(f"[Scene {scene_id}] ❌ {result.get('error', 'Unknown')}")

            result["generation_time"] = gen_time
            results.append(result)

        total_time = time.time() - total_start
        success_count = sum(1 for r in results if r.get("success") and r.get("audio_data"))

        print(f"\n{'='*60}")
        print(f"[SequentialGen] ✅ 완료: {success_count}/{total}개 성공")
        print(f"[SequentialGen] ⏱️ 총 시간: {total_time:.1f}초")
        print(f"[SequentialGen] ⏱️ 씬당 평균: {total_time/total:.1f}초")
        print(f"{'='*60}")

        if progress_callback:
            try:
                progress_callback(total, total, f"생성 완료 ({success_count}/{total})")
            except:
                pass

        return results

    def _generate_single(self, scene: Dict, params: Dict) -> Dict:
        """단일 씬 생성"""

        text = scene.get("text", "")
        scene_id = scene.get("scene_id", 0)
        char_count = len(text.replace(" ", "").replace("\n", ""))

        fail_result = {
            "scene_id": scene_id,
            "text": text,
            "text_preview": text[:50] + "..." if len(text) > 50 else text,
            "char_count": char_count,
            "audio_data": None,
            "duration": 0,
            "chunks_count": 1,
            "status": "failed",
            "success": False
        }

        if not text.strip():
            return {**fail_result, "error": "빈 텍스트"}

        request_data = {
            "text": text,
            "settings": {
                "language": params.get("language", "ko"),
                "voice_ref_path": params.get("voice_ref_path"),
                "exaggeration": params.get("exaggeration", 0.5),
                "cfg_weight": params.get("cfg_weight", 0.5),
                "temperature": params.get("temperature", 0.8),
                "speed": params.get("speed", 1.0),
                "repetition_penalty": params.get("repetition_penalty", 1.4),
                "seed": params.get("seed"),
            }
        }

        try:
            response = self.session.post(
                f"{self.api_url}/generate",
                json=request_data,
                timeout=self.timeout
            )

            if response.status_code != 200:
                return {**fail_result, "error": f"HTTP {response.status_code}"}

            result = response.json()

            if not result.get("success"):
                return {**fail_result, "error": result.get("error", "서버 실패")}

            audio_url = result.get("audio_url") or result.get("audio_path", "")
            if not audio_url:
                return {**fail_result, "error": "audio_url 없음"}

            # 다운로드
            audio_resp = self.session.get(
                f"{self.api_url}{audio_url}",
                timeout=60
            )

            if audio_resp.status_code != 200:
                return {**fail_result, "error": f"다운로드 HTTP {audio_resp.status_code}"}

            audio_data = audio_resp.content
            if not audio_data or len(audio_data) < 1000:
                return {**fail_result, "error": "오디오 데이터 없음"}

            duration = result.get("duration_seconds") or result.get("duration") or 0

            return {
                "scene_id": scene_id,
                "text": text,
                "text_preview": text[:50] + "..." if len(text) > 50 else text,
                "char_count": char_count,
                "audio_data": audio_data,
                "duration": duration,
                "chunks_count": 1,
                "status": "success",
                "success": True
            }

        except requests.exceptions.Timeout:
            return {**fail_result, "error": f"타임아웃 ({self.timeout}초)"}
        except Exception as e:
            return {**fail_result, "error": str(e)}

    def close(self):
        try:
            self.session.close()
        except:
            pass


# ============================================================
# 간편 함수
# ============================================================

def generate_scenes_parallel(
    scenes: List[Dict],
    params: Dict,
    max_workers: int = 3,
    timeout_per_scene: int = 300,
    use_sequential: bool = True,  # ⭐ 기본값 순차 모드 (GPU 1개 최적)
    progress_callback: Optional[Callable] = None
) -> List[Dict]:
    """
    TTS 생성 함수 (순차/병렬 선택)

    Args:
        scenes: 씬 리스트
        params: TTS 파라미터
        max_workers: 병렬 시 동시 처리 수
        timeout_per_scene: 씬당 타임아웃
        use_sequential: True=순차(GPU 1개 최적), False=병렬
        progress_callback: 진행 콜백

    수정사항:
    - 기본값 순차 모드 (GPU 1개 환경에서 더 빠름)
    - 병렬 시 오버헤드 제거
    """

    if use_sequential:
        # ⭐ 순차 모드 (기본, GPU 1개 최적)
        generator = SequentialTTSGenerator(timeout=timeout_per_scene)
        try:
            results = generator.generate_all(scenes, params, progress_callback)
        finally:
            generator.close()
    else:
        # 병렬 모드 (멀티 GPU 환경용)
        generator = ParallelTTSGenerator(
            max_workers=max_workers,
            timeout=timeout_per_scene
        )
        results = generator.generate_all(scenes, params, progress_callback)

    # 최종 검증 로그
    final_success = sum(1 for r in results if r and r.get("success") and r.get("audio_data"))
    mode = "순차" if use_sequential else "병렬"
    print(f"\n[generate_scenes] 최종 반환: {final_success}/{len(scenes)}개 성공 ({mode} 모드)")

    return results
