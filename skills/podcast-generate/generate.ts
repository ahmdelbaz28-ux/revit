#!/usr/bin/env tsx

/**
 * generate.ts - 统一入口（纯 SDK 版本）
 * 原资料 -> podcast_script.md + podcast.wav
 *
 * 只使用 z-ai-web-dev-sdk，不依赖 z-ai CLI
 *
 * Usage:
 *   tsx generate.ts --input=material.txt --out_dir=out
 *   tsx generate.ts --input=material.md --out_dir=out --duration=5
 */

import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import ZAI from "z-ai-web-dev-sdk";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// -----------------------------
// Types
// -----------------------------
interface GenConfig {
	mode: "dual" | "single-male" | "single-female";
	temperature: number;
	durationManual: number;
	charsPerMin: number;
	hostName: string;
	guestName: string;
	audience: string;
	tone: string;
	maxAttempts: number;
	timeoutSec: number;
	voiceHost: string;
	voiceGuest: string;
	speed: number;
	pauseMs: number;
}

interface Segment {
	idx: number;
	speaker: "host" | "guest";
	name: string;
	text: string;
}

// -----------------------------
// Config
// -----------------------------
const DEFAULT_CONFIG: GenConfig = {
	mode: "dual",
	temperature: 0.9,
	durationManual: 0,
	charsPerMin: 240,
	hostName: "小谱",
	guestName: "锤锤",
	audience: "白领小白",
	tone: "轻松但有信息密度",
	maxAttempts: 3,
	timeoutSec: 300,
	voiceHost: "xiaochen",
	voiceGuest: "chuichui",
	speed: 1.0,
	pauseMs: 200,
};

const DURATION_RANGE_LOW = 3;
const DURATION_RANGE_HIGH = 20;
const BUDGET_TOLERANCE = 0.15;

// -----------------------------
// Functions
// -----------------------------

function parseArgs(): { [key: string]: any } {
	const args = process.argv.slice(2);
	const result: { [key: string]: any } = {};

	for (let i = 0; i < args.length; i++) {
		const arg = args[i];
		if (arg.startsWith("--")) {
			const key = arg.slice(2);
			if (key.includes("=")) {
				const [k, v] = key.split("=");
				result[k] = v;
			} else if (i + 1 < args.length && !args[i + 1].startsWith("--")) {
				result[key] = args[i + 1];
				i++;
			} else {
				result[key] = true;
			}
		}
	}

	return result;
}

function readText(filePath: string): string {
	let content = fs.readFileSync(filePath, "utf-8");
	content = content.replace(/\r\n/g, "\n");
	content = content.replace(/\n{3,}/g, "\n\n");
	content = content.replace(/[ \t]{2,}/g, " ");
	content = content.replace(/-\n/g, "");
	return content.trim();
}

function countNonWsChars(text: string): number {
	return text.replace(/\s+/g, "").length;
}

function chooseDurationMinutes(
	inputChars: number,
	low: number = DURATION_RANGE_LOW,
	high: number = DURATION_RANGE_HIGH,
): number {
	const estimated = Math.max(
		low,
		Math.min(high, Math.floor(inputChars / 1000)),
	);
	return estimated;
}

function charBudget(
	durationMin: number,
	charsPerMin: number,
	tolerance: number,
): [number, number, number] {
	const target = durationMin * charsPerMin;
	const low = Math.floor(target * (1 - tolerance));
	const high = Math.ceil(target * (1 + tolerance));
	return [target, low, high];
}

