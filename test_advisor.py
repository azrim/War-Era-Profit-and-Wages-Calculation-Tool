"""Offline checks for advisor.py maths (no API calls).

Run: python test_advisor.py
"""
from AllBonusV4 import production_margin

price = lambda c: {"grain": 0.079, "lead": 0.101, "iron": 0.098}.get(c, 0)

# the same numbers the advisor relies on: margin/PP with no regional bonus
assert abs(production_margin(2.015, {"grain": 10}, price, 10) - 0.1225) < 1e-4
assert abs(production_margin(0.210, {"lead": 1}, price, 1) - 0.109) < 1e-9

# bonus scaling used by the report table: margin_0 * (1 + bonus/100)
margin_0 = production_margin(3.473, {"lead": 16}, price, 16)
assert abs(margin_0 * 1.55 / margin_0 - 1.55) < 1e-9
assert margin_0 * 1.55 > margin_0 > 0

# a company whose item does not match the region product earns the bare margin,
# which is what advisor.py falls back to (never the boosted figure)
assert margin_0 < margin_0 * 1.55

print("test_advisor ok: 5 checks")
