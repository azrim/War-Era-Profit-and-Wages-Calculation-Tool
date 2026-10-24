"""Company advisor: what each of your factories should produce, and where.

Reads the newest region/product table produced by AllBonusV4 (bonus per region,
profit per production point, wages) and joins it with your own companies.

The game's API is read-only, so this only recommends; the actual change happens
in-game. Region bonus applies to the region's own product (`Bonus Source` in the
table), so a company earns the bonus only when its item matches that product.

Run: python advisor.py [--owner UID] [--table reports/<date>/extracted_countries.csv]
"""
import argparse
import glob
import json
import os
import urllib.parse
import urllib.request

import pandas as pd

from AllBonusV4 import production_margin

BASE = "https://api2.warera.io/trpc"
DEFAULT_OWNER = "6a88123605843a89895f21ef"  # Hearthaka


def api(token, path, payload, timeout=30):
    url = f"{BASE}/{path}?input={urllib.parse.quote(json.dumps(payload))}"
    req = urllib.request.Request(url, headers={"X-Api-Key": token, "User-Agent": "curl/8"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())["result"]["data"]


def load_prices(token, codes):
    """Game-calculated price per item (same source the wages tool uses by default)."""
    return api(token, "itemTrading.getPrices", {"json": None})


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--owner", default=os.environ.get("OWNER_UID", DEFAULT_OWNER))
    ap.add_argument("--table", help="extracted_countries.csv (default: newest under reports/)")
    args = ap.parse_args()

    token = open(os.path.expanduser("~/.config/warera/api_key")).read().strip()

    table_path = args.table
    if not table_path:
        found = sorted(glob.glob("reports/*/extracted_countries.csv"))
        if not found:
            raise SystemExit("no report table found; run AllBonusV4.py --cli first")
        table_path = found[-1]

    df = pd.read_csv(table_path)
    df = df[df["Profit per PP"] > 0]

    # region -> its own product and profit/PP (the bonus only applies to that product)
    by_region = df.set_index("Region Name")
    # product -> best regions for that product, sorted by profit/PP
    by_product = df.sort_values("Profit per PP", ascending=False)

    company_ids = api(token, "company.getCompanies", {"userId": args.owner, "perPage": 50})["items"]
    companies = [api(token, "company.getById", {"companyId": cid}) for cid in company_ids]
    assert all(c.get("user") == args.owner for c in companies), "filter ignored: not your companies"

    cfg = api(token, "gameConfig.getGameConfig", {"json": None})
    recipes = cfg["items"]
    prices = load_prices(token, None)

    def base_margin(item):
        """Margin/PP with no regional bonus, using game prices."""
        meta = recipes.get(item) or {}
        pp = meta.get("productionPoints")
        if not pp:
            return None
        needs = meta.get("productionNeeds") or {}
        goods = prices.get(item, 0)
        return production_margin(goods, needs, lambda c: prices.get(c, 0), pp)

    rows = []
    for c in companies:
        item = c["itemCode"]
        region_id = c["region"]
        region = api(token, "region.getById", {"regionId": region_id})
        rname = region.get("name", "?")

        if rname in by_region.index:
            r = by_region.loc[rname]
            if isinstance(r, pd.DataFrame):
                r = r.iloc[0]
            bonus = float(r["Total Bonus"])
            bonus_product = r["Bonus Source"]
            profit_pp = float(r["Profit per PP"]) if item == bonus_product else base_margin(item)
            wage = float(r["Top wages after tax"])
        else:
            bonus, bonus_product, profit_pp, wage = 0.0, None, base_margin(item), 0.0

        if profit_pp is None:
            continue

        # `company.production` is NOT a rate: it is the stored production-point
        # backlog waiting to be turned into items, capped by the storage upgrade
        # (200 per level). Daily capacity comes from the automatedEngine upgrade
        # (24 PP per level), which is what a per-day figure must use.
        upgrades = cfg["upgradesConfig"]
        engine_lv = (c.get("activeUpgradeLevels") or {}).get("automatedEngine", 1)
        storage_lv = (c.get("activeUpgradeLevels") or {}).get("storage", 1)
        pp_day = upgrades["automatedEngine"]["levels"][str(engine_lv)]["stats"]["dailyProd"]
        stock = c["production"]
        cap = upgrades["storage"]["levels"][str(storage_lv)]["stats"]["maxProduction"]
        workers = c.get("workerCount", 0)
        max_workers = upgrades["breakRoom"]["levels"][
            str((c.get("activeUpgradeLevels") or {}).get("breakRoom", 1))]["stats"]["maxWorkers"]

        # 1) same item, best region that actually bonuses it
        same_item = by_product[(by_product["Bonus Source"] == item) & (by_product["Region Name"] != rname)]
        move = same_item.iloc[0] if len(same_item) else None

        # 2) same region, switch to the product the region actually bonuses
        switch = None
        if bonus_product and bonus_product != item:
            switch_pp = base_margin(bonus_product)
            if switch_pp is not None:
                switch = (bonus_product, profit_pp if False else float(by_region.loc[rname]["Profit per PP"]))

        # 3) best possible pair anywhere
        best_any = by_product.iloc[0]

        rows.append({
            "company": c.get("name", "?"),
            "item": item,
            "region": rname,
            "bonus": bonus,
            "bonus_product": bonus_product,
            "pp_day": pp_day,
            "stock": stock,
            "cap": cap,
            "workers": workers,
            "max_workers": max_workers,
            "profit_pp": profit_pp,
            "per_day": profit_pp * pp_day,
            "move_to": None if move is None else move["Region Name"],
            "move_gain_day": 0.0 if move is None else (float(move["Profit per PP"]) - profit_pp) * pp_day,
            "switch_to": None if switch is None else switch[0],
            "switch_gain_day": 0.0 if switch is None else (switch[1] - profit_pp) * pp_day,
            "best_any": f"{best_any['Bonus Source']}@{best_any['Region Name']}",
            "best_any_gain_day": (float(best_any["Profit per PP"]) - profit_pp) * pp_day,
        })

    rows.sort(key=lambda r: -r["per_day"])
    total = sum(r["per_day"] for r in rows)
    print(f"table: {table_path}")
    print(f"{len(rows)} pabrik · total profit sekarang {total:.2f}/hari\n")
    print(f"{'pabrik':<20}{'item':<11}{'region':<20}{'bonus':>6}{'profit/PP':>10}{'PP/hari':>9}{'/hari':>8}"
          f"{'stok':>9}{'pekerja':>9}  {'aksi':<34}{'delta/hari':>10}")
    for r in rows:
        actions = []
        if r["move_gain_day"] > 0.005:
            actions.append(f"pindah→{r['move_to']}")
        if r["switch_gain_day"] > 0.005:
            actions.append(f"ganti→{r['switch_to']}")
        if r["best_any_gain_day"] > 0.005:
            actions.append(f"retool→{r['best_any']}")
        action = " + ".join(actions) if actions else "biarkan"
        gain = max(r["move_gain_day"], r["switch_gain_day"], r["best_any_gain_day"], 0.0)
        flag = "" if r["bonus_product"] == r["item"] else f" (region bonus untuk {r['bonus_product']})"
        print(f"{r['company'][:19]:<20}{r['item']:<11}{r['region'][:19]:<20}{r['bonus']:>5.0f}%"
              f"{r['profit_pp']:>10.3f}{r['pp_day']:>9.0f}{r['per_day']:>8.2f}"
              f"{r['stock']:>4.0f}/{r['cap']:<4.0f}{r['workers']:>4}/{r['max_workers']:<4.0f}"
              f"  {action:<34}{gain:>10.2f}{flag}")

    # production stalls when the stored backlog hits the storage cap
    for r in rows:
        if r["stock"] > 0.9 * r["cap"]:
            print(f"⚠️ {r['company']}: stok produksi {r['stock']:.0f}/{r['cap']:.0f} hampir penuh — "
                  f"produksi berhenti sampai diambil")


    best_pp = float(by_product.iloc[0]["Profit per PP"])
    best_item = str(by_product.iloc[0]["Bonus Source"])
    print(f"\npasangan terbaik di pasar saat ini: {rows[0]['best_any']} ({best_pp:.3f}/PP)")

    # how much of that can the market absorb? profit/PP assumes you can sell.
    book = api(token, "tradingOrder.getTopOrders", {"itemCode": best_item, "limit": 100})
    bid_depth = sum(float(o.get("quantity", 0)) for o in (book.get("buyOrders") or []))
    would_make = sum(r["pp_day"] for r in rows if r["item"] != best_item) / \
        (recipes[best_item]["productionPoints"] or 1)
    print(f"kedalaman bid {best_item}: {bid_depth:.0f} unit · output jika semua pabrik diretool: "
          f"{would_make:.1f} unit/hari → {'aman' if would_make < bid_depth else 'PERINGATAN: melebihi bid, harga akan turun'}")

    # inputs must be buyable at that scale: compare daily need with what is on sale
    best_needs = recipes.get(best_item, {}).get("productionNeeds") or {}
    for raw, qty in best_needs.items():
        ask = api(token, "tradingOrder.getTopOrders", {"itemCode": raw, "limit": 100})
        ask_depth = sum(float(o.get("quantity", 0)) for o in (ask.get("sellOrders") or []))
        need = qty * would_make
        print(f"  bahan {raw}: butuh {need:.0f}/hari · dijual {ask_depth:.0f} unit → "
              f"{'cukup' if need < ask_depth else 'PERINGATAN: kebutuhan melebihi barang yang dijual'}")

    # raw-material position: what his factories consume vs what he produces himself
    produced = {r["item"] for r in rows}
    need = {}
    for r in rows:
        for raw, qty in (recipes.get(r["item"], {}).get("productionNeeds") or {}).items():
            need[raw] = need.get(raw, 0) + qty * r["pp_day"] / recipes[r["item"]]["productionPoints"]
    if need:
        print("\nbahan mentah yang dibutuhkan pabrikmu per hari:")
        for raw, qty in sorted(need.items(), key=lambda kv: -kv[1]):
            own = "diproduksi sendiri" if raw in produced else "TIDAK diproduksi sendiri — beli di pasar"
            raw_pp = float(by_product[by_product["Bonus Source"] == raw]["Profit per PP"].max() or 0)
            print(f"  {raw:<11}{qty:>8.2f}/hari  {own}  (margin tambang {raw_pp:.3f}/PP)")


if __name__ == "__main__":
    main()