function buildPrompts(
	material: string,
	cfg: GenConfig,
	durationMin: number,
	budgetTarget: number,
	budgetLow: number,
	budgetHigh: number,
	attemptHint: string = "",
): [string, string] {
	let system: string;
	let user: string;

	if (cfg.mode === "dual") {
		system =
			`你是一个播客脚本编剧，擅长把资料提炼成双人对谈播客。` +
			`角色固定为男主持「${cfg.hostName}」与女嘉宾「${cfg.guestName}」。` +
			`你写作口播化、信息密度适中、有呼吸感、节奏自然。` +
			`你必须严格遵守输出格式与字数预算。`;

		const hintBlock = attemptHint
			? `\n【上一次生成纠偏提示】\n${attemptHint}\n`
			: "";

		user = `请把下面【资料】改写为中文播客脚本，形式为双人对谈（男主持 ${cfg.hostName} + 女嘉宾 ${cfg.guestName}）。
时长目标：${durationMin} 分钟。

【硬性约束】
1) 总字数必须在 ${budgetLow} 到 ${budgetHigh} 字之间（目标约 ${budgetTarget} 字）。
2) 严格使用轮次交替输出：每段必须以"**${cfg.hostName}**："或"**${cfg.guestName}**："开头。
3) 必须包含完整的叙事结构（但不要在对话中写出结构标签）：
   - 开场：Hook 引入 + 本期主题介绍
   - 主体：3个不同维度的内容，用自然过渡语连接
   - 总结：回顾要点 + 行动建议（1句话，明确可执行）
4) 不要在对话中写"核心点1"、"第一点"等结构标签，用自然的过渡语如"说到这个"、"还有个有趣的事"、"另外"等
5) 不要照念原文，不要大段引用；要用口播化表达。
6) 受众：${cfg.audience}
7) 风格：${cfg.tone}

【呼吸感与自然对话 - 重要！】
为了营造真实播客的呼吸感，请：
1) 适度加入语气词和感叹词：嗯、哦、啊、对、没错、哈哈、哇、天呐、啧啧等
2) 多用互动式表达："你说得对"、"这就很有意思了"、"等等，让我想想"、"我懂你的意思"
3) 适当加入思考和停顿的暗示："这个问题嘛..."、"怎么说呢..."、"其实..."
4) 避免过于密集的信息输出，每段控制在3-5句话，给听众消化时间
5) 用类比和生活化的例子来解释复杂概念
6) 两人之间要有自然的呼应和追问，而不是各说各话
7) 不同主题之间用自然过渡语连接，不要出现"核心点1/2/3"等标签

【输出格式示例】
**${cfg.hostName}**：开场……
**${cfg.guestName}**：回应……
（一直交替到结束）

${hintBlock}
【资料】
${material}
`;
	} else {
		const speakerName =
			cfg.mode === "single-male" ? cfg.hostName : cfg.guestName;
		const gender = cfg.mode === "single-male" ? "男性" : "女性";

		system =
			`你是一个${gender}单人播客主播，名字叫「${speakerName}」。` +
			`你擅长把资料提炼成单人独白式播客，像讲课、读书分享、知识科普一样。` +
			`你写作口播化、信息密度适中、有呼吸感、节奏自然。` +
			`你必须严格遵守输出格式与字数预算。`;

		const hintBlock = attemptHint
			? `\n【上一次生成纠偏提示】\n${attemptHint}\n`
			: "";

		user = `请把下面【资料】改写为中文单人播客脚本，形式为独白式讲述（主播：${speakerName}）。
时长目标：${durationMin} 分钟。

【硬性约束】
1) 总字数必须在 ${budgetLow} 到 ${budgetHigh} 字之间（目标约 ${budgetTarget} 字）。
2) 所有内容均由「${speakerName}」一人讲述，每段都以"**${speakerName}**："开头。
3) 必须包含完整的叙事结构（但不要在对话中写出结构标签）：
   - 开场：Hook 引入 + 本期主题介绍
   - 主体：3个不同维度的内容，用自然过渡语连接
   - 总结：回顾要点 + 行动建议（1句话，明确可执行）
4) 不要在对话中写"核心点1"、"第一点"等结构标签，用自然的过渡语如"说到这个"、"还有个有趣的事"、"另外"等
5) 不要照念原文，不要大段引用；要用口播化表达。
6) 受众：${cfg.audience}
7) 风格：${cfg.tone}

【单人播客的呼吸感 - 重要！】
为了营造自然的单人播客呼吸感，请：
1) 适度加入语气词和感叹词：嗯、哦、啊、对、没错、哈哈、哇、天呐、啧啧等
2) 多用自问自答式表达："你可能会问...答案是..."、"这是为什么呢？让我来解释..."
3) 适当加入思考和停顿的暗示："这个问题嘛..."、"怎么说呢..."、"其实..."
4) 避免过于密集的信息输出，每段控制在3-5句话，给听众消化时间
5) 用类比和生活化的例子来解释复杂概念
6) 像在和朋友聊天一样，而不是在念课文

【输出格式示例】
**${speakerName}**：开场，大家好，我是${speakerName}，今天我们来聊……
**${speakerName}**：说到这个，最近有个特别有意思的事……
（所有内容都由${speakerName}讲述，分段输出）

${hintBlock}
【资料】
${material}
`;
	}

	return [system, user];
}

