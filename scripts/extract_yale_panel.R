# Supervised extraction of the covered slice of the Yale Budget Lab
# tariff-rate-tracker panel for the us-tariff-panel comparison suite.
#
# This is the supervised generation leg (see reference/us-tariff-panel/
# README.md): loading the full panel takes ~200 s and ~78 GB RSS, so it runs
# on the build machine, never in CI. CI consumes only the committed extract.
#
# READ-ONLY on the Yale checkout. Writes only into reference/us-tariff-panel/.
#
# Usage (from the axiom-oracles repo root):
#   YALE_TRACKER_CHECKOUT=/path/to/tariff-rate-tracker Rscript scripts/extract_yale_panel.R
#
# The Yale panel must have been built locally in legal-date mode with:
#   --full --unweighted --skip-release-check
# (recorded in the provenance JSON; the flags cannot be derived from the rds,
# so they are part of the supervised protocol: the operator attests the build
# invocation, and the script enforces everything that IS machine-checkable —
# the checkout must be at EXPECTED_YALE_COMMIT with no tracked modifications
# and an upstream Budget-Lab-Yale remote. Bumping the Yale pin = editing
# EXPECTED_YALE_COMMIT here, which is a reviewed diff.)

EXPECTED_YALE_COMMIT <- "c4307e514196618afcbf88cf7fd33746417eeabf"
EXPECTED_YALE_REPO <- "Budget-Lab-Yale/tariff-rate-tracker"

suppressPackageStartupMessages({
  library(dplyr)
  library(readr)
  library(jsonlite)
})

yale <- Sys.getenv("YALE_TRACKER_CHECKOUT")
if (!nzchar(yale)) {
  stop("set YALE_TRACKER_CHECKOUT to the tariff-rate-tracker checkout")
}
yale <- path.expand(yale)
rds_path <- file.path(yale, "data/timeseries/rate_timeseries.rds")
if (!file.exists(rds_path)) {
  stop("panel not found: ", rds_path, " (build it in the Yale checkout first)")
}

out_dir <- "reference/us-tariff-panel"
if (!dir.exists(out_dir)) {
  stop("run from the axiom-oracles repo root (missing ", out_dir, ")")
}
lines_path <- file.path(out_dir, "covered_lines.txt")
covered_lines <- readLines(lines_path)
covered_lines <- trimws(covered_lines)
covered_lines <- covered_lines[nzchar(covered_lines) & !startsWith(covered_lines, "#")]
if (!all(grepl("^[0-9]{10}$", covered_lines))) {
  stop("covered_lines.txt entries must be 10-digit HTS codes")
}
if (length(covered_lines) == 0) {
  stop("covered_lines.txt is empty — an empty covered slice verifies nothing")
}
if (anyDuplicated(covered_lines)) {
  stop("covered_lines.txt has duplicate entries: ",
       paste(unique(covered_lines[duplicated(covered_lines)]), collapse = ", "))
}
# Append-only guard: the previously stamped coverage must survive a refresh.
# Narrowing the reference (dropping a poorly matching line) is exactly the
# reviewer-independence failure this suite exists to prevent; a deliberate
# scope cut requires deleting the provenance stamp in the same reviewed diff.
prev_prov_path <- file.path(out_dir, "yale_panel_provenance.json")
if (file.exists(prev_prov_path)) {
  prev_lines <- unlist(jsonlite::read_json(prev_prov_path)$covered_lines)
  dropped <- setdiff(prev_lines, covered_lines)
  if (length(dropped) > 0) {
    stop("covered_lines.txt dropped previously covered line(s): ",
         paste(dropped, collapse = ", "),
         " — coverage is append-only (see README.md)")
  }
}
cat("covered lines:", length(covered_lines), "\n")

sha256 <- function(path) {
  out <- system2("shasum", c("-a", "256", path), stdout = TRUE)
  strsplit(out, " ")[[1]][1]
}

