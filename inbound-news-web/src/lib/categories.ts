import type { Post } from "./types";

// These three are the only categories the bot actually writes to Supabase
// right now (see Post["category"] in types.ts). The original design mock
// had nine sections (AI, DeFi, Big Tech, Hardware, Science, Regulation,
// Cambodia...) — add them here once the backend tags posts with them.
export const CATEGORIES: { slug: Post["category"]; label: string }[] = [
  { slug: "tech", label: "Tech" },
  { slug: "startup", label: "Startups" },
  { slug: "cyber", label: "Cybersecurity" },
];
