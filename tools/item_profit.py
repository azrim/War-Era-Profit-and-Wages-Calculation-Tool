"""WarEra: which producible item is most profitable right now.

Market-wide ranking: for every tradable product with a recipe, walk the bid book
(sell output) and ask book (buy inputs) at the newest stored snapshot.
Ranked by margin per production point; bid depth shows how much is sellable.
"""
import json, os, sqlite3, urllib.parse, urllib.request

TOK = open(os.path.expanduser("~/.config/warera/api_key")).read().strip()
BASE = "https://api2.warera.io/trpc"
DB = "data/warera_market.sqlite3"
OWNER = os.environ.get("OWNER_UID", "6a88123605843a89895f21ef")  # Hearthaka


def call(path, payload, timeout=25):
    url = BASE + path + "?input=" + urllib.parse.quote(json.dumps(payload))
    req = urllib.request.Request(url, headers={"X-Api-Key": TOK, "User-Agent": "curl/8"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:200]
    except Exception as e:
        return -1, str(e)[:200]


def walk(levels, qty):
    left, value = qty, 0.0
    for price, avail in levels:
        take = min(left, avail)
        value += take * price
        left -= take
        if left <= 1e-12:
            break
    return value, qty - left


cfg = call("/gameConfig.getGameConfig", {"json": None})[1]["result"]["data"]["items"]

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
for code, meta in cfg.items():
    pp = meta.get("productionPoints")
    if meta.get("type") != "product" or meta.get("isTradable") is not True or not pp:
        continue
    bid_levels = books.get((code, "bid"), [])
    if not bid_levels:
        continue
    # value one production point's worth of output (1/pp units)
    units = 1.0 / pp
    rev, filled = walk(bid_levels, units)   # walk returns (value, FILLED)
    if filled < units - 1e-9:  # bid book cannot even absorb 1 PP of output
        continue
    cost, ok = 0.0, True
    for need, qty in (meta.get("productionNeeds") or {}).items():
        want = qty * units
        c2, filled = walk(books.get((need, "ask"), []), want)
        if filled < want - 1e-9:  # ask book cannot supply the recipe
            ok = False
            break
        cost += c2
    if not ok:
        continue
    margin = rev - cost  # rev/cost are for `units` output = 1 PP worth → margin IS per-PP
    depth = sum(q for _p, q in bid_levels)
    rows.append((code, pp, round(rev / units, 4), round(cost / units, 4),
                 round(margin, 5), round(depth)))

rows.sort(key=lambda r: -r[4])
print(f"snapshot {snap_at} · margin per production point (jual di bid, beli di ask, 1 PP output)\n")
print(f"{'item':<13}{'PP':>4}{'jual':>9}{'bahan':>9}{'margin/PP':>11}{'depth bid':>11}")
for r in rows:
    print(f"{r[0]:<13}{r[1]:>4}{r[2]:>9}{r[3]:>9}{r[4]:>11}{r[5]:>11}")

# Hearthaka check
st, body = call("/company.getCompanies", {"userId": OWNER, "perPage": 50})
if st == 200 and isinstance(body, dict):
    ids = body["result"]["data"]["items"]
    comps = []
    for i in ids:
        st2, c = call("/company.getById", {"companyId": i})
        if st2 == 200 and isinstance(c, dict):
            comps.append(c["result"]["data"])
    ok = sum(1 for c in comps if c.get("user") == OWNER)
    print(f"\nHearthaka ({OWNER}): {ok}/{len(ids)} pabrik terverifikasi owner")