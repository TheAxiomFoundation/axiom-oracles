#!/usr/bin/env Rscript

fail = function(...) {
  stop(paste0(...), call. = FALSE)
}

input_path = Sys.getenv("AXIOM_ORACLES_YALE_INPUT")
output_path = Sys.getenv("AXIOM_ORACLES_YALE_OUTPUT")
variables_env = Sys.getenv("AXIOM_ORACLES_YALE_VARIABLES")
repo = Sys.getenv("YALE_TAXSIM_REPO")
macro_root = Sys.getenv("YALE_TAXSIM_MACRO_ROOT")
tax_law_id = Sys.getenv("YALE_TAXSIM_TAX_LAW_ID", unset = "baseline")

if (input_path == "") {
  fail("AXIOM_ORACLES_YALE_INPUT is required")
}
if (output_path == "") {
  fail("AXIOM_ORACLES_YALE_OUTPUT is required")
}
if (repo == "") {
  fail("YALE_TAXSIM_REPO is required")
}
if (!dir.exists(repo)) {
  fail("YALE_TAXSIM_REPO does not exist: ", repo)
}
if (macro_root == "") {
  fail("YALE_TAXSIM_MACRO_ROOT is required")
}
missing_macro_files = file.path(macro_root, c("historical.csv", "projections.csv"))
missing_macro_files = missing_macro_files[!file.exists(missing_macro_files)]
if (length(missing_macro_files) > 0) {
  fail(
    "YALE_TAXSIM_MACRO_ROOT must contain historical.csv and projections.csv; ",
    "missing: ",
    paste(missing_macro_files, collapse = ", ")
  )
}

requirements_path = file.path(repo, "requirements.txt")
if (!file.exists(requirements_path)) {
  fail("Cannot find Yale requirements.txt under YALE_TAXSIM_REPO")
}
required_packages = readLines(requirements_path, warn = FALSE)
required_packages = required_packages[nzchar(required_packages)]
missing_packages = required_packages[
  !vapply(required_packages, requireNamespace, logical(1), quietly = TRUE)
]
if (length(missing_packages) > 0) {
  fail(
    "Missing Yale R packages: ",
    paste(missing_packages, collapse = ", "),
    ". Install them from the Yale Tax-Simulator repo with: ",
    "Rscript -e 'options(repos=c(CRAN=\"https://cloud.r-project.org\")); ",
    "install.packages(readLines(\"requirements.txt\"))'"
  )
}

suppressPackageStartupMessages(
  invisible(capture.output(lapply(required_packages, library, character.only = TRUE)))
)

old_wd = getwd()
on.exit(setwd(old_wd), add = TRUE)
setwd(repo)

return_vars = list()
source("src/misc/utils.R")
source("src/calc/utils.R")
source("src/data/economy.R")
source("src/data/tax_law.R")
calc_files = list.files("src/calc/functions", recursive = TRUE, full.names = TRUE)
invisible(lapply(sort(calc_files), source))
source("src/calc/do_taxes.R")

original_parse_calc_fn_input = parse_calc_fn_input
parse_calc_fn_input = function(tax_unit, req_vars, fill_missings = FALSE) {
  if (!is.data.frame(tax_unit)) {
    stopifnot(is.list(tax_unit))
    tax_unit = as_tibble(tax_unit)
  }

  missing = c()
  given_vars = names(tax_unit)
  for (var in req_vars) {
    if (!(var %in% given_vars)) {
      if (str_sub(var, -2) == "[]") {
        prefix = str_sub(var, end = -3)
        if ((prefix %in% given_vars) || paste0(prefix, 1) %in% given_vars) {
          next
        }
      }
      missing = c(missing, var)
    }
  }

  if (length(missing) > 0) {
    policy_like = missing[
      grepl("^[[:alnum:]_]+\\.", missing) & !grepl("^r\\.", missing)
    ]
    if (length(policy_like) > 0) {
      stop(
        "The following tax law variables were not supplied by Yale tax_law: ",
        paste0(policy_like, collapse = " "),
        call. = FALSE
      )
    }
    fill_names = setdiff(missing, policy_like)
    tax_unit = bind_cols(
      tax_unit,
      fill_names %>%
        map(.f = ~ rep(0, nrow(tax_unit))) %>%
        set_names(fill_names) %>%
        as_tibble()
    )
  }

  original_parse_calc_fn_input(tax_unit, req_vars, fill_missings = FALSE)
}

output_root = file.path(tempdir(), "axiom-yale-taxsim-output")
for (type in c("static", "conventional")) {
  dir.create(
    file.path(output_root, type, "supplemental"),
    recursive = TRUE,
    showWarnings = FALSE
  )
}

input_rows = read_csv(
  input_path,
  show_col_types = FALSE,
  col_types = cols(id = col_character(), .default = col_guess())
)
if (!("id" %in% names(input_rows))) {
  input_rows$id = as.character(seq_len(nrow(input_rows)))
}
if (!("year" %in% names(input_rows))) {
  fail("Yale bridge input must include a year column")
}
if (!("filing_status" %in% names(input_rows))) {
  fail("Yale bridge input must include a filing_status column")
}

years = sort(unique(as.integer(input_rows$year)))
scenario_info = list(
  ID = "baseline",
  tax_law_id = tax_law_id,
  years = years,
  output_path = output_root
)
vat_price_offset = tibble(
  year = years,
  cpi_factor = 1,
  gdp_deflator_factor = 1
)
excess_growth_offset = tibble(
  year = years,
  income_factor = 1
)
indexes = generate_indexes(macro_root, vat_price_offset, excess_growth_offset)
tax_law = build_tax_law(scenario_info, indexes)

copy_column = function(df, to, from) {
  if (!(to %in% names(df)) && from %in% names(df)) {
    df[[to]] = df[[from]]
  }
  df
}

