/**
 * Who each oracle IS, and any tie it has to Axiom.
 * Keyed by the dashboard's oracle id (otherOracle in utils/suites.js), not
 * the raw engine id: EUROMOD-platform reports split into euromod, ukmod and
 * southmod. An oracle with an acknowledgement or licence its terms require
 * carries it here, and its record page shows both.
 */

import {
  UKMOD_RELEASE,
  southmodAcknowledgement,
  ukmodAcknowledgement,
} from "./suites";

export const ORACLE_IDENTITY = {
  policyengine: {
    org: "PolicyEngine",
    what: "Open-source tax–benefit microsimulation of US and UK law. Max Ghenis is CEO of both Axiom and PolicyEngine, which he co-founded, and PSL Foundation fiscally sponsors both organizations.",
    url: "https://policyengine.org",
  },
  taxsim: {
    org: "NBER",
    what: "TAXSIM-35 — the National Bureau of Economic Research's federal and state income-tax calculator, the reference model of empirical tax research. PolicyEngine is building TAXSIM's successor with its author's cooperation, and Axiom's runs use the TAXSIM executable that PolicyEngine packages (policyengine-taxsim).",
    url: "https://taxsim.nber.org/",
  },
  taxcalc: {
    org: "Policy Simulation Library",
    what: "Tax-Calculator — open-source US federal income-tax microsimulation used by think tanks across the spectrum.",
    url: "https://github.com/PSLmodels/Tax-Calculator",
  },
  euromod: {
    org: "European Commission JRC",
    what: "The EU's official tax–benefit microsimulation model, covering all member states including Belgium.",
    url: "https://euromod-web.jrc.ec.europa.eu/",
  },
  ukmod: {
    org: "University of Essex (CeMPA)",
    what: `UKMOD — a tax–benefit microsimulation model for the UK and its four nations, run on the EUROMOD platform and developed by the Centre for Microsimulation and Policy Analysis (CeMPA) at the University of Essex. Axiom runs its registration-free public release (${UKMOD_RELEASE}) on synthetic households.`,
    url: "https://www.microsimulation.ac.uk/ukmod/",
    acknowledgement: ukmodAcknowledgement(),
    licence: {
      name: "CC BY-NC-ND 4.0",
      url: "https://creativecommons.org/licenses/by-nc-nd/4.0/",
    },
  },
  southmod: {
    org: "UNU-WIDER",
    what: "SOUTHMOD — UNU-WIDER's tax–benefit microsimulation models for countries in the Global South, run on the EUROMOD software under the SOUTHMOD_A4.0 licence. The model and its input data stay on Axiom's licensed machine; the comparison households are synthetic.",
    url: "https://www.wider.unu.edu/project/southmod-simulating-tax-and-benefit-policies-development-phase-3",
    acknowledgement: southmodAcknowledgement(),
  },
  accessnyc: {
    org: "NYC Opportunity",
    what: "ACCESS NYC — New York City's official benefits screening service.",
    url: "https://access.nyc.gov/",
  },
  prd: {
    org: "Policy Rules Database",
    what: "The Atlanta Fed's Policy Rules Database of US safety-net program rules.",
    url: "https://www.atlantafed.org/economic-mobility-and-resilience/advancing-careers-for-low-income-families/policy-rules-database",
  },
  "snap-qc": {
    org: "USDA Food and Nutrition Service",
    what: "SNAP Quality Control public-use file — the USDA's national sample of active SNAP cases, each reviewed by state QC reviewers who reinterview the household. Axiom is compared with FSBEN, the file's final calculated benefit, which Mathematica computes for USDA from each edited case record; the benefit received is a separate field (RAWBEN). The file keeps only eligible households and the replay takes income and several deductions as given, so it checks benefit arithmetic and leaves eligibility untested.",
    url: "https://snapqcdata.net/datafiles",
  },
  spsm: {
    org: "Statistics Canada",
    what: "SPSD/M — Statistics Canada's Social Policy Simulation Database and Model, the reference Canadian tax–transfer microsimulation, run under licence over its synthetic database. Results carry the SPSD/M licence attribution; per-household evidence stays local.",
    url: "https://www.statcan.gc.ca/en/microsimulation/spsdm/spsdm",
  },
};

/**
 * The oracles among `ids` whose terms ask published output to carry an
 * acknowledgement or a licence link; the footer links each one's record.
 */
export function attributedOracles(ids) {
  return ids.filter(
    (id) => ORACLE_IDENTITY[id]?.acknowledgement || ORACLE_IDENTITY[id]?.licence,
  );
}