async function callZAI(
	systemPrompt: string,
	userPrompt: string,
	_temperature: number,
): Promise<string> {
	const zai = await ZAI.create();

	const completion = await zai.chat.completions.create({
		messages: [
			{ role: "assistant", content: systemPrompt },
			{ role: "user", content: userPrompt },
		],
		thinking: { type: "disabled" },
	});

	const content = completion.choices[0]?.message?.content || "";
	return content;
}

function scriptToSegments(
	script: string,
	hostName: string,
	guestName: string,
): Segment[] {
	const segments: Segment[] = [];
	const lines = script.split("\n");

	let current: Segment | null = null;
	let idx = 0;

	const hostPrefix = `**${hostName}**：`;
	const guestPrefix = `**${guestName}**：`;

	for (const rawLine of lines) {
		const line = rawLine.trim();
		if (!line) continue;

		if (line.startsWith(hostPrefix)) {
			idx++;
			current = {
				idx,
				speaker: "host",
				name: hostName,
				text: line.slice(hostPrefix.length).trim(),
			};
			segments.push(current);
		} else if (line.startsWith(guestPrefix)) {
			idx++;
			current = {
				idx,
				speaker: "guest",
				name: guestName,
				text: line.slice(guestPrefix.length).trim(),
			};
			segments.push(current);
		} else {
			if (current) {
				current.text = `${current.text} ${line}`.trim();
			}
		}
	}

	return segments;
}

function validateScript(
	script: string,
	cfg: GenConfig,
	budgetLow: number,
	budgetHigh: number,
): [boolean, string[]] {
	const reasons: string[] = [];

	if (cfg.mode === "dual") {
		const hostTag = `**${cfg.hostName}**：`;
		const guestTag = `**${cfg.guestName}**：`;

		if (!script.includes(hostTag)) reasons.push(`缺少主持人标识：${hostTag}`);
		if (!script.includes(guestTag)) reasons.push(`缺少嘉宾标识：${guestTag}`);

		const turns = script
			.split("\n")
			.filter((line) => line.startsWith(hostTag) || line.startsWith(guestTag));
		if (turns.length < 8) reasons.push("对谈轮次过少：建议至少 8 轮");
	} else {
		const speakerName =
			cfg.mode === "single-male" ? cfg.hostName : cfg.guestName;
		const speakerTag = `**${speakerName}**：`;

		if (!script.includes(speakerTag))
			reasons.push(`缺少主播标识：${speakerTag}`);

		const turns = script
			.split("\n")
			.filter((line) => line.startsWith(speakerTag));
		if (turns.length < 5) reasons.push("播客段数过少：建议至少 5 段");
	}

	const n = countNonWsChars(script);
	if (n < budgetLow || n > budgetHigh) {
		reasons.push(
			`字数不在预算：当前约 ${n} 字，预算 ${budgetLow}-${budgetHigh}`,
		);
	}

	// 只检查开场和总结，不检查"核心点1/2/3"标签（因为不应该出现在对话中）
	const mustHave = ["开场", "总结"];
	for (const kw of mustHave) {
		if (!script.includes(kw)) {
			reasons.push(`缺少结构要素：${kw}（请在对话中自然引入）`);
		}
	}

	// 检查是否有足够的对话轮次（确保内容覆盖了多个主题）
	const lineCount = script.split("\n").filter((l) => l.trim()).length;
	if (lineCount < 10) {
		reasons.push("对话轮次过少，建议至少10段对话");
	}

	return [reasons.length === 0, reasons];
}

