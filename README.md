# P-Plate Car Finder (Victoria, Australia)

A small local web app + database to help an 18-year-old P1/P2 driver in Victoria
choose a **safe, legal and affordable first car**.

It stores candidate cars, checks each one against the **current Victorian
probationary ("P-plate") vehicle rules**, and lets you filter, tag and compare
them. It can also search for current rule guidance / first-car recommendations
and pull in listings (live where permitted, otherwise CSV or mock data).

> **Guidance only — not legal advice.** Victorian rules change and this app may
> be wrong or out of date. Always confirm the *exact make/model/variant* on the
> official **probationary vehicle database** or with VicRoads before buying or
> driving. Listing data can be stale or incorrect — verify on the source site.

---

## 1. The Victorian P-plate rules this app implements

Verified against Transport Victoria / VicRoads (re-checked October 2026). In Victoria a
probationary driver (P1 **or** P2, of **any age**) must **not** drive a vehicle
that is a *probationary prohibited vehicle* (PPV). A vehicle is prohibited if
**any** of the following is true:

1. **Banned rating** — it has a `banned` rating in the Victorian *probationary
   vehicle database* (or is `under review`).
2. **Power-to-mass ratio > 130 kW per tonne** of **tare mass**. `ratio = power
   (kW) ÷ mass (tonnes)`. Tare mass is lighter than the kerb weight most
   listings quote, so the official ratio is slightly *higher* than one
   calculated from kerb weight.
3. **Performance engine modification** — the engine has been modified to
   increase performance, unless the modification was done by the manufacturer
   when the vehicle was originally built.

**Common misconceptions (Victoria):**

* The old **absolute power caps (~125 / 149 kW)** are **obsolete**. Victoria has
  used the power-to-mass test plus the banned-vehicle database since
  **29 October 2019**. This app ships with the absolute cap **disabled**
  (`PPLATE_ABSOLUTE_POWER_LIMIT_KW` is unset).
* There is **no blanket turbo / supercharger / V8 / rotary ban** in Victoria.
  A modern turbo car under 130 kW/t can be legal; a naturally-aspirated car over
  the limit is not.
* The **variant matters**, not the badge: a base model can be legal while the
  performance variant is banned (e.g. Tesla Model 3 RWD vs Performance).
* **EVs are not exempt**: the 130 kW/t test applies to electric drivelines too.
  Many single-motor EVs are under the limit (e.g. BYD Dolphin ~46 kW/t), while
  dual-motor/performance EVs are not (e.g. Tesla Model 3 Performance ~185 kW/t).

**Exemptions** (not applied by this tool): learner, full and overseas licence
holders are not subject to the rule; a supervising fully-licensed driver,
automatic work-related exemptions, and approved undue-hardship exemptions exist.

### Sources used

