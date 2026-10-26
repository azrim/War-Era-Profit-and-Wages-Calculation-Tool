"""v0.27 readiness probe.

v0.27 (26/10/2026 ~14:00 UTC) removes regional bonuses (deposits off, strategic
resources no longer boost production, country specialisation and party ethics
gone), replaces the job market with NPC employees, and rewrites the region map
(726 -> 742 regions, many renamed). This script answers two questions:

  1. What does the API look like now? (run with --api after the update)
  2. Did any of my companies change item, region or upgrade level?
     (--snapshot before now, --snapshot after once the update is live)

Usage:
  python probe_v027.py --snapshot before
  python probe_v027.py --api
  python probe_v027.py --snapshot after
"""
import argparse
import json
import os
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://api2.warera.io"
OWNER = "6a88123605843a89895f21ef"  # Hearthaka
SNAP_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "snapshots")


def token():
    return open(os.path.expanduser("~/.config/warera/api_key")).read().strip()


def api(path, payload, tok):
    url = f"{BASE}/trpc/{path}?input=" + urllib.parse.quote(json.dumps(payload))
    req = urllib.request.Request(url, headers={"X-Api-Key": tok, "User-Agent": "curl/8"})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            return 200, json.loads(r.read().decode())["result"]["data"]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:160]
    except Exception as e:
        return -1, f"{type(e).__name__}: {e}"


def companies(tok):
    st, body = api("company.getCompanies", {"userId": OWNER, "perPage": 50}, tok)
    if st != 200:
        return []
    out = []
    for cid in body["items"]:
        st, c = api("company.getById", {"companyId": cid}, tok)
        if st == 200:
            out.append({
                "name": c.get("name"),
                "itemCode": c.get("itemCode"),
                "region": c.get("region"),
                "upgrades": c.get("activeUpgradeLevels"),
                "workerCount": c.get("workerCount"),
            })
    return out


def snapshot(kind, tok):
    os.makedirs(SNAP_DIR, exist_ok=True)
    path = os.path.join(SNAP_DIR, f"v027_{kind}.json")
    data = {"companies": companies(tok)}
    st, regions = api("region.getRegionsObject", {}, tok)
    if st == 200:
        data["regions"] = sorted(
            (r.get("name"), r.get("_id")) for r in
            (regions.values() if isinstance(regions, dict) else regions))
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=1)
    print(f"snapshot {kind}: {len(data['companies'])} pabrik, "
          f"{len(data.get('regions', []))} region → {path}")

    other = os.path.join(SNAP_DIR, "v027_before.json" if kind == "after" else "v027_after.json")
    if os.path.exists(other):
        before = json.load(open(os.path.join(SNAP_DIR, "v027_before.json"), encoding="utf-8"))
        after = json.load(open(os.path.join(SNAP_DIR, "v027_after.json"), encoding="utf-8"))
        names_before = {n for n, _ in before.get("regions", [])}
        names_after = {n for n, _ in after.get("regions", [])}
        print(f"region baru: {len(names_after - names_before)}, hilang: {len(names_before - names_after)}")
        for c_b, c_a in zip(before["companies"], after["companies"]):
            if c_b["itemCode"] != c_a["itemCode"] or c_b["region"] != c_a["region"]:
                print(f"  berubah: {c_b['name']} {c_b['itemCode']}@{c_b['region']} → "
                      f"{c_a['itemCode']}@{c_a['region']}")


def api_surface(tok):
    spec = json.loads(urllib.request.urlopen(urllib.request.Request(
        f"{BASE}/openapi.json", headers={"User-Agent": "curl/8"}), timeout=25).read())
    paths = sorted(spec["paths"])
    for kw in ("employee", "worker", "company", "manager", "skill", "region", "country"):
        hits = [p for p in paths if kw in p.lower()]
        print(f"\n== {kw} ({len(hits)}) ==")
        for p in hits:
            print("  ", p)

    print("\n== company object fields ==")
    cs = companies(tok)
    if cs:
        st, c = api("company.getById", {"companyId": api(
            "company.getCompanies", {"userId": OWNER, "perPage": 50}, tok)[1]["items"][0]}, tok)
        print("  ", sorted(c))

    print("\n== gameConfig company/worker/employee/upgrades ==")
    st, cfg = api("gameConfig.getGameConfig", {"json": None}, tok)
    if st == 200:
        for key in ("company", "worker", "employee"):
            if key in cfg:
                print(f"  {key}: {json.dumps(cfg[key])[:400]}")
        br = (cfg.get("upgradesConfig") or {}).get("breakRoom") or {}
        print(f"  breakRoom levels: {json.dumps(br.get('levels'))[:400]}")

    print("\n== region/country fields ==")
    st, regions = api("region.getRegionsObject", {}, tok)
    if st == 200:
        first = list(regions.values())[0] if isinstance(regions, dict) else regions[0]
        print("  region:", sorted(first))
    st, countries = api("country.getAllCountries", {"json": None}, tok)
    if st == 200 and countries:
        print("  country:", sorted(countries[0]))

    print("\n== company.getProductionBonus ==")
    ids = api("company.getCompanies", {"userId": OWNER, "perPage": 50}, tok)[1]["items"]
    print("  ", api("company.getProductionBonus", {"companyId": ids[0]}, tok))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", choices=["before", "after"])
    ap.add_argument("--api", action="store_true", help="dump the post-update API surface")
    args = ap.parse_args()
    tok = token()
    if args.snapshot:
        snapshot(args.snapshot, tok)
    if args.api:
        api_surface(tok)
    if not args.snapshot and not args.api:
        ap.print_help()