function makeRetryHint(
	reasons: string[],
	cfg: GenConfig,
	budgetLow: number,
	budgetHigh: number,
): string {
	const lines = ["请严格修复以下问题后重新生成："];
	for (const r of reasons) lines.push(`- ${r}`);
	lines.push(`- 总字数必须在 ${budgetLow}-${budgetHigh} 之间。`);

	if (cfg.mode === "dual") {
		lines.push(
			`- 每段必须以"**${cfg.hostName}**："或"**${cfg.guestName}**："开头。`,
		);
	} else {
		const speakerName =
			cfg.mode === "single-male" ? cfg.hostName : cfg.guestName;
		lines.push(
			`- 所有内容都由一人讲述，每段必须以"**${speakerName}**："开头。`,
		);
	}

	lines.push(
		'- 必须包含开场和总结，中间用自然过渡语连接不同主题，不要出现"核心点1/2/3"等标签。',
	);
	return lines.join("\n");
}

async function ttsRequest(
	zai: any,
	text: string,
	voice: string,
	speed: number,
): Promise<Buffer> {
	const response = await zai.audio.tts.create({
		input: text,
		voice: voice,
		speed: speed,
		response_format: "wav",
		stream: false,
	});

	const arrayBuffer = await response.arrayBuffer();
	const buffer = Buffer.from(new Uint8Array(arrayBuffer));
	return buffer;
}

function ensureSilenceWav(
	filePath: string,
	params: { nchannels: number; sampwidth: number; framerate: number },
	ms: number,
): void {
	const { nchannels, sampwidth, framerate } = params;
	const nframes = Math.floor((framerate * ms) / 1000);
	const silenceFrame = Buffer.alloc(sampwidth * nchannels, 0);
	const frames = Buffer.alloc(silenceFrame.length * nframes, 0);

	const header = Buffer.alloc(44);
	header.write("RIFF", 0);
	header.writeUInt32LE(36 + frames.length, 4);
	header.write("WAVE", 8);
	header.write("fmt ", 12);
	header.writeUInt32LE(16, 16);
	header.writeUInt16LE(1, 20);
	header.writeUInt16LE(nchannels, 22);
	header.writeUInt32LE(framerate, 24);
	header.writeUInt32LE(framerate * nchannels * sampwidth, 28);
	header.writeUInt16LE(nchannels * sampwidth, 32);
	header.writeUInt16LE(sampwidth * 8, 34);
	header.write("data", 36);
	header.writeUInt32LE(frames.length, 40);

	fs.writeFileSync(filePath, Buffer.concat([header, frames]));
}

function wavParams(filePath: string): {
	nchannels: number;
	sampwidth: number;
	framerate: number;
} {
	const buffer = fs.readFileSync(filePath);
	const nchannels = buffer.readUInt16LE(22);
	const sampwidth = buffer.readUInt16LE(34) / 8;
	const framerate = buffer.readUInt32LE(24);
	return { nchannels, sampwidth, framerate };
}

