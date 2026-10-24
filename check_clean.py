"""Check whether the newest stored report is clean before digesting it.

A report whose Country Name column is empty was fetched during a network
outage; shipping it would present garbage rankings as real ones.

Run: python check_clean.py <path-to-extracted_countries.csv>
Prints one line: OK <path>  or  BAD <reason>
"""
import sys

import pandas as pd


def main():
    if len(sys.argv) != 2:
        print("usage: check_clean.py <extracted_countries.csv>")
        return 2
    path = sys.argv[1]
    try:
        df = pd.read_csv(path)
    except Exception as exc:
        print(f"BAD unreadable CSV: {exc}")
        return 1
    if df.empty:
        print("BAD no rows")
        return 1
    known = (df["Country Name"] != "Unknown").sum()
    if known == 0:
        print("BAD country data missing for every region (fetch failed)")
        return 1
    if known < 0.8 * len(df):
        print(f"BAD only {known}/{len(df)} regions have country data; network unreliable")
        return 1
    print(f"OK {path} ({known}/{len(df)} regions with country data)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
