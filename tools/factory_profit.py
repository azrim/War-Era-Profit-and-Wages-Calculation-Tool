"""Factory profitability with real order-book walking.

For each of his companies: walk the bid book to sell one day of output, walk the
ask book to buy one day of inputs, report net per day and per production point.
Read-only; uses the newest stored order-book snapshot.
"""
import json, os, sqlite3, urllib.parse, urllib.request

TOK = open(os.path.expanduser("~/.config/warera/api_key")).read().strip()
BASE = "https://api2.warera.io/trpc"
UID = "69c569fb726ef783dffa1faf"
DB = "data/warera_market.sqlite3"
INPUT_SIDE = os.environ.get("INPUT_SIDE", "ask")  # ask = beli di pasar, bid = opportunity cost


def call(path, payload=None, timeout=30):
    url = BASE + path
    if payload is not None:
        url += "?input=" + urllib.parse.quote(json.dumps(payload))
    req = urllib.request.Request(url, headers={"X-Api-Key": TOK, "User-Agent": "curl/8"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())["result"]["data"]


def walk(levels, qty):
    """Spend qty against (price, quantity) levels; return (value, filled)."""
    left, value = qty, 0.0
    for price, avail in levels:
        take = min(left, avail)
        value += take * price
        left -= take
        if left <= 1e-12:
            break
    return value, qty - left


cfg = call("/gameConfig.getGameConfig", {"json": None})["items"]
# company.getCompanies must be called with the BARE object: wrapped in {"json": ...}
# the userId filter is silently ignored and you get the global list instead.
ids = call("/company.getCompanies", {"userId": UID, "perPage": 50})["items"]
companies = [call("/company.getById", {"companyId": cid}) for cid in ids]
assert all(c.get("user") == UID for c in companies), "filter ignored: got other players' companies"
print(f"{len(companies)} pabrik milik {UID}")

con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
newest = con.execute("select max(observed_at_epoch) from order_book_observations").fetchone()[0]
books = {}
for item, side, price, qty in con.execute("""
        select o.item_code, l.side, l.price, l.quantity
        from order_book_levels l join order_book_observations o on o.id = l.observation_id
        where o.observed_at_epoch = ?
        order by o.item_code, l.side, l.level_position""", (newest,)):
    books.setdefault((item, side), []).append((price, qty))
snap_at = con.execute("select observed_at from order_book_observations where observed_at_epoch=? limit 1", (newest,)).fetchone()[0]

rows = []
for c in companies:
    code, pp = c["itemCode"], cfg.get(c["itemCode"], {}).get("productionPoints")
    needs = cfg.get(code, {}).get("productionNeeds") or {}
    units = c["production"] / pp if pp else 0.0
    rev, filled = walk(books.get((code, "bid"), []), units)
    cost = 0.0
    for need, qty in needs.items():
        c2, _f = walk(books.get((need, INPUT_SIDE), []), qty * units)
        cost += c2
    net = rev - cost
    rows.append(dict(item=code, name=c["name"], pp=pp, units=units, ppday=c["production"],
                     rev=rev, cost=cost, net=net, per_pp=net / c["production"] if c["production"] else 0,
                     filled=filled, want=units, workers=c.get("workerCount")))

rows.sort(key=lambda r: -r["net"])
print(f"snapshot {snap_at}  (bid untuk jual output, ask untuk beli input)\n")
print(f"{'item':<11}{'pabrik':<20}{'PP/hari':>8}{'unit/h':>8}{'omzet/h':>9}{'bahan/h':>9}{'net/h':>9}{'net/PP':>9}{'isi bid':>9}")
for r in rows:
    print(f"{r['item']:<11}{(r['name'] or '')[:19]:<20}{r['ppday']:>8.1f}{r['units']:>8.2f}{r['rev']:>9.2f}"
          f"{r['cost']:>9.2f}{r['net']:>9.2f}{r['per_pp']:>9.4f}{r['filled']:>7.1f}/{r['want']:.1f}")
print(f"\ntotal net/hari: {sum(r['net'] for r in rows):.2f}")
print(f"PP/hari total: {sum(r['ppday'] for r in rows):.1f}")
