"""Offline check for the margin maths (no API calls).

Run: python selftest.py
"""
from AllBonusV4 import production_margin

prices = {"grain": 0.079, "iron": 0.098, "lead": 0.101, "petroleum": 0.105, "fish": 3.966}
# mirrors the app: a missing price counts as 0
get = lambda code: prices.get(code, 0)

# 10 grain -> 1 bread in 10 PP  (the "many inputs" recipe shape)
assert abs(production_margin(2.015, {"grain": 10}, get, 10) - 0.1225) < 1e-4
# 10 iron -> 1 steel in 10 PP
assert abs(production_margin(1.991, {"iron": 10}, get, 10) - 0.1011) < 1e-4
# 1 lead -> 1 lightAmmo in 1 PP
assert abs(production_margin(0.210, {"lead": 1}, get, 1) - 0.109) < 1e-9
# no inputs at all (raw material): margin is simply price / PP
assert abs(production_margin(0.203, {}, get, 1) - 0.203) < 1e-9
# large PP per unit: 1 fish -> 1 cookedFish in 40 PP
assert abs(production_margin(9.0, {"fish": 1}, get, 40) - (9.0 - 3.966) / 40) < 1e-9
# multi-input recipe (not in the game yet, but the loader supports it)
assert abs(production_margin(10.0, {"a": 2, "b": 3}, lambda c: {"a": 1.0, "b": 2.0}.get(c, 0), 5) - 0.4) < 1e-9
# unknown input prices count as free, matching upstream behaviour
assert abs(production_margin(1.0, {"missing": 4}, get, 2) - 0.5) < 1e-9

print("selftest ok: 7 checks")
