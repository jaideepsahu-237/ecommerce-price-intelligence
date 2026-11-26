# Project Plan and Architecture

## 1. Project purpose

**Ecommerce Price Intelligence** is a smartphone price comparison
application. A user searches for a phone and the application collects
publicly accessible listings from multiple retailers, identifies
equivalent variants, compares prices and offers, estimates EMI, and
recommends the best comparable deal.

This document records the intended structure, responsibilities, data
flow, and implementation plan. It is a development target, not a
description of features already completed.

## 2. Scope

### Core scope

-   Search by smartphone brand/model.
-   Optional storage, colour, and budget filters.
-   Collect listings from at least three retailers: Croma, Vijay Sales,
    and Reliance Digital.
-   Normalize product names, variants, INR prices, and discounts.
-   Capture public offer details and availability where available.
-   Calculate indicative EMI from price, down payment, tenure, and
    interest-rate assumptions.
-   Rank comparable results and show source URLs and scrape timestamps.
-   Store crawl metadata and price history.
-   Return partial results if one retailer fails.

### Out of scope for the first version

-   Bypassing CAPTCHA, login, or other access controls.
-   Guaranteeing that every retailer always permits automated
    collection.
-   Treating every bank discount, cashback, and EMI promotion as
    combinable.
-   Building a complex recommendation/AI engine before the core
    comparison works.

Optional later improvements include scheduled refreshes, price-drop
alerts, a deal score, and browser automation for permitted pages that
require rendering.

## 3. Planned folder and module responsibilities

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
├── .env.example
├── .gitignore
├── requirements.txt
├── run.py
├── README.md
├── PROJECT_PLAN.md
└── Dockerfile
```

### Root files

  -----------------------------------------------------------------------
  File                                Responsibility
  ----------------------------------- -----------------------------------
  `run.py`                            Development entry point that
                                      creates/runs the Flask app

  `requirements.txt`                  Python dependencies

  `.env`                              Local secrets and
                                      environment-specific settings;
                                      never commit

  `.env.example`                      Names of required settings with
                                      safe example values

  `.gitignore`                        Excludes virtual environment,
                                      `.env`, cache, database and
                                      generated files

  `README.md`                         Setup, run, test, and usage
                                      instructions

  `Dockerfile`                        Optional container build
                                      instructions
  -----------------------------------------------------------------------

### `app/` modules

  -----------------------------------------------------------------------
  Module                              Responsibility
  ----------------------------------- -----------------------------------
  `__init__.py`                       Flask application factory; register
                                      blueprints and initialize
                                      extensions

  `config.py`                         Load configuration and environment
                                      variables

  `extensions.py`                     Create shared extension objects,
                                      such as SQLAlchemy
  -----------------------------------------------------------------------

### `app/models/`

-   `product.py`: normalized product identity and retailer listing
    details, as the final schema requires.
-   `offer.py`: offer text, type, bank, discount, and
    eligibility/validity information.
-   `price_history.py`: observed prices with source and timestamp.

The schema should distinguish a normalized product/variant from each
retailer's listing. One phone variant may have multiple retailer
listings.

### `app/routes/`

-   `pages.py`: render the search and results pages.
-   `search.py`: accept search filters and return comparison results.
-   `health.py`: provide a simple health-check endpoint.

Routes should validate input and delegate scraping/comparison work to
services rather than containing scraper logic themselves.

### `app/scrapers/`

-   `base.py`: define the common adapter interface, shared request
    settings, and normalized output contract.
-   `croma.py`: retailer-specific collection and parsing for Croma.
-   `vijay_sales.py`: retailer-specific collection and parsing for Vijay
    Sales.
-   `reliance_digital.py`: retailer-specific collection and parsing for
    Reliance Digital.

Each adapter should return the same internal data shape. A new retailer
should be addable without rewriting the comparison logic.

### `app/services/`

-   `search_service.py`: coordinate a search across available retailer
    adapters and combine partial results.
-   `matching_service.py`: normalize model/storage/colour labels and
    decide whether listings represent the same variant.
-   `pricing_service.py`: parse and normalize prices, discounts, and
    effective-price assumptions.
-   `emi_service.py`: calculate indicative EMI and total repayment from
    clearly stated inputs.

### Frontend

-   `templates/index.html`: search form for model, storage, colour,
    budget, EMI tenure, down payment, and source filter.
-   `templates/results.html`: comparison table, offers, availability,
    source links, timestamps, and best-deal explanation.
-   `static/css/style.css`: page styling.
-   `static/js/app.js`: small client-side interactions and API calls if
    needed.

### `tests/`

-   `test_scrapers.py`: parser and adapter behavior using sample/saved
    responses where possible.
-   `test_matching.py`: model, storage, and colour
    normalization/matching.
-   `test_emi.py`: EMI calculation and edge cases.

More test modules can be added as features grow.

## 4. Architecture / request flow

``` text
Browser
  |
  | Search model + optional filters
  v
