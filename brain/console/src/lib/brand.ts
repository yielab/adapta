/** Brand constants — single source of truth for the console.
 *  SSOT: docs/reference/BRAND.md §1–§2
 *  Update here; never scatter raw strings across views.
 */

export const BRAND = {
  name:    "Brain From Cero",
  tagline: "Your model. Your data. Your servers.",
  /** Mode framing (locked product rule — never call RAG "training") */
  modes: {
    knowledge: {
      label:       "Knowledge",
      action:      "Give it knowledge",
      description: "Answers grounded in your documents, with citations. The weights don't change.",
    },
    behavior: {
      label:       "Behavior",
      action:      "Change how it behaves",
      description: "Teach it a style, format, or skill by fine-tuning.",
    },
  },
  docs: "https://github.com/santiagoyie/brainFromCero/blob/main/docs/user-guide/operator-console.md",
} as const;
