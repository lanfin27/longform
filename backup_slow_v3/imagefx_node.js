/**
 * ImageFX Node.js 래퍼 v7.1
 * rohitaryal/imagefx-api 라이브러리 사용
 *
 * v7.1: 모델명 매핑 수정 (IMAGEN_4 → IMAGEN_3_5)
 * - 라이브러리 v3.0.3에서 IMAGEN_3_5만 지원
 * - IMAGEN_3_5가 실제로 IMAGEN 4 (라이브러리 주석 참고)
 * - IMAGEN_4, IMAGEN_3, IMAGEN_3_1 모두 IMAGEN_3_5로 매핑
 *
 * v7.0: Prompt 클래스를 사용하여 시드 제대로 전달
 * - 문자열 프롬프트 대신 Prompt 객체 사용
 * - 시드가 실제로 API에 전달되도록 수정
 */

// ============================================================
// v7.1: 모델명 매핑 (라이브러리 v3.0.3 기준)
// IMAGEN_3_5만 지원됨 (실제로 IMAGEN 4)
// ============================================================
const MODEL_MAP = {
    "IMAGEN_4": "IMAGEN_3_5",      // IMAGEN_4 → IMAGEN_3_5 (라이브러리 지원 모델)
    "IMAGEN_3_5": "IMAGEN_3_5",    // 그대로
    "IMAGEN_3": "IMAGEN_3_5",      // 미지원 → IMAGEN_3_5로 대체
    "IMAGEN_3_1": "IMAGEN_3_5",    // 미지원 → IMAGEN_3_5로 대체
};

const fs = require("fs");
const path = require("path");

