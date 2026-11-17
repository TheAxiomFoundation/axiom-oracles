/**
 * Dashboard wording for one disposition entry. An entry may carry a
 * `display` block (dispositions/<suite>.yaml, validated in
 * axiom_oracles/comparison/dispositions.py): `title` replaces the entry id as
 * the note's title, and `cause` replaces the class tag. Entries without it
 * keep the id-derived title and the class tag.
 *
 * Kept free of React so plain node can test it.
 */

/** Tag text for each `display.cause` (DISPLAY_CAUSES in dispositions.py). */
export const DISPLAY_CAUSE_LABELS = Object.freeze({
  comparison_setup: "comparison set-up",
  open: "cause open",
});

export function humanizeSlug(id) {
  const s = String(id || "").replaceAll("-", " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/** The note's title: `display.title` when set, else the humanized entry id. */
export function displayTitle(entry) {
  const title = entry?.display?.title;
  return typeof title === "string" && title.trim()
    ? title
    : humanizeSlug(entry?.id);
}

/** The tag for `display.cause`, or null when the entry sets none (or an
 *  unknown one), so the caller falls back to the class tag. */
export function displayCauseLabel(entry) {
  const cause = entry?.display?.cause;
  return typeof cause === "string" && Object.hasOwn(DISPLAY_CAUSE_LABELS, cause)
    ? DISPLAY_CAUSE_LABELS[cause]
    : null;
}
