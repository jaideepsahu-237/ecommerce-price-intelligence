# Ecommerce Price Intelligence

A Flask-based smartphone price comparison application that collects
publicly available product and offer information from multiple
retailers, normalizes comparable product variants, estimates EMI, and
highlights the best available deal.

> **Project status:** Initial planning / development setup. The
> structure and features below describe the intended implementation;
> they are not a claim that all features are already working.

## Goals

A user should be able to search for a smartphone by model and optionally
filter by storage, colour, and budget. The application will collect
matching listings from at least three retail sources:

-   Croma
-   Vijay Sales
-   Reliance Digital

It will then normalize product details and prices, capture publicly
visible offers and availability, calculate indicative EMI values, and
display a comparison with source links and scrape timestamps.

## Planned technology

  -----------------------------------------------------------------------
  Area                                Technology
  ----------------------------------- -----------------------------------
  Language                            Python

  Web application / backend           Flask

  Frontend                            Flask templates, HTML, CSS,
                                      JavaScript

  Scraping                            Requests, BeautifulSoup

  Database                            PostgreSQL preferred; SQLite can be
                                      used for local development

  ORM                                 Flask-SQLAlchemy / SQLAlchemy

  Configuration                       python-dotenv

  Testing                             Pytest

  Optional browser automation         Playwright, only where permitted
                                      and genuinely required

  Deployment                          Docker (planned)
  -----------------------------------------------------------------------

No paid API is required for the planned core implementation. Retailer
pages can change or restrict automated access, so scraper availability
cannot be guaranteed permanently.

## Planned project structure

``` text
ecommerce-price-intelligence/
├── app/
│   ├── __init__.py
│   ├── config.py
│   ├── extensions.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── product.py
│   │   ├── offer.py
│   │   └── price_history.py
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── pages.py
│   │   ├── search.py
│   │   └── health.py
│   ├── scrapers/
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── croma.py
│   │   ├── vijay_sales.py
│   │   └── reliance_digital.py
│   ├── services/
│   │   ├── search_service.py
│   │   ├── matching_service.py
│   │   ├── pricing_service.py
│   │   └── emi_service.py
│   ├── templates/
│   │   ├── index.html
│   │   └── results.html
│   └── static/
│       ├── css/style.css
│       └── js/app.js
├── tests/
│   ├── test_scrapers.py
│   ├── test_matching.py
│   └── test_emi.py
├── .env.example
├── .gitignore
├── requirements.txt
├── run.py
├── README.md
├── PROJECT_PLAN.md
└── Dockerfile
```

See [PROJECT_PLAN.md](PROJECT_PLAN.md) for the responsibility of each
module, architecture flow, data plan, development phases, and
implementation decisions.

## Local setup

### 1. Clone the repository

``` bash
git clone <your-repository-url>
cd ecommerce-price-intelligence
```

### 2. Create and activate a virtual environment

Windows:

``` bash
python -m venv venv
venv\Scripts\activate
```

macOS / Linux:

``` bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install dependencies

``` bash
pip install -r requirements.txt
```

The initial dependency set is expected to include:

``` text
Flask
Flask-SQLAlchemy
SQLAlchemy
requests
beautifulsoup4
python-dotenv
pytest
```

Add `psycopg2-binary` when using PostgreSQL. Add `playwright` only if a
permitted source requires browser rendering.

### 4. Configure environment variables

Create a local `.env` file based on `.env.example`. Do not commit
`.env`.

Example values (adjust to your local database):

``` env
FLASK_ENV=development
SECRET_KEY=replace-with-a-local-secret
DATABASE_URL=sqlite:///price_intelligence.db
REQUEST_TIMEOUT=15
```

For PostgreSQL, use a suitable SQLAlchemy connection URL instead of the
SQLite URL.

### 5. Run the application

Once the Flask entry point and routes have been implemented:

``` bash
python run.py
```

The local development URL and exact run instructions will be confirmed
in this section when the application entry point is ready.

## Planned application flow

1.  User submits a phone model and optional filters.
2.  Flask validates the search request.
3.  The search service invokes the retailer scraper adapters.
4.  Each adapter returns product data in a common format.
5.  The matching service groups listings that represent the same model
    and variant.
6.  The pricing and offer services normalize prices and calculate
    eligible indicative values.
7.  Results and crawl metadata are persisted.
8.  The UI displays comparable listings, offers, estimated EMI,
    availability, source links, and scrape time.

## Planned data captured

Product/listing information may include:

-   Product name, brand, model, storage, colour, SKU / model number, and
    variant identifier
-   Product URL, image URL, retailer/source, seller, and currency
-   MRP, selling price, discount, and availability
-   Rating and review count when exposed by the source
-   Offer text, offer type, bank, offer discount, and
    validity/eligibility details when available
-   EMI availability, tenure, interest rate, and calculated monthly EMI
-   Scrape timestamp and crawl/run identifier

Only information actually exposed by a source will be populated. Missing
values should remain unknown rather than being guessed.

## Example API routes (planned)

  ---------------------------------------------------------------------------
  Method                  Route                       Purpose
  ----------------------- --------------------------- -----------------------
  GET                     `/`                         Render the search page

  POST                    `/api/search`               Search and compare
                                                      listings

  GET                     `/api/product/<id>`         Return normalized
                                                      product / variant
                                                      details

  GET                     `/api/offers/<id>`          Return offer and EMI
                                                      information

  GET                     `/api/price-history/<id>`   Return stored price
                                                      history

  GET                     `/health`                   Health check
  ---------------------------------------------------------------------------

These routes are the intended interface and may be adjusted during
implementation.

## Reliability and responsible scraping

-   Check each website's robots.txt, terms, and access restrictions
    before scraping.
-   Do not bypass CAPTCHA, authentication, paywalls, or other access
    controls.
-   Use sensible request timeouts, conservative rate limits, and bounded
    concurrency.
-   Handle HTTP errors, connection failures, malformed responses, and
    missing fields.
-   A failure at one retailer should not prevent results from other
    retailers being returned.
-   Store the source URL and scrape timestamp with collected data.
-   Keep retailer-specific parsing inside its adapter so changes are
    isolated.
-   Do not assume bank discounts can always be combined; preserve
    eligibility conditions and label calculations as estimates.

## Testing

Run the automated tests with:

``` bash
pytest
```

Tests will cover scraper parsing using saved/sample responses where
possible, product matching, price normalization, EMI calculations, and
partial source failures. Live scraper checks should be limited and
respectful of retailer rules.

## Current development checklist

-   [ ] Create the Flask application factory and configuration
-   [ ] Add database connection and initial models
-   [ ] Define a common scraper result format and base adapter
-   [ ] Implement and test the first retailer adapter
-   [ ] Implement the other two retailer adapters
-   [ ] Add product matching and price normalization
-   [ ] Add offer extraction and EMI calculations
-   [ ] Add search and comparison routes
-   [ ] Build the search and results pages
-   [ ] Persist crawl metadata and price history
-   [ ] Add tests, logging, documentation, and Docker setup

## Important note

Retailer websites can change their HTML, APIs, availability, and
anti-bot policies at any time. The application should report partial
results and source failures honestly rather than displaying fabricated
prices or offers.