function joinWavsWave(
	outPath: string,
	wavPaths: string[],
	pauseMs: number,
): void {
	if (wavPaths.length === 0) throw new Error("No wav files to join.");

	const ref = wavPaths[0];
	const refParams = wavParams(ref);
	const silencePath = path.join(os.tmpdir(), `_silence_${Date.now()}.wav`);
	if (pauseMs > 0) ensureSilenceWav(silencePath, refParams, pauseMs);

	const chunks: Buffer[] = [];

	for (let i = 0; i < wavPaths.length; i++) {
		const wavPath = wavPaths[i];
		const buffer = fs.readFileSync(wavPath);
		const dataStart = buffer.indexOf("data") + 8;
		const data = buffer.subarray(dataStart);

		const params = wavParams(wavPath);
		if (
			params.nchannels !== refParams.nchannels ||
			params.sampwidth !== refParams.sampwidth ||
			params.framerate !== refParams.framerate
		) {
			throw new Error(`WAV params mismatch: ${wavPath}`);
		}

		chunks.push(data);

		if (pauseMs > 0 && i < wavPaths.length - 1) {
			const silenceBuffer = fs.readFileSync(silencePath);
			const silenceData = silenceBuffer.subarray(
				silenceBuffer.indexOf("data") + 8,
			);
			chunks.push(silenceData);
		}
	}

	const totalDataSize = chunks.reduce((sum, buf) => sum + buf.length, 0);
	const header = Buffer.alloc(44);
	header.write("RIFF", 0);
	header.writeUInt32LE(36 + totalDataSize, 4);
	header.write("WAVE", 8);
	header.write("fmt ", 12);
	header.writeUInt32LE(16, 16);
	header.writeUInt16LE(1, 20);
	header.writeUInt16LE(refParams.nchannels, 22);
	header.writeUInt32LE(refParams.framerate, 24);
	header.writeUInt32LE(
		refParams.framerate * refParams.nchannels * refParams.sampwidth,
		28,
	);
	header.writeUInt16LE(refParams.nchannels * refParams.sampwidth, 32);
	header.writeUInt16LE(refParams.sampwidth * 8, 34);
	header.write("data", 36);
	header.writeUInt32LE(totalDataSize, 40);

	const output = Buffer.concat([header, ...chunks]);
	fs.writeFileSync(outPath, output);

	if (fs.existsSync(silencePath)) fs.unlinkSync(silencePath);
}

