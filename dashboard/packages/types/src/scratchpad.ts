import { z } from "zod";

export const ScratchpadSectionSchema = z.enum(["ideas", "raw"]);
export type ScratchpadSection = z.infer<typeof ScratchpadSectionSchema>;

export const ScratchpadNoteSummaryViewSchema = z.object({
  section: ScratchpadSectionSchema.optional().default("ideas"),
  filename: z.string(),
  slug: z.string(),
  path: z.string(),
  title: z.string(),
  sha: z.string(),
  size: z.number().int().optional().default(0),
  html_url: z.string().nullable().optional(),
});
export type ScratchpadNoteSummaryView = z.infer<typeof ScratchpadNoteSummaryViewSchema>;

export const ScratchpadCatalogResponseSchema = z.object({
  config_repo: z.string().optional().default(""),
  refreshed_at: z.string().nullable().optional(),
  ideas_directory: z.string().optional().default("scratchpad"),
  raw_directory: z.string().optional().default("raw"),
  ideas: z.array(ScratchpadNoteSummaryViewSchema).optional().default([]),
  raw: z.array(ScratchpadNoteSummaryViewSchema).optional().default([]),
});
export type ScratchpadCatalogResponse = z.infer<typeof ScratchpadCatalogResponseSchema>;

export const ScratchpadNoteDetailViewSchema = z.object({
  section: ScratchpadSectionSchema.optional().default("ideas"),
  filename: z.string(),
  slug: z.string(),
  path: z.string(),
  title: z.string(),
  content: z.string(),
  sha: z.string(),
  html_url: z.string().nullable().optional(),
});
export type ScratchpadNoteDetailView = z.infer<typeof ScratchpadNoteDetailViewSchema>;

export const ScratchpadSuggestRequestSchema = z.object({
  raw_text: z.string().min(1),
  title_hint: z.string().nullable().optional(),
  model: z.string().nullable().optional(),
});
export type ScratchpadSuggestRequest = z.infer<typeof ScratchpadSuggestRequestSchema>;

export const ScratchpadSuggestResponseSchema = z.object({
  title: z.string(),
  slug: z.string(),
  filename: z.string(),
  target_path: z.string(),
  content: z.string(),
  model: z.string(),
});
export type ScratchpadSuggestResponse = z.infer<typeof ScratchpadSuggestResponseSchema>;

export const ScratchpadSaveRequestSchema = z.object({
  title: z.string().default(""),
  content: z.string().min(1),
  section: ScratchpadSectionSchema.default("ideas"),
  mode: z.enum(["ai", "raw"]).nullable().optional(),
});
export type ScratchpadSaveRequest = z.infer<typeof ScratchpadSaveRequestSchema>;

export const ScratchpadSaveResponseSchema = z.object({
  section: ScratchpadSectionSchema.optional().default("ideas"),
  filename: z.string(),
  slug: z.string(),
  path: z.string(),
  title: z.string(),
  sha: z.string(),
  content: z.string(),
  size: z.number().int().optional().default(0),
  html_url: z.string().nullable().optional(),
  config_repo: z.string(),
});
export type ScratchpadSaveResponse = z.infer<typeof ScratchpadSaveResponseSchema>;

export const ScratchpadDeleteResponseSchema = z.object({
  section: ScratchpadSectionSchema,
  filename: z.string(),
  path: z.string(),
  deleted: z.boolean(),
});
export type ScratchpadDeleteResponse = z.infer<typeof ScratchpadDeleteResponseSchema>;
