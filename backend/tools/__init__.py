"""
ARA-1 Tools Package
Importing all tool modules triggers registration with the registry.
"""
from backend.tools.registry import registry

# Import all tool modules — each module registers its tools on import
from backend.tools import (
    sec_filing_search,
    financial_data_api,
    earnings_transcript,
    web_search,
    news_search,
    sentiment_analysis,
    peer_comparison,
    vector_db_ops,
    fact_checker,
    calculation_engine,
    company_profile,
    market_data_tool,
    risk_analysis_tool,
    report_generator,
)

__all__ = ["registry"]