// -----------------------------
// Main
// -----------------------------
async function main() {
	const args = parseArgs();

	const inputPath = args.input;
	const outDir = args.out_dir;
	const topic = args.topic;

	// 检查参数：必须提供 input 或 topic 之一
	if ((!inputPath && !topic) || !outDir) {
		console.error("Usage: tsx generate.ts --input=<file> --out_dir=<dir>");
		console.error(
			"   OR: tsx generate.ts --topic=<search-term> --out_dir=<dir>",
		);
		console.error("");
		console.error("Examples:");
		console.error("  # From file");
		console.error("  npm run generate -- --input=article.txt --out_dir=out");
		console.error("  # From web search");
		console.error('  npm run generate -- --topic="最新AI新闻" --out_dir=out');
		process.exit(1);
	}

	// Merge config
	const cfg: GenConfig = {
		...DEFAULT_CONFIG,
		mode: (args.mode || "dual") as GenConfig["mode"],
		durationManual: parseInt(args.duration || "0", 10),
		hostName: args.host_name || DEFAULT_CONFIG.hostName,
		guestName: args.guest_name || DEFAULT_CONFIG.guestName,
		voiceHost: args.voice_host || DEFAULT_CONFIG.voiceHost,
		voiceGuest: args.voice_guest || DEFAULT_CONFIG.voiceGuest,
		speed: parseFloat(args.speed || String(DEFAULT_CONFIG.speed)),
		pauseMs: parseInt(args.pause_ms || String(DEFAULT_CONFIG.pauseMs), 10),
	};

	// Create output directory
	if (!fs.existsSync(outDir)) {
		fs.mkdirSync(outDir, { recursive: true });
	}

	// 根据模式获取资料
	let material: string;
	let _inputSource: string;

	if (inputPath) {
		// 模式1：从文件读取
		console.log(`[MODE] Reading from file: ${inputPath}`);
		material = readText(inputPath);
		_inputSource = `file:${inputPath}`;
	} else if (topic) {
		// 模式2：联网搜索
		console.log(`[MODE] Searching web for topic: ${topic}`);
		const zai = await ZAI.create();

		const searchResults = await zai.functions.invoke("web_search", {
			query: topic,
			num: 10,
		});

		if (!Array.isArray(searchResults) || searchResults.length === 0) {
			console.error(`未找到关于"${topic}"的搜索结果`);
			process.exit(2);
		}

		console.log(`[SEARCH] Found ${searchResults.length} results`);

		// 将搜索结果转换为文本资料
		material = searchResults
			.map(
				(r: any, i: number) =>
					`【来源 ${i + 1}】${r.name}\n${r.snippet}\n链接：${r.url}`,
			)
			.join("\n\n");

		_inputSource = `web_search:${topic}`;
		console.log(`[SEARCH] Compiled material (${material.length} chars)`);
	} else {
		console.error("[ERROR] Neither --input nor --topic provided");
		process.exit(1);
	}

	const inputChars = material.length;

	// Calculate duration
	let durationMin: number;
	if (cfg.durationManual >= 3 && cfg.durationManual <= 20) {
		durationMin = cfg.durationManual;
	} else {
		durationMin = chooseDurationMinutes(
			inputChars,
			DURATION_RANGE_LOW,
			DURATION_RANGE_HIGH,
		);
	}

	const [target, low, high] = charBudget(
		durationMin,
		cfg.charsPerMin,
		BUDGET_TOLERANCE,
	);

	console.log(
		`[INFO] input_chars=${inputChars} duration=${durationMin}min budget=${low}-${high}`,
	);

	let attemptHint = "";
	let lastScript: string | null = null;

	// Initialize ZAI SDK (reuse for TTS)
	const zai = await ZAI.create();

	// Generate script
	for (let attempt = 1; attempt <= cfg.maxAttempts; attempt++) {
		const [systemPrompt, userPrompt] = buildPrompts(
			material,
			cfg,
			durationMin,
			target,
			low,
			high,
			attemptHint,
		);

		try {
			console.log(`[LLM] Attempt ${attempt}/${cfg.maxAttempts}...`);
			const content = await callZAI(systemPrompt, userPrompt, cfg.temperature);
			lastScript = content;

			const [ok, reasons] = validateScript(content, cfg, low, high);

			if (ok) {
				break;
			}

			attemptHint = makeRetryHint(reasons, cfg, low, high);
			console.error(`[WARN] Validation failed:`, reasons.join(", "));
		} catch (error: any) {
			console.error(`[ERROR] LLM call failed: ${error.message}`);
			throw error;
		}
	}

	if (!lastScript) {
		console.error("[ERROR] 未生成任何脚本输出。");
		process.exit(1);
	}

	// Write script
	const scriptPath = path.join(outDir, "podcast_script.md");
	fs.writeFileSync(scriptPath, lastScript, "utf-8");
	console.log(`[DONE] podcast_script.md -> ${scriptPath}`);

	// Parse segments
	const segments = scriptToSegments(lastScript, cfg.hostName, cfg.guestName);
	console.log(`[INFO] Parsed ${segments.length} segments`);

	// Generate TTS using SDK
	const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "podcast_segments_"));
	const produced: string[] = [];

	try {
		for (let i = 0; i < segments.length; i++) {
			const seg = segments[i];
			const text = seg.text.trim();
			if (!text) continue;

			let voice: string;
			if (cfg.mode === "dual") {
				voice = seg.speaker === "host" ? cfg.voiceHost : cfg.voiceGuest;
			} else if (cfg.mode === "single-male") {
				voice = cfg.voiceHost;
			} else {
				voice = cfg.voiceGuest;
			}

			const wavPath = path.join(
				tmpDir,
				`seg_${seg.idx.toString().padStart(4, "0")}.wav`,
			);

			console.log(
				`[TTS] [${i + 1}/${segments.length}] idx=${seg.idx} speaker=${seg.speaker} voice=${voice}`,
			);

			const buffer = await ttsRequest(zai, text, voice, cfg.speed);
			fs.writeFileSync(wavPath, buffer);
			produced.push(wavPath);
		}

		// Join segments
		const podcastPath = path.join(outDir, "podcast.wav");
		console.log(
			`[JOIN] Joining ${produced.length} wav files -> ${podcastPath}`,
		);

		joinWavsWave(podcastPath, produced, cfg.pauseMs);
		console.log(`[DONE] podcast.wav -> ${podcastPath}`);
	} finally {
		// Cleanup temp directory
		try {
			fs.rmSync(tmpDir, { recursive: true, force: true });
		} catch (error: any) {
			console.error(`[WARN] Failed to cleanup temp dir: ${error.message}`);
		}
	}

	console.log("\n[FINAL OUTPUT]");
	console.log(`  📄 podcast_script.md -> ${scriptPath}`);
	console.log(`  🎙️  podcast.wav       -> ${path.join(outDir, "podcast.wav")}`);
}

main().catch((error) => {
	console.error("[FATAL ERROR]", error);
	process.exit(1);
});
