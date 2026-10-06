// src/utils/suites.js
var US_STATE_NAMES = {
  AL: "Alabama",
  AK: "Alaska",
  AZ: "Arizona",
  AR: "Arkansas",
  CA: "California",
  CO: "Colorado",
  CT: "Connecticut",
  DE: "Delaware",
  DC: "District of Columbia",
  FL: "Florida",
  GA: "Georgia",
  HI: "Hawaii",
  ID: "Idaho",
  IL: "Illinois",
  IN: "Indiana",
  IA: "Iowa",
  KS: "Kansas",
  KY: "Kentucky",
  LA: "Louisiana",
  ME: "Maine",
  MD: "Maryland",
  MA: "Massachusetts",
  MI: "Michigan",
  MN: "Minnesota",
  MS: "Mississippi",
  MO: "Missouri",
  MT: "Montana",
  NE: "Nebraska",
  NV: "Nevada",
  NH: "New Hampshire",
  NJ: "New Jersey",
  NM: "New Mexico",
  NY: "New York",
  NC: "North Carolina",
  ND: "North Dakota",
  OH: "Ohio",
  OK: "Oklahoma",
  OR: "Oregon",
  PA: "Pennsylvania",
  RI: "Rhode Island",
  SC: "South Carolina",
  SD: "South Dakota",
  TN: "Tennessee",
  TX: "Texas",
  UT: "Utah",
  VT: "Vermont",
  VA: "Virginia",
  WA: "Washington",
  WV: "West Virginia",
  WI: "Wisconsin",
  WY: "Wyoming"
};
var JURISDICTION_LABELS = {
  ...US_STATE_NAMES,
  US: "Federal (US)",
  UK: "United Kingdom",
  BE: "Belgium",
  DEU: "Germany",
  CAN: "Canada",
  NYC: "New York City"
};
var SUITE_OVERRIDES = {
  "ca-federal-schedule-tax-spsm": {
    family: "canada_personal_income_tax",
    jurisdiction: "CAN",
    label: "Canada federal schedule tax (vs SPSD/M)",
    region: "ca",
    kind: "household",
    order: 300
  },
  "fiit-ecps": {
    family: "federal_income_tax",
    jurisdiction: "US",
    label: "Federal income tax",
    region: "us",
    kind: "household",
    order: 10
  },
  "fiit-taxsim-ecps": {
    family: "federal_income_tax",
    jurisdiction: "US",
    label: "Federal income tax (vs TAXSIM)",
    region: "us",
    kind: "household",
    order: 12
  },
  "co-tax-intersection-taxsim": {
    family: "federal_income_tax",
    jurisdiction: "CO",
    label: "Full federal tax, with Colorado for the SALT deduction (vs TAXSIM)",
    region: "us",
    kind: "household",
    order: 202
  },
  "taxcalc-fiit-ecps": {
    family: "federal_income_tax",
    jurisdiction: "US",
    label: "Federal income tax (Tax-Calculator vs PolicyEngine)",
    region: "us",
    kind: "household",
    order: 11
  },
  "ssa-parameters": {
    family: "social_security",
    jurisdiction: "US",
    label: "Social Security wage-indexed amounts",
    region: "us",
    kind: "parameter",
    order: 20
  },
  "ssi-ecps": {
    family: "ssi",
    jurisdiction: "US",
    label: "SSI (Supplemental Security Income)",
    region: "us",
    kind: "household",
    order: 24
  },
  "ssi-parameters": {
    family: "ssi",
    jurisdiction: "US",
    label: "SSI income exclusions",
    region: "us",
    kind: "parameter",
    order: 25
  },
  "ak-apa-state-supplement": {
    family: "state_ssi_supplement",
    jurisdiction: "AK",
    label: "Alaska APA payment standards",
    region: "us",
    kind: "parameter",
    order: 27
  },
  "mi-ssp-payments": {
    family: "state_ssi_supplement",
    jurisdiction: "MI",
    label: "Michigan SSP payments",
    region: "us",
    kind: "parameter",
    order: 28
  },
  "ca-capi-limits": {
    family: "state_ssi_supplement",
    jurisdiction: "CA",
    label: "California CAPI resource limits",
    region: "us",
    kind: "parameter",
    order: 29
  },
  "co-state-supplement": {
    family: "state_ssi_supplement",
    jurisdiction: "CO",
    label: "Colorado OAP grant standard",
    region: "us",
    kind: "parameter",
    order: 26
  },
  "ny-tanf-ecps": {
    family: "tanf",
    jurisdiction: "NY",
    label: "New York TANF (Family Assistance)",
    region: "us",
    kind: "household",
    order: 220
  },
  "wa-tanf-ecps": {
    family: "tanf",
    jurisdiction: "WA",
    label: "Washington TANF (WorkFirst)",
    region: "us",
    kind: "household",
    order: 221
  },
  "fl-tca-standards": {
    family: "tanf",
    jurisdiction: "FL",
    label: "Florida TCA payment standards",
    region: "us",
    kind: "parameter",
    order: 226
  },
  "md-tca-payments": {
    family: "tanf",
    jurisdiction: "MD",
    label: "Maryland TCA payment schedule",
    region: "us",
    kind: "parameter",
    order: 227
  },
  "me-tanf-standards": {
    family: "tanf",
    jurisdiction: "ME",
    label: "Maine TANF standards",
    region: "us",
    kind: "parameter",
    order: 228
  },
  "al-tanf-payment-standards": {
    family: "tanf",
    jurisdiction: "AL",
    label: "Alabama TANF payment standards",
    region: "us",
    kind: "parameter",
    order: 229
  },
  "az-tanf-deductions": {
    family: "tanf",
    jurisdiction: "AZ",
    label: "Arizona cash assistance deductions",
    region: "us",
    kind: "parameter",
    order: 230
  },
  "ga-tanf-standards": {
    family: "tanf",
    jurisdiction: "GA",
    label: "Georgia TANF financial standards",
    region: "us",
    kind: "parameter",
    order: 224
  },
  "ak-atap-standards": {
    family: "tanf",
    jurisdiction: "AK",
    label: "Alaska ATAP need standards",
    region: "us",
    kind: "parameter",
    order: 225
  },
  "tx-tanf-parameters": {
    family: "tanf",
    jurisdiction: "TX",
    label: "Texas TANF needs parameters",
    region: "us",
    kind: "parameter",
    order: 226
  },
  "wa-tanf-payment-standard": {
    family: "tanf",
    jurisdiction: "WA",
    label: "Washington TANF payment standards",
    region: "us",
    kind: "parameter",
    order: 221
  },
  "ny-tanf-standards": {
    family: "tanf",
    jurisdiction: "NY",
    label: "New York TANF need standards",
    region: "us",
    kind: "parameter",
    order: 222
  },
  "medicaid-magi-co-ecps": {
    family: "medicaid_eligibility_groups",
    jurisdiction: "CO",
    label: "Medicaid eligibility groups (CO slice)",
    region: "us",
    kind: "household",
    order: 215
  },
  "medicaid-thresholds-states": {
    family: "medicaid_chip_bhp_thresholds",
    jurisdiction: "US",
    label: "Medicaid / CHIP thresholds — 49-state CMS card",
    region: "us",
    kind: "parameter",
    order: 212
  },
  "ga-health-thresholds": {
    family: "medicaid_chip_bhp_thresholds",
    jurisdiction: "GA",
    label: "Georgia Medicaid / CHIP / BHP thresholds",
    region: "us",
    kind: "parameter",
    order: 211
  },
  "pell-parameters": {
    family: "pell_grant",
    jurisdiction: "US",
    label: "Pell Grant award amounts",
    region: "us",
    kind: "parameter",
    order: 240
  },
  "lifeline-parameters": {
    family: "lifeline",
    jurisdiction: "US",
    label: "Lifeline income limit",
    region: "us",
    kind: "parameter",
    order: 290
  },
  "csfp-parameters": {
    family: "csfp",
    jurisdiction: "US",
    label: "CSFP income limit",
    region: "us",
    kind: "parameter",
    order: 291
  },
  "hi-income-tax-parameters": {
    family: "state_income_tax",
    jurisdiction: "HI",
    label: "Hawaii income tax amounts",
    region: "us",
    kind: "parameter",
    order: 118
  },
  "ia-income-tax-parameters": {
    family: "state_income_tax",
    jurisdiction: "IA",
    label: "Iowa income tax exemption credits",
    region: "us",
    kind: "parameter",
    order: 119
  },
  "irs-adjustment-parameters": {
    family: "federal_income_tax",
    jurisdiction: "US",
    label: "Federal IRC adjustment/deduction amounts",
    region: "us",
    kind: "parameter",
    order: 11
  },
  "co-state-income-tax-taxsim": {
    family: "state_income_tax",
    jurisdiction: "CO",
    label: "Colorado income tax (vs TAXSIM)",
    region: "us",
    kind: "household",
    order: 201
  },
  "co-state-income-tax-ecps": {
    family: "state_income_tax",
    jurisdiction: "CO",
    label: "Colorado income tax",
    region: "us",
    kind: "household",
    order: 200
  },
  "co-health-thresholds": {
    family: "medicaid_chip_bhp_thresholds",
    jurisdiction: "CO",
    label: "Colorado Medicaid / CHIP / BHP thresholds",
    region: "us",
    kind: "parameter",
    order: 210
  },
  "ca-tanf-ecps": {
    family: "tanf",
    jurisdiction: "CA",
    label: "California CalWORKs",
    region: "us",
    kind: "household",
    order: 218
  },
  "ks-tanf-ecps": {
    family: "tanf",
    jurisdiction: "KS",
    label: "Kansas TANF maximum benefit",
    region: "us",
    kind: "household",
    order: 216
  },
  "az-tanf-ecps": {
    family: "tanf",
    jurisdiction: "AZ",
    label: "Arizona Cash Assistance",
    region: "us",
    kind: "household",
    order: 217
  },
  "mn-tanf-ecps": {
    family: "tanf",
    jurisdiction: "MN",
    label: "Minnesota MFIP",
    region: "us",
    kind: "household",
    order: 223
  },
  "co-tanf-ecps": {
    family: "tanf",
    jurisdiction: "CO",
    label: "Colorado Works TANF",
    region: "us",
    kind: "household",
    order: 219
  },
  "co-tanf-coverage": {
    family: "tanf",
    jurisdiction: "CO",
    label: "Colorado Works TANF",
    region: "us",
    kind: "coverage",
    order: 220
  },
  "uk-universal-credit-efrs": {
    family: "universal_credit",
    jurisdiction: "UK",
    label: "UK Universal Credit",
    region: "uk",
    kind: "household",
    order: 300
  },
  "uk-universal-credit": {
    family: "universal_credit",
    jurisdiction: "UK",
    label: "UK Universal Credit (UKMOD)",
    region: "uk",
    kind: "household",
    order: 301
  },
  "uk-tax-benefits-efrs": {
    family: "uk_tax_benefits",
    jurisdiction: "UK",
    label: "UK tax & benefits",
    region: "uk",
    kind: "household",
    order: 310
  },
  "be-worker-pit": {
    family: "be_personal_income_tax",
    jurisdiction: "BE",
    label: "Belgium worker PIT",
    region: "be",
    kind: "household",
    order: 500
  },
  "be-worker-ssc": {
    family: "be_social_security",
    jurisdiction: "BE",
    label: "Belgium employee social-security contributions",
    region: "be",
    kind: "household",
    order: 510
  },
  "be-employer-ssc": {
    family: "be_social_security",
    jurisdiction: "BE",
    label: "Belgium employer social-security contributions",
    region: "be",
    kind: "household",
    order: 512
  },
  "be-self-employed-ssc": {
    family: "be_social_security",
    jurisdiction: "BE",
    label: "Belgium self-employed social-security contributions",
    region: "be",
    kind: "household",
    order: 515
  },
  "be-special-social-security-contribution": {
    family: "be_social_security",
    jurisdiction: "BE",
    label: "Belgium special social-security contribution",
    region: "be",
    kind: "household",
    order: 516
  },
  "be-flemish-social-protection-premium": {
    family: "be_social_security",
    jurisdiction: "BE",
    label: "Belgium Flemish Social Protection premium",
    region: "be",
    kind: "household",
    order: 517
  },
  "be-flemish-jobbonus": {
    family: "be_social_security",
    jurisdiction: "BE",
    label: "Belgium Flemish jobbonus",
    region: "be",
    kind: "household",
    order: 518
  },
  "be-cadastral-income-indexation": {
    family: "be_personal_income_tax",
    jurisdiction: "BE",
    label: "Belgium cadastral income indexation",
    region: "be",
    kind: "household",
    order: 518.5
  },
  "be-property-tax": {
    family: "be_personal_income_tax",
    jurisdiction: "BE",
    label: "Belgium immovable withholding",
    region: "be",
    kind: "household",
    order: 519
  },
  "be-social-assistance": {
    family: "be_social_assistance",
    jurisdiction: "BE",
    label: "Belgium social integration income support",
    region: "be",
    kind: "household",
    order: 520
  },
  "be-elderly-income-support": {
    family: "be_social_assistance",
    jurisdiction: "BE",
    label: "Belgium elderly income guarantee",
    region: "be",
    kind: "household",
    order: 530
  },
  "be-maternity-leave": {
    family: "be_health_insurance",
    jurisdiction: "BE",
    label: "Belgium maternity leave indemnity",
    region: "be",
    kind: "household",
    order: 540
  },
  "be-birth-leave": {
    family: "be_health_insurance",
    jurisdiction: "BE",
    label: "Belgium birth leave compensation",
    region: "be",
    kind: "household",
    order: 541
  },
  "be-marital-quotient": {
    family: "be_personal_income_tax",
    jurisdiction: "BE",
    label: "Belgium marital quotient",
    region: "be",
    kind: "household",
    order: 501
  },
  "be-regional-pit-surcharge": {
    family: "be_personal_income_tax",
    jurisdiction: "BE",
    label: "Belgium regional PIT surcharge",
    region: "be",
    kind: "household",
    order: 502
  },
  "be-local-municipal-pit": {
    family: "be_personal_income_tax",
    jurisdiction: "BE",
    label: "Belgium municipal PIT surcharge",
    region: "be",
    kind: "household",
    order: 503
  },
  "be-capital-income-tax": {
    family: "be_personal_income_tax",
    jurisdiction: "BE",
    label: "Belgium capital income tax",
    region: "be",
    kind: "household",
    order: 504
  },
  "be-article-51-forfait": {
    family: "be_personal_income_tax",
    jurisdiction: "BE",
    label: "Belgium Article 51 forfait",
    region: "be",
    kind: "household",
    order: 505
  },
  "be-worker-tax-income-list": {
    family: "be_personal_income_tax",
    jurisdiction: "BE",
    label: "Belgium worker tax income grid",
    region: "be",
    kind: "household",
    order: 506
  },
  "be-pensioner-contributions": {
    family: "be_social_security",
    jurisdiction: "BE",
    label: "Belgium pensioner contributions",
    region: "be",
    kind: "household",
    order: 513
  },
  "be-work-bonus-credit": {
    family: "be_social_security",
    jurisdiction: "BE",
    label: "Belgium work bonus",
    region: "be",
    kind: "household",
    order: 514
  },
  "be-unemployment": {
    family: "be_unemployment",
    jurisdiction: "BE",
    label: "Belgium unemployment benefits",
    region: "be",
    kind: "household",
    order: 525
  },
  "be-study-allowance": {
    family: "be_study_allowance",
    jurisdiction: "BE",
    label: "Belgium study allowance",
    region: "be",
    kind: "household",
    order: 545
  },
  "be-family-child-benefit-base": {
    family: "be_family_benefits",
    jurisdiction: "BE",
    label: "Belgium child benefit — base amounts",
    region: "be",
    kind: "household",
    order: 550
  },
  "be-family-child-benefit-social-supplement": {
    family: "be_family_benefits",
    jurisdiction: "BE",
    label: "Belgium child benefit — social supplement",
    region: "be",
    kind: "household",
    order: 551
  },
  "be-family-child-benefit-wallonia-social-supplement": {
    family: "be_family_benefits",
    jurisdiction: "BE",
    label: "Belgium child benefit — Wallonia social supplement",
    region: "be",
    kind: "household",
    order: 552
  },
  "be-family-child-benefit-brussels-same-age-household": {
    family: "be_family_benefits",
    jurisdiction: "BE",
    label: "Belgium child benefit — Brussels same-age household",
    region: "be",
    kind: "household",
    order: 553
  },
  "be-family-child-benefit-income-list": {
    family: "be_family_benefits",
    jurisdiction: "BE",
    label: "Belgium child benefit — income grid",
    region: "be",
    kind: "household",
    order: 554
  },
  "be-family-birth-allowance": {
    family: "be_family_benefits",
    jurisdiction: "BE",
    label: "Belgium birth allowance",
    region: "be",
    kind: "household",
    order: 555
  },
  "be-worker-disposable-income-list": {
    family: "be_disposable_income",
    jurisdiction: "BE",
    label: "Belgium worker disposable income",
    region: "be",
    kind: "household",
    order: 560
  },
  "uk-worker-pit": {
    family: "uk_income_tax",
    jurisdiction: "UK",
    label: "UK worker income tax (UKMOD)",
    region: "uk",
    kind: "household",
    order: 320
  },
  "uk-worker-nic": {
    family: "uk_national_insurance",
    jurisdiction: "UK",
    label: "UK worker employee NIC (UKMOD)",
    region: "uk",
    kind: "household",
    order: 322
  },
  "uk-income-tax-scottish": {
    family: "uk_income_tax",
    jurisdiction: "UK",
    label: "UK income tax — Scottish rates (UKMOD)",
    region: "uk",
    kind: "household",
    order: 321
  },
  "uk-income-tax-dividend": {
    family: "uk_income_tax",
    jurisdiction: "UK",
    label: "UK income tax — dividends (UKMOD)",
    region: "uk",
    kind: "household",
    order: 321.1
  },
  "uk-income-tax-savings": {
    family: "uk_income_tax",
    jurisdiction: "UK",
    label: "UK income tax — savings (UKMOD)",
    region: "uk",
    kind: "household",
    order: 321.2
  },
  "uk-income-tax-mixed": {
    family: "uk_income_tax",
    jurisdiction: "UK",
    label: "UK income tax — mixed income (UKMOD)",
    region: "uk",
    kind: "household",
    order: 321.3
  },
  "uk-employer-nic": {
    family: "uk_national_insurance",
    jurisdiction: "UK",
    label: "UK employer NIC (UKMOD)",
    region: "uk",
    kind: "household",
    order: 323
  },
  "uk-self-employed-nic": {
    family: "uk_national_insurance",
    jurisdiction: "UK",
    label: "UK self-employed NIC (UKMOD)",
    region: "uk",
    kind: "household",
    order: 324
  },
  "uk-child-benefit": {
    family: "uk_child_benefit",
    jurisdiction: "UK",
    label: "UK Child Benefit",
    region: "uk",
    kind: "household",
    order: 330
  },
  "uk-pension-credit": {
    family: "uk_pension_credit",
    jurisdiction: "UK",
    label: "UK Pension Credit",
    region: "uk",
    kind: "household",
    order: 332
  },
  "uk-benefit-cap": {
    family: "uk_benefit_cap",
    jurisdiction: "UK",
    label: "UK benefit cap",
    region: "uk",
    kind: "household",
    order: 334
  },
  "uk-winter-fuel": {
    family: "uk_winter_fuel",
    jurisdiction: "UK",
    label: "UK Winter Fuel Payment",
    region: "uk",
    kind: "household",
    order: 336
  },
  "uk-maternity-allowance": {
    family: "uk_maternity_allowance",
    jurisdiction: "UK",
    label: "UK Maternity Allowance",
    region: "uk",
    kind: "household",
    order: 338
  },
  "uk-statutory-maternity-pay": {
    family: "uk_statutory_maternity_pay",
    jurisdiction: "UK",
    label: "UK Statutory Maternity Pay",
    region: "uk",
    kind: "household",
    order: 339
  },
  "uk-statutory-paternity-pay": {
    family: "uk_statutory_paternity_pay",
    jurisdiction: "UK",
    label: "UK Statutory Paternity Pay",
    region: "uk",
    kind: "household",
    order: 340
  },
  "uk-sure-start-maternity-grant": {
    family: "uk_sure_start_maternity_grant",
    jurisdiction: "UK",
    label: "UK Sure Start Maternity Grant",
    region: "uk",
    kind: "household",
    order: 341
  },
  "uk-best-start-foods": {
    family: "uk_best_start_foods",
    jurisdiction: "UK",
    label: "Scotland Best Start Foods",
    region: "uk",
    kind: "household",
    order: 342
  },
  "uk-healthy-start": {
    family: "uk_healthy_start",
    jurisdiction: "UK",
    label: "UK Healthy Start",
    region: "uk",
    kind: "household",
    order: 343
  },
  "de-worker-dual-oracle": {
    family: "de_worker_tax_contributions",
    jurisdiction: "DEU",
    label: "Germany worker tax and social insurance",
    region: "de",
    kind: "household",
    order: 600
  },
  "de-kindergeld-eligibility": {
    family: "de_kindergeld",
    jurisdiction: "DEU",
    label: "Germany Kindergeld child eligibility",
    region: "de",
    kind: "household",
    order: 601
  },
  "nyc-income-tax-gap": {
    family: "nyc_income_tax",
    jurisdiction: "NYC",
    label: "NYC income tax components",
    region: "us",
    kind: "diagnostic",
    order: 400
  },
  "nyc-income-tax-ecps-diagnostic": {
    family: "nyc_income_tax",
    jurisdiction: "NYC",
    label: "NYC income tax ECPS diagnostic",
    region: "us",
    kind: "diagnostic",
    order: 410
  },
  "nyc-synthetic": {
    family: "nyc_income_tax",
    jurisdiction: "NYC",
    label: "NYC synthetic scenarios",
    region: "us",
    kind: "diagnostic",
    order: 420
  }
};
var POPULACE_CAMPAIGN_STATES = [
  "AL",
  "AR",
  "AZ",
  "CO",
  "CT",
  "DE",
  "GA",
  "HI",
  "IA",
  "IL",
  "IN",
  "KS",
  "LA",
  "MI",
  "MS",
  "MT",
  "NC",
  "NJ",
  "NM",
  "NY",
  "OH",
  "OK",
  "PA",
  "SC",
  "UT",
  "VA",
  "VT",
  "WV"
];
for (const st of POPULACE_CAMPAIGN_STATES) {
  SUITE_OVERRIDES[`${st.toLowerCase()}-income-tax-populace`] = {
    family: "state_income_tax",
    jurisdiction: st,
    label: `${US_STATE_NAMES[st]} income tax — full Populace`,
    region: "us",
    kind: "household",
    order: 90
  };
}
var SLUG_ACRONYMS = new Set([
  "uk",
  "us",
  "dk",
  "be",
  "de",
  "tv",
  "vat",
  "jsa",
  "pe",
  "lbtt",
  "ltt",
  "ecps",
  "qc"
]);
function topLevelAggregates(aggregates) {
  const rows = aggregates || [];
  const concepts = new Set(rows.map((agg) => agg.concept));
  return rows.filter((agg) => !(agg.parent && concepts.has(agg.parent)));
}

