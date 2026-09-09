#!/usr/bin/env python3
"""Compute DE program closure from a pinned exact-citation-path snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "closure" / "de"
SOURCE_PATH = OUT_DIR / "source.json"
SUMMARY_PATH = OUT_DIR / "summary.json"

# Review pin for the committed denominator. Changing any corpus row,
# classification, boundary, or program root requires an explicit re-review.
_REQUIREMENT_FRONTIER = (
    "closed: closure must disposition the act's subordinate instruments "
    "(oracles#491); this closure declares none"
)
_REQUIREMENT_DEPENDENCY = (
    "closed: closure must type every leaf and encode every law-derived "
    "dependency (CERTIFIED.md v3); this closure declares no "
    "dependency-closure block"
)
SOURCE_SHA256 = 'cb8ae24d75abff21fd57afed5f07448bef65c2f289ddbb4b0fd1b762bcdf0c62'

SOURCE_SCHEMA = "axiom_oracles.de_closure_source.v1"
SUMMARY_SCHEMA = "axiom_oracles.de_closure_summary.v1"
RELEASE = 'de-rulespec-2026-09-09-kindergeld-swiss-coordination'
RELEASE_CONTENT_SHA256 = '1a6201bd7521952f52bcce2261a6b1a5cf15e30b145d7daba189cfe1b7fe1f77'
RELEASE_SELECTOR_SHA256 = 'fff38c38e07dce53e492e754a8812069641643b0e4ff3e47f03d5a54a0203721'
CORPUS_COMMIT = '495236ce303398c8cea3d1d8f1e5fdcda5b09488'
RULESPEC_COMMIT = "25fe6cb5be81f6187ab2ba37e918165ae8e58cf5"
RESOLUTION_PROTOCOL = {
    "descendants_by": "parent_citation_path",
    "filename_filters": False,
    "key": "citation_path",
    "match": "exact",
    "protocol": "de-exact-citation-closure-v1",
}

ESTG_66 = "de/statute/estg/66"
STEFEG_ROOT = "de/statute/bgbl-2024-i-449/steuerfortentwicklungsgesetz"
STEFEG_CONTENT = f"{STEFEG_ROOT}/document-1"
KINDRG_CONTEXT_ROOT = "de/statute/bgbl-1997-i-2942/kindschaftsrechtsreformgesetz/parentage-commencement-extract"
KINDERGELD_BOUNDARIES = (
    "de/statute/estg/62",
    "de/statute/estg/63",
    "de/statute/estg/64",
    "de/statute/estg/65",
)

PROGRAM_ROOT_NODES = {
    "de/kindergeld": ("de:statutes/estg/66#monthly_kindergeld_per_child",),
    "de/rv-employee-contribution": (
        "de:statutes/sgb-6/168#employee_pension_insurance_contribution_share",
        "de:regulations/svbezgrv-2025/4#general_pension_insurance_monthly_contribution_assessment_ceiling",
    ),
    "de/unterhaltsvorschuss": ("de:statutes/uhvorschg/2#advance_maintenance_amount",),
}
PROGRAM_SOURCE_PATHS = {
    "de/kindergeld": (ESTG_66, "de/statute/bgb/1591", "de/statute/bgb/187", "de/statute/estg/78"),
    "de/rv-employee-contribution": (
        "de/regulation/bsv-2018/1",
        "de/regulation/svbezgrv-2025/4",
        "de/statute/sgb-6/168",
    ),
    "de/unterhaltsvorschuss": (
        "de/regulation/minuhv/1",
        "de/statute/uhvorschg/2",
        ESTG_66,
    ),
}
PROGRAM_EVIDENCE_ROOTS = {
    "de/kindergeld": (STEFEG_ROOT, KINDRG_CONTEXT_ROOT),
    "de/rv-employee-contribution": (),
    "de/unterhaltsvorschuss": (),
}

EXPECTED_INVENTORIES = {
    'data/corpus/inventory/de/guidance/2026-09-08-de-kindergeld-cjeu.json': ('74e8dfa9aded09d34cad08c04249da5016ac478b0bace29562d11343e74ef21e', 2),
    'data/corpus/inventory/de/guidance/2026-09-08-de-kindergeld-eea-parties.json': ('21fe11fffb91908b23414dd8187f1050ee3edad287c3b31b7bf6ff1af0808efc', 2),
    'data/corpus/inventory/de/guidance/2026-09-08-de-kindergeld-handbooks-remaining.json': ('ff2fd62b1257752348fa8ec3419d2ee2eeb149e9491e6ee2b06dd5e7ab4300bb', 16),
    'data/corpus/inventory/de/guidance/2026-09-08-de-kindergeld-handbooks-retained.json': ('4ee7704f4529a59b80d4c4087338d3ebaeecfc1f350ed6f4c2f9a0a967cbb178', 4),
    'data/corpus/inventory/de/guidance/2026-09-08-de-kindergeld-parentage-constitutional.json': ('f9d0947eecd1ea1e9ba1307ff52144c36cdf366165a7f465a73b4a386607cf28', 4),
    'data/corpus/inventory/de/guidance/2026-09-08-de-kindergeld-ristbv.json': ('9babd54bdf9bb21617eee3e6ab5893b2783e65149f7cd258e432c9773b6e0cb0', 2),
    'data/corpus/inventory/de/guidance/2026-09-09-de-kindergeld-allowance-explanation.json': ('0ff6f48069381b5e5c02392eceddd7495e450d4f0bb60f6f667fbf89d407504a', 2),
    'data/corpus/inventory/de/guidance/2026-09-09-de-kindergeld-bmf-letter-context.json': ('741158c6661fcc152978385ded67a9d927c9afaad99e460ec03ac98a0b9d7257', 6),
    'data/corpus/inventory/de/guidance/2026-09-09-de-kindergeld-civil-partner-letter.json': ('f5937de472767d6a9a44757714c595c185aaab0d2519654191a22934d74d486d', 2),
    'data/corpus/inventory/de/regulation/2026-07-16-de-federal-tax-benefit-r2026-07-21-2025-instruments.json': ('1bf25f052f0c0cb5271bab85c24854b4268149c10cd6261649e3e417fee1ca70', 172),
    'data/corpus/inventory/de/regulation/2026-09-08-de-kindergeld-arb.json': ('b9e58ff44fa50d050a8f4680d9ea28e44ccabeb6ea0b4f5d54c9eaeba6f51df2', 2),
    'data/corpus/inventory/de/regulation/2026-09-08-de-kindergeld-bilateral.json': ('038860404e92952a4064d42413160b7a152f3d99aee28cacd7f49aed112da45f', 44),
    'data/corpus/inventory/de/regulation/2026-09-08-de-kindergeld-dependencies.json': ('16d6428a20439fd1ab7885572a06f2bed83cf529c54e33703b2341ab1eb791e1', 9),
    'data/corpus/inventory/de/regulation/2026-09-08-de-kindergeld-eea.json': ('c3bd7372757fdbe1f25e7caf47b14e233688e94b5e9096a915c731f2937c2558', 2),
    'data/corpus/inventory/de/regulation/2026-09-08-de-kindergeld-eu.json': ('3b977d73c0702ed2e46684fb6695983d5f50d5b10474a2a36f686f2dbf3c8b58', 8),
    'data/corpus/inventory/de/regulation/2026-09-08-de-kindergeld-withdrawal.json': ('540056c017b466168bb39e4ec226113ecf07512621e3cc4dd5a8b3d7c4160240', 2),
    'data/corpus/inventory/de/regulation/2026-09-09-de-kindergeld-swiss-coordination.json': ('37f2e8707ddec20f420fee594a5c69e6ce9fbe452f81a9459dc37a47adbe8e28', 4),
    'data/corpus/inventory/de/regulation/2026-09-09-de-kindergeld-treaty-texts.json': ('917dd8b4c99accc034736e3c5c1a3f4fbd283ccffac31768e08431f034521e02', 4),
    'data/corpus/inventory/de/statute/2026-07-16-de-federal-tax-benefit-r2026-07-21-2025-instruments.json': ('0a31685dd6d68051111646df421f7fe86b551e9166981acdead13a112b2fd974', 3376),
    'data/corpus/inventory/de/statute/2026-09-08-de-kindergeld-bgbl.json': ('deb452cf32367d1558b3248c84c0136bddbb425a070e693a6dd1099ce2a17604', 2),
    'data/corpus/inventory/de/statute/2026-09-08-de-kindergeld-civil-dependencies.json': ('dfe174ac522bf22e96937e05caec2a53edc37bd95b1060f36779ff5cde696d34', 3136),
    'data/corpus/inventory/de/statute/2026-09-08-de-kindergeld-dependencies.json': ('9894e4d836a873d7c44c57d82407395ffbfa5e9ad470dd51746229bfc7bf3f7e', 854),
    'data/corpus/inventory/de/statute/2026-09-08-de-kindergeld-historical-sgb.json': ('8f377ffd80ab33b6cd80c092f76ab0714ee14eecf4cc8ff1ab5559247144df76', 4),
    'data/corpus/inventory/de/statute/2026-09-08-de-kindergeld-parentage-2025-history.json': ('80df42142b65ba82f10629e5708f3cc56ab845a4addf4877e8fbf9ceb21d4a95', 18),
    'data/corpus/inventory/de/statute/2026-09-08-de-kindergeld-parentage-context.json': ('f16addeedc8098894e5959e842559657013c9c243e08715466ad0f3ec4dbb8a6', 2),
    'data/corpus/inventory/de/statute/2026-09-08-de-kindergeld-parentage-history.json': ('ae7a93143e0abb6e59dbe04c2feb18ccb636f2cca420725770f577c7ab7b934c', 2),
    'data/corpus/inventory/de/statute/2026-09-08-de-kindergeld-parentage-transition.json': ('6a3c0ab21d4487fc69adf4fb063af1829d7c9c1e0f54731ee53764e11361dc64', 535),
    'data/corpus/inventory/de/statute/2026-09-09-de-kindergeld-treaty-texts.json': ('690e9fd98b343628f7f77e0186ed74459346f4a120ae58b74495a62d60f5628f', 4),
}
EXPECTED_PROVISION_SOURCES = {
    'data/corpus/provisions/de/guidance/2026-09-08-de-kindergeld-cjeu.jsonl': ('80f92f8559a0f422b0d45b25af6aba2430de1650c03dd1722eab5f99cc803b29', 2),
    'data/corpus/provisions/de/guidance/2026-09-08-de-kindergeld-eea-parties.jsonl': ('8b2f92d88c2b7b2a87d1b7d3839c5c00c574899513bbcc206b4c04f22e806bff', 2),
    'data/corpus/provisions/de/guidance/2026-09-08-de-kindergeld-handbooks-remaining.jsonl': ('3fa9db7aea52a6fcd34dc6d69bc688835bdc4eb32ccae58689f6666d0f321b14', 16),
    'data/corpus/provisions/de/guidance/2026-09-08-de-kindergeld-handbooks-retained.jsonl': ('b1a49775e67be84de2b12bd2b355597f0c92086697f794a39b2c9c93c58d9d85', 4),
    'data/corpus/provisions/de/guidance/2026-09-08-de-kindergeld-parentage-constitutional.jsonl': ('1d2cbaea3ad02547e1432d6024efbbeed2d7bf17bd242fe14230082285b8ab39', 4),
    'data/corpus/provisions/de/guidance/2026-09-08-de-kindergeld-ristbv.jsonl': ('436fece03eb7134430846ed4eb689155f93976bac46e0d413c29f091bb346cac', 2),
    'data/corpus/provisions/de/guidance/2026-09-09-de-kindergeld-allowance-explanation.jsonl': ('9fa16911f8963b2f3bc97bb78495d84a4571a1a3b21b2e5a5ba8d54bad220e97', 2),
    'data/corpus/provisions/de/guidance/2026-09-09-de-kindergeld-bmf-letter-context.jsonl': ('7557a3800822439c310f3fcfca0c070ffdcb3259347d824e987d343a3261bf9b', 6),
    'data/corpus/provisions/de/guidance/2026-09-09-de-kindergeld-civil-partner-letter.jsonl': ('847da9da0164b56d23efb1afc15fd6dd79da674ab404711b8e2fdb93e48db050', 2),
    'data/corpus/provisions/de/regulation/2026-07-16-de-federal-tax-benefit-r2026-07-21-2025-instruments.jsonl': ('abf3c4dcc16224370a4e5e717325fa6374818a5821f3419d981b4cc9c11f6528', 172),
    'data/corpus/provisions/de/regulation/2026-09-08-de-kindergeld-arb.jsonl': ('29b5ec6c5e7f75349e3bcf8b15e752b9ab67163b70912f79f7270651a7eb60df', 2),
    'data/corpus/provisions/de/regulation/2026-09-08-de-kindergeld-bilateral.jsonl': ('f7de60269f7a96e555a2720a7e28cdf3465edac3c526daaf886d42e5ec86739e', 44),
    'data/corpus/provisions/de/regulation/2026-09-08-de-kindergeld-dependencies.jsonl': ('d1b07e68f9d1590374f8c458e1515b3c5060fb63b29b816de6460197375a8b97', 9),
    'data/corpus/provisions/de/regulation/2026-09-08-de-kindergeld-eea.jsonl': ('5d8089d89a8e2403bd0612430add225790580f37eaeba8db7f69f6ed0ca7075b', 2),
    'data/corpus/provisions/de/regulation/2026-09-08-de-kindergeld-eu.jsonl': ('5e1d4de7f1e5ef4201f4f313a6fc977d5720760b95c3af3ec244cfcb43b64bf1', 8),
    'data/corpus/provisions/de/regulation/2026-09-08-de-kindergeld-withdrawal.jsonl': ('22ccceba91ddb360b530a0f7bf89d21f3edc6e41520c335d6bb8d7d64002b9c6', 2),
    'data/corpus/provisions/de/regulation/2026-09-09-de-kindergeld-swiss-coordination.jsonl': ('6826c7014ae59f2727b96bfe11bba0d0ade920d7b251b8be6a9bb29d78d84b2e', 4),
    'data/corpus/provisions/de/regulation/2026-09-09-de-kindergeld-treaty-texts.jsonl': ('f1958634c2f77c09df09f66892a37946a76929da7dcef8b40f84a4d26cfed045', 4),
    'data/corpus/provisions/de/statute/2026-07-16-de-federal-tax-benefit-r2026-07-21-2025-instruments.jsonl': ('e22b6f2910e5d736e7fd58553d23ccb94c5b5f3116ab99d476311bcfb2f83d31', 3376),
    'data/corpus/provisions/de/statute/2026-09-08-de-kindergeld-bgbl.jsonl': ('80e30533507e1479acebc62038163f87052cab82d208ffe3314ab65e82ada6de', 2),
    'data/corpus/provisions/de/statute/2026-09-08-de-kindergeld-civil-dependencies.jsonl': ('3ec9ce938c85f9d8fd7b74e22b207a6621ea7b9eda19c69adedb2c873a4ccd68', 3136),
    'data/corpus/provisions/de/statute/2026-09-08-de-kindergeld-dependencies.jsonl': ('a864c05c97085b3d601ff204ccdc20c4c845ec1e0469b7a237ff0b3719088bac', 854),
    'data/corpus/provisions/de/statute/2026-09-08-de-kindergeld-historical-sgb.jsonl': ('6cd843c3a51b602a754735b27a02dd838d58cd461db865cc4860d9cf22f7192a', 4),
    'data/corpus/provisions/de/statute/2026-09-08-de-kindergeld-parentage-2025-history.jsonl': ('656c01d2a1010a937bee8bbcd689f9ed3e0f189089d8f1e864909f51ad0b5510', 18),
    'data/corpus/provisions/de/statute/2026-09-08-de-kindergeld-parentage-context.jsonl': ('906ddf936de0e23c6f1b80685272b0744b16cbcd1a26e1466a48dbf5647e767f', 2),
    'data/corpus/provisions/de/statute/2026-09-08-de-kindergeld-parentage-history.jsonl': ('9e67248ae3d7a44cb7307e1a1a4c247796610faeb233a0238026e5ab27e5d6cf', 2),
    'data/corpus/provisions/de/statute/2026-09-08-de-kindergeld-parentage-transition.jsonl': ('c8bafa5f3805c99097ecea6c1f89ecf3f036ff560562776b35f3ab4229f06059', 535),
    'data/corpus/provisions/de/statute/2026-09-09-de-kindergeld-treaty-texts.jsonl': ('c1b0e259edab999e9cfa262eca2f039cf457617304e0af242b050209fa02f717', 4),
}

HASH_RE = re.compile(r"^[0-9a-f]{64}$")
CLASSIFICATIONS = frozenset({"encoded", "excluded", "pending"})
SIGNATURE_STATES = frozenset({"signed", "pending", "not_applicable"})


class ClosureError(ValueError):
    """The committed DE closure denominator is malformed or inconsistent."""


def _sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _canonical_sha256(value: object) -> str:
    raw = json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode()
    return _sha256(raw)


def _require_hash(value: object, label: str) -> str:
    if not isinstance(value, str) or not HASH_RE.fullmatch(value):
        raise ClosureError(f"{label} must be a lowercase 64-hex sha256")
    return value


def _require_nonempty(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ClosureError(f"{label} must be a non-empty string")
    return value


def _validate_pinned_files(
    raw_rows: object,
    expected: dict[str, tuple[str, int]],
    label: str,
) -> None:
    if not isinstance(raw_rows, list):
        raise ClosureError(f"corpus {label} must be an array")
    paths = [row.get("path") for row in raw_rows if isinstance(row, dict)]
    if paths != sorted(expected):
        raise ClosureError(f"corpus {label} path set or order drifted")
    for row in raw_rows:
        if not isinstance(row, dict):
            raise ClosureError(f"corpus {label} contains a non-object entry")
        path = row["path"]
        expected_sha, expected_count = expected[path]
        if row.get("sha256") != expected_sha or row.get("row_count") != expected_count:
            raise ClosureError(f"corpus {label} pin drifted for {path}")


def load_source() -> dict:
    """Load the source snapshot only when its reviewed bytes still match."""

    try:
        raw = SOURCE_PATH.read_bytes()
        if _sha256(raw) != SOURCE_SHA256:
            raise ClosureError(
                "DE closure source bytes changed; review and re-pin the denominator"
            )
        source = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        raise ClosureError(f"cannot read the DE closure source: {exc}") from exc
    if not isinstance(source, dict):
        raise ClosureError("DE closure source must contain an object")
    return source


def _row_index(corpus: dict) -> tuple[dict[str, dict], dict[str, list[str]]]:
    raw_rows = corpus.get("rows")
    if not isinstance(raw_rows, list) or not raw_rows:
        raise ClosureError("corpus rows must be a non-empty array")
    citation_paths = [
        row.get("citation_path") for row in raw_rows if isinstance(row, dict)
    ]
    if citation_paths != sorted(set(citation_paths)):
        raise ClosureError("corpus rows must have unique, sorted citation paths")

    rows: dict[str, dict] = {}
    children: dict[str, list[str]] = defaultdict(list)
    provision_pins = {row["path"]: row["sha256"] for row in corpus["provision_sources"]}
    for row in raw_rows:
        if not isinstance(row, dict):
            raise ClosureError("corpus rows contains a non-object entry")
        citation_path = _require_nonempty(
            row.get("citation_path"), "corpus row citation_path"
        )
        if not citation_path.startswith("de/"):
            raise ClosureError(f"non-DE citation path in snapshot: {citation_path}")
        _require_nonempty(row.get("record_id"), f"{citation_path} record_id")
        if not isinstance(row.get("line_number"), int) or row["line_number"] < 1:
            raise ClosureError(f"{citation_path} has an invalid line_number")
        provision_file = _require_nonempty(
            row.get("provision_file"), f"{citation_path} provision_file"
        )
        if provision_file not in provision_pins:
            raise ClosureError(f"{citation_path} names an unpinned provision file")
        if row.get("provision_file_sha256") != provision_pins[provision_file]:
            raise ClosureError(f"{citation_path} provision-file sha drifted")
        _require_hash(row.get("row_sha256"), f"{citation_path} row_sha256")
        _require_hash(row.get("source_sha256"), f"{citation_path} source_sha256")
        body_sha = row.get("body_sha256")
        body_length = row.get("body_length")
        if body_sha is not None:
            _require_hash(body_sha, f"{citation_path} body_sha256")
        if not isinstance(body_length, int) or body_length < 0:
            raise ClosureError(f"{citation_path} has an invalid body_length")
        if (body_length == 0) != (body_sha is None):
            raise ClosureError(
                f"{citation_path} body length/hash presence does not conserve"
            )
        parent = row.get("parent_citation_path")
        if parent is not None:
            _require_nonempty(parent, f"{citation_path} parent_citation_path")
            children[parent].append(citation_path)
        rows[citation_path] = row

    for parent, child_paths in children.items():
        if parent not in rows:
            raise ClosureError(f"snapshot child refers to absent parent {parent!r}")
        if child_paths != sorted(set(child_paths)):
            raise ClosureError(f"children of {parent!r} must be unique and sorted")
    return rows, children


def _descendants(root: str, children: dict[str, list[str]]) -> list[str]:
    reached: set[str] = set()
    stack = list(children.get(root, ()))
    while stack:
        citation = stack.pop()
        if citation in reached:
            continue
        reached.add(citation)
        stack.extend(children.get(citation, ()))
    return sorted(reached)


def _validate_module_catalog(source: dict, rows: dict[str, dict]) -> dict[str, dict]:
    rulespec = source.get("rulespec")
    if not isinstance(rulespec, dict):
        raise ClosureError("rulespec snapshot must be an object")
    if (
        rulespec.get("repository") != "TheAxiomFoundation/rulespec-de"
        or rulespec.get("observed_main_commit") != RULESPEC_COMMIT
        or rulespec.get("claim_mode") != "attested"
    ):
        raise ClosureError("DE RuleSpec repository pin drifted")
    modules = rulespec.get("modules")
    if not isinstance(modules, list):
        raise ClosureError("rulespec modules must be an array")
    citations = [row.get("citation_path") for row in modules if isinstance(row, dict)]
    expected_citations = sorted(
        {citation for values in PROGRAM_SOURCE_PATHS.values() for citation in values}
    )
    if citations != expected_citations:
        raise ClosureError("rulespec module citation set or order drifted")
    indexed: dict[str, dict] = {}
    for module in modules:
        if not isinstance(module, dict):
            raise ClosureError("rulespec modules contains a non-object entry")
        citation = module["citation_path"]
        if citation not in rows:
            raise ClosureError(
                f"RuleSpec module citation is absent from corpus: {citation}"
            )
        classification = module.get("classification")
        signature_state = module.get("signature_state")
        if module.get("claim_mode") != "attested":
            raise ClosureError(f"{citation} module observation must be attested")
        if classification not in CLASSIFICATIONS - {"excluded"}:
            raise ClosureError(f"{citation} has invalid module classification")
        if signature_state not in SIGNATURE_STATES:
            raise ClosureError(f"{citation} has invalid signature_state")
        _require_nonempty(module.get("reason"), f"{citation} module reason")
        if classification == "encoded" and signature_state == "not_applicable":
            raise ClosureError(
                f"encoded module {citation} cannot waive signature state"
            )
        if classification == "pending" and signature_state == "signed":
            raise ClosureError(f"pending module {citation} cannot be signed")
        artifact = module.get("artifact")
        if signature_state == "signed":
            if not isinstance(artifact, dict):
                raise ClosureError(f"signed module {citation} lacks artifact pins")
            if artifact.get("commit") != RULESPEC_COMMIT:
                raise ClosureError(f"signed module {citation} is not pinned to main")
            _require_nonempty(artifact.get("path"), f"{citation} artifact path")
            _require_hash(artifact.get("sha256"), f"{citation} artifact sha256")
            _require_nonempty(
                artifact.get("manifest_path"), f"{citation} manifest path"
            )
            _require_hash(
                artifact.get("manifest_sha256"), f"{citation} manifest sha256"
            )
        elif artifact is not None:
            if not isinstance(artifact, dict):
                raise ClosureError(f"{citation} artifact pin must be an object")
            _require_nonempty(artifact.get("ref"), f"{citation} artifact ref")
            _require_nonempty(artifact.get("path"), f"{citation} artifact path")
            _require_hash(artifact.get("sha256"), f"{citation} artifact sha256")
        indexed[citation] = module

    estg = indexed[ESTG_66]
    if (
        estg.get("classification") != "encoded"
        or estg.get("signature_state") != "signed"
    ):
        raise ClosureError(
            "EStG 66 must be encoded and signed on the pinned main commit "
            "(rulespec-de PR #42, 2026-08-19); the pre-signing pending state "
            "is no longer valid"
        )
    return indexed


def _validate_evidence_root(
    evidence: dict,
    rows: dict[str, dict],
    children: dict[str, list[str]],
) -> dict:
    citation = evidence.get("citation_path")
    evidence_contracts = {
        STEFEG_ROOT: (STEFEG_CONTENT, ESTG_66, "SteFeG"),
        KINDRG_CONTEXT_ROOT: (
            f"{KINDRG_CONTEXT_ROOT}/document-1", "de/statute/bgb", "KindRG"
        ),
    }
    if citation not in evidence_contracts:
        raise ClosureError(f"unexpected DE evidence root {citation!r}")
    content_path, expected_target, label = evidence_contracts[citation]
    if citation not in rows:
        raise ClosureError(f"evidence root does not resolve exactly: {citation}")
    if evidence.get("resolution") != "self_and_descendants":
        raise ClosureError(f"{label} evidence must resolve by parent-linked descendants")
    _require_nonempty(evidence.get("reason"), f"{label} evidence reason")
    descendants = _descendants(citation, children)
    if descendants != [content_path]:
        raise ClosureError(f"{label} evidence descendant denominator drifted")
    child = rows[content_path]
    if child.get("body_length", 0) <= 0 or child.get("body_sha256") is None:
        raise ClosureError(f"{label} evidence child has no content-bearing body")
    targets = rows[citation].get("amendment_targets")
    if not isinstance(targets, list) or targets != sorted(set(targets)):
        raise ClosureError(f"{label} amendment targets must be unique and sorted")
    if expected_target not in targets:
        target_label = "EStG 66" if citation == STEFEG_ROOT else "BGB"
        raise ClosureError(f"{label} evidence does not target {target_label}")
    return {
        "citation_path": citation,
        "classification": "evidence",
        "classification_claim_mode": "attested",
        "reason": evidence["reason"],
        "resolution": "self_and_descendants",
        "resolution_claim_mode": "computed",
        "resolved_citation_paths": [citation, *descendants],
        "content_sha256": child["body_sha256"],
        "source_sha256": child["source_sha256"],
    }


def _validate_boundaries(
    program: str,
    raw_boundaries: object,
    rows: dict[str, dict],
) -> list[dict]:
    if not isinstance(raw_boundaries, list):
        raise ClosureError(f"{program}: boundaries must be an array")
    inputs = [row.get("input") for row in raw_boundaries if isinstance(row, dict)]
    if inputs != sorted(set(inputs)):
        raise ClosureError(f"{program}: boundary inputs must be unique and sorted")
    if program == "de/kindergeld":
        citations = tuple(
            row.get("citation_path") for row in raw_boundaries if isinstance(row, dict)
        )
        if citations != KINDERGELD_BOUNDARIES:
            raise ClosureError("Kindergeld boundary citation denominator drifted")
    rendered = []
    for boundary in raw_boundaries:
        if not isinstance(boundary, dict):
            raise ClosureError(f"{program}: boundary contains a non-object entry")
        classification = boundary.get("classification")
        if classification not in {
            "excluded-with-reason",
            "open-law-derived-dependency",
        }:
            raise ClosureError(
                f"{program}: boundary classification must be "
                "excluded-with-reason or open-law-derived-dependency"
            )
        if (
            classification == "open-law-derived-dependency"
            and boundary.get("leaf_kind") != "law_derived"
        ):
            raise ClosureError(
                f"{program}: an open law-derived dependency must carry "
                "leaf_kind: law_derived (CERTIFIED.md v3)"
            )
        if boundary.get("assignment_required") is not True:
            raise ClosureError(
                f"{program}: every boundary input must require assignment"
            )
        _require_nonempty(boundary.get("input"), f"{program} boundary input")
        _require_nonempty(boundary.get("reason"), f"{program} boundary reason")
        citation = boundary.get("citation_path")
        if citation is not None and citation not in rows:
            raise ClosureError(
                f"{program}: boundary citation does not resolve exactly: {citation}"
            )
        if citation is None:
            _require_nonempty(boundary.get("basis"), f"{program} boundary basis")
        rendered.append(
            {
                "assignment_required": True,
                "basis": boundary.get("basis"),
                "citation_path": citation,
                "claim_mode": "attested",
                "classification": classification,
                **(
                    {"leaf_kind": boundary["leaf_kind"]}
                    if classification == "open-law-derived-dependency"
                    else {}
                ),
                "input": boundary["input"],
                "reason": boundary["reason"],
            }
        )
    return rendered


def build(source: dict) -> dict:
    """Validate the pinned denominator and compute per-program source closure."""

    if source.get("schema") != SOURCE_SCHEMA:
        raise ClosureError("unexpected DE closure source schema")
    if source.get("jurisdiction") != "de" or source.get("period") != "2025":
        raise ClosureError("DE closure jurisdiction or period drifted")
    if source.get("resolution") != RESOLUTION_PROTOCOL:
        raise ClosureError("DE citation resolution protocol drifted")

    corpus = source.get("corpus")
    if not isinstance(corpus, dict):
        raise ClosureError("corpus snapshot must be an object")
    if (
        corpus.get("repository") != "TheAxiomFoundation/axiom-corpus"
        or corpus.get("commit") != CORPUS_COMMIT
        or corpus.get("release") != RELEASE
        or corpus.get("release_content_sha256") != RELEASE_CONTENT_SHA256
        or corpus.get("release_selector_sha256") != RELEASE_SELECTOR_SHA256
    ):
        raise ClosureError("DE corpus release pin drifted")
    _validate_pinned_files(
        corpus.get("inventories"), EXPECTED_INVENTORIES, "inventories"
    )
    _validate_pinned_files(
        corpus.get("provision_sources"),
        EXPECTED_PROVISION_SOURCES,
        "provision sources",
    )
    rows, children = _row_index(corpus)
    modules = _validate_module_catalog(source, rows)

    raw_programs = source.get("programs")
    if not isinstance(raw_programs, dict) or set(raw_programs) != set(
        PROGRAM_ROOT_NODES
    ):
        raise ClosureError("DE program declaration set drifted")
    programs: dict[str, dict] = {}
    all_pending: set[str] = set()
    all_signature_pending: set[str] = set()
    for program in sorted(PROGRAM_ROOT_NODES):
        declaration = raw_programs[program]
        if not isinstance(declaration, dict):
            raise ClosureError(f"{program}: declaration must be an object")
        if declaration.get("claim_mode") != "attested":
            raise ClosureError(f"{program}: subgraph declaration must be attested")
        root_nodes = declaration.get("root_nodes")
        if root_nodes != list(PROGRAM_ROOT_NODES[program]):
            raise ClosureError(f"{program}: root node denominator drifted")
        raw_sources = declaration.get("declared_sources")
        if not isinstance(raw_sources, list):
            raise ClosureError(f"{program}: declared_sources must be an array")
        source_paths = tuple(
            row.get("citation_path") for row in raw_sources if isinstance(row, dict)
        )
        if source_paths != PROGRAM_SOURCE_PATHS[program]:
            raise ClosureError(f"{program}: declared citation root set drifted")
        source_rows = []
        for declared in raw_sources:
            if not isinstance(declared, dict):
                raise ClosureError(f"{program}: declared source must be an object")
            citation = declared["citation_path"]
            if citation not in rows:
                raise ClosureError(
                    f"{program}: source citation does not resolve exactly: {citation}"
                )
            role = _require_nonempty(
                declared.get("role"), f"{program} source role for {citation}"
            )
            module = modules[citation]
            state = (
                "encoded_pending_signature"
                if module["classification"] == "encoded"
                and module["signature_state"] == "pending"
                else module["classification"]
            )
            source_rows.append(
                {
                    "citation_path": citation,
                    "claim_mode": "attested",
                    "classification": module["classification"],
                    "reason": module["reason"],
                    "role": role,
                    "signature_state": module["signature_state"],
                    "state": state,
                }
            )
        raw_evidence = declaration.get("evidence_roots")
        if not isinstance(raw_evidence, list):
            raise ClosureError(f"{program}: evidence_roots must be an array")
        evidence_paths = tuple(
            row.get("citation_path") for row in raw_evidence if isinstance(row, dict)
        )
        if evidence_paths != PROGRAM_EVIDENCE_ROOTS[program]:
            raise ClosureError(f"{program}: evidence root set drifted")
        evidence_rows = [
            _validate_evidence_root(evidence, rows, children)
            for evidence in raw_evidence
        ]
        boundaries = _validate_boundaries(program, declaration.get("boundaries"), rows)

        pending = sorted(
            row["citation_path"]
            for row in source_rows
            if row["classification"] == "pending"
        )
        signature_pending = sorted(
            row["citation_path"]
            for row in source_rows
            if row["signature_state"] == "pending"
        )
        all_pending.update(pending)
        all_signature_pending.update(signature_pending)
        status_counts = Counter(row["classification"] for row in source_rows)
        open_dependencies = [
            row
            for row in boundaries
            if row["classification"] == "open-law-derived-dependency"
        ]
        status_counts["excluded"] += len(boundaries) - len(open_dependencies)
        status_counts["open_dependency"] += len(open_dependencies)
        status_counts["evidence"] += len(evidence_rows)
        signature_counts = Counter(row["signature_state"] for row in source_rows)
        source_closed = not pending
        citation_paths = sorted(
            {
                *(row["citation_path"] for row in source_rows),
                *(
                    citation
                    for evidence in evidence_rows
                    for citation in evidence["resolved_citation_paths"]
                ),
                *(
                    boundary["citation_path"]
                    for boundary in boundaries
                    if boundary["citation_path"] is not None
                ),
            }
        )
        citation_roots = {
            *(row["citation_path"] for row in source_rows),
            *(row["citation_path"] for row in evidence_rows),
            *(
                boundary["citation_path"]
                for boundary in boundaries
                if boundary["citation_path"] is not None
            ),
        }
        # CERTIFIED.md v3: exact-path spine resolution is necessary, never
        # sufficient. The DE closure declares no subordinate-instrument
        # frontier and no typed-leaf dependency ledger, so the v3 word
        # ``closed`` is false for every program until a central-validated
        # ledger exists; the exact-path result survives as ``spine_closed``.
        v3_requirements = [
            _REQUIREMENT_FRONTIER,
            _REQUIREMENT_DEPENDENCY,
        ]
        programs[program] = {
            "blockers": [
                f"{row['citation_path']}: {row['reason']}"
                for row in source_rows
                if row["classification"] == "pending"
            ]
            + v3_requirements
            + [
                f"{row['citation_path']}: {row['input']} is an open "
                "law-derived dependency (CERTIFIED.md v3)"
                for row in open_dependencies
            ],
            "boundaries": boundaries,
            "boundary_count": len(boundaries),
            "by_signature_state": {
                name: signature_counts[name]
                for name in ("signed", "pending", "not_applicable")
            },
            "by_status": {
                name: status_counts[name]
                for name in (
                    "encoded",
                    "excluded",
                    "evidence",
                    "pending",
                    "open_dependency",
                )
            },
            "citation_root_count": len(citation_roots),
            "citation_paths": citation_paths,
            "closed": False,
            "closed_claim_mode": "computed",
            "closed_requirements": v3_requirements,
            "closure_status": "open",
            "spine_closed": source_closed,
            "spine_closed_claim_mode": "computed",
            "declared_sources": source_rows,
            "evidence_roots": evidence_rows,
            "pending_citations": pending,
            "root_node_count": len(root_nodes),
            "root_nodes": root_nodes,
            "signature_blockers": [
                f"{citation}: signed RuleSpec artifact has not landed"
                for citation in signature_pending
            ],
            "signature_pending_citations": signature_pending,
            "subgraph_sha256": _canonical_sha256(
                {
                    "boundaries": boundaries,
                    "corpus_release_content_sha256": RELEASE_CONTENT_SHA256,
                    "declared_sources": source_rows,
                    "evidence_roots": evidence_rows,
                    "resolution": RESOLUTION_PROTOCOL,
                    "root_nodes": root_nodes,
                }
            ),
            "unresolved_sources": pending,
        }

    return {
        "schema": SUMMARY_SCHEMA,
        "jurisdiction": "de",
        "period": "2025",
        "closed": False,
        "closed_claim_mode": "computed",
        "spine_closed": all(row["spine_closed"] for row in programs.values()),
        "claim_modes": {
            "attested": (
                "corpus and RuleSpec pins, module observations, and declared "
                "subgraph boundaries"
            ),
            "computed": (
                "exact citation resolution, source-closure verdicts, pending "
                "sets, counts, and digests"
            ),
        },
        "corpus_commit": CORPUS_COMMIT,
        "corpus_release": RELEASE,
        "corpus_release_content_sha256": RELEASE_CONTENT_SHA256,
        "pending_citations": sorted(all_pending),
        "programs": programs,
        "resolution": {
            **RESOLUTION_PROTOCOL,
            "sha256": _canonical_sha256(RESOLUTION_PROTOCOL),
        },
        "rulespec_commit": RULESPEC_COMMIT,
        "signature_pending_citations": sorted(all_signature_pending),
        "source": {
            "artifact": str(SOURCE_PATH.relative_to(REPO_ROOT)),
            "sha256": _sha256(SOURCE_PATH.read_bytes()),
        },
    }


def _render(value: dict) -> str:
    return json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    try:
        summary = build(load_source())
    except (OSError, json.JSONDecodeError, ClosureError) as exc:
        print(f"DE closure ERROR: {exc}", file=sys.stderr)
        return 1
    rendered = _render(summary)
    if args.check:
        if not SUMMARY_PATH.exists() or SUMMARY_PATH.read_text() != rendered:
            print("DE closure summary drifted", file=sys.stderr)
            return 1
        print("DE closure summary up to date")
        return 0
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    SUMMARY_PATH.write_text(rendered)
    print(f"wrote {SUMMARY_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
