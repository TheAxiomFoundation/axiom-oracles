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
# (recorded in the provenance JSON; the flags cannot be derived from the rds).

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
cat("covered lines:", length(covered_lines), "\n")

sha256 <- function(path) {
  out <- system2("shasum", c("-a", "256", path), stdout = TRUE)
  strsplit(out, " ")[[1]][1]
}

yale_commit <- system2("git", c("-C", yale, "rev-parse", "HEAD"), stdout = TRUE)

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

csv_path <- file.path(out_dir, "yale_panel_slice.csv")
write_csv(slice, csv_path)
cat("wrote", nrow(slice), "rows to", csv_path, "\n")

script_path <- "scripts/extract_yale_panel.R"
provenance <- list(
  schema_version = "us_tariff_panel.reference_provenance.v1",
  reference = "Yale Budget Lab tariff-rate-tracker (legal-date statutory panel)",
  yale_repo = "Budget-Lab-Yale/tariff-rate-tracker",
  yale_commit = yale_commit,
  panel_artifact = "data/timeseries/rate_timeseries.rds",
  panel_sha256 = rds_sha,
  panel_bytes = file.info(rds_path)$size,
  panel_build_flags = "--full --unweighted --skip-release-check",
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
