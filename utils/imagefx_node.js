/**
 * ImageFX Node.js 래퍼 v6.1
 * rohitaryal/imagefx-api 라이브러리 사용
 *
 * 수정: generate() → generateImage()
 */

const fs = require("fs");
const path = require("path");

async function main() {
    try {
        // 라이브러리 동적 로드
        const { ImageFX } = require("@rohitaryal/imagefx-api");
        console.log("[ImageFX-Node] 라이브러리 로드 완료");

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
            seed
        } = options;

        console.log("[ImageFX-Node] 이미지 생성 시작...");
        console.log("[ImageFX-Node] 프롬프트:", prompt.substring(0, 50) + "...");
        console.log("[ImageFX-Node] 모델:", model || "기본값");
        console.log("[ImageFX-Node] 비율:", aspectRatio || "기본값");

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

        // 시드 설정
        if (seed) {
            generateOptions.seed = parseInt(seed, 10);
        }

        console.log("[ImageFX-Node] 옵션:", JSON.stringify(generateOptions));

        // ============================================
        // 핵심 수정: generate() → generateImage()
        // ============================================
        let images;

        // 방법 1: generateImage 메서드 (README 기준)
        if (typeof fx.generateImage === "function") {
            console.log("[ImageFX-Node] generateImage() 메서드 사용");
            images = await fx.generateImage(prompt, generateOptions);
        }
        // 방법 2: generate 메서드 (혹시 버전에 따라 다를 경우)
        else if (typeof fx.generate === "function") {
            console.log("[ImageFX-Node] generate() 메서드 사용");
            images = await fx.generate(prompt, generateOptions);
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

        // 성공 결과 출력
        outputResult({
            success: true,
            path: savedPath,
            count: images.length
        });

        process.exit(0);

    } catch (error) {
        console.error("[ImageFX-Node] 오류:", error.message);

        // 상세 오류 정보
        if (error.response) {
            console.error("[ImageFX-Node] API 응답:", error.response.status, error.response.data);
        }

        outputResult({
            success: false,
            error: error.message
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
