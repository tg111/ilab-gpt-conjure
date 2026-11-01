import { imageMentionPayload } from "./prompt-image-mentions";
import { getLegacyBridge } from "./state";
import { translate } from "./i18n";

function legacyMethod(name: string, ...args: any[]): any {
  const method = getLegacyBridge().methods[name];
  if (typeof method !== "function") {
    throw new Error("Legacy method " + name + " is not initialized");
  }
  return method(...args);
}

function getPromptText(): string { return legacyMethod("getPromptText"); }
function expandPromptSnippets(prompt: any): string { return legacyMethod("expandPromptSnippets", prompt); }
function galleryInputs(): any[] { return legacyMethod("galleryInputs"); }
function categoryPromptRole(category: any): string { return legacyMethod("categoryPromptRole", category); }
export function promptTokenReplacement(prompt: any): string {
  return expandPromptSnippets(prompt);
}

export function galleryPrompt() {
  const galleries = galleryInputs();
  // Prompt processing is disabled, so gallery reference notes are always kept.
  if (!galleries.length) return null;
  return {
    header: translate("promptModel.galleryHeader"),
    template: translate("promptModel.galleryInstruction"),
    references: galleries.map((source: any) => {
      const promptNote = String(source.prompt_note || "").trim();
      return {
        id: source.id,
        name: source.name,
        role: source.category_prompt_role || categoryPromptRole(source.category),
        note: promptNote ? ` ${promptNote}` : "",
      };
    }),
  };
}

export function buildPromptForModel(): string {
  // Gallery guidance stays structured until the server resolves duplicate image identities.
  const mentions = imageMentionPayload();
  return mentions ? mentions.model_parts.map((part: any) => typeof part === "string" ? part : part.text).join("")
    : expandPromptSnippets(getPromptText());
}

export function currentPromptForModel(): string {
  // Prompt processing is disabled, but snippets and image reference notes are
  // user content and stay in the prompt sent to every model.
  return buildPromptForModel();
}

export function initPromptModelFeature(): void {
  Object.assign(getLegacyBridge().methods, {
    promptTokenReplacement,
    galleryPrompt,
    buildPromptForModel,
    currentPromptForModel,
  });
}