* Transport Victoria — [Vehicles for probationary drivers](https://transport.vic.gov.au/road-and-active-transport/registration-and-licensing/licences/probationary-licence/vehicles-for-probationary-drivers)
  (primary: banned / power-to-mass / modification rule).
* Victorian **probationary vehicles database** (Approved / Banned / Under review):
  <https://vicroadssafevehicles.carsalesnetwork.com.au/#/search>
* VicRoads — [Driving on your Ps](https://www.vicroads.vic.gov.au/ls-and-ps/driving-on-your-ps).
* Road Safety (Drivers) Regulations 2019 (Vic), reg 57 — statutory basis.
* Transport Victoria — [Exemptions to drive a prohibited vehicle](https://transport.vic.gov.au/road-and-active-transport/registration-and-licensing/licences/probationary-licence/exemptions-to-drive-a-prohibited-vehicle).
* VACC MotorTech — [Can I drive an EV on my P-plates?](https://motortech.com.au/can-i-drive-an-ev-on-my-p-plates-yes-and-no/) (EV guidance).
* carsales editorial — [P-plate prohibited vehicles update](https://www.carsales.com.au/editorial/details/p-plate-prohibited-vehicles-update-100374/).

### How the compliance engine decides

`pplate/services/p_plate_compliance.py` evaluates each car in this order:

| # | Test | Result |
|---|------|--------|
| 1 | Performance engine modification (`modified=True`) | **non-compliant** |
| 2 | Known high-performance model/variant (conservative heuristic list) or `listed_high_performance=True` | **non-compliant** |
| 3 | Configured absolute power cap (disabled by default) | non-compliant if exceeded |
| 4 | `power_kw ÷ (weight_kg/1000)` ≥ 130 | **non-compliant** |
| 4 | ratio in `[120, 130)` ("borderline" band) | **unknown → verify** |
| 4 | ratio < 120 | **compliant** |
| — | power or weight missing | **unknown** (never a false "compliant") |

The borderline band exists because official ratios use **tare** mass (lighter →
higher ratio) than the kerb weight we usually hold. Thresholds are configurable
via `.env`; the "listed model" list is a conservative secondary check layered on
top of the maths, and the maths is always the primary test.

---

## 2. Features

* **Car database** — make, model, variant, year, engine cc, power (kW), weight
  (kg), computed power-to-weight, body type, fuel, transmission, cylinders,
  price (AUD), odometer, location, ANCAP stars + year, listing URL, source.
* **P-plate flag per car** with a short explanation and an explicit
  three-state result: `compliant` / `non_compliant` / `unknown`.
* **Manual CRUD** — add, edit, delete cars; extra flags for
  *performance-modified* and *on high-performance list*.
* **Recommend / not-recommend** with notes/pros-cons.
* **Filter & search** — price range, body, fuel, transmission, min ANCAP,
  P-plate status, recommended, source, free-text, and sort.
* **Dashboard** — counts of compliant / non-compliant / unknown / recommended.
* **Run recommendation search** — web search for current rules + first-car guides
  (Tavily API if a key is provided, otherwise a bundled authoritative knowledge
  base) and seeds ~15 curated first cars.
* **Fetch live listings** — `carsales` (best-effort, robots-respecting), `csv`
  import, or `mock` for offline demos. Every listing is normalised and tagged.
* **Transparency** — all external HTTP requests are rate-limited, cached, and
  logged (`external_request_log`); search and fetch runs are recorded.
* **Disclaimers** throughout the UI.

---

## 3. Tech stack

* **Backend:** Python 3.11+ / FastAPI, SQLAlchemy 2.0, Alembic, Pydantic v2.
* **Database:** SQLite for local dev (swap to PostgreSQL via `DATABASE_URL`).
* **Frontend:** server-rendered Jinja2 templates + a little CSS (no build step).
* **HTTP:** httpx + BeautifulSoup with robots.txt checks, rate limiting, caching.

---

## 4. Project structure

```
p-plate-car-finder/
├── app.py                     # ASGI entry point (uvicorn app:app)
├── requirements.txt
├── .env.example
├── alembic.ini
├── alembic/
│   ├── env.py
│   └── versions/0001_initial.py
├── data/
│   └── listings.csv           # sample CSV import
├── scripts/
│   ├── seed.py                # 20 example cars
│   ├── run_recommendations.py
│   └── fetch_listings.py
├── tests/
│   └── test_p_plate_compliance.py
└── pplate/
    ├── config/                # settings (env vars)
    ├── db/                    # engine, session, Base
    ├── models/                # Car, RecommendationSource, SearchRun, FetchRun...
    ├── schemas/               # Pydantic request/response models
    ├── services/
    │   ├── p_plate_compliance.py   # ← the rules engine
    │   ├── car_service.py          # CRUD, filters, stats
    │   ├── external_http.py        # robots + rate limit + cache + logging
    │   ├── recommendation_search.py
    │   └── listing_fetch.py
    ├── routes/                # api_cars, api_tools, ui
    ├── templates/             # base, dashboard, car_form, rules, sources
    └── static/style.css
```

---

## 5. Setup

```bash
cd p-plate-car-finder

# 1. Virtualenv
python3 -m venv .venv
source .venv/bin/activate         # Windows: .venv\Scripts\activate

# 2. Dependencies
pip install -r requirements.txt

# 3. Configuration
cp .env.example .env               # edit if you want Postgres / a Tavily key

# 4. Database schema (choose one)
alembic upgrade head               # migrations
# ...or just start the app: it also creates tables on startup (AUTO_CREATE_TABLES=true)

# 5. Seed example data (optional but recommended)
python scripts/seed.py

# 6. Run
uvicorn app:app --reload
```

Open <http://127.0.0.1:8000>. Interactive API docs at
<http://127.0.0.1:8000/docs>.

### Recommended workflow in the UI

1. **Run recommendation search** (Dashboard → Tools) to load rule sources and
   seed ~15 recommended first cars.
2. **Fetch live listings** with provider `mock` (offline), `csv` (uses
   `data/listings.csv`), or `carsales` (best effort).
3. Use the **filters** to show only *P-plate compliant* cars.
4. **Add** any private listings manually and mark them recommended / not.

---

## 6. Recommendation search

```bash
python scripts/run_recommendations.py
# or: POST /api/tools/recommendations
```

* If `TAVILY_API_KEY` is set in `.env`, live web search is used; otherwise the
  app stores a bundled set of authoritative sources (offline-safe).
* Always upserts ~15 curated first-car models (Corolla, Mazda3, i30, Rio, Swift,
  Jazz, Accent, Pulsar, Cerato, Camry, Mazda2, Yaris, …) with typical used price
  ranges, specs, ANCAP rating and pros/cons — all comfortably under 130 kW/t.
* Every query and result is recorded in `search_runs` / `recommendation_sources`.

## 7. Fetching listings

```bash
python scripts/fetch_listings.py --provider mock --limit 20
python scripts/fetch_listings.py --provider csv
python scripts/fetch_listings.py --provider carsales --query "Toyota Corolla"
```

* **`mock`** — deterministic synthetic listings; works offline; includes a mix of
  compliant / borderline / non-compliant examples.
* **`csv`** — imports `data/listings.csv` (edit `LISTINGS_CSV_PATH`). Columns:
  `external_id,make,model,variant,year,engine_size_cc,power_kw,weight_kg,body_type,fuel_type,transmission,price_aud,odometer_km,location,safety_rating_stars,safety_rating_year,listing_url`.
  This is the **plug-in point** for any future API or manual export.
* **`carsales`** — checks `robots.txt` first; if crawling is disallowed it logs
  the decision and returns nothing rather than circumventing the block. If
  allowed, it parses embedded JSON-LD. Facebook Marketplace is intentionally
  **not** implemented (no stable public endpoint); import via CSV instead.

All providers are normalised to the same fields, de-duplicated by `external_id`,
upserted, and run through the compliance engine.

## 8. Compliance: changing the thresholds

Edit `.env` (no code change needed):

```ini
PPLATE_POWER_TO_MASS_LIMIT=130.0   # kW per tonne
PPLATE_BORDERLINE_LOWER=120.0      # ratios in [lower, limit) => "verify"
# PPLATE_ABSOLUTE_POWER_LIMIT_KW=149   # legacy; leave unset in Victoria
```

The conservative "known high-performance model" regex list lives at the top of
`pplate/services/p_plate_compliance.py`; extend it as the regulator's list
changes. Re-run `POST /api/cars/{id}/recheck` (or just edit a car) to recompute.

---

## 9. API reference & curl examples

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/health` | Health / version |
| GET | `/api/cars` | List/search cars (filters below) |
| POST | `/api/cars` | Create a car |
| GET | `/api/cars/{id}` | Get one car |
| PUT/PATCH | `/api/cars/{id}` | Update a car |
| DELETE | `/api/cars/{id}` | Delete a car |
| POST | `/api/cars/{id}/recheck` | Recompute P-plate result |
| GET | `/api/cars/stats` | Compliance/recommended counts |
| GET | `/api/rules` | Rules summary, thresholds, source URLs |
| POST | `/api/tools/recommendations` | Run recommendation search |
| POST | `/api/tools/fetch-listings` | Fetch listings |
| GET | `/api/recommendation-sources` | Stored sources |
| GET | `/api/search-runs`, `/api/fetch-runs` | Run history |

Filter query params for `GET /api/cars`:
`q, min_price, max_price, body_type, fuel_type, transmission, min_safety,
compliance (compliant|non_compliant|unknown), recommended (true|false),
source, sort, limit, offset`.

```bash
# Stats
curl -s localhost:8000/api/cars/stats

# Only P-plate compliant cars under $15,000, cheapest first
curl -s "localhost:8000/api/cars?compliance=compliant&max_price=15000&sort=price_asc"

# Add a car
curl -s -X POST localhost:8000/api/cars \
  -H 'Content-Type: application/json' \
  -d '{"make":"Toyota","model":"Corolla","year":2016,"power_kw":103,"weight_kg":1280,
       "body_type":"hatch","fuel_type":"petrol","transmission":"CVT","price_aud":13500}'

# Recompute compliance for car 1
curl -s -X POST localhost:8000/api/cars/1/recheck

# Trigger the tools
curl -s -X POST localhost:8000/api/tools/recommendations -H 'Content-Type: application/json' -d '{}'
curl -s -X POST localhost:8000/api/tools/fetch-listings \
  -H 'Content-Type: application/json' -d '{"provider":"mock","limit":10}'

# The Victorian rules this app uses
curl -s localhost:8000/api/rules
```

Run the tests:

```bash
pytest -q
```

---

## 10. External request etiquette

* `robots.txt` is fetched and honoured per host (see `ExternalClient`).
* Per-host **rate limiting** and an on-disk **cache** avoid hammering sites.
* Every outbound request is **logged** to `external_request_log` (and the
  console); search and fetch runs are recorded.
* Where scraping is disallowed, the code degrades gracefully to CSV/mock;
  wiring a future API is a single new provider function returning normalised
  dicts.

## 11. Security & privacy

* No authentication (local dev), but routes are split so auth can be added as a
  dependency later. No personal data is stored beyond the car list.
* Secrets come from `.env` (git-ignored); nothing sensitive is logged.
* Clear, repeated disclaimers: legal compliance is the driver's responsibility,
  and listing data may be stale or wrong.

## 12. Switching to PostgreSQL

```ini
DATABASE_URL=postgresql+psycopg2://user:password@localhost:5432/pplate
```

Install `psycopg2-binary`, then `alembic upgrade head`. The models and
migration use portable types, so no code changes are needed.

## 13. Extending

* **New listing source:** add a function returning normalised car dicts in
  `pplate/services/listing_fetch.py` and dispatch it in `fetch_listings()`.
* **New rule:** update thresholds in `.env` and/or the regex list in
  `p_plate_compliance.py`; the reason strings and tests document the logic.
* **Auth:** add a dependency to the `/api` routers.
