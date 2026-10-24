# War-Era-Profit-and-Wages-Calculation-Tool-V4

A fully automated desktop application for the game **WarEra**. This tool pulls live market and region data via the WarEra API, runs complex economic formulas (factoring in Strategic Resources, Deposits, and Party Ethics), and generates visual dashboards of the most profitable regions.

## ✨ Features

* **Easy to Use:** A standalone `.exe` desktop interface (No Python installation required!).
* **Secure API Key Manager:** Automatically saves and loads your WarEra API key locally. The input field is masked to protect your token if you are streaming or screen-sharing.
* **Live Market Integration:** Fetches real-time trading prices for all goods and raw materials, including newly added industries like Wood and Paper.
* **Complex Math Engine:** Calculates total production bonuses, Price of Production, Profit per PP, and Worker Wages (Pre and Post-Tax).
* **CSV Export:** Compiles all merged country, party, and region data into a detailed `extracted_countries.csv` spreadsheet.
* **Dual Visual Dashboards:** * Automatically generates a `wages_summary_chart.png` highlighting the single highest-profit region per product.
  * Generates a ranked `ranked_wages_chart.png` showcasing all highly profitable regions (Top Net Wages > 0.12) sorted for quick investment decisions.

## 🚀 Installation & Usage

1. Go to the **Releases** tab on the right side of this GitHub page.
2. Download the latest `ProfitnWagesCalc_V4.zip` file.
3. Extract the `.zip` folder somewhere on your computer.
4. Double-click **`AllBonusV4.exe`** to run the program.
5. When the window opens, paste your **WarEra API Key** (must start with `wae_`) into the secure input box and click **Save & Run**.
6. Once finished, check the folder for your newly generated CSV and PNG dashboards!

## 📁 Output Files

When you run the app, it will generate four files in the same folder:
* `warera_api_key.txt`: Created locally to remember your API key for next time. 
* `extracted_countries.csv`: The raw, calculated data for every region.
* `wages_summary_chart.png`: A colour-coded table showing the most profitable region for each major product.
* `ranked_wages_chart.png`: A comprehensive ranked list of the most lucrative regions globally based on post-tax wages.

## 🔒 Security & Privacy Transparency
This application communicates directly with the official WarEra API. Your API key is **never** sent to any third-party servers. It is only saved locally on your own computer in the `warera_api_key.txt` file, so you don't have to type it in every time. Treat that text file like a password!

## 🖥️ Headless / CLI mode (fork addition)

No GUI, no `.exe` needed — useful for servers, cron, or piping into other scripts:

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt   # Windows: .venv\Scripts\pip

# game-calculated prices (same numbers as the GUI)
python AllBonusV4.py --cli

# execution-price mode: sell output at the order-book bid, buy inputs at the ask
python AllBonusV4.py --cli --book

# explicit key / output directory
python AllBonusV4.py --cli --book --key wae_xxx --out ./reports
```

Key resolution order: `--key` → `warera_api_key.txt` → `~/.config/warera/api_key`.
Running with no arguments still opens the original GUI.

## 🔧 Changes in this fork

* **Recipes are read from the game, not hardcoded.** The upstream `RECIPES` table
  had to be edited by hand whenever WarEra added an item or changed a ratio, and
  unknown items silently produced zeros. Recipes now come from
  `gameConfig.getGameConfig()` (20 items, multi-input supported); the old table is
  kept only as an offline fallback.
* **`--book` pricing.** Upstream used `itemTrading.getPrices`, which is a lagging
  game-side calculation. With `--book` the profit is computed against real order
  book quotes (bid for goods, ask for inputs). On the same market this reads
  ~0.6–1.8% lower than the game price — small, but it is the number you can
  actually execute.
* **`--cli` headless mode** with `--key`, `--book`, `--out` (details above).
* **Fixed: `requests` was imported after first use.** It worked only because the
  import line executed before any call; it is now a normal top-level import.
* **Fixed: crash on an empty API response** — the CSV writer indexed
  `combined_extracted_data[0]` unguarded and raised `IndexError`.
* **Fixed: wrong log message** claiming chart 1 was saved as `wages_summary_chart.png`
  when the file is `product_profitability_ranking_chart.png`.
* **Pandas 3 deprecations removed** (`DataFrame.rename(..., inplace=True)`), so runs
  no longer print `Pandas4Warning` on modern pandas.
* **`requirements.txt` added** (requests, pandas, matplotlib).

### Reading the CSV

Each row's prices and profit belong to the product in **`Bonus Source`**, not
`Specialisation`. They differ whenever a region's deposit beats the country's
specialisation, and grouping by `Specialisation` then pairs a product with the
wrong price. Also: `Country Name` is the region's *current owner*, so an occupied
region (e.g. Kyushu held by Chile) shows the occupier, not the original country.
`Profit per PP` is a **pre-wage gross margin**; the wage columns are a separate
"maximum affordable wage" estimate and carry an unexplained `+10` constant.

## 📄 License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

### Acknowledgments
* Portions of the Python logic, including the Flask conversion and Matplotlib chart generation for the market data, were developed with the assistance of Google's Gemini AI.