yale_commit <- system2("git", c("-C", yale, "rev-parse", "HEAD"), stdout = TRUE)
if (yale_commit != EXPECTED_YALE_COMMIT) {
  stop("Yale checkout is at ", yale_commit, ", expected ",
       EXPECTED_YALE_COMMIT,
       " — a pin bump must edit EXPECTED_YALE_COMMIT in this script")
}
dirty <- system2(
  "git", c("-C", yale, "status", "--porcelain", "--untracked-files=no"),
  stdout = TRUE
)
if (length(dirty) > 0) {
  stop("Yale checkout has modified tracked files — refusing to stamp ",
       "provenance for a dirty source tree:\n",
       paste(dirty, collapse = "\n"))
}
yale_remote <- tryCatch(
  system2("git", c("-C", yale, "remote", "get-url", "origin"), stdout = TRUE),
  warning = function(w) ""
)
if (!grepl(EXPECTED_YALE_REPO, yale_remote, fixed = TRUE)) {
  stop("Yale checkout origin remote is '", yale_remote, "', expected a ",
       EXPECTED_YALE_REPO, " remote — refusing a fork-built panel")
}

# Spine + statutory reference columns ONLY. Estimation-touched and effective
# columns (base_rate, rate_*, total_rate, total_additional, metal shares,
# swiss_*, usmca_eligible, heading_program, base_rate_type, deriv_type,
# s232_annex, is_copper_heading) are deliberately excluded — they are not
# parity targets (see laneB design memo / campaign definition).
SPINE <- c("hts10", "country", "revision", "effective_date",
           "valid_from", "valid_until")
STATUTORY <- c(
  "statutory_base_rate",
  "statutory_rate_232",
  "statutory_rate_ieepa_recip",
  "statutory_rate_ieepa_fent",
  "statutory_rate_301",
  "statutory_rate_301_cs",
  "statutory_rate_s301fl",
  "statutory_rate_s301br",
  "statutory_rate_s338",
  "statutory_rate_s122",
  "statutory_rate_section_201",
  "statutory_rate_other"
)

cat("hashing rds...\n")
rds_sha <- sha256(rds_path)
cat("loading panel (expect ~200 s / ~78 GB RSS)...\n")
t0 <- Sys.time()
ts <- readRDS(rds_path)
cat("loaded", nrow(ts), "rows in",
    round(as.numeric(difftime(Sys.time(), t0, units = "secs"))), "s\n")

missing <- setdiff(c(SPINE, STATUTORY), names(ts))
if (length(missing) > 0) {
  stop("panel schema drift — missing columns: ", paste(missing, collapse = ", "))
}
# The reviewed allowlist must equal the COMPLETE upstream statutory-column
# set: a new statutory_* authority added by Yale must fail here until it is
# classified into the comparison (silently excluding it would contradict the
# sum-of-statutory-columns totals claim).
upstream_statutory <- grep("^statutory_", names(ts), value = TRUE)
unclassified <- setdiff(upstream_statutory, STATUTORY)
if (length(unclassified) > 0) {
  stop("Yale added statutory column(s) not in the reviewed allowlist: ",
       paste(unclassified, collapse = ", "),
       " — classify them into the extract/suite before refreshing")
}

slice <- ts %>%
  filter(hts10 %in% covered_lines) %>%
  select(all_of(c(SPINE, STATUTORY))) %>%
  arrange(hts10, country, valid_from)

absent <- setdiff(covered_lines, unique(slice$hts10))
if (length(absent) > 0) {
  stop("covered lines absent from the Yale panel: ",
       paste(absent, collapse = ", "),
       " — do not silently drop; resolve coverage first")
}

