# Ecommerce Price Intelligence

A Flask-based smartphone price comparison platform that collects publicly available product, pricing, and offer information from multiple Indian electronics retailers, normalizes comparable variants, calculates indicative EMI, and ranks the best available deals.

> **Active retailers:** **Vijay Sales**, **Reliance Digital**, and **Poorvika**.
> (`CromaScraper` is retained in `app/scrapers/croma.py` but disabled by default in `SearchService` due to `403` WAF blocks.)

## Features

- **Multi-Retailer Search & Filtering:** Search by model/brand with optional filters for `storage`, `colour`, `min_budget`, `max_budget`, and `source` (retailer).
- **Variant Normalization & Accessory Filtering:** Groups equivalent listings across retailers into deterministic `variant_id` slugs and filters out cases, covers, chargers, and sub-₹3,000 accessories.
- **Offer & Effective Price Calculation:** Enriches top listings with client-side bank/card discounts via Playwright + Chromium, computes `effective_price` separately from `selling_price`, and explains why `best_deal` ranked first.
- **Indicative EMI Calculator:** Computes reducing-balance and 0% no-cost EMI estimates from `tenure`, `down_payment`, and `annual_rate`.
- **Persistence & Price History:** Stores `Product`, `Retailer`, `ProductListing`, and `PriceHistory` snapshots in PostgreSQL, with DB cache fallback if live scrapers return no results.
- **Request Logging:** Logs all incoming HTTP requests, status codes, and response times to `logs/api.log`.

## Technology Stack

| Area | Technology |
| :--- | :--- |
| Language | Python 3.12+ |
| Web / API | Flask, Jinja2, Bootstrap 5 |
| Scraping & Enrichment | `requests`, `beautifulsoup4`, `playwright` (Chromium) |
| Database / ORM | PostgreSQL (`psycopg2-binary`), Flask-SQLAlchemy / SQLAlchemy |
| Testing | `pytest` |
| Containerization | Docker & Docker Compose |

## Project Structure

```text
ecommerce-price-intelligence/
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── extensions.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── product.py
│   │   ├── retailer.py
│   │   ├── product_listing.py
│   │   └── price_history.py
│   ├── routes/
│   │   ├── pages.py
│   │   ├── search.py
│   │   └── health.py
│   ├── scrapers/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── vijay_sales.py
│   │   ├── reliance_digital.py
│   │   ├── poorvika.py
│   │   └── croma.py
│   ├── services/
│   │   ├── search_service.py
│   │   ├── matching_service.py
│   │   ├── emi_service.py
│   │   └── offer_enrichment.py
│   └── templates/
│       ├── index.html
│       └── results.html
├── tests/
│   ├── test_api.py
│   ├── test_emi.py
│   ├── test_filters_and_offers.py
│   └── test_matching.py
├── .env.example
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── run.py
├── seed_data.py
├── sample_output.json
├── PROJECT_PLAN.md
└── README.md
```

## Local Setup & Run Commands

### 1. Create and activate a virtual environment

Windows (PowerShell):

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

macOS / Linux:

```bash
python3 -m venv venv
source venv/bin/activate
```

### 2. Install dependencies and Playwright Chromium

```bash
pip install -r requirements.txt
playwright install chromium
```

### 3. Configure environment variables

Copy `.env.example` to `.env` and set your PostgreSQL connection string:

```env
SECRET_KEY=replace-with-a-local-secret
DEBUG=True
DATABASE_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/ecommerce_price_intelligence
```

### 4. Seed initial retailers/products (optional)

```bash
python seed_data.py
```

### 5. Run the Flask application

```bash
python run.py
```

Open `http://127.0.0.1:5000/` in your browser. All HTTP requests are logged to `logs/api.log`.

---

## Run with Docker

The repository includes `Dockerfile` and `docker-compose.yml` (PostgreSQL 16 + Flask web app with Playwright Chromium).

### Build and start all services

```bash
docker compose up --build
```

### Run in detached mode

```bash
docker compose up -d --build
```

### View application logs

```bash
docker compose logs -f web
```

### Stop services

```bash
docker compose down
```

To also remove the PostgreSQL data volume:

```bash
docker compose down -v
```

Once running, access the app at `http://127.0.0.1:5000/`.

---

## API Endpoints

| Method | Route | Purpose |
| :--- | :--- | :--- |
| `GET` | `/` | Render the smartphone search UI |
| `GET` | `/results` | Render filtered comparison & EMI results page |
| `GET` / `POST` | `/api/search` | Search, filter, enrich offers, calculate EMI, and rank deals |
| `GET` | `/api/product/<id>` | Return normalized product/variant details and listings |
| `GET` | `/api/offers/<id>` | Return retailer offers and indicative EMI options |
| `GET` | `/api/price-history/<id>` | Return historical price observations |
| `GET` | `/health` | Service health check |

### `/api/search` Parameters

- `query` *(required)*: Smartphone model or brand (e.g., `iPhone 17`, `Samsung S26`)
- `tenure` *(optional, default `12`)*: EMI tenure in months
- `down_payment` *(optional, default `0.0`)*: Down payment in INR
- `annual_rate` *(optional, default `14.0`)*: Annual interest rate `%` (`0` for No-Cost EMI)
- `storage` *(optional)*: e.g., `128 GB`, `256 GB`, `512 GB`, `1 TB`
- `colour` *(optional)*: e.g., `Black`, `Blue`
- `min_budget` / `max_budget` *(optional)*: Price range in INR
- `source` *(optional)*: `vijay-sales`, `reliance-digital`, `poorvika`, or `all`

A sample response is saved in `sample_output.json`.

---

## Testing

Run the full test suite from the project root:

```bash
pytest -v
```

---

## Notes & Limitations

- Retailer HTML, APIs, stock, and anti-bot protections can change at any time; failures in one retailer do not crash the search.
- To balance response speed with offer accuracy, Playwright enriches up to `max_per_retailer=5` filtered listings per retailer for client-side bank/card discounts.
- All EMI and effective-price calculations are indicative estimates; verify final card eligibility on the retailer's store page.
