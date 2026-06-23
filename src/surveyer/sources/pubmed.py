"""PubMed source adapter. NCBI E-utilities: esearch + efetch (XML)."""

from __future__ import annotations

import os
import re
import xml.etree.ElementTree as ET

import structlog

from surveyer.models import Record, SearchResult
from surveyer.sources.base import HttpClient, coerce_int

log = structlog.get_logger()

ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

# cap per call
PAGE_SIZE = 200
BATCH_SIZE = 200


def make_pubmed_params() -> dict[str, str]:
    """Shared NCBI params: the tool id, plus api_key for a higher rate limit."""
    params = {"tool": "surveyer"}
    key = os.environ.get("NCBI_API_KEY")
    if key:
        params["api_key"] = key
    return params


def _author_name(author: ET.Element) -> str | None:
    """Format one Author element as 'ForeName LastName' (or just LastName)."""
    last = author.findtext("LastName")
    if not last:
        return None
    fore = author.findtext("ForeName") or author.findtext("Initials")
    return f"{fore} {last}" if fore else last


def _abstract(article: ET.Element) -> str | None:
    """Join AbstractText nodes, prefixing structured sections with their Label."""
    parts: list[str] = []
    for node in article.findall("./Abstract/AbstractText"):
        text = "".join(node.itertext()).strip()
        if not text:
            continue
        label = node.get("Label")
        parts.append(f"{label}: {text}" if label else text)
    return "\n".join(parts) if parts else None


def _year(article: ET.Element) -> int | None:
    """Extract the publication year from PubDate/Year or a MedlineDate string."""
    pubdate = article.find("./Journal/JournalIssue/PubDate")
    if pubdate is None:
        return None
    year = pubdate.findtext("Year")
    if year and year.isdigit():
        return int(year)
    match = re.search(r"\d{4}", pubdate.findtext("MedlineDate") or "")
    return int(match.group()) if match else None


def parse_pubmed(xml_text: str) -> list[Record]:
    """Parse a PubMed efetch XML response into a list of Records."""
    root = ET.fromstring(xml_text)
    out: list[Record] = []
    for art in root.findall(".//PubmedArticle"):
        citation = art.find("MedlineCitation")
        article = citation.find("Article") if citation is not None else None
        if citation is None or article is None:
            continue
        pmid = citation.findtext("PMID")
        doi = next(
            (
                (aid.text or "").strip() or None
                for aid in art.findall("./PubmedData/ArticleIdList/ArticleId")
                if aid.get("IdType") == "doi"
            ),
            None,
        )
        authors = [
            name
            for a in article.findall("./AuthorList/Author")
            if (name := _author_name(a))
        ]
        keywords = [
            d.text.strip()
            for d in citation.findall("./MeshHeadingList/MeshHeading/DescriptorName")
            if d.text and d.text.strip()
        ]
        title_el = article.find("ArticleTitle")
        title = "".join(title_el.itertext()) if title_el is not None else ""
        out.append(
            Record(
                title=title.rstrip(". "),
                doi=doi,
                authors=authors,
                year=_year(article),
                venue=article.findtext("./Journal/Title")
                or article.findtext("./Journal/ISOAbbreviation"),
                abstract=_abstract(article),
                keywords=keywords,
                url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else None,
            )
        )
    return out


class PubMedSource:
    """PubMed bibliographic source adapter."""

    name = "pubmed"

    def __init__(self, client: HttpClient, *, year_min=None, year_max=None) -> None:
        """Initialise the PubMed source with the HTTP client and year bounds."""
        self.client = client
        self.year_min = year_min
        self.year_max = year_max

    def _esearch(self, terms: str, max_results: int) -> tuple[list[str], int | None]:
        """Collect PMIDs from esearch (paginating via retstart) and the match total."""
        ids: list[str] = []
        api_total: int | None = None
        retstart = 0
        while len(ids) < max_results:
            retmax = min(max_results - len(ids), PAGE_SIZE)
            params: dict = {
                "db": "pubmed",
                "term": terms,
                "retmode": "json",
                "retmax": retmax,
                "retstart": retstart,
                **make_pubmed_params(),
            }
            if self.year_min or self.year_max:
                params["datetype"] = "pdat"
                if self.year_min:
                    params["mindate"] = self.year_min
                if self.year_max:
                    params["maxdate"] = self.year_max
            raw = self.client.get_json(ESEARCH, params=params)
            result = raw.get("esearchresult", {})
            if api_total is None:
                api_total = coerce_int(result.get("count"))
            batch = result.get("idlist", [])
            ids.extend(batch)
            if len(batch) < retmax:
                break
            retstart += retmax
        return ids[:max_results], api_total

    def search(self, terms: str, *, max_results: int) -> SearchResult:
        """Search PubMed via esearch then efetch, returning records and API total."""
        ids, api_total = self._esearch(terms, max_results)
        out: list[Record] = []
        for start in range(0, len(ids), BATCH_SIZE):
            chunk = ids[start : start + BATCH_SIZE]
            params = {
                "db": "pubmed",
                "id": ",".join(chunk),
                "rettype": "abstract",
                "retmode": "xml",
                **make_pubmed_params(),
            }
            xml_text = self.client.get_text(EFETCH, params=params)
            if xml_text:
                out.extend(parse_pubmed(xml_text))
        return SearchResult(records=out[:max_results], api_total=api_total)