async function main() {
    try {
        // 라이브러리 동적 로드 - Prompt 클래스도 함께 로드
        const { ImageFX, Prompt } = require("@rohitaryal/imagefx-api");
        console.log("[ImageFX-Node] 라이브러리 로드 완료 (ImageFX + Prompt)");

        // 명령줄 인자 파싱
        const args = process.argv.slice(2);
        const options = {};

        for (let i = 0; i < args.length; i += 2) {
            if (args[i] && args[i + 1]) {
                const key = args[i].replace(/^--/, "");
                options[key] = args[i + 1];
            }
        }

        // 필수 인자 확인
        if (!options.cookie) {
            console.error("[ImageFX-Node] 오류: --cookie 인자가 필요합니다");
            outputResult({ success: false, error: "cookie 인자 누락" });
            process.exit(1);
        }

        if (!options.prompt) {
            console.error("[ImageFX-Node] 오류: --prompt 인자가 필요합니다");
            outputResult({ success: false, error: "prompt 인자 누락" });
            process.exit(1);
        }

        const {
            cookie,
            prompt,
            outputPath = "./output/generated.png",
            model,
            aspectRatio,
            count = "1",
            seed,
            negativePrompt  // ⭐ 네거티브 프롬프트 추가
        } = options;

        console.log("[ImageFX-Node] 이미지 생성 시작...");
        console.log("[ImageFX-Node] 프롬프트:", prompt.substring(0, 50) + "...");
        console.log("[ImageFX-Node] 모델:", model || "기본값");
        console.log("[ImageFX-Node] 비율:", aspectRatio || "기본값");
        console.log("[ImageFX-Node] 네거티브:", negativePrompt ? negativePrompt.substring(0, 50) + "..." : "없음");

        // ImageFX 클라이언트 생성
        const fx = new ImageFX(cookie);

        // 생성 옵션
        const generateOptions = {
            count: parseInt(count, 10) || 1
        };

        // 모델 설정 (라이브러리가 지원하는 경우)
        if (model) {
            generateOptions.model = model;
        }

        // 비율 설정 (라이브러리가 지원하는 경우)
        if (aspectRatio) {
            generateOptions.size = aspectRatio;
        }

        // ⭐ v1.2: 시드 설정 - 항상 시드를 사용하여 재현성 보장
        // 사용자가 시드를 제공하지 않으면 랜덤 시드 생성
        let usedSeed;
        if (seed) {
            usedSeed = parseInt(seed, 10);
        } else {
            // 랜덤 시드 생성 (1 ~ 2147483647)
            usedSeed = Math.floor(Math.random() * 2147483647) + 1;
            console.log("[ImageFX-Node] 🎲 랜덤 시드 생성:", usedSeed);
        }
        generateOptions.seed = usedSeed;

        // ⭐ 네거티브 프롬프트 설정 (라이브러리가 지원하는 경우)
        if (negativePrompt) {
            generateOptions.negativePrompt = negativePrompt;
        }

        console.log("[ImageFX-Node] 옵션:", JSON.stringify(generateOptions));
        console.log("[ImageFX-Node] 네거티브 포함:", generateOptions.negativePrompt ? "✅" : "❌");

        // ============================================
        // v7.0: Prompt 클래스를 사용하여 시드 제대로 전달
        // 문자열 프롬프트 대신 Prompt 객체 생성
        // ============================================

        // aspectRatio 매핑 (라이브러리 형식에 맞게)
        // "LANDSCAPE" → "IMAGE_ASPECT_RATIO_LANDSCAPE"
        let mappedAspectRatio = aspectRatio;
        if (aspectRatio && !aspectRatio.startsWith("IMAGE_ASPECT_RATIO_")) {
            mappedAspectRatio = `IMAGE_ASPECT_RATIO_${aspectRatio}`;
        }

        // 네거티브 프롬프트가 있으면 프롬프트에 추가
        let finalPrompt = prompt;
        if (negativePrompt && negativePrompt.trim()) {
            // ImageFX는 네거티브 프롬프트를 별도로 지원하지 않으므로
            // 프롬프트 끝에 추가하거나 무시 (API 특성에 따라)
            console.log("[ImageFX-Node] ⚠️ 네거티브 프롬프트는 ImageFX API에서 직접 지원하지 않음");
        }

        // ============================================================
        // v7.1: 모델명 매핑 적용 (IMAGEN_4 → IMAGEN_3_5)
        // ============================================================
        const requestedModel = model || "IMAGEN_4";
        const mappedModel = MODEL_MAP[requestedModel] || "IMAGEN_3_5";

        if (requestedModel !== mappedModel) {
            console.log(`[ImageFX-Node] 🔄 모델 매핑: ${requestedModel} → ${mappedModel}`);
        }

        // Prompt 객체 생성 - 시드가 실제로 전달됨
        const promptObj = new Prompt({
            seed: usedSeed,
            prompt: finalPrompt,
            numberOfImages: parseInt(count, 10) || 1,
            aspectRatio: mappedAspectRatio,
            generationModel: mappedModel  // v7.1: 매핑된 모델 사용
        });

        console.log("[ImageFX-Node] 🎯 Prompt 객체 생성:");
        console.log("[ImageFX-Node]   - seed:", usedSeed);
        console.log("[ImageFX-Node]   - numberOfImages:", parseInt(count, 10) || 1);
        console.log("[ImageFX-Node]   - aspectRatio:", mappedAspectRatio);
        console.log("[ImageFX-Node]   - generationModel:", mappedModel, `(요청: ${requestedModel})`);

        let images;

        // Prompt 객체를 사용하여 이미지 생성
        if (typeof fx.generateImage === "function") {
            console.log("[ImageFX-Node] generateImage(Prompt) 메서드 사용");
            images = await fx.generateImage(promptObj);
        }
        // 방법 2: generate 메서드 (혹시 버전에 따라 다를 경우)
        else if (typeof fx.generate === "function") {
            console.log("[ImageFX-Node] generate(Prompt) 메서드 사용");
            images = await fx.generate(promptObj);
        }
        // 방법 3: 직접 호출
        else {
            // ImageFX 클래스의 메서드 목록 출력
            console.log("[ImageFX-Node] 사용 가능한 메서드:", Object.getOwnPropertyNames(Object.getPrototypeOf(fx)));
            throw new Error("지원되는 이미지 생성 메서드를 찾을 수 없습니다");
        }

        // 결과 확인
        if (!images || images.length === 0) {
            throw new Error("이미지 생성 실패: 결과 없음");
        }

        console.log(`[ImageFX-Node] ${images.length}개 이미지 생성됨`);

        // 출력 디렉토리 생성
        const outputDir = path.dirname(outputPath);
        if (outputDir && !fs.existsSync(outputDir)) {
            fs.mkdirSync(outputDir, { recursive: true });
        }

        // 첫 번째 이미지 저장
        let savedPath;

        // Image 객체의 save 메서드 사용
        if (typeof images[0].save === "function") {
            savedPath = images[0].save(outputDir);
            console.log("[ImageFX-Node] save() 메서드로 저장됨:", savedPath);
        }
        // 또는 직접 저장
        else if (images[0].data || images[0].buffer || images[0].encodedImage) {
            const imageData = images[0].data || images[0].buffer || Buffer.from(images[0].encodedImage, "base64");
            fs.writeFileSync(outputPath, imageData);
            savedPath = outputPath;
            console.log("[ImageFX-Node] 직접 저장됨:", savedPath);
        }
        else {
            // 이미지 객체 구조 확인
            console.log("[ImageFX-Node] 이미지 객체 키:", Object.keys(images[0]));
            throw new Error("이미지 데이터를 저장할 수 없습니다");
        }

        // v1.2: 시드 값 추출 (이미지 객체 또는 사용된 시드)
        let extractedSeed = usedSeed;  // 기본값: 우리가 사용한 시드
        if (images[0]) {
            // API 응답에서 시드가 있으면 그것을 사용
            const apiSeed = images[0].seed || images[0].generationSeed ||
                           images[0].metadata?.seed || images[0].info?.seed;
            if (apiSeed) {
                extractedSeed = apiSeed;
            }
        }
        console.log("[ImageFX-Node] 🔑 최종 시드:", extractedSeed);

        // 성공 결과 출력 (시드 항상 포함)
        outputResult({
            success: true,
            path: savedPath,
            count: images.length,
            seed: extractedSeed,  // v1.2: 시드 항상 반환
            model: model || "default",
            aspectRatio: aspectRatio || "default"
        });

        process.exit(0);

    } catch (error) {
        console.error("[ImageFX-Node] 오류:", error.message);

        // 상세 오류 정보 추출
        let errorMessage = error.message;
        let errorCode = null;
        let errorReason = null;

        // API 응답에서 상세 에러 추출
        if (error.response) {
            console.error("[ImageFX-Node] API 응답:", error.response.status, JSON.stringify(error.response.data));
            errorCode = error.response.status;

            // Google API 에러 형식 파싱
            const data = error.response.data;
            if (data && data.error) {
                errorMessage = data.error.message || errorMessage;

                // details에서 reason 추출
                if (data.error.details && data.error.details.length > 0) {
                    errorReason = data.error.details[0].reason;
                    console.error("[ImageFX-Node] 에러 상세:", errorReason);
                }
            }
        }

        // 에러 객체의 다른 속성에서도 정보 추출
        if (error.cause) {
            console.error("[ImageFX-Node] 원인:", error.cause);
        }
        if (error.code) {
            errorCode = errorCode || error.code;
        }

        outputResult({
            success: false,
            error: errorMessage,
            errorCode: errorCode,
            errorReason: errorReason
        });

        process.exit(1);
    }
}

function outputResult(result) {
    // 구분자로 결과 출력 (Python에서 파싱하기 쉽게)
    console.log("===RESULT===");
    console.log(JSON.stringify(result));
}

// 실행
main();