Flask route: POST /api/search
  |
  v
Search service
  |
  +----> Croma adapter
  |
  +----> Vijay Sales adapter
  |
  +----> Reliance Digital adapter
  |
  v
Common normalized listing records
  |
  +----> Product matching service
  |
  +----> Price / offer normalization
  |
  +----> EMI calculation service
  |
  v
Database: products, listings, offers, price history, crawl metadata
  |
  v
Ranked comparison response
  |
  v
Results page / JSON response
```

A retailer adapter can fail independently. The search service should
record that source's failure and still return valid results from the
other sources.

## 5. Common scraper output

All adapters should map retailer-specific fields into a consistent
internal structure. A conceptual listing record:

``` json
{
  "product_name": "Example Phone 256 GB",
  "brand": "Example",
  "model": "Example Phone",
  "storage": "256 GB",
  "colour": null,
  "sku": null,
  "product_url": "https://retailer.example/product",
  "image_url": null,
  "source": "retailer_name",
  "currency": "INR",
  "mrp": null,
  "selling_price": 99999,
  "discount": null,
  "availability": "unknown",
  "seller": null,
  "rating": null,
  "review_count": null,
  "offer_text": null,
  "scraped_at": "ISO-8601 timestamp",
  "crawl_id": "unique-run-id"
}
```

This is an example contract only. Values must come from the source or be
left `null`/unknown. Do not invent product, price, offer, or stock
information.

## 6. Product matching approach

Retailers may use different titles for the same phone. Matching should
compare meaningful attributes rather than relying only on exact title
equality.

Suggested order:

1.  Normalize text (case, whitespace, punctuation, and common storage
    notation).
2.  Identify brand and model.
3.  Compare storage capacity.
4.  Compare colour when the user selected one and the source exposes it.
5.  Use SKU/model number when available.
6.  Mark uncertain matches rather than silently combining different
    variants.

A 128 GB listing must not be grouped with a 256 GB listing. Colour
aliases should only be merged when there is a defensible mapping.

## 7. Price, offer, and EMI rules

Keep these concepts separate:

-   **MRP:** listed maximum retail price, if shown.
-   **Selling price:** retailer's current displayed price.
-   **Offer facts:** exact public offer text, bank/card, discount,
    conditions, and validity if exposed.
-   **Estimated effective cost:** a calculation based only on offers
    whose eligibility assumptions are explicit.
-   **Estimated EMI:** a calculation based on financed amount, interest
    rate, and tenure.

For a standard reducing-balance loan, the EMI calculation is:

``` text
P = amount financed
r = monthly interest rate (annual rate / 12 / 100)
n = number of monthly payments

