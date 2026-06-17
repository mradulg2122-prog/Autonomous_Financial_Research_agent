"""
Tool: sec_filing_search
Searches SEC EDGAR for company filings (10-K, 10-Q, 8-K, etc.)
Extracts risk factors and MD&A sections.
"""
from __future__ import annotations

import re
from typing import Any, Optional

import httpx

from backend.core.config import settings
from backend.core.errors import ToolExecutionError
from backend.core.logging import get_logger
from backend.core.retry import with_retry
from backend.tools.registry import registry

logger = get_logger(__name__)

EDGAR_BASE = "https://efts.sec.gov/LATEST/search-index"
EDGAR_SEARCH = "https://efts.sec.gov/LATEST/search-index?q={query}&dateRange=custom&startdt={start}&enddt={end}&forms={form}"
EDGAR_COMPANY_SEARCH = "https://www.sec.gov/cgi-bin/browse-edgar?company={name}&CIK=&type={form}&dateb=&owner=include&count=10&search_text=&action=getcompany"
EDGAR_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik}.json"
EDGAR_FILING_CONTENT = "https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{file}"


async def _get_company_cik(ticker: str) -> Optional[str]:
    """Look up a company's CIK number by ticker."""
    url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&company={ticker}&type=10-K&dateb=&owner=include&count=5&search_text=&output=atom"
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(url, headers={"User-Agent": "ARA-1 research@ara1.ai"})
        text = resp.text
        # Extract CIK from EDGAR response
        match = re.search(r"CIK=(\d+)", text)
        return match.group(1) if match else None


async def _fetch_recent_filings(cik: str, form_type: str, limit: int = 5) -> list[dict]:
    """Fetch recent filings from SEC EDGAR submissions API."""
    padded_cik = cik.zfill(10)
    url = EDGAR_SUBMISSIONS.format(cik=padded_cik)
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.get(url, headers={"User-Agent": "ARA-1 research@ara1.ai"})
        if resp.status_code != 200:
            return []
        data = resp.json()

    filings = data.get("filings", {}).get("recent", {})
    forms = filings.get("form", [])
    dates = filings.get("filingDate", [])
    accessions = filings.get("accessionNumber", [])
    primary_docs = filings.get("primaryDocument", [])

    results = []
    for i, form in enumerate(forms):
        if form == form_type and len(results) < limit:
            results.append({
                "form": form,
                "date": dates[i] if i < len(dates) else "",
                "accession": accessions[i] if i < len(accessions) else "",
                "primary_doc": primary_docs[i] if i < len(primary_docs) else "",
                "cik": cik,
            })
    return results


async def _extract_section(text: str, section: str) -> str:
    """Extract a named section from a filing (basic heuristic)."""
    patterns = {
        "risk_factors": r"(?i)(Item\s+1A\.?\s+Risk\s+Factors)(.*?)(?=Item\s+1B|Item\s+2|\Z)",
        "mda": r"(?i)(Item\s+7\.?\s+Management.s\s+Discussion)(.*?)(?=Item\s+7A|Item\s+8|\Z)",
        "business": r"(?i)(Item\s+1\.?\s+Business)(.*?)(?=Item\s+1A|Item\s+2|\Z)",
    }
    pattern = patterns.get(section, "")
    if not pattern:
        return ""
    match = re.search(pattern, text, re.DOTALL)
    if match:
        content = match.group(2).strip()
        return content[:5000]  # Limit size
    return ""


@registry.register(
    name="sec_filing_search",
    description=(
        "Search SEC EDGAR for company filings (10-K, 10-Q, 8-K). "
        "Extracts risk factors, MD&A sections, and business descriptions. "
        "Use this to get official regulatory disclosures and financial statements."
    ),
    parameters={
        "type": "object",
        "properties": {
            "ticker": {
                "type": "string",
                "description": "Company stock ticker symbol (e.g., AAPL, MSFT)",
            },
            "form_type": {
                "type": "string",
                "enum": ["10-K", "10-Q", "8-K", "DEF 14A", "S-1"],
                "description": "SEC form type to retrieve",
                "default": "10-K",
            },
            "sections": {
                "type": "array",
                "items": {"type": "string", "enum": ["risk_factors", "mda", "business"]},
                "description": "Sections to extract from the filing",
                "default": ["risk_factors", "mda"],
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of filings to retrieve",
                "default": 3,
            },
        },
        "required": ["ticker"],
    },
    timeout=45.0,
)
@with_retry(service="sec_edgar")
async def sec_filing_search(
    ticker: str,
    form_type: str = "10-K",
    sections: list[str] = None,
    limit: int = 3,
) -> dict[str, Any]:
    """Search and extract SEC filings."""
    if sections is None:
        sections = ["risk_factors", "mda"]

    logger.info("sec_filing_search", ticker=ticker, form_type=form_type)

    # Get CIK
    cik = await _get_company_cik(ticker)
    if not cik:
        return {
            "ticker": ticker,
            "form_type": form_type,
            "filings": [],
            "message": f"Could not find CIK for ticker {ticker}. Company may not be SEC-registered.",
        }

    # Get recent filings
    filings = await _fetch_recent_filings(cik, form_type, limit)
    if not filings:
        return {
            "ticker": ticker,
            "cik": cik,
            "form_type": form_type,
            "filings": [],
            "message": f"No {form_type} filings found for {ticker}",
        }

    results = []
    for filing in filings:
        filing_result: dict[str, Any] = {
            "form": filing["form"],
            "date": filing["date"],
            "accession": filing["accession"],
            "cik": cik,
            "sections": {},
        }

        # Try to fetch and extract sections from the primary doc
        if filing.get("primary_doc"):
            try:
                accession_clean = filing["accession"].replace("-", "")
                doc_url = (
                    f"https://www.sec.gov/Archives/edgar/data/{cik}/"
                    f"{accession_clean}/{filing['primary_doc']}"
                )
                async with httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.get(
                        doc_url,
                        headers={"User-Agent": "ARA-1 research@ara1.ai"},
                    )
                    if resp.status_code == 200:
                        text = resp.text
                        for section in sections:
                            extracted = await _extract_section(text, section)
                            if extracted:
                                filing_result["sections"][section] = extracted
            except Exception as exc:
                logger.warning("sec_doc_fetch_error", error=str(exc))

        results.append(filing_result)

    return {
        "ticker": ticker,
        "cik": cik,
        "form_type": form_type,
        "total_found": len(results),
        "filings": results,
        "source": "SEC EDGAR",
        "source_tier": 1,
    }
