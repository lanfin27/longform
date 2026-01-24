/**
 * ImageFX Persistent Worker v2.0
 *
 * 단일 프로세스로 여러 이미지 생성 요청을 처리
 * stdin으로 JSON 요청을 받고 stdout으로 JSON 응답 반환
 *
 * v2.0 변경사항:
 * - 🔧 Prompt 클래스를 사용하여 시드 제대로 전달!
 * - 문자열 프롬프트 대신 Prompt 객체 생성
 * - 시드가 실제로 API에 전달되도록 수정
 *
 * 최적화:
 * - ImageFX 클라이언트 1회만 초기화
 * - 프로세스 재사용으로 시작 시간 절약
 * - 연결 풀링
 */

const readline = require("readline");
const fs = require("fs");
const path = require("path");

// 전역 상태
let fxClient = null;
let PromptClass = null;  // v2.0: Prompt 클래스 참조
let initialized = false;
let currentCookie = null;
let requestCount = 0;
let startTime = Date.now();

// 초기화 함수
async function initialize(cookie) {
    if (initialized && currentCookie === cookie) {
        return { success: true, message: "Already initialized" };
    }

    try {
        // v2.0: Prompt 클래스도 함께 로드
        const { ImageFX, Prompt } = require("@rohitaryal/imagefx-api");
        fxClient = new ImageFX(cookie);
        PromptClass = Prompt;
        currentCookie = cookie;
        initialized = true;
        startTime = Date.now();
        requestCount = 0;

        return { success: true, message: "Initialized" };
    } catch (error) {
        console.error("[ImageFX-Worker] 초기화 실패:", error.message);
        return { success: false, error: error.message };
    }
}

// 이미지 생성 함수
async function generateImage(request) {
    if (!initialized || !fxClient) {
        return { success: false, error: "Not initialized. Send init request first." };
    }

    if (!PromptClass) {
        return { success: false, error: "Prompt class not loaded. Re-initialize required." };
    }

    const {
        prompt,
        outputPath,
        model,
        aspectRatio,
        count = 1,
        seed,
        negativePrompt
    } = request;

    if (!prompt) {
        return { success: false, error: "prompt is required" };
    }

    requestCount++;

    try {
        // ═══════════════════════════════════════════════════════════════
        // v2.0: 시드 설정 (Prompt 객체에 직접 전달)
        // ═══════════════════════════════════════════════════════════════
        let usedSeed;
        if (seed !== undefined && seed !== null) {
            usedSeed = parseInt(seed, 10);
            console.error(`[ImageFX-Worker v2.0] 🔒 잠긴 시드 사용: ${usedSeed}`);
        } else {
            usedSeed = Math.floor(Math.random() * 2147483647) + 1;
            console.error(`[ImageFX-Worker v2.0] 🎲 랜덤 시드 생성: ${usedSeed}`);
        }

        // ═══════════════════════════════════════════════════════════════
        // v2.0: aspectRatio 매핑 (라이브러리 형식에 맞게)
        // "LANDSCAPE" → "IMAGE_ASPECT_RATIO_LANDSCAPE"
        // ═══════════════════════════════════════════════════════════════
        let mappedAspectRatio = aspectRatio || "IMAGE_ASPECT_RATIO_LANDSCAPE";
        if (aspectRatio && !aspectRatio.startsWith("IMAGE_ASPECT_RATIO_")) {
            mappedAspectRatio = `IMAGE_ASPECT_RATIO_${aspectRatio}`;
        }

        // ═══════════════════════════════════════════════════════════════
        // v2.0: 모델 매핑
        // ═══════════════════════════════════════════════════════════════
        let mappedModel = model || "IMAGEN_3_5";
        // IMAGEN_4는 실제로 IMAGEN_3_5로 전달됨 (라이브러리 제한)
        if (mappedModel === "IMAGEN_4") {
            mappedModel = "IMAGEN_3_5";  // 라이브러리가 지원하는 모델명
        }

        // v2.1: 로그 최소화 - 에러 시에만 상세 출력

        // ═══════════════════════════════════════════════════════════════
        // v2.0: Prompt 객체 생성 - 시드가 실제로 API에 전달됨!
        // ═══════════════════════════════════════════════════════════════
        const promptObj = new PromptClass({
            seed: usedSeed,
            prompt: prompt,
            numberOfImages: parseInt(count, 10) || 1,
            aspectRatio: mappedAspectRatio,
            generationModel: mappedModel
        });


        // 이미지 생성 - Prompt 객체 전달
        let images;
        if (typeof fxClient.generateImage === "function") {
            images = await fxClient.generateImage(promptObj);
        } else if (typeof fxClient.generate === "function") {
            images = await fxClient.generate(promptObj);
        } else {
            throw new Error("No supported generation method found");
        }

        if (!images || images.length === 0) {
            throw new Error("No images generated");
        }


        // 출력 디렉토리 생성
        const finalOutputPath = outputPath || `./output/generated_${Date.now()}.png`;
        const outputDir = path.dirname(finalOutputPath);
        if (outputDir && !fs.existsSync(outputDir)) {
            fs.mkdirSync(outputDir, { recursive: true });
        }

        // 이미지 저장
        let savedPath;
        if (typeof images[0].save === "function") {
            savedPath = images[0].save(outputDir);
        } else if (images[0].data || images[0].buffer || images[0].encodedImage) {
            const imageData = images[0].data || images[0].buffer || Buffer.from(images[0].encodedImage, "base64");
            fs.writeFileSync(finalOutputPath, imageData);
            savedPath = finalOutputPath;
        } else {
            throw new Error("Cannot save image data");
        }

        // 시드 추출 (API 응답에서 시드 확인)
        let extractedSeed = usedSeed;  // 기본값: 우리가 보낸 시드
        if (images[0]) {
            const apiSeed = images[0].seed || images[0].generationSeed ||
                           images[0].metadata?.seed || images[0].info?.seed;
            if (apiSeed) {
                extractedSeed = apiSeed;
            }
        }

        return {
            success: true,
            path: savedPath,
            seed: extractedSeed,
            count: images.length,
            requestNumber: requestCount
        };

    } catch (error) {
        // v2.1: 에러 시에만 로그
        console.error(`[ImageFX-Worker] 오류:`, error.message);

        // 상세 에러 정보 추출
        let errorMessage = error.message;
        let errorCode = null;
        let errorReason = null;

        if (error.response) {
            errorCode = error.response.status;
            const data = error.response.data;
            if (data && data.error) {
                errorMessage = data.error.message || errorMessage;
                if (data.error.details && data.error.details.length > 0) {
                    errorReason = data.error.details[0].reason;
                }
            }
        }

        return {
            success: false,
            error: errorMessage,
            errorCode,
            errorReason,
            requestNumber: requestCount
        };
    }
}

