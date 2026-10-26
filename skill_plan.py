"""Skill allocation planner for the v0.27 economy.

Reads your level, skill points and companies from the API, then ranks every
allocation of those points against a money-per-day model:

  self-work PP = (2.4 x energy max / 10) x production value     (10% regen hourly)
  engine PP    = factories x automatedEngine PP/day             (free, no wage)
  employee PP  = staff x Production/4 x 24 x (1 + 2% x mgmt + extras)

Facts (gameConfig API + v0.27 article + warera.wiki): energy 100+10/lv pays for
self-work, hiring and training (10 each); production 30+3/lv; companies lv+2;
management lv+1 with +2% employee production per point (2%..22%); v0.27 removed
every regional production bonus, so margin/PP is the raw market price.

Run: python skill_plan.py [--margin 0.104] [--employees 2] [--emp-stat 2.5]
"""
import argparse
import json
import os
import urllib.parse
import urllib.request

BASE = "https://api2.warera.io/trpc"
OWNER = "6a88123605843a89895f21ef"
COSTS = {lv: lv * (lv + 1) // 2 for lv in range(11)}
ENGINE_PP = 144         # average automatedEngine output per factory per day
HOURS = 24
SKILLS = ("companies", "energy", "production", "management", "leadership")


def token():
    return open(os.path.expanduser("~/.config/warera/api_key")).read().strip()


def api(path, payload, tok):
    url = f"{BASE}/{path}?input=" + urllib.parse.quote(json.dumps(payload))
    req = urllib.request.Request(url, headers={"X-Api-Key": tok, "User-Agent": "curl/8"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode())["result"]["data"]


def evaluate(alloc, points, factories, margin, per_company, emp_stat):
    comp, energy, prod, mgmt, _lead = alloc
    cost = sum(COSTS[lv] for lv in alloc)
    if cost > points:
        return None
    working = min(min(2 + comp, 12), factories)

    pp_self = (2.4 * (100 + 10 * energy) / 10) * (30 + 3 * prod)
    pp_engine = working * ENGINE_PP
    staff = working * per_company
    pp_emp = staff * (emp_stat / 4) * HOURS * (1 + 0.02 * (mgmt + 1) + 0.25)
    return {"cost": cost, "self": pp_self, "engine": pp_engine, "emp": pp_emp,
            "money": (pp_self + pp_engine + pp_emp) * margin}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--margin", type=float, default=0.104, help="money per PP")
    ap.add_argument("--employees", type=int, default=2, help="employees per factory")
    ap.add_argument("--emp-stat", type=float, default=2.5, help="employee Production stat")
    args = ap.parse_args()

    tok = token()
    me = api("user.getUserById", {"userId": OWNER}, tok)
    lv = me["leveling"]
    factories = len(api("company.getCompanies", {"userId": OWNER, "perPage": 50}, tok)["items"])
    points = lv["totalSkillPoints"]
    comp_needed = max(0, min(10, factories - 2))   # companies value = level+2
    print(f"level {lv['level']} · {points} poin ({lv['availableSkillPoints']} belum dipakai) · "
          f"{factories} pabrik → companies minimal level {comp_needed}")

    def money(a):
        return evaluate(a, points, factories, args.margin, args.employees, args.emp_stat)

    cur = tuple((me["skills"].get(s) or {}).get("level", 0) for s in SKILLS)
    c = money(cur)
    print(f"\nbuild sekarang: {dict(zip(SKILLS, cur))} = {c['money']:.0f} uang/hari, "
          f"{c['cost']} poin, sisa {points - c['cost']}")

    best, best_money = None, -1
    from itertools import product
    for a in product(range(11), repeat=5):
        if a[0] < comp_needed:
            continue
        r = money(a)
        if r and r["money"] > best_money:
            best, best_money = a, r["money"]
    print(f"optimal       : {dict(zip(SKILLS, best))} = {best_money:.0f} uang/hari, "
          f"{money(best)['cost']} poin")
    r = money(best)
    print(f"  self-work {r['self']:.0f} PP · engine {r['engine']:.0f} PP · employee {r['emp']:.0f} PP")

    print("\nnaik 1 level dari build sekarang, diurut per poin:")
    rows = []
    for i, name in enumerate(SKILLS):
        if cur[i] >= 10:
            continue
        a = list(cur)
        a[i] += 1
        r2 = money(tuple(a))
        if not r2:
            continue
        d_pts = COSTS[a[i]] - COSTS[cur[i]]
        rows.append((name, a[i], d_pts, r2["money"] - c["money"]))
    for name, level, d_pts, gain in sorted(rows, key=lambda t: -(t[3] / t[2])):
        print(f"  {name:<11}→ {level:<2} ({d_pts:>2} poin) +{gain:6.1f} uang/hari "
              f"= {gain / d_pts:5.2f} per poin")

    selfwork = (30 + 3 * best[2]) * args.margin
    train = (1 / 4) * HOURS * (1 + 0.02 * (best[3] + 1) + 0.25) * args.margin
    print(f"\nnilai 1 sesi 10 energi: self-work {selfwork:.2f} uang · "
          f"training +{train:.2f} uang/hari (balik modal {selfwork / train:.0f} hari)")


if __name__ == "__main__":
    main()