ensure_column = function(df, name, value) {
  if (!(name %in% names(df))) {
    df[[name]] = value
  }
  df
}

numeric_column = function(df, name, default = 0) {
  if (name %in% names(df)) {
    value = suppressWarnings(as.numeric(df[[name]]))
    value[is.na(value)] = default
    value
  } else {
    rep(default, nrow(df))
  }
}

normalize_input = function(df) {
  df = copy_column(df, "care_exp", "childcare_exp")
  df = copy_column(df, "salt_prop", "prop_tax")
  df = copy_column(df, "first_mort_int", "mort_int")
  df = copy_column(df, "txbl_pens_dist", "gross_pens_dist")

  df = ensure_column(df, "wages1", 0)
  df = ensure_column(df, "wages2", 0)
  df = ensure_column(df, "sole_prop1", 0)
  df = ensure_column(df, "sole_prop2", 0)
  if (!("wages" %in% names(df))) {
    df$wages = numeric_column(df, "wages1") + numeric_column(df, "wages2")
  }
  if (!("sole_prop" %in% names(df))) {
    df$sole_prop =
      numeric_column(df, "sole_prop1") + numeric_column(df, "sole_prop2")
  }

  df = ensure_column(df, "weight", 1)
  df = ensure_column(df, "blind1", FALSE)
  df = ensure_column(df, "blind2", FALSE)
  df = ensure_column(df, "dep_status", FALSE)
  df = ensure_column(df, "filer", 1)
  df = ensure_column(df, "kg_lt_basis", 0)
  df = ensure_column(df, "kg_lt_years_held", 0)
  df = ensure_column(df, "txbl_pens_dist", 0)
  df = ensure_column(df, "txbl_ira_dist", 0)
  zero_defaults = c(
    "part_active",
    "part_passive",
    "part_active_loss",
    "part_passive_loss",
    "part_179",
    "scorp_active",
    "scorp_passive",
    "scorp_active_loss",
    "scorp_passive_loss",
    "scorp_179",
    "rent",
    "rent_loss",
    "estate",
    "estate_loss",
    "farm",
    "farm1",
    "farm2",
    "trad_contr_er1",
    "trad_contr_er2",
    "txbl_int",
    "exempt_int",
    "div_ord",
    "div_pref",
    "kg_st",
    "kg_lt",
    "gross_pens_dist",
    "gross_ss",
    "ui",
    "state_ref",
    "other_gains",
    "alimony",
    "other_inc",
    "care_exp",
    "salt_prop",
    "first_mort_int",
    "char_cash",
    "char_noncash",
    "salt_workaround_part",
    "salt_workaround_scorp"
  )
  for (name in zero_defaults) {
    df = ensure_column(df, name, 0)
  }

  df$filing_status = as.integer(df$filing_status)
  df$year = as.integer(df$year)
  if ("age2" %in% names(df)) {
    df$age2 = if_else(df$filing_status == 2, as.numeric(df$age2), NA_real_)
  }

  n_child = numeric_column(df, "n_dep_child", default = 0)
  if (!("n_dep_eitc" %in% names(df))) {
    df$n_dep_eitc = n_child
  }
  if (!("n_dep" %in% names(df))) {
    df$n_dep = n_child
  }
  for (i in 1:3) {
    has_child = n_child >= i
    age_name = paste0("dep_age", i)
    ssn_name = paste0("dep_ssn", i)
    ctc_name = paste0("dep_ctc", i)
    if (!(age_name %in% names(df))) {
      df[[age_name]] = if_else(has_child, 2 + 3 * i, NA_real_)
    }
    if (!(ssn_name %in% names(df))) {
      df[[ssn_name]] = if_else(has_child, TRUE, NA)
    }
    if (!(ctc_name %in% names(df))) {
      df[[ctc_name]] = if_else(has_child, TRUE, NA)
    }
  }

  df
}

requested_variables = character()
if (variables_env != "") {
  requested_variables = strsplit(variables_env, ",", fixed = TRUE)[[1]]
  requested_variables = requested_variables[nzchar(requested_variables)]
}
default_variables = c(
  "liab_iit_net",
  "std_ded",
  "agi",
  "txbl_inc",
  "liab_bc",
  "eitc",
  "ctc_nonref",
  "ctc_ref",
  "liab_amt"
)
output_variables = unique(c(
  "id",
  if (length(requested_variables)) requested_variables else default_variables
))

vars_1040 = return_vars %>%
  remove_by_name("calc_pr") %>%
  unlist() %>%
  set_names(NULL) %>%
  unique()

globals = list(random_numbers = tibble(r.eitc_precert = numeric()))

tax_units = normalize_input(input_rows) %>%
  left_join(tax_law, by = c("year", "filing_status"))

for (year in years) {
  rows = tax_units %>% filter(.data$year == year)
  if (nrow(rows) == 0) {
    next
  }
  globals$random_numbers = tibble(r.eitc_precert = rep(1, nrow(rows)))
  rows = calc_kg_cpi_ratio(rows, indexes, year)
  rows = rows %>%
    do_taxes(
      baseline_pr_er = NULL,
      vars_1040 = vars_1040,
      vars_payroll = return_vars$calc_pr
    )
  if (!exists("results", inherits = FALSE)) {
    results = rows
  } else {
    results = bind_rows(results, rows)
  }
}

if (!exists("results", inherits = FALSE)) {
  results = tibble(id = character())
}
missing_outputs = setdiff(output_variables, names(results))
if (length(missing_outputs) > 0) {
  fail(
    "Yale Tax-Simulator did not produce requested columns: ",
    paste(missing_outputs, collapse = ", ")
  )
}

results %>%
  select(all_of(output_variables)) %>%
  write_csv(output_path)