# Slice integrity: these must hold BEFORE the extract is written, so a
# refresh against a degraded upstream panel fails loudly instead of
# committing a plausible-looking but broken reference.
if (anyDuplicated(slice[, c("hts10", "country", "valid_from")])) {
  stop("duplicate (hts10, country, valid_from) keys in the slice")
}
for (col in STATUTORY) {
  v <- slice[[col]]
  if (any(is.na(v)) || any(!is.finite(v)) || any(v < 0)) {
    stop("invalid rates in ", col, ": NA/non-finite/negative values present")
  }
}
if (any(slice$valid_from > slice$valid_until)) {
  stop("reversed validity interval(s) in the slice")
}
# Intervals per (hts10, country) must tile time exactly: sorted by
# valid_from, each interval starts the day after the previous one ends
# (inclusive-inclusive convention) — no gaps, no overlaps.
interval_check <- slice %>%
  group_by(hts10, country) %>%
  arrange(valid_from, .by_group = TRUE) %>%
  summarise(
    contiguous = all(valid_from[-1] == valid_until[-n()] + 1),
    n_intervals = n(),
    .groups = "drop"
  )
if (!all(interval_check$contiguous)) {
  bad <- interval_check %>% filter(!contiguous)
  stop("interval gaps/overlaps in ", nrow(bad), " (hts10, country) series, ",
       "e.g. ", bad$hts10[1], "/", bad$country[1])
}
# Every covered line must carry the full country set and the same interval
# profile — a line silently losing countries or revisions must not pass.
country_sets <- slice %>%
  group_by(hts10) %>%
  summarise(n_countries = n_distinct(country), .groups = "drop")
if (n_distinct(country_sets$n_countries) != 1) {
  stop("covered lines carry differing country counts: ",
       paste(country_sets$hts10, country_sets$n_countries,
             sep = "=", collapse = ", "))
}
if (n_distinct(interval_check$n_intervals) != 1) {
  stop("(hts10, country) series carry differing interval counts — a line ",
       "lost revisions/intervals; inspect before committing")
}

csv_path <- file.path(out_dir, "yale_panel_slice.csv")
write_csv(slice, csv_path)
cat("wrote", nrow(slice), "rows to", csv_path, "\n")

script_path <- "scripts/extract_yale_panel.R"
provenance <- list(
  schema_version = "us_tariff_panel.reference_provenance.v1",
  reference = "Yale Budget Lab tariff-rate-tracker (legal-date statutory panel)",
  yale_repo = EXPECTED_YALE_REPO,
  yale_commit = yale_commit,
  yale_remote = yale_remote,
  yale_tree_clean = TRUE,
  panel_artifact = "data/timeseries/rate_timeseries.rds",
  panel_sha256 = rds_sha,
  panel_bytes = file.info(rds_path)$size,
  panel_build_flags = "--full --unweighted --skip-release-check",
  panel_build_attestation = paste(
    "Build flags and date mode cannot be derived from the rds;",
    "they are attested by the supervising operator per the protocol in",
    "reference/us-tariff-panel/README.md. The script machine-verifies the",
    "checkout commit (== the reviewed EXPECTED_YALE_COMMIT pin), clean",
    "tracked state, and upstream remote."
  ),
  date_mode = "legal",
  panel_rows_total = nrow(ts),
  extractor = script_path,
  extractor_sha256 = sha256(script_path),
  covered_lines = as.list(covered_lines),
  columns = as.list(c(SPINE, STATUTORY)),
  extract_rows = nrow(slice),
  extract_countries = n_distinct(slice$country),
  extract_revisions = n_distinct(slice$revision),
  valid_from_range = c(format(min(slice$valid_from)), format(max(slice$valid_from))),
  valid_until_range = c(format(min(slice$valid_until)), format(max(slice$valid_until))),
  extract_sha256 = sha256(csv_path),
  extracted_at = format(Sys.time(), "%Y-%m-%dT%H:%M:%S%z")
)
prov_path <- file.path(out_dir, "yale_panel_provenance.json")
write_json(provenance, prov_path, auto_unbox = TRUE, pretty = TRUE)
cat("wrote", prov_path, "\n")