// src/utils/data.js
async function loadOracleData(basePath = "") {
  let reportFiles = ["policyengine-taxsim.json"];
  try {
    const manifestResp = await fetch(`${basePath}/data/manifest.json`);
    if (manifestResp.ok) {
      const manifest = await manifestResp.json();
      reportFiles = manifest.reports || reportFiles;
    }
  } catch {}
  let reports = [];
  try {
    const overviewResp = await fetch(`${basePath}/data/overview.json`);
    if (overviewResp.ok) {
      const overview = await overviewResp.json();
      reports = overview.reports || [];
    }
  } catch {}
  if (reports.length === 0) {
    const settled = await Promise.all(reportFiles.map(async (file) => {
      try {
        const resp = await fetch(`${basePath}/data/${file}`);
        if (!resp.ok)
          return null;
        const report = await resp.json();
        report.file = file;
        return report;
      } catch {
        return null;
      }
    }));
    reports = settled.filter(Boolean);
  }
  for (const report of reports) {
    const fromFile = (report.file || "").match(/^axiom-policyengine-([a-z]{2}-snap-ecps)\.json$/);
    if (fromFile && (!report.suite || report.suite === "nyc-synthetic") && report.suite !== fromFile[1]) {
      report.suite = fromFile[1];
    }
  }
  let allPrograms = [];
  try {
    const programsResp = await fetch(`${basePath}/data/programs.json`);
    if (programsResp.ok) {
      const payload = await programsResp.json();
      allPrograms = payload.programs || [];
    }
  } catch {}
  let knownCauses = [];
  try {
    const causesResp = await fetch(`${basePath}/data/known_causes.json`);
    if (causesResp.ok) {
      const payload = await causesResp.json();
      knownCauses = payload.entries || [];
    }
  } catch {}
  let coverageOverview = null;
  try {
    const coverageResp = await fetch(`${basePath}/data/coverage_overview.json`);
    if (coverageResp.ok) {
      coverageOverview = await coverageResp.json();
    }
  } catch {}
  let euromodCoverage = null;
  try {
    const euromodResp = await fetch(`${basePath}/data/euromod-be-coverage.json`);
    if (euromodResp.ok) {
      euromodCoverage = await euromodResp.json();
    }
  } catch {}
  let euromodIssues = null;
  try {
    const euromodIssuesResp = await fetch(`${basePath}/data/euromod-issues.json`);
    if (euromodIssuesResp.ok) {
      euromodIssues = await euromodIssuesResp.json();
    }
  } catch {}
  let freshness = null;
  try {
    const freshnessResp = await fetch(`${basePath}/data/freshness.json`);
    if (freshnessResp.ok) {
      freshness = await freshnessResp.json();
    }
  } catch {}
  const programs = allPrograms.filter((p) => p.encoding_status !== "missing");
  const allowedConcepts = new Set(programs.map((p) => p.id));
  for (const report of reports) {
    for (const aggregate of report.aggregates || []) {
      if ((aggregate.comparison_count || 0) > 0 || (aggregate.quality_flags || []).length > 0 || (report.summary?.alarms || []).length > 0) {
        allowedConcepts.add(aggregate.concept);
      }
    }
  }
  for (const report of reports) {
    for (const concept of report.concepts || []) {
      if (allowedConcepts.has(concept.id)) {
        allowedConcepts.add(concept.id);
      } else if (concept.parent && allowedConcepts.has(concept.parent)) {
        allowedConcepts.add(concept.id);
      }
    }
  }
  const filteredReports = reports.map((report) => filterReportToConcepts(report, allowedConcepts));
  const suites = [
    ...new Set(filteredReports.map((r) => r.suite).filter(Boolean))
  ].sort();
  const data = buildNWayData(filteredReports);
  return {
    ...data,
    programs,
    reports: filteredReports,
    suites,
    knownCauses,
    coverageOverview,
    euromodCoverage,
    euromodIssues,
    freshness
  };
}
function filterReportsBySuite(reports, suite) {
  if (!suite || suite === "all")
    return reports;
  return reports.filter((r) => r.suite === suite);
}
function filterReportToConcepts(report, allowed) {
  if (allowed.size === 0)
    return report;
  return {
    ...report,
    concepts: (report.concepts || []).filter((c) => allowed.has(c.id)),
    aggregates: (report.aggregates || []).filter((a) => allowed.has(a.concept)),
    mismatches: (report.mismatches || []).filter((m) => allowed.has(m.concept)),
    cases: (report.cases || []).map((c) => ({
      ...c,
      mismatches: (c.mismatches || []).filter((m) => allowed.has(m.concept))
    }))
  };
}
function buildNWayData(reports) {
  const oracleSet = new Set;
  const conceptMap = new Map;
  for (const report of reports) {
    const left = report.engines?.left;
    const right = report.engines?.right;
    if (left)
      oracleSet.add(left);
    if (right)
      oracleSet.add(right);
    for (const concept of report.concepts || []) {
      if (!conceptMap.has(concept.id)) {
        conceptMap.set(concept.id, concept);
      }
    }
  }
  const oracles = [...oracleSet].sort();
  const concepts = [...conceptMap.values()];
  const matrix = {};
  for (const concept of concepts) {
    matrix[concept.id] = {};
    for (const left of oracles) {
      matrix[concept.id][left] = {};
      for (const right of oracles) {
        if (left === right) {
          matrix[concept.id][left][right] = 100;
        } else {
          matrix[concept.id][left][right] = null;
        }
      }
    }
  }
  for (const report of reports) {
    const left = report.engines?.left;
    const right = report.engines?.right;
    if (!left || !right)
      continue;
    for (const agg of report.aggregates || []) {
      const rate = agg.match_rate;
      if (rate != null && matrix[agg.concept]) {
        matrix[agg.concept][left][right] = rate;
        matrix[agg.concept][right][left] = rate;
      }
    }
  }
  const overallMatrix = {};
  for (const left of oracles) {
    overallMatrix[left] = {};
    for (const right of oracles) {
      if (left === right) {
        overallMatrix[left][right] = 100;
        continue;
      }
      const rates = concepts.map((c) => matrix[c.id]?.[left]?.[right]).filter((r) => r != null);
      overallMatrix[left][right] = rates.length > 0 ? rates.reduce((a, b) => a + b, 0) / rates.length : null;
    }
  }
  const caseIndex = new Map;
  for (const report of reports) {
    const left = report.engines?.left;
    const right = report.engines?.right;
    for (const c of report.cases || []) {
      if (!caseIndex.has(c.case_id)) {
        caseIndex.set(c.case_id, {
          case_id: c.case_id,
          metadata: c.metadata || {},
          values: {},
          mismatches: [],
          match_rate: c.match_rate
        });
      }
      const entry = caseIndex.get(c.case_id);
      for (const m of c.mismatches || []) {
        if (!entry.values[m.concept])
          entry.values[m.concept] = {};
        entry.values[m.concept][left] = m.left;
        entry.values[m.concept][right] = m.right;
        entry.mismatches.push({
          ...m,
          pair: `${left} vs ${right}`
        });
      }
    }
  }
  const allCases = [...caseIndex.values()];
  const reportCaseCount = reports.reduce((acc, r) => acc + (Number.isFinite(r.case_count) ? r.case_count : (r.cases || []).length), 0);
  const aggregateTotals = reports.reduce((acc, r) => {
    for (const agg of topLevelAggregates(r.aggregates)) {
      acc.matches += agg.comparison_count - agg.mismatch_count || 0;
      acc.mismatches += agg.mismatch_count || 0;
      acc.comparisons += agg.comparison_count || 0;
    }
    return acc;
  }, { matches: 0, mismatches: 0, comparisons: 0 });
  const summary = {
    totalCases: reportCaseCount,
    totalOracles: oracles.length,
    totalConcepts: concepts.length,
    totalReports: reports.length,
    overallMatchRate: aggregateTotals.comparisons > 0 ? aggregateTotals.matches / aggregateTotals.comparisons * 100 : 0,
    mismatchCount: aggregateTotals.mismatches
  };
  return { oracles, reports, matrix, overallMatrix, concepts, allCases, summary };
}
export {
  loadOracleData,
  filterReportsBySuite,
  buildNWayData
};
