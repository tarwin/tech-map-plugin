"""Collect the inventory for every provider listed in tech-map.config.json, then rebuild data/inv.json.

Usage: python3 -I scripts/collect.py [provider ...]     (default: all configured providers)
Each provider runs on its own; one failing (expired login, missing CLI) doesn't stop the others."""
import json, os, subprocess, sys

here = os.path.dirname(os.path.abspath(__file__))
root = os.path.dirname(here)
cfg = json.load(open(os.path.join(root, "tech-map.config.json")))
wanted = sys.argv[1:] or list(cfg.get("providers", {}))
RUNNERS = {
    "aws": ["bash", os.path.join(here, "providers", "aws.sh")],
    **{p: [sys.executable, "-I", os.path.join(here, "providers", f"{p}.py")] for p in ("gcp", "azure", "cloudflare", "vercel", "netlify")},
}
failed = []
for p in wanted:
    if p not in cfg.get("providers", {}):
        print(f"{p}: not in tech-map.config.json providers; skipping"); continue
    if p not in RUNNERS:
        print(f"{p}: no collector (add scripts/providers/{p}.py following common.py)"); failed.append(p); continue
    print(f"\n######## {p}")
    if subprocess.run(RUNNERS[p], cwd=root).returncode != 0:
        failed.append(p)
subprocess.run([sys.executable, "-I", os.path.join(here, "inv.py")], cwd=root, check=True)
if failed:
    sys.exit(f"\ncollection failed or incomplete for: {', '.join(failed)}")
