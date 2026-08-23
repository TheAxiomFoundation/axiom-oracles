/**
 * Central suite metadata.
 *
 * Every view used to carry its own hand-copied suite → label map, so new
 * suites (az/or/ut/fl SNAP) silently fell back to raw slugs in some views.
 * This module derives metadata from the suite slug where possible and keeps
 * one small override table for the irregular suites.
 *
 * `kind` drives what a suite counts toward:
 *  - "household": measured over survey households; included in headline numbers
 *  - "parameter": parameter-value check, not end-to-end eligibility
 *  - "coverage":  coverage surface only, no case-level comparison yet
 *  - "diagnostic": instrumentation / gap-analysis run; excluded from headlines
 */

export const US_STATE_NAMES = {
  AL: "Alabama", AK: "Alaska", AZ: "Arizona", AR: "Arkansas",
  CA: "California", CO: "Colorado", CT: "Connecticut", DE: "Delaware",
  DC: "District of Columbia", FL: "Florida", GA: "Georgia", HI: "Hawaii",
  ID: "Idaho", IL: "Illinois", IN: "Indiana", IA: "Iowa", KS: "Kansas",
  KY: "Kentucky", LA: "Louisiana", ME: "Maine", MD: "Maryland",
  MA: "Massachusetts", MI: "Michigan", MN: "Minnesota", MS: "Mississippi",
  MO: "Missouri", MT: "Montana", NE: "Nebraska", NV: "Nevada",
  NH: "New Hampshire", NJ: "New Jersey", NM: "New Mexico", NY: "New York",
  NC: "North Carolina", ND: "North Dakota", OH: "Ohio", OK: "Oklahoma",
  OR: "Oregon", PA: "Pennsylvania", RI: "Rhode Island", SC: "South Carolina",
  SD: "South Dakota", TN: "Tennessee", TX: "Texas", UT: "Utah",
  VT: "Vermont", VA: "Virginia", WA: "Washington", WV: "West Virginia",
  WI: "Wisconsin", WY: "Wyoming",
};

export const JURISDICTION_LABELS = {
  ...US_STATE_NAMES,
  US: "Federal (US)",
  UK: "United Kingdom",
  BE: "Belgium",
  DEU: "Germany",
  CAN: "Canada",
  NYC: "New York City",
};

export const FAMILY_LABELS = {
  snap: "SNAP food assistance",
  federal_income_tax: "Federal income tax",
  social_security: "Social Security (OASDI) amounts",
  ssi: "SSI (Supplemental Security Income)",
  state_ssi_supplement: "SSI state supplements (APA, CAPI, OAP, SSP, MSA…)",
  snap_federal: "SNAP federal rules (7 USC / 7 CFR)",
  state_income_tax: "State income tax",
  nyc_income_tax: "NYC income tax",
  medicaid_chip_bhp_thresholds: "Medicaid / CHIP / BHP thresholds",
  medicaid_eligibility_groups: "Medicaid eligibility groups (42 CFR 435)",
  chip: "CHIP (children's health insurance)",
  medicare: "Medicare entitlement",
  tanf: "TANF cash assistance",
  childcare_assistance: "Child care assistance",
  pell_grant: "Pell Grant / federal student aid",
  immigrant_eligibility: "Immigrant benefit eligibility (PRWORA)",
  energy_rebates: "IRA home energy rebates",
  head_start: "Head Start",
  lifeline: "Lifeline (phone / broadband subsidy)",
  csfp: "CSFP (commodity supplemental food)",
  other_federal: "Other federal provisions",
  universal_credit: "Universal Credit",
  uk_tax_benefits: "UK tax & benefits",
  uk_income_tax: "UK income tax",
  uk_national_insurance: "UK National Insurance",
  be_personal_income_tax: "Belgium personal income tax",
  be_social_security: "Belgium social security",
  be_social_assistance: "Belgium social assistance",
  be_health_insurance: "Belgium health insurance",
  be_family_benefits: "Belgium family benefits",
  be_unemployment: "Belgium unemployment benefits",
  be_study_allowance: "Belgium study allowance",
  be_disposable_income: "Belgium disposable income",
  de_worker_tax_contributions: "Germany worker tax and social insurance",
  canada_personal_income_tax: "Canada personal income tax",
  canada_family_benefits: "Canada family and disability benefits",
};

