/**
 * Names of the outputs one case evaluated to zero / false.
 *
 * `oz` is the case's hex bitmask over the suite's `output_slots`, written by
 * scripts/emit_case_artifacts.py: hex digit `i >> 2` holds slot `i` at bit
 * `3 - (i & 3)`. A slot outside both `o` (non-zero values) and `oz` was not
 * evaluated for the case, so it is not listed.
 *
 * A case with no zero-valued output (`o0` absent) has none to list. A case
 * with `o0` but no `oz` comes from a chunk written before per-case masks.
 * That evidence queried every recorded rule for every case, so its zeros are
 * read as every slot it does not list as non-zero. That over-lists a slot
 * whose value the writer dropped for the case (an undetermined judgment or a
 * non-numeric value), which only a per-case mask can tell apart.
 */
export function zeroOutputNames(caseRow, outputSlots) {
  if (!Array.isArray(outputSlots)) return [];
  const mask = caseRow?.oz;
  if (typeof mask === "string") {
    return outputSlots.filter((_, i) => {
      const digit = Number.parseInt(mask[i >> 2] ?? "0", 16);
      return ((digit >> (3 - (i & 3))) & 1) === 1;
    });
  }
  if (!(caseRow?.o0 > 0)) return [];
  const present = new Set(
    (Array.isArray(caseRow?.o) ? caseRow.o : []).map((record) => record.n),
  );
  return outputSlots.filter((name) => !present.has(name));
}
