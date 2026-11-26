import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
    DEBUG = os.getenv("DEBUG", "True").lower() == "true"

    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Scraper Endpoints
    CROMA_BASE_URL = os.getenv("CROMA_BASE_URL", "https://www.croma.com")
    CROMA_API_URL = os.getenv("CROMA_API_URL", "https://api.croma.com")

    VIJAY_SALES_BASE_URL = os.getenv("VIJAY_SALES_BASE_URL", "https://www.vijaysales.com")
    VIJAY_SALES_CATEGORY_URL = os.getenv(
        "VIJAY_SALES_CATEGORY_URL", "https://www.vijaysales.com/c/iphones"
    )

    RELIANCE_DIGITAL_BASE_URL = os.getenv(
        "RELIANCE_DIGITAL_BASE_URL", "https://www.reliancedigital.in"
    )
    RELIANCE_DIGITAL_CATEGORY_URL = os.getenv(
        "RELIANCE_DIGITAL_CATEGORY_URL",
        "https://www.reliancedigital.in/smartphones/c/S101710",
    )