const SUITE_OVERRIDES = {
  "ca-federal-schedule-tax-spsm": {
    family: "canada_personal_income_tax",
    jurisdiction: "CAN",
    label: "Canada federal schedule tax (vs SPSD/M)",
    region: "ca",
    kind: "household",
    order: 300,
  },
  "fiit-ecps": {
    family: "federal_income_tax",
    jurisdiction: "US",
    label: "Federal income tax",
    region: "us",
    kind: "household",
    order: 10,
  },
  "fiit-taxsim-ecps": {
    family: "federal_income_tax",
    jurisdiction: "US",
    label: "Federal income tax (vs TAXSIM)",
    region: "us",
    kind: "household",
    order: 12,
  },
  "co-tax-intersection-taxsim": {
    family: "federal_income_tax",
    jurisdiction: "CO",
    label: "Full federal tax, with Colorado for the SALT deduction (vs TAXSIM)",
    region: "us",
    kind: "household",
    order: 202,
  },
  "taxcalc-fiit-ecps": {
    family: "federal_income_tax",
    jurisdiction: "US",
    label: "Federal income tax (Tax-Calculator vs PolicyEngine)",
    region: "us",
    kind: "household",
    order: 11,
  },
  "ssa-parameters": {
    family: "social_security",
    jurisdiction: "US",
    label: "Social Security wage-indexed amounts",
    region: "us",
    kind: "parameter",
    order: 20,
  },
  "ssi-ecps": {
    family: "ssi",
    jurisdiction: "US",
    label: "SSI (Supplemental Security Income)",
    region: "us",
    kind: "household",
    order: 24,
  },
  "ssi-parameters": {
    family: "ssi",
    jurisdiction: "US",
    label: "SSI income exclusions",
    region: "us",
    kind: "parameter",
    order: 25,
  },
  "ak-apa-state-supplement": {
    family: "state_ssi_supplement",
    jurisdiction: "AK",
    label: "Alaska APA payment standards",
    region: "us",
    kind: "parameter",
    order: 27,
  },
  "mi-ssp-payments": {
    family: "state_ssi_supplement",
    jurisdiction: "MI",
    label: "Michigan SSP payments",
    region: "us",
    kind: "parameter",
    order: 28,
  },
  "ca-capi-limits": {
    family: "state_ssi_supplement",
    jurisdiction: "CA",
    label: "California CAPI resource limits",
    region: "us",
    kind: "parameter",
    order: 29,
  },
  "co-state-supplement": {
    family: "state_ssi_supplement",
    jurisdiction: "CO",
    label: "Colorado OAP grant standard",
    region: "us",
    kind: "parameter",
    order: 26,
  },
  "ny-tanf-ecps": {
    family: "tanf",
    jurisdiction: "NY",
    label: "New York TANF (Family Assistance)",
    region: "us",
    kind: "household",
    order: 220,
  },
  "wa-tanf-ecps": {
    family: "tanf",
    jurisdiction: "WA",
    label: "Washington TANF (WorkFirst)",
    region: "us",
    kind: "household",
    order: 221,
  },
  "fl-tca-standards": {
    family: "tanf",
    jurisdiction: "FL",
    label: "Florida TCA payment standards",
    region: "us",
    kind: "parameter",
    order: 226,
  },
  "md-tca-payments": {
    family: "tanf",
    jurisdiction: "MD",
    label: "Maryland TCA payment schedule",
    region: "us",
    kind: "parameter",
    order: 227,
  },
  "me-tanf-standards": {
    family: "tanf",
    jurisdiction: "ME",
    label: "Maine TANF standards",
    region: "us",
    kind: "parameter",
    order: 228,
  },
  "al-tanf-payment-standards": {
    family: "tanf",
    jurisdiction: "AL",
    label: "Alabama TANF payment standards",
    region: "us",
    kind: "parameter",
    order: 229,
  },
  "az-tanf-deductions": {
    family: "tanf",
    jurisdiction: "AZ",
    label: "Arizona cash assistance deductions",
    region: "us",
    kind: "parameter",
    order: 230,
  },
  "ga-tanf-standards": {
    family: "tanf",
    jurisdiction: "GA",
    label: "Georgia TANF financial standards",
    region: "us",
    kind: "parameter",
    order: 224,
  },
  "ak-atap-standards": {
    family: "tanf",
    jurisdiction: "AK",
    label: "Alaska ATAP need standards",
    region: "us",
    kind: "parameter",
    order: 225,
  },
  "tx-tanf-parameters": {
    family: "tanf",
    jurisdiction: "TX",
    label: "Texas TANF needs parameters",
    region: "us",
    kind: "parameter",
    order: 226,
  },
  "wa-tanf-payment-standard": {
    family: "tanf",
    jurisdiction: "WA",
    label: "Washington TANF payment standards",
    region: "us",
    kind: "parameter",
    order: 221,
  },
  "ny-tanf-standards": {
    family: "tanf",
    jurisdiction: "NY",
    label: "New York TANF need standards",
    region: "us",
    kind: "parameter",
    order: 222,
  },
  "medicaid-magi-co-ecps": {
    family: "medicaid_eligibility_groups",
    jurisdiction: "CO",
    label: "Medicaid eligibility groups (CO slice)",
    region: "us",
    kind: "household",
    order: 215,
  },
  "medicaid-thresholds-states": {
    family: "medicaid_chip_bhp_thresholds",
    jurisdiction: "US",
    label: "Medicaid / CHIP thresholds — 49-state CMS card",
    region: "us",
    kind: "parameter",
    order: 212,
  },
  "ga-health-thresholds": {
    family: "medicaid_chip_bhp_thresholds",
    jurisdiction: "GA",
    label: "Georgia Medicaid / CHIP / BHP thresholds",
    region: "us",
    kind: "parameter",
    order: 211,
  },
  "pell-parameters": {
    family: "pell_grant",
    jurisdiction: "US",
    label: "Pell Grant award amounts",
    region: "us",
    kind: "parameter",
    order: 240,
  },
  "lifeline-parameters": {
    family: "lifeline",
    jurisdiction: "US",
    label: "Lifeline income limit",
    region: "us",
    kind: "parameter",
    order: 290,
  },
  "csfp-parameters": {
    family: "csfp",
    jurisdiction: "US",
    label: "CSFP income limit",
    region: "us",
    kind: "parameter",
    order: 291,
  },
  "hi-income-tax-parameters": {
    family: "state_income_tax",
    jurisdiction: "HI",
    label: "Hawaii income tax amounts",
    region: "us",
    kind: "parameter",
    order: 118,
  },
  "ia-income-tax-parameters": {
    family: "state_income_tax",
    jurisdiction: "IA",
    label: "Iowa income tax exemption credits",
    region: "us",
    kind: "parameter",
    order: 119,
  },
  "irs-adjustment-parameters": {
    family: "federal_income_tax",
    jurisdiction: "US",
    label: "Federal IRC adjustment/deduction amounts",
    region: "us",
    kind: "parameter",
    order: 11,
  },
  "co-state-income-tax-taxsim": {
    family: "state_income_tax",
    jurisdiction: "CO",
    label: "Colorado income tax (vs TAXSIM)",
    region: "us",
    kind: "household",
    order: 201,
  },
  "co-state-income-tax-ecps": {
    family: "state_income_tax",
    jurisdiction: "CO",
    label: "Colorado income tax",
    region: "us",
    kind: "household",
    order: 200,
  },
  "co-health-thresholds": {
    family: "medicaid_chip_bhp_thresholds",
    jurisdiction: "CO",
    label: "Colorado Medicaid / CHIP / BHP thresholds",
    region: "us",
    kind: "parameter",
    order: 210,
  },
  "ca-tanf-ecps": {
    family: "tanf",
    jurisdiction: "CA",
    label: "California CalWORKs",
    region: "us",
    kind: "household",
    order: 218,
  },
  "ks-tanf-ecps": {
    family: "tanf",
    jurisdiction: "KS",
    label: "Kansas TANF maximum benefit",
    region: "us",
    kind: "household",
    order: 216,
  },
  "az-tanf-ecps": {
    family: "tanf",
    jurisdiction: "AZ",
    label: "Arizona Cash Assistance",
    region: "us",
    kind: "household",
    order: 217,
  },
  "mn-tanf-ecps": {
    family: "tanf",
    jurisdiction: "MN",
    label: "Minnesota MFIP",
    region: "us",
    kind: "household",
    order: 223,
  },
  "co-tanf-ecps": {
    family: "tanf",
    jurisdiction: "CO",
    label: "Colorado Works TANF",
    region: "us",
    kind: "household",
    order: 219,
  },
  "co-tanf-coverage": {
    family: "tanf",
    jurisdiction: "CO",
    label: "Colorado Works TANF",
    region: "us",
    kind: "coverage",
    order: 220,
  },
  "uk-universal-credit-efrs": {
    family: "universal_credit",
    jurisdiction: "UK",
    label: "UK Universal Credit",
    region: "uk",
    kind: "household",
    order: 300,
  },
  "uk-universal-credit": {
    family: "universal_credit",
    jurisdiction: "UK",
    label: "UK Universal Credit (UKMOD)",
    region: "uk",
    kind: "household",
    order: 301,
  },
  "uk-tax-benefits-efrs": {
    family: "uk_tax_benefits",
    jurisdiction: "UK",
    label: "UK tax & benefits",
    region: "uk",
    kind: "household",
    order: 310,
  },
  "be-worker-pit": {
    family: "be_personal_income_tax",
    jurisdiction: "BE",
    label: "Belgium worker PIT",
    region: "be",
    kind: "household",
    order: 500,
  },
  "be-worker-ssc": {
    family: "be_social_security",
    jurisdiction: "BE",
    label: "Belgium employee social-security contributions",
    region: "be",
    kind: "household",
    order: 510,
  },
  "be-employer-ssc": {
    family: "be_social_security",
    jurisdiction: "BE",
    label: "Belgium employer social-security contributions",
    region: "be",
    kind: "household",
    order: 512,
  },
  "be-self-employed-ssc": {
    family: "be_social_security",
    jurisdiction: "BE",
    label: "Belgium self-employed social-security contributions",
    region: "be",
    kind: "household",
    order: 515,
  },
  "be-special-social-security-contribution": {
    family: "be_social_security",
    jurisdiction: "BE",
    label: "Belgium special social-security contribution",
    region: "be",
    kind: "household",
    order: 516,
  },
  "be-flemish-social-protection-premium": {
    family: "be_social_security",
    jurisdiction: "BE",
    label: "Belgium Flemish Social Protection premium",
    region: "be",
    kind: "household",
    order: 517,
  },
  "be-flemish-jobbonus": {
    family: "be_social_security",
    jurisdiction: "BE",
    label: "Belgium Flemish jobbonus",
    region: "be",
    kind: "household",
    order: 518,
  },
  "be-cadastral-income-indexation": {
    family: "be_personal_income_tax",
    jurisdiction: "BE",
    label: "Belgium cadastral income indexation",
    region: "be",
    kind: "household",
    order: 518.5,
  },
  "be-property-tax": {
    family: "be_personal_income_tax",
    jurisdiction: "BE",
    label: "Belgium immovable withholding",
    region: "be",
    kind: "household",
    order: 519,
  },
  "be-social-assistance": {
    family: "be_social_assistance",
    jurisdiction: "BE",
    label: "Belgium social integration income support",
    region: "be",
    kind: "household",
    order: 520,
  },
  "be-elderly-income-support": {
    family: "be_social_assistance",
    jurisdiction: "BE",
    label: "Belgium elderly income guarantee",
    region: "be",
    kind: "household",
    order: 530,
  },
  "be-maternity-leave": {
    family: "be_health_insurance",
    jurisdiction: "BE",
    label: "Belgium maternity leave indemnity",
    region: "be",
    kind: "household",
    order: 540,
  },
  "be-birth-leave": {
    family: "be_health_insurance",
    jurisdiction: "BE",
    label: "Belgium birth leave compensation",
    region: "be",
    kind: "household",
    order: 541,
  },
  "be-marital-quotient": {
    family: "be_personal_income_tax",
    jurisdiction: "BE",
    label: "Belgium marital quotient",
    region: "be",
    kind: "household",
    order: 501,
  },
  "be-regional-pit-surcharge": {
    family: "be_personal_income_tax",
    jurisdiction: "BE",
    label: "Belgium regional PIT surcharge",
    region: "be",
    kind: "household",
    order: 502,
  },
  "be-local-municipal-pit": {
    family: "be_personal_income_tax",
    jurisdiction: "BE",
    label: "Belgium municipal PIT surcharge",
    region: "be",
    kind: "household",
    order: 503,
  },
  "be-capital-income-tax": {
    family: "be_personal_income_tax",
    jurisdiction: "BE",
    label: "Belgium capital income tax",
    region: "be",
    kind: "household",
    order: 504,
  },
  "be-article-51-forfait": {
    family: "be_personal_income_tax",
    jurisdiction: "BE",
    label: "Belgium Article 51 forfait",
    region: "be",
    kind: "household",
    order: 505,
  },
  "be-worker-tax-income-list": {
    family: "be_personal_income_tax",
    jurisdiction: "BE",
    label: "Belgium worker tax income grid",
    region: "be",
    kind: "household",
    order: 506,
  },
  "be-pensioner-contributions": {
    family: "be_social_security",
    jurisdiction: "BE",
    label: "Belgium pensioner contributions",
    region: "be",
    kind: "household",
    order: 513,
  },
  "be-work-bonus-credit": {
    family: "be_social_security",
    jurisdiction: "BE",
    label: "Belgium work bonus",
    region: "be",
    kind: "household",
    order: 514,
  },
  "be-unemployment": {
    family: "be_unemployment",
    jurisdiction: "BE",
    label: "Belgium unemployment benefits",
    region: "be",
    kind: "household",
    order: 525,
  },
  "be-study-allowance": {
    family: "be_study_allowance",
    jurisdiction: "BE",
    label: "Belgium study allowance",
    region: "be",
    kind: "household",
    order: 545,
  },
  "be-family-child-benefit-base": {
    family: "be_family_benefits",
    jurisdiction: "BE",
    label: "Belgium child benefit — base amounts",
    region: "be",
    kind: "household",
    order: 550,
  },
  "be-family-child-benefit-social-supplement": {
    family: "be_family_benefits",
    jurisdiction: "BE",
    label: "Belgium child benefit — social supplement",
    region: "be",
    kind: "household",
    order: 551,
  },
  "be-family-child-benefit-wallonia-social-supplement": {
    family: "be_family_benefits",
    jurisdiction: "BE",
    label: "Belgium child benefit — Wallonia social supplement",
    region: "be",
    kind: "household",
    order: 552,
  },
  "be-family-child-benefit-brussels-same-age-household": {
    family: "be_family_benefits",
    jurisdiction: "BE",
    label: "Belgium child benefit — Brussels same-age household",
    region: "be",
    kind: "household",
    order: 553,
  },
  "be-family-child-benefit-income-list": {
    family: "be_family_benefits",
    jurisdiction: "BE",
    label: "Belgium child benefit — income grid",
    region: "be",
    kind: "household",
    order: 554,
  },
  "be-family-birth-allowance": {
    family: "be_family_benefits",
    jurisdiction: "BE",
    label: "Belgium birth allowance",
    region: "be",
    kind: "household",
    order: 555,
  },
  "be-worker-disposable-income-list": {
    family: "be_disposable_income",
    jurisdiction: "BE",
    label: "Belgium worker disposable income",
    region: "be",
    kind: "household",
    order: 560,
  },
  "uk-worker-pit": {
    family: "uk_income_tax",
    jurisdiction: "UK",
    label: "UK worker income tax (UKMOD)",
    region: "uk",
    kind: "household",
    order: 320,
  },
  "uk-worker-nic": {
    family: "uk_national_insurance",
    jurisdiction: "UK",
    label: "UK worker employee NIC (UKMOD)",
    region: "uk",
    kind: "household",
    order: 322,
  },
  "uk-income-tax-scottish": {
    family: "uk_income_tax",
    jurisdiction: "UK",
    label: "UK income tax — Scottish rates (UKMOD)",
    region: "uk",
    kind: "household",
    order: 321,
  },
  "uk-income-tax-dividend": {
    family: "uk_income_tax",
    jurisdiction: "UK",
    label: "UK income tax — dividends (UKMOD)",
    region: "uk",
    kind: "household",
    order: 321.1,
  },
  "uk-income-tax-savings": {
    family: "uk_income_tax",
    jurisdiction: "UK",
    label: "UK income tax — savings (UKMOD)",
    region: "uk",
    kind: "household",
    order: 321.2,
  },
  "uk-income-tax-mixed": {
    family: "uk_income_tax",
    jurisdiction: "UK",
    label: "UK income tax — mixed income (UKMOD)",
    region: "uk",
    kind: "household",
    order: 321.3,
  },
  "uk-employer-nic": {
    family: "uk_national_insurance",
    jurisdiction: "UK",
    label: "UK employer NIC (UKMOD)",
    region: "uk",
    kind: "household",
    order: 323,
  },
  "uk-self-employed-nic": {
    family: "uk_national_insurance",
    jurisdiction: "UK",
    label: "UK self-employed NIC (UKMOD)",
    region: "uk",
    kind: "household",
    order: 324,
  },
  "uk-child-benefit": {
    family: "uk_child_benefit",
    jurisdiction: "UK",
    label: "UK Child Benefit",
    region: "uk",
    kind: "household",
    order: 330,
  },
  "uk-pension-credit": {
    family: "uk_pension_credit",
    jurisdiction: "UK",
    label: "UK Pension Credit",
    region: "uk",
    kind: "household",
    order: 332,
  },
  "uk-benefit-cap": {
    family: "uk_benefit_cap",
    jurisdiction: "UK",
    label: "UK benefit cap",
    region: "uk",
    kind: "household",
    order: 334,
  },
  "uk-winter-fuel": {
    family: "uk_winter_fuel",
    jurisdiction: "UK",
    label: "UK Winter Fuel Payment",
    region: "uk",
    kind: "household",
    order: 336,
  },
  "uk-maternity-allowance": {
    family: "uk_maternity_allowance",
    jurisdiction: "UK",
    label: "UK Maternity Allowance",
    region: "uk",
    kind: "household",
    order: 338,
  },
  "uk-statutory-maternity-pay": {
    family: "uk_statutory_maternity_pay",
    jurisdiction: "UK",
    label: "UK Statutory Maternity Pay",
    region: "uk",
    kind: "household",
    order: 339,
  },
  "uk-statutory-paternity-pay": {
    family: "uk_statutory_paternity_pay",
    jurisdiction: "UK",
    label: "UK Statutory Paternity Pay",
    region: "uk",
    kind: "household",
    order: 340,
  },
  "uk-sure-start-maternity-grant": {
    family: "uk_sure_start_maternity_grant",
    jurisdiction: "UK",
    label: "UK Sure Start Maternity Grant",
    region: "uk",
    kind: "household",
    order: 341,
  },
  "uk-best-start-foods": {
    family: "uk_best_start_foods",
    jurisdiction: "UK",
    label: "Scotland Best Start Foods",
    region: "uk",
    kind: "household",
    order: 342,
  },
  "uk-healthy-start": {
    family: "uk_healthy_start",
    jurisdiction: "UK",
    label: "UK Healthy Start",
    region: "uk",
    kind: "household",
    order: 343,
  },
  "de-worker-dual-oracle": {
    family: "de_worker_tax_contributions",
    jurisdiction: "DEU",
    label: "Germany worker tax and social insurance",
    region: "de",
    kind: "household",
    order: 600,
  },
  "nyc-income-tax-gap": {
    family: "nyc_income_tax",
    jurisdiction: "NYC",
    label: "NYC income tax components",
    region: "us",
    kind: "diagnostic",
    order: 400,
  },
  "nyc-income-tax-ecps-diagnostic": {
    family: "nyc_income_tax",
    jurisdiction: "NYC",
    label: "NYC income tax ECPS diagnostic",
    region: "us",
    kind: "diagnostic",
    order: 410,
  },
  "nyc-synthetic": {
    family: "nyc_income_tax",
    jurisdiction: "NYC",
    label: "NYC synthetic scenarios",
    region: "us",
    kind: "diagnostic",
    order: 420,
  },
};