// 상태 조회
function getStatus() {
    const uptime = Math.round((Date.now() - startTime) / 1000);
    return {
        success: true,
        initialized,
        requestCount,
        uptimeSeconds: uptime,
        memoryUsage: process.memoryUsage()
    };
}

// 종료
function shutdown() {
    return { success: true, message: "Shutting down", totalRequests: requestCount };
}

// 메인 루프 - stdin에서 요청 읽기
const rl = readline.createInterface({
    input: process.stdin,
    output: process.stdout,
    terminal: false
});

// v2.1: 시작 로그 최소화

rl.on("line", async (line) => {
    try {
        const request = JSON.parse(line);
        let response;

        switch (request.type) {
            case "init":
                response = await initialize(request.cookie);
                break;

            case "generate":
                response = await generateImage(request);
                break;

            case "status":
                response = getStatus();
                break;

            case "shutdown":
                response = shutdown();
                console.log(JSON.stringify(response));
                process.exit(0);
                break;

            case "ping":
                response = { success: true, message: "pong", timestamp: Date.now() };
                break;

            default:
                response = { success: false, error: `Unknown request type: ${request.type}` };
        }

        // 응답 출력 (stdout으로)
        console.log(JSON.stringify(response));

    } catch (error) {
        console.error("[ImageFX-Worker v2.0] JSON 파싱 오류:", error.message);
        console.log(JSON.stringify({ success: false, error: `Parse error: ${error.message}` }));
    }
});

rl.on("close", () => {
    console.error("[ImageFX-Worker v2.0] stdin 닫힘 - 종료");
    process.exit(0);
});

// 예외 처리
process.on("uncaughtException", (error) => {
    console.error("[ImageFX-Worker v2.0] 처리되지 않은 예외:", error.message);
    console.log(JSON.stringify({ success: false, error: `Uncaught exception: ${error.message}` }));
});

process.on("unhandledRejection", (reason, promise) => {
    console.error("[ImageFX-Worker v2.0] 처리되지 않은 Promise 거부:", reason);
});
