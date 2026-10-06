import subprocess, sys, yaml
rev = sys.argv[1]
files = subprocess.check_output(["git","ls-tree","--name-only",f"{rev}:comparisons"]).decode().split()
names=[]
for f in sorted(files):
    if not f.endswith(".yaml") or f.endswith(".fixtures.yaml"): continue
    c = yaml.safe_load(subprocess.check_output(["git","show",f"{rev}:comparisons/{f}"]))
    if not isinstance(c,dict) or "name" not in c: continue
    if not (c.get("runner") or {}).get("type"): continue
    if c.get("ci")=="manual": continue
    names.append(f[:-5])
print(rev, len(names), [n for n in names if "snap-qc" in n])