// State-tax Populace campaign — one suite per ready state, projected from
// reports/state-tax-populace-campaign-*.json by
// scripts/emit_populace_campaign_artifacts.py. Each groups into its
// state's income-tax program page beside the six-case grid suite; the
// campaign is the full pinned US Populace (every routed tax unit), so it
// leads the grid in ordering.
const POPULACE_CAMPAIGN_STATES = [
  "AL", "AR", "AZ", "CO", "CT", "DE", "GA", "HI", "IA", "IL", "IN", "KS",
  "LA", "MI", "MS", "MT", "NC", "NJ", "NM", "NY", "OH", "OK", "PA", "SC",
  "UT", "VA", "VT", "WV",
];
for (const st of POPULACE_CAMPAIGN_STATES) {
  SUITE_OVERRIDES[`${st.toLowerCase()}-income-tax-populace`] = {
    family: "state_income_tax",
    jurisdiction: st,
    label: `${US_STATE_NAMES[st]} income tax — full Populace`,
    region: "us",
    kind: "household",
    order: 90,
  };
}

const SNAP_SUITE_RE = /^([a-z]{2})-snap-ecps$/;
// USDA SNAP Quality Control lanes: same program family as the ECPS suites,
// compared against the QC administrative sample instead.
const SNAP_QC_SUITE_RE = /^([a-z]{2})-snap-qc$/;
// State income-tax liability grids (completed-return boundary).
const STATE_TAX_SUITE_RE = /^([a-z]{2})-income-tax-liability$/;
// TANF household suites without an explicit override.
const TANF_ECPS_SUITE_RE = /^([a-z]{2})-tanf-ecps$/;

