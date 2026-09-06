"""Delete expired disposition entries flagged by the fresh suite merges."""
import json
import yaml

for s in ["al", "sc", "nc", "ma", "fl", "ga", "ny", "ca"]:
    suite = f"{s}-snap-ecps"
    report = json.load(open(f"dashboard/public/data/axiom-policyengine-{suite}.json"))
    expired = set(
        report["summary"].get("dispositioned", {}).get("expired_entries", [])
    )
    if not expired:
        print(f"{suite}: none expired")
        continue
    path = f"dispositions/{suite}.yaml"
    doc = yaml.safe_load(open(path))
    before = len(doc["entries"])
    doc["entries"] = [e for e in doc["entries"] if e["id"] not in expired]
    open(path, "w").write(
        yaml.safe_dump(doc, sort_keys=False, width=78, allow_unicode=True)
    )
    print(f"{suite}: pruned {before - len(doc['entries'])} of {before} entries")
