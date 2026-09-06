import json
PIN7 = "c13cdf7dda5948e7a86ff0c317872f93743a2084"
PINCA = "edc62ea566a617cf5b9c3b620f712b73c6767c94"
WIP = "6056d4ad6c38"
for s in ["al","sc","nc","ma","fl","ga","ny","ca"]:
    path = f"dashboard/public/data/axiom-policyengine-{s}-snap-ecps.json"
    d = json.load(open(path))
    rs = d["provenance"]["rulespecs"]
    changed = False
    for entry in rs:
        if entry["repo"].endswith("rulespec-us") and entry.get("sha", "").startswith(WIP):
            entry["sha"] = PINCA if s == "ca" else PIN7
            changed = True
    if changed:
        open(path, "w").write(json.dumps(d, indent=2, sort_keys=True) + "\n")
    print(s, "restamped" if changed else "already-correct", rs[0]["sha"][:12])