// Fallback labels: humanize the slug instead of echoing it raw
// ("uk-council-tax-reduction" → "UK council tax reduction").
const SLUG_ACRONYMS = new Set([
  "uk", "us", "dk", "be", "de", "tv", "vat", "jsa", "pe", "lbtt", "ltt",
  "ecps", "qc",
]);
function humanizeSlug(slug) {
  return slug
    .split("-")
    .map((part) =>
      SLUG_ACRONYMS.has(part) ? part.toUpperCase() : part,
    )
    .join(" ")
    .replace(/^./, (c) => c.toUpperCase());
}

/** Resolve display + grouping metadata for a suite slug. */
export function suiteMeta(suite) {
  const slug = String(suite || "");
  if (SUITE_OVERRIDES[slug]) return { suite: slug, ...SUITE_OVERRIDES[slug] };

  const snap = slug.match(SNAP_SUITE_RE);
  if (snap) {
    const abbr = snap[1].toUpperCase();
    const stateName = US_STATE_NAMES[abbr] || abbr;
    return {
      suite: slug,
      family: "snap",
      jurisdiction: abbr,
      label: `${stateName} SNAP`,
      region: "us",
      kind: "household",
      order: 100,
    };
  }

  const snapQc = slug.match(SNAP_QC_SUITE_RE);
  if (snapQc && US_STATE_NAMES[snapQc[1].toUpperCase()]) {
    const abbr = snapQc[1].toUpperCase();
    return {
      suite: slug,
      family: "snap",
      jurisdiction: abbr,
      label: `${US_STATE_NAMES[abbr]} SNAP (vs SNAP QC)`,
      region: "us",
      kind: "household",
      order: 105,
    };
  }

  const stateTax = slug.match(STATE_TAX_SUITE_RE);
  if (stateTax && US_STATE_NAMES[stateTax[1].toUpperCase()]) {
    const abbr = stateTax[1].toUpperCase();
    return {
      suite: slug,
      family: "state_income_tax",
      jurisdiction: abbr,
      label: `${US_STATE_NAMES[abbr]} income tax`,
      region: "us",
      kind: "household",
      order: 45,
    };
  }

  const tanf = slug.match(TANF_ECPS_SUITE_RE);
  if (tanf && US_STATE_NAMES[tanf[1].toUpperCase()]) {
    const abbr = tanf[1].toUpperCase();
    return {
      suite: slug,
      family: "tanf",
      jurisdiction: abbr,
      label: `${US_STATE_NAMES[abbr]} TANF`,
      region: "us",
      kind: "household",
      order: 222,
    };
  }

  return {
    suite: slug,
    family: slug || "unknown",
    jurisdiction: null,
    label: slug ? humanizeSlug(slug) : "Unnamed run",
    region: slug.startsWith("uk-")
      ? "uk"
      : slug.startsWith("be-")
        ? "be"
        : slug.startsWith("ca-")
          ? "ca"
          : slug.startsWith("de-")
            ? "de"
            : slug.startsWith("dk-")
              ? "dk"
              : "us",
    kind: "household",
    order: 500,
  };
}

