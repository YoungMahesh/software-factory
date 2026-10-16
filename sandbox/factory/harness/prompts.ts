import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const PROMPTS_DIR = path.resolve(__dirname, "prompts");

const promptCache = new Map<string, string>();

/**
 * Loads a markdown prompt template from the prompts directory, caching it in memory.
 *
 * @param name - Template name (e.g. "planner_system" or "planner_system.md")
 * @param reload - Whether to bypass the cache and reload from disk
 * @returns The prompt template string
 * @throws Error if the template file does not exist
 */
export function loadPromptTemplate(name: string, reload: boolean = false): string {
  const cleanName = name.endsWith(".md") ? name.slice(0, -3) : name;
  if (!reload && promptCache.has(cleanName)) {
    return promptCache.get(cleanName)!;
  }

  const filePath = path.resolve(PROMPTS_DIR, `${cleanName}.md`);
  if (!fs.existsSync(filePath)) {
    throw new Error(`Prompt template '${cleanName}' not found at ${filePath}`);
  }

  const content = fs.readFileSync(filePath, "utf-8");
  promptCache.set(cleanName, content);
  return content;
}

/**
 * Renders a prompt template with {{variable}} substitution.
 *
 * @param name - Template name
 * @param variables - Variables to interpolate
 * @param reload - Whether to reload the template from disk
 * @returns Rendered prompt string
 */
export function renderPromptTemplate(
  name: string,
  variables?: Record<string, string>,
  reload: boolean = false
): string {
  const template = loadPromptTemplate(name, reload);
  if (!variables) {
    return template;
  }
  return template.replace(/\{\{([a-zA-Z0-9_]+)\}\}/g, (match, varName) => {
    return Object.hasOwn(variables, varName) ? variables[varName] : match;
  });
}

// System prompts per specialized role
export const PLANNER_SYSTEM_PROMPT = loadPromptTemplate("planner_system");
export const CODER_SYSTEM_PROMPT = loadPromptTemplate("coder_system");
export const REVIEWER_SYSTEM_PROMPT = loadPromptTemplate("reviewer_system");
