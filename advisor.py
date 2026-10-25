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

    # company move / change-item are paid in concrete (see the comment below);
    # value it at the best ask so payback can be expressed in money.
    cbook = api(token, "tradingOrder.getTopOrders", {"itemCode": "concrete", "limit": 20})
    asks = sorted(float(o["price"]) for o in (cbook.get("sellOrders") or []))
    concrete_price = asks[0] if asks else float(prices.get("concrete", 0))

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

        # Both actions are paid in CONCRETE, not money: the game's own move and
        # change-item dialogs render `cost:{items:{concrete: company.moveCost}}`
        # / `{concrete: company.changeItemCost}` (both 5). Convert to money with
        # the concrete market price so payback means something.
        cost_move = float(cfg["company"]["moveCost"])
        cost_item = float(cfg["company"]["changeItemCost"])
        options = []
        if move is not None:
            options.append({
                "label": f"pindah ke {move['Region Name']}",
                "concrete": cost_move,
                "gain": (float(move["Profit per PP"]) - profit_pp) * pp_day,
            })
        if switch is not None:
            options.append({
                "label": f"ganti produk jadi {switch[0]} (tetap di {rname})",
                "concrete": cost_item,
                "gain": (switch[1] - profit_pp) * pp_day,
            })
        if best_any["Bonus Source"] != item or best_any["Region Name"] != rname:
            options.append({
                "label": f"pindah ke {best_any['Region Name']} + ganti produk jadi {best_any['Bonus Source']}",
                "concrete": cost_move + cost_item,
                "gain": (float(best_any["Profit per PP"]) - profit_pp) * pp_day,
            })
        for o in options:
            o["cost"] = o["concrete"] * concrete_price
            o["payback"] = (o["cost"] / o["gain"]) if o["gain"] > 0 else float("inf")

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
            "options": options,
        })

    rows.sort(key=lambda r: -r["per_day"])
    total = sum(r["per_day"] for r in rows)

    def n(x):
        """Indonesian decimal comma, one decimal place."""
        return f"{x:.1f}".replace(".", ",")

    best_item = str(by_product.iloc[0]["Bonus Source"])
    best_pp = float(by_product.iloc[0]["Profit per PP"])

    keep, change = [], []
    for r in rows:
        viable = [o for o in r["options"] if o["gain"] > 0.05]
        if viable:
            change.append((r, max(viable, key=lambda o: o["gain"])))
        else:
            keep.append(r)
    change.sort(key=lambda t: -t[1]["gain"])
    after = total + sum(o["gain"] for _, o in change)
    total_cost = sum(o["cost"] for _, o in change)
    total_concrete = sum(o["concrete"] for _, o in change)

    print(f"🏭 Advisor pabrik — {os.path.basename(os.path.dirname(table_path))} (harga order book)")
    print(f"Sekarang {n(total)} uang/hari dari {len(rows)} pabrik.")

    if keep:
        print(f"\n✅ Biarkan ({len(keep)})")
        for r in keep:
            print(f"• {r['company']}: {r['item']} di {r['region']} — {n(r['per_day'])}/hari")

    if change:
        print(f"\n🔧 Ubah ({len(change)} pabrik, tambah {n(sum(o['gain'] for _, o in change))}/hari)")
        for r, o in change:
            print(f"• {r['company']}: {r['item']} di {r['region']} → {o['label']}")
            print(f"   +{n(o['gain'])}/hari · balik modal {n(o['payback'])} hari")
        print(f"\nKalau semua diubah: {n(after)}/hari (naik {n((after / total - 1) * 100)}%).")
        print(f"Total biaya {total_concrete:.0f} concrete (≈ {n(total_cost)} uang @ {n(concrete_price)}/concrete).")
    else:
        print("\nTidak ada yang perlu diubah — semua pabrik sudah di produk dan region terbaik.")

    print("\n📌 Catatan")
    print(f"• Biaya: pindah {cfg['company']['moveCost']} concrete, ganti produk "
          f"{cfg['company']['changeItemCost']} concrete — tanpa uang.")

    # market absorption for the recommended product
    book = api(token, "tradingOrder.getTopOrders", {"itemCode": best_item, "limit": 100})
    bid_depth = sum(float(o.get("quantity", 0)) for o in (book.get("buyOrders") or []))
    would_make = sum(r["pp_day"] for r in rows) / (recipes[best_item]["productionPoints"] or 1)
    if would_make < bid_depth:
        print(f"• {best_item}: pembeli siap {bid_depth:.0f} unit, produksimu {n(would_make)}/hari — aman.")
    else:
        print(f"• {best_item}: produksimu {n(would_make)}/hari melebihi pembeli siap {bid_depth:.0f} — harga bisa turun.")

    best_needs = recipes.get(best_item, {}).get("productionNeeds") or {}
    for raw, qty in best_needs.items():
        ask = api(token, "tradingOrder.getTopOrders", {"itemCode": raw, "limit": 100})
        ask_depth = sum(float(o.get("quantity", 0)) for o in (ask.get("sellOrders") or []))
        need = qty * would_make
        verdict = "cukup" if need < ask_depth else "KURANG, harus cari pemasok"
        print(f"• bahan {raw}: butuh {need:.0f}/hari, dijual {ask_depth:.0f} unit — {verdict}.")

    # idle capacity and full storage are worth more than any product choice
    idle = [r for r in rows if r["workers"] < r["max_workers"]]
    if idle:
        print(f"• Pekerja kosong: {len(idle)} pabrik punya slot pekerja belum terisi "
              f"(kapasitas tambahan tanpa biaya ubah).")
    full = [r for r in rows if r["stock"] > 0.9 * r["cap"]]
    for r in full:
        print(f"• ⚠️ {r['company']}: stok {r['stock']:.0f}/{r['cap']:.0f} hampir penuh, produksi berhenti.")

    produced = {r["item"] for r in rows}
    need = {}
    for r in rows:
        for raw, qty in (recipes.get(r["item"], {}).get("productionNeeds") or {}).items():
            need[raw] = need.get(raw, 0) + qty * r["pp_day"] / recipes[r["item"]]["productionPoints"]
    bought = [f"{raw} {qty:.0f}/hari" for raw, qty in sorted(need.items(), key=lambda kv: -kv[1])
              if raw not in produced]
    if bought:
        print(f"• Semua bahan dibeli di pasar: {', '.join(bought)} — tidak ada tambang sendiri.")


if __name__ == "__main__":
    main()