export function suiteLabel(suite) {
  return suiteMeta(suite).label;
}

export function suiteRegion(suite) {
  return suiteMeta(suite).region;
}

export function suiteKind(suite) {
  return suiteMeta(suite).kind;
}

/** True when one side of the comparison is Axiom. */
export function isAxiomPair(report) {
  return report?.engines?.left === "axiom" || report?.engines?.right === "axiom";
}

/** The non-Axiom engine in an Axiom-pair report (e.g. policyengine, taxsim). */
export function otherOracle(report) {
  if (!isAxiomPair(report)) return null;
  return report.engines.left === "axiom"
    ? report.engines.right
    : report.engines.left;
}

/**
 * Stable anchor id for a verification run. Keyed by (suite, engine pair) so
 * the same suite run against different oracles gets distinct anchors.
 */
export function runAnchor(report) {
  const suite = report?.suite || "report";
  if (isAxiomPair(report)) return `run-${suite}-vs-${otherOracle(report)}`;
  const left = report?.engines?.left || "left";
  const right = report?.engines?.right || "right";
  return `run-${suite}-${left}-${right}`;
}

/**
 * How many verified programs a report represents. Most reports verify one
 * program (its eligibility and amount concepts are facets of the same
 * program), but the federal income tax suite tests separable pieces — CTC,
 * EITC, standard deduction, … — each of which counts on its own. The four
 * payroll components group as one piece, matching the breakout table.
 */
