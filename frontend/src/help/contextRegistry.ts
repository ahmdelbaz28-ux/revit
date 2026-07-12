
import {
	HELP_CATEGORY_LABELS,
	HELP_TOPIC_ORDER,
	HELP_TOPICS,
} from "./helpTopics";
import type {
	HelpCategory,
	HelpSearchResult,
	HelpTextDirection,
	HelpTopic,
	HelpTopicId,
} from "./types";

export function getHelpTopic(
	topicId: HelpTopicId | string | null | undefined,  // NOSONAR: typescript:S6571
): HelpTopic | undefined {
	if (!topicId) return undefined;
	return HELP_TOPICS[topicId as HelpTopicId] ?? undefined;
}

export function getHelpTopics(): HelpTopic[] {
	return HELP_TOPIC_ORDER.map((topicId) => HELP_TOPICS[topicId]).filter(
		(topic): topic is HelpTopic => Boolean(topic),
	);
}

export function getHelpCategories(): HelpCategory[] {
	const categories = new Set<HelpCategory>();

	for (const topic of Object.values(HELP_TOPICS)) {
		categories.add(topic.category);
	}

	return Array.from(categories).sort((a, b) => {
		const labelA = HELP_CATEGORY_LABELS[a] ?? HELP_CATEGORY_LABELS.general;
		const labelB = HELP_CATEGORY_LABELS[b] ?? HELP_CATEGORY_LABELS.general;
		return labelA.en.localeCompare(labelB.en);
	});
}

export function getCategoryLabel(
	category: HelpCategory,
	direction: HelpTextDirection,
): string {
	const labels = HELP_CATEGORY_LABELS[category] ?? HELP_CATEGORY_LABELS.general;
	return direction === "rtl" ? labels.ar : labels.en;
}

export function getTopicText(topic: HelpTopic, direction: HelpTextDirection) {
	return direction === "rtl"
		? {
				title: topic.titleAr,
				description: topic.descriptionAr,
				steps: topic.stepsAr,
				warnings: topic.warningsAr,
			}
		: {
				title: topic.titleEn,
				description: topic.descriptionEn,
				steps: topic.stepsEn,
				warnings: topic.warningsEn,
			};
}

function normalize(value: string): string {
	return value
		.toLocaleLowerCase()
		.normalize("NFKD")
		.replace(/[\u0300-\u036f]/g, "")
		.replace(/[^\p{L}\p{N}\s-]/gu, " ")
		.replace(/\s+/g, " ")
		.trim();
}

function tokenize(value: string): string[] {
	const normalized = normalize(value);
	return normalized ? normalized.split(" ") : [];
}

function includesToken(haystack: string, token: string): boolean {
	const normalizedHaystack = normalize(haystack);
	return normalizedHaystack === token || normalizedHaystack.includes(token);
}

function scoreTopic(
	topic: HelpTopic,
	tokens: string[],
): { score: number; matchedKeywords: string[] } {
	if (tokens.length === 0) {
		return { score: 1, matchedKeywords: [] };
	}

	let score = 0;
	const matchedKeywords = new Set<string>();
	const title = `${topic.titleEn} ${topic.titleAr}`;
	const description = `${topic.descriptionEn} ${topic.descriptionAr}`;
	const steps = [...topic.stepsEn, ...topic.stepsAr].join(" ");
	const warnings = [...topic.warningsEn, ...topic.warningsAr].join(" ");
	const keywords = topic.keywords.join(" ");

	for (const token of tokens) {
		if (normalize(topic.id) === token) {
			score += 100;
			continue;
		}

		if (includesToken(title, token)) score += 18;
		if (includesToken(description, token)) score += 8;
		if (includesToken(topic.category, token)) score += 6;
		if (includesToken(steps, token)) score += 5;
		if (includesToken(warnings, token)) score += 3;

		for (const keyword of topic.keywords) {
			if (includesToken(keyword, token)) {
				score += 12;
				matchedKeywords.add(keyword);
			}
		}
	}

	if (includesToken(keywords, tokens.join(" "))) {
		score += 20;
	}

	return { score, matchedKeywords: Array.from(matchedKeywords) };
}

export function searchHelpTopics(
	query: string,
	category: HelpCategory | "all" = "all",
): HelpSearchResult[] {
	const tokens = tokenize(query);
	const results: HelpSearchResult[] = [];

	for (const topicId of HELP_TOPIC_ORDER) {
		const topic = HELP_TOPICS[topicId];
		if (!topic) continue;
		if (category !== "all" && topic.category !== category) continue;

		const { score, matchedKeywords } = scoreTopic(topic, tokens);

		if (tokens.length === 0 || score > 0) {
			results.push({ topic, score, matchedKeywords });
		}
	}

	return results.sort((a, b) => {
		if (b.score !== a.score) return b.score - a.score;
		return a.topic.id.localeCompare(b.topic.id);
	});
}

export function getFallbackHelpTopic(query: string): HelpTopic | undefined {
	const normalized = normalize(query);

	if (  // NOSONAR — CPD: intentional pattern
		normalized.includes("auth") ||
		normalized.includes("login") ||
		normalized.includes("token") ||
		normalized.includes("permission") ||
		normalized.includes("مصادقة") ||
		normalized.includes("دخول") ||
		normalized.includes("صلاحية")
	) {
		return HELP_TOPICS["troubleshooting.auth"];
	}

	if (  // NOSONAR — CPD: intentional pattern
		normalized.includes("api") ||
		normalized.includes("request") ||
		normalized.includes("timeout") ||
		normalized.includes("network") ||
		normalized.includes("طلب") ||
		normalized.includes("مهلة") ||
		normalized.includes("شبكة")
	) {
		return HELP_TOPICS["troubleshooting.api"];
	}

	if (
		normalized.includes("crash") ||
		normalized.includes("reload") ||
		normalized.includes("error") ||
		normalized.includes("تعطل") ||
		normalized.includes("خطأ")
	) {
		return HELP_TOPICS["troubleshooting.app-crash"];
	}

	return HELP_TOPICS["troubleshooting.backend"];
}

export function getRelatedTopics(topic: HelpTopic): HelpTopic[] {
	return topic.relatedTopics
		.map((topicId) => HELP_TOPICS[topicId])
		.filter((relatedTopic): relatedTopic is HelpTopic => Boolean(relatedTopic));
}

export function getFirstTopicForContext(
	contextId: HelpTopicId | string | null | undefined,  // NOSONAR: typescript:S6571
): HelpTopic | undefined {
	const exact = getHelpTopic(contextId);
	if (exact) return exact;

	const normalizedContext = normalize(contextId ?? "");
	if (!normalizedContext) return undefined;

	const orderedTopics = Object.values(HELP_TOPICS).sort((a, b) =>
		a.id.localeCompare(b.id),
	);

	return orderedTopics.find((topic) => {
		const searchable = normalize(
			`${topic.id} ${topic.titleEn} ${topic.titleAr} ${topic.keywords.join(" ")}`,
		);
		return searchable.includes(normalizedContext);
	});
}
