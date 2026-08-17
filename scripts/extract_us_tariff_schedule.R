#!/usr/bin/env Rscript
suppressPackageStartupMessages({library(data.table); library(digest); library(jsonlite)})

args <- commandArgs(trailingOnly=TRUE)
root <- normalizePath(ifelse(length(args) >= 1, args[[1]], "."))
yale <- normalizePath(ifelse(length(args) >= 2, args[[2]], "/Users/maxghenis/TheAxiomFoundation/_tariff-yale"))
out <- file.path(root, "reference/us-tariff-schedule")
dir.create(out, recursive=TRUE, showWarnings=FALSE)
started <- Sys.time()
script_arg <- grep("^--file=", commandArgs(trailingOnly=FALSE), value=TRUE)
script_path <- normalizePath(sub("^--file=", "", script_arg[[1]]))
window_start <- as.Date("2026-02-15"); window_end <- as.Date("2026-08-01")
cap <- 12000000L
stat_cols <- c("statutory_base_rate", "statutory_rate_232", "statutory_rate_ieepa_recip",
 "statutory_rate_ieepa_fent", "statutory_rate_301", "statutory_rate_301_cs",
 "statutory_rate_s301fl", "statutory_rate_s301br", "statutory_rate_s338",
 "statutory_rate_s122", "statutory_rate_section_201", "statutory_rate_other")
spine <- c("hts10", "country", "revision", "valid_from", "valid_until")
rds <- file.path(yale, "data/timeseries/rate_timeseries.rds")
sha <- function(path) digest(file=path, algo="sha256", serialize=FALSE)

x <- readRDS(rds)
setDT(x)
stopifnot(setequal(grep("^statutory_", names(x), value=TRUE), stat_cols))
stopifnot(all(c(spine, stat_cols) %in% names(x)))
keep <- which(x$valid_until >= window_start & x$valid_from <= window_end)
x <- x[keep, c(spine, stat_cols), with=FALSE]
rm(keep); invisible(gc())
x[, country := as.character(country)]
cat("stage=filtered rows=", nrow(x), " elapsed_s=", as.numeric(difftime(Sys.time(),started,units="secs")), "\n", sep="")
x[, `:=`(clipped_from=pmax(valid_from, window_start), clipped_until=pmin(valid_until, window_end))]
invalid_rates <- vapply(x[, ..stat_cols], function(v) any(!is.finite(v) | v < 0), logical(1))
if (any(invalid_rates)) stop("invalid statutory rate")
setkey(x, hts10, country, clipped_from, clipped_until)
if (anyDuplicated(x[, .(hts10,country,clipped_from,clipped_until)])) stop("duplicate keys")
x[, prev_until := shift(clipped_until), by=.(hts10,country)]
if (x[!is.na(prev_until) & clipped_from != prev_until + 1L, .N]) stop("interval gap/overlap")
x[, prev_until := NULL]
country_sets <- x[, .(n_country=uniqueN(country)), by=hts10]
if (uniqueN(country_sets$n_country) != 1L) stop("unequal country sets by line")

# Canonical exact expected-side trajectory; every distinct value survives.
x[, row_sig := do.call(paste, c(.SD, sep="|")), .SDcols=c("clipped_from","clipped_until","revision",stat_cols)]
traj <- x[, .(trajectory=paste(row_sig, collapse=";"), interval_cells=.N), by=.(hts10,country)]
cat("stage=trajectories pairs=", nrow(traj), " elapsed_s=", as.numeric(difftime(Sys.time(),started,units="secs")), "\n", sep="")
bridge <- fread(file.path(root,"reference/us-tariff-panel/census_iso_bridge.csv"), colClasses="character", na.strings="")
setnames(bridge, "census_code", "country")
bridge[, country := as.character(country)]
additions <- fread(file.path(out,"census-iso-bridge-additions.csv"), colClasses="character", na.strings="")
setnames(additions, "census_code", "country")
bridge <- rbind(bridge[!is.na(iso2) & iso2!="", .(country,iso2,name)], additions[,.(country,iso2,name)])
missing_bridge <- setdiff(unique(traj$country), bridge$country)
if (length(missing_bridge)) stop(paste("unbridged Census country:", paste(missing_bridge,collapse=",")))
traj[, trajectory_sha256 := vapply(trajectory, digest, "", algo="sha256", serialize=FALSE)]
classes <- traj[, .(class_members=.N, interval_cells=unique(interval_cells), members=paste(sort(country),collapse=";")), by=.(hts10,trajectory_sha256)]
classes[, class_id := paste0(hts10,"-",substr(trajectory_sha256,1,20))]
traj[, iso2 := bridge$iso2[match(country, bridge$country)]]
if (traj[is.na(iso2) | iso2=="", .N]) stop("unbridged Census country")
cat("stage=bridge-closed elapsed_s=", as.numeric(difftime(Sys.time(),started,units="secs")), "\n", sep="")
reg <- fromJSON(file.path(out,"origin-regimes.json"), simplifyVector=FALSE)
groups <- reg$named_overlay_groups
regime <- function(iso) {
 bits <- c(iso %in% unlist(reg$column_2), vapply(groups, function(v) iso %in% unlist(v), logical(1)), iso %in% unlist(reg$fta_preference))
 paste(as.integer(bits), collapse="")
}
iso_values <- sort(unique(traj$iso2)); regime_lookup <- setNames(vapply(iso_values, regime, ""), iso_values)
traj[, origin_regime := regime_lookup[iso2]]
traj[, selection_hash := vapply(paste(hts10,trajectory_sha256,country,sep="|"), digest, "", algo="sha256", serialize=FALSE)]
setorder(traj, hts10, trajectory_sha256, selection_hash)
traj[, representative := seq_len(.N)==1L, by=.(hts10,trajectory_sha256)]
traj[, representative_regime := origin_regime[1L], by=.(hts10,trajectory_sha256)]
hamming <- function(a,b) sum(strsplit(a,"")[[1]] != strsplit(b,"")[[1]])
traj[, regime_distance := mapply(hamming, origin_regime, representative_regime)]
traj[, guard := { candidate <- !representative & regime_distance==max(regime_distance); result <- rep(FALSE,.N); if (any(candidate)) result[which(candidate)[1L]] <- TRUE; result }, by=.(hts10,trajectory_sha256)]
traj[, selected := representative | guard]

