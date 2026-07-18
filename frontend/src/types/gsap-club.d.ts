/**
 * Type declarations for GSAP Club plugins (SplitText, DrawSVGPlugin, CustomEase).
 *
 * These are Club GSAP plugins that require a paid membership and are NOT
 * included in the free GSAP npm package. The runtime code loads them
 * dynamically with graceful fallback when unavailable.
 *
 * These declarations satisfy the TypeScript compiler so that the
 * Club plugin imports resolve, even though the actual modules may
 * not be installed (the runtime handles that gracefully with try/catch).
 */

declare module "gsap/SplitText" {
  export class SplitText {
    constructor(
      target: Element | Element[] | string,
      vars?: {
        type?: "chars" | "words" | "lines";
        charsClass?: string;
        wordsClass?: string;
        linesClass?: string;
        position?: string;
        wordDelimiter?: string;
        lineThreshold?: number;
      },
    );
    chars: Element[] | null;
    words: Element[] | null;
    lines: Element[] | null;
    selector: (value: string) => Element[];
    revert(): void;
    static version: string;
  }
}

declare module "gsap/DrawSVGPlugin" {
  interface DrawSVGPluginType {
    version: string;
  }
  const DrawSVGPlugin: DrawSVGPluginType;
  export { DrawSVGPlugin };
}

declare module "gsap/CustomEase" {
  export class CustomEase {
    constructor(id: string, progress: string);
    static create(id: string, progress: string): CustomEase;
    static get(id: string): CustomEase;
    static version: string;
  }
}