EMI = P * r * (1 + r)^n / ((1 + r)^n - 1)
```

If the rate is zero, EMI is `P / n`.

The UI must label calculated EMI and effective cost as estimates. A
no-cost EMI assumption should only be used when the source explicitly
supports it and the assumption is documented. Do not assume that bank
discounts, exchange benefits, and cashback can all be combined.

## 8. Database planning

The initial logical entities are:

  -----------------------------------------------------------------------
  Entity                              Purpose
  ----------------------------------- -----------------------------------
  Product / Variant                   Canonical phone model and variant
                                      identity

  Retailer Listing                    Source-specific title, URL, seller,
                                      price, and availability

  Offer                               Offer facts and conditions
                                      associated with a listing

  Price History                       Price observations over time

  Crawl Run                           Run ID, source, start/end time,
                                      status, and error summary
  -----------------------------------------------------------------------

The exact table columns and relationships will be finalized during
database implementation. Keep source URL and scrape timestamp with each
observation.

## 9. Reliability and responsible collection

-   Review robots.txt, terms of service, and access restrictions for
    each retailer before collecting data.
-   Do not bypass CAPTCHA, authentication, or access controls.
-   Set request timeouts and conservative per-domain request intervals.
-   Use bounded concurrency; do not send uncontrolled parallel requests.
-   Handle 403, 404, 429, 5xx, timeouts, connection failures, malformed
    HTML/JSON, and missing fields.
-   Retry only transient failures, with limited backoff. Do not
    repeatedly retry access-denied responses.
-   Cache or persist data where appropriate to avoid unnecessary repeat
    requests.
-   Log source, URL, crawl ID, timestamp, status, and useful error
    details.
-   Return partial results when a source fails.
-   Keep selectors and parsing logic inside the relevant adapter.

## 10. Planned API

  Method   Endpoint                    Purpose
  -------- --------------------------- ----------------------------------
  GET      `/`                         Render search page
  POST     `/api/search`               Run search and return comparison
  GET      `/api/product/<id>`         Get normalized product / variant
  GET      `/api/offers/<id>`          Get offer and EMI details
  GET      `/api/price-history/<id>`   Get historical observations
  GET      `/health`                   Health status

These are planned endpoints and can be adjusted as implementation
proceeds.

## 11. Development phases

  -----------------------------------------------------------------------
  Phase                   Deliverable             Completion check
  ----------------------- ----------------------- -----------------------
  1\. Foundation          Flask factory, config,  App starts and health
                          extensions, entry point route responds

  2\. Data layer          Initial models and      Tables can be created
                          database setup          and queried

  3\. First scraper       One retailer adapter    Returns real,
                                                  source-linked records
                                                  where permitted

  4\. Other scrapers      Two more retailer       Three adapters use the
                          adapters                same output contract

  5\. Normalization       Price parsing and       Equivalent variants
                          variant matching        group; different
                                                  storage does not

  6\. Offers and EMI      Offer extraction and    Calculations pass unit
                          EMI service             tests and show
                                                  assumptions

  7\. Search and UI       Search API and          User can search and
                          comparison pages        inspect results

  8\. History and         Crawl metadata, price   Errors do not crash the
  reliability             history, partial        complete search
                          failures, logs          

  9\. Delivery            Tests, README, sample   Another person can
                          output, Docker          follow setup
                                                  instructions
  -----------------------------------------------------------------------

## 12. Definition of a successful first version

The first version is ready for review when:

-   A user can submit a phone search through the Flask UI.
-   The system attempts at least three retailer sources.
-   It returns comparable, source-linked results where the sources
    permit collection.
-   It distinguishes model/storage variants sufficiently to avoid
    misleading comparisons.
-   It normalizes prices and preserves offer conditions.
-   EMI is calculated from documented assumptions and labelled as an
    estimate.
-   A failed retailer does not crash the entire search.
-   Scrape timestamps and useful logs are stored.
-   Tests and README instructions are provided.

## 13. Optional enhancements after core completion

-   Scheduled refresh with a background job system.
-   Price history chart and price-drop detection.
-   A transparent deal score based on price, offer value, stock, and
    source reliability.
-   Additional retailer adapters.
-   Playwright fallback for permitted pages that genuinely require
    browser rendering.
-   Domain-aware asynchronous scraping with strict concurrency limits.