# Marginal repair, oracle-spine-only. Usually empty; deterministic SHA first.
missing_country <- setdiff(unique(traj$country), unique(traj[selected==TRUE]$country))
if (length(missing_country)) traj[country %in% missing_country, selected := selected | selection_hash==sort(selection_hash)[1L], by=country]
missing_line <- setdiff(unique(traj$hts10), unique(traj[selected==TRUE]$hts10))
if (length(missing_line)) traj[hts10 %in% missing_line, selected := selected | selection_hash==sort(selection_hash)[1L], by=hts10]
selected_pairs <- traj[selected==TRUE,.(hts10,country,iso2,trajectory_sha256,representative,guard,origin_regime)]
selected <- merge(x[, c(spine,"clipped_from","clipped_until",stat_cols),with=FALSE], selected_pairs, by=c("hts10","country"))
quotient_cells <- nrow(selected); guard_cells <- selected[guard==TRUE,.N]

counts <- list(full_interval_cells=nrow(x), full_lines=uniqueN(x$hts10), full_countries=uniqueN(x$country),
 full_revisions=uniqueN(x$revision), trajectory_classes=nrow(classes), representative_interval_cells=selected[representative==TRUE,.N],
 guard_interval_cells=guard_cells, evaluated_interval_cells=quotient_cells, cap=cap, guard_dropped_for_cap=FALSE,
 under_cap=quotient_cells <= cap, selected_pairs=nrow(selected_pairs), guard_pairs=selected_pairs[guard==TRUE,.N])
write_json(counts, file.path(out,"quotient-receipt.json"), pretty=TRUE, auto_unbox=TRUE)
if (quotient_cells > cap) stop(sprintf("STOP: measured quotient %d exceeds cap %d", quotient_cells, cap))

fwrite(traj[,.(hts10,country,iso2,trajectory_sha256,interval_cells,origin_regime,representative,guard,regime_distance,selected)], file.path(out,"trajectory-class-map.csv.gz"))
fwrite(selected, file.path(out,"selected-intervals.csv.gz"))
exposure <- x[, lapply(.SD, function(v) sum(v > 0)), .SDcols=stat_cols]
write_json(as.list(exposure[1]), file.path(out,"full-exposure.json"), pretty=TRUE, auto_unbox=TRUE)
integrity <- list(schema_columns=c(spine,stat_cols), statutory_columns=stat_cols, duplicate_keys=0, interval_gaps_or_overlaps=0,
 country_set_per_line=unique(country_sets$n_country), unbridged_countries=0, selected_lines=uniqueN(selected$hts10), selected_countries=uniqueN(selected$country),
 every_class_represented=selected_pairs[,uniqueN(paste(hts10,trajectory_sha256))]==nrow(classes), regime_table_sha256=sha(file.path(out,"origin-regimes.json")))
write_json(integrity, file.path(out,"integrity-receipt.json"), pretty=TRUE, auto_unbox=TRUE)
prov <- list(schema="axiom_oracles.us_tariff_schedule_reference.v1", yale_commit=system2("git",c("-C",yale,"rev-parse","HEAD"),stdout=TRUE),
 rds_path=rds,rds_sha256=sha(rds),window=list(start=as.character(window_start),end=as.character(window_end)),legal_date_mode=TRUE,
 invocation=paste(commandArgs(),collapse=" "),extractor_sha256=sha(script_path),bridge_sha256=sha(file.path(root,"reference/us-tariff-panel/census_iso_bridge.csv")),bridge_additions_sha256=sha(file.path(out,"census-iso-bridge-additions.csv")),
 regime_table_sha256=sha(file.path(out,"origin-regimes.json")),selected_extract_sha256=sha(file.path(out,"selected-intervals.csv.gz")),
 class_map_sha256=sha(file.path(out,"trajectory-class-map.csv.gz")),counts=counts,extracted_at=format(Sys.time(),tz="UTC",usetz=TRUE),wall_clock_seconds=as.numeric(difftime(Sys.time(),started,units="secs")))
write_json(prov,file.path(out,"provenance.json"),pretty=TRUE,auto_unbox=TRUE)
cat(toJSON(counts,auto_unbox=TRUE,pretty=TRUE),"\n")
