# tools/

Two standalone scripts kept from an earlier WarEra market-analysis attempt.

Both read the order-book SQLite store produced by
[`sandokas/warera-marketguide`](https://github.com/sandokas/warera-marketguide)
(`data/warera_market.sqlite3`), which is **not** part of this repo — point `DB`
in each file at such a store, or use them as reference logic.

* `factory_profit.py` — per-company profitability for one player's factories
  (company list from `company.getCompanies`, recipes from `gameConfig`, prices
  walked through the stored order book). Set `OWNER_UID` to the player id.
* `item_profit.py` — market-wide ranking of every producible item by margin per
  production point, with bid depth.

For region/bonus/wage questions prefer the main tool in this repo
(`AllBonusV4.py --cli --book`), which needs no local database.