export function reportProgramCount(report) {
  const family = suiteMeta(report?.suite).family;
  // Medicaid eligibility groups: each 42 CFR 435 group concept is its own
  // verified program surface, like the federal income tax pieces below.
  if (family === "medicaid_eligibility_groups") {
    const concepts = new Set(
      (report.aggregates || [])
        .filter((agg) => (agg.comparison_count || 0) > 0)
        .map((agg) => agg.concept),
    );
    return Math.max(1, concepts.size);
  }
  if (family !== "federal_income_tax") return 1;
  const pieces = new Set();
  for (const agg of report.aggregates || []) {
    if (!((agg.comparison_count || 0) > 0)) continue;
    const concept = String(agg.concept || "");
    pieces.add(concept.startsWith("us:tax/payroll") ? "payroll" : concept);
  }
  return Math.max(1, pieces.size);
}

/**
 * Some suites (fiit, UK EFRS) report a concept HIERARCHY: a parent row
 * (e.g. #liability) plus component rows (#ctc, #eitc, …) that break the
 * parent down. Components are the parent's anatomy, not extra checks —
 * summing every row double-counts. Keep a row only when its parent is
 * absent from the same report (flat suites have no parents at all; the
 * NYC components suite names a parent that lives in another suite).
 */
export function topLevelAggregates(aggregates) {
  const rows = aggregates || [];
  const concepts = new Set(rows.map((agg) => agg.concept));
  return rows.filter((agg) => !(agg.parent && concepts.has(agg.parent)));
}

/** Aggregate one report's aggregates into a single matched/total metric. */
export function reportMetric(report) {
  let total = 0;
  let mismatches = 0;
  for (const agg of topLevelAggregates(report?.aggregates)) {
    total += agg.comparison_count || 0;
    mismatches += agg.mismatch_count || 0;
  }
  // The disposition merge (dispositions/<suite>.yaml) stamps the summary
  // with both rates: raw, and explained — matches plus mismatches carrying
  // a schema-validated disposition (explained residuals, upstream engine
  // gaps, bridge artifacts).
  const dispositioned = report?.summary?.dispositioned || null;
  return {
    total,
    mismatches,
    matched: total - mismatches,
    rate: total > 0 ? ((total - mismatches) / total) * 100 : null,
    explainedRate:
      dispositioned && total > 0 ? dispositioned.explained_rate : null,
    unexplainedCount: dispositioned ? dispositioned.unexplained_count : null,
  };
}

/**
 * Plain-language status for a measured agreement rate. Tiers match
 * rateColor() in utils/colors.js so a tile and its run row never disagree:
 * 90%+ reads as verified, not as a warning.
 */
/**
 * Near-agreement: exact matches plus mismatches within a dollar threshold.
 * Only computable when the report carries its COMPLETE mismatch list —
 * large suites slim the dashboard copy to the first 1,000 rows, and a
 * partial list would overstate closeness. Returns null when not computable
 * or when it would not differ from the exact rate.
 */
export const NEAR_THRESHOLD_USD = 100;

export function nearMetric(report, threshold = NEAR_THRESHOLD_USD) {
  const metric = reportMetric(report);
  if (!metric.total || !metric.mismatches) return null;
  const list = report?.mismatches || [];
  const declared = report?.summary?.mismatch_count;
  if (declared == null || list.length !== declared) return null;
  let near = 0;
  for (const m of list) {
    const diff = m?.difference;
    if (typeof diff === "number" && Math.abs(diff) <= threshold) near += 1;
  }
  if (near === 0) return null;
  const rate = ((metric.matched + near) / metric.total) * 100;
  return { rate, near, threshold };
}

/** Stable, URL-safe program identity: family__jurisdiction. */
export function programKey(meta) {
  return `${meta.family}__${meta.jurisdiction}`;
}

export function rateStatus(rate) {
  if (rate == null) return "unmeasured";
  if (rate >= 90) return "verified";
  if (rate >= 70) return "diverging";
  return "attention";
}
