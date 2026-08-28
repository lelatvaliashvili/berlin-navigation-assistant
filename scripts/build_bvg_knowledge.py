import argparse
import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import urldefrag, urljoin
import requests
import yaml
from bs4 import BeautifulSoup
from markdownify import markdownify


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_CONFIG_PATH = PROJECT_ROOT / "config" / "sources.yaml"
DATA_DIR = PROJECT_ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
DRAFT_DIR = DATA_DIR / "curation_drafts"
DISCOVERY_FILE = DATA_DIR / "ticket_urls.json"
BASE_URL = "https://www.bvg.de"
ALL_TICKETS_URL = (
    "https://www.bvg.de/en/subscriptions-and-tickets/all-tickets"
)


def load_source_config() -> dict:
    with SOURCE_CONFIG_PATH.open(
        "r",
        encoding="utf-8",
    ) as file:
        return yaml.safe_load(file)


SOURCE_CONFIG = load_source_config()


def create_session() -> requests.Session:
    session = requests.Session()

    session.headers.update({
        "User-Agent": (
            "llm-guardrails-mobility/0.1 "
            "(educational prototype; low-volume requests)"
        )
    })

    return session


def fetch_html(
    session: requests.Session,
    url: str,
) -> str:
    response = session.get(
        url,
        timeout=20,
    )

    response.raise_for_status()

    return response.text


def discover_ticket_urls(
    session: requests.Session,
) -> list[dict[str, str]]:
    """
    Discover individual ticket pages linked from BVG's All Tickets page.
    This only DISCOVERS URLs. It does not add them to the knowledge base.
    """

    html = fetch_html(session, ALL_TICKETS_URL)

    soup = BeautifulSoup(html, "html.parser")

    discovered: dict[str, dict[str, str]] = {}

    for link in soup.find_all("a", href=True):
        href = link["href"]

        full_url = urljoin(BASE_URL, href)

        # Remove #fragment portions.
        full_url, _ = urldefrag(full_url)

        if (
            "/en/subscriptions-and-tickets/all-tickets/"
            not in full_url
        ):
            continue

        label = " ".join(link.stripped_strings).strip()

        if not label:
            label = full_url.rsplit("/", 1)[-1]

        discovered[full_url] = {
            "title": label,
            "url": full_url,
        }

    return sorted(
        discovered.values(),
        key=lambda item: item["url"],
    )


def extract_main_content(html: str) -> str:
    """
    Extract the main page content and convert it to Markdown.

    Output is still a DRAFT and requires human review.
    """

    soup = BeautifulSoup(html, "html.parser")

    # Prefer actual main content rather than whole page.
    main = (
        soup.find("main")
        or soup.find("article")
        or soup.body
    )

    if main is None:
        raise ValueError("Could not find page content.")

    # Remove common non-knowledge elements.
    for tag in main.find_all([
        "script",
        "style",
        "noscript",
        "svg",
        "form",
        "button",
        "nav",
        "footer",
    ]):
        tag.decompose()

    markdown = markdownify(
        str(main),
        heading_style="ATX",
        bullets="-",
    )

    # Avoid huge gaps in generated Markdown.
    markdown = re.sub(
        r"\n{3,}",
        "\n\n",
        markdown,
    )

    return markdown.strip()


def build_frontmatter(
    *,
    title: str,
    category: str,
    topic: str,
    source_url: str,
    curation: str,
    review_status: str,
) -> dict:
    """Build consistent KB metadata."""

    return {
        "title": title,
        "category": category,
        "topic": topic,
        "source_name": "BVG",
        "source_urls": [source_url],
        "source_language": "en",
        "content_language": "en",
        "retrieved_at": date.today().isoformat(),
        "curation": curation,
        "review_status": review_status,
    }


def write_markdown(
    path: Path,
    metadata: dict,
    body: str,
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    yaml_metadata = yaml.safe_dump(
        metadata,
        sort_keys=False,
        allow_unicode=True,
    ).strip()

    content = (
        "---\n"
        f"{yaml_metadata}\n"
        "---\n\n"
        f"{body.strip()}\n"
    )

    path.write_text(
        content,
        encoding="utf-8",
    )


def inspect_source(
    session: requests.Session,
    source_key: str,
) -> None:
    """
    Fetch a configured source and print a preview.

    Nothing is written to the final KB.
    """

    source = SOURCE_CONFIG[source_key]

    html = fetch_html(
        session,
        source["url"],
    )

    body = extract_main_content(html)

    print("=" * 80)
    print(f"SOURCE: {source_key}")
    print(f"TITLE:  {source['title']}")
    print(f"URL:    {source['url']}")
    print(f"CHARS:  {len(body)}")
    print("=" * 80)

    print(body[:3000])

    if len(body) > 3000:
        print("\n... [preview truncated] ...")


def create_draft(
    session: requests.Session,
    source_key: str,
) -> Path:
    """
    Fetch a selected source and create a local curation draft
    """
    source = SOURCE_CONFIG[source_key]

    html = fetch_html(
        session,
        source["url"],
    )

    body = extract_main_content(html)

    metadata = build_frontmatter(
        title=source["title"],
        category=source["category"],
        topic=source["topic"],
        source_url=source["url"],
        curation="automated_extraction",
        review_status="needs_review",
    )

    output_path = (
        DRAFT_DIR
        / f"{source_key}.draft.md"
    )

    write_markdown(
        output_path,
        metadata,
        body,
    )

    return output_path


def run_discovery(
    session: requests.Session,
) -> None:
    urls = discover_ticket_urls(session)

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    DISCOVERY_FILE.write_text(
        json.dumps(
            urls,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(
        f"Discovered {len(urls)} ticket URLs.\n"
    )

    for item in urls:
        print(
            f"{item['title']}\n"
            f"  {item['url']}\n"
        )

    print(
        f"Saved discovery results to:\n"
        f"{DISCOVERY_FILE}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="BVG knowledge-source utility"
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    subparsers.add_parser(
        "discover",
        help="Discover ticket URLs from the BVG All Tickets page",
    )

    inspect_parser = subparsers.add_parser(
        "inspect",
        help="Fetch and preview one configured source",
    )

    inspect_parser.add_argument(
        "source",
        choices=SOURCE_CONFIG.keys(),
    )

    draft_parser = subparsers.add_parser(
        "draft",
        help="Generate a local Markdown curation draft",
    )

    draft_parser.add_argument(
        "source",
        choices=SOURCE_CONFIG.keys(),
    )

    args = parser.parse_args()

    session = create_session()

    if args.command == "discover":
        run_discovery(session)

    elif args.command == "inspect":
        inspect_source(session, args.source)

    elif args.command == "draft":
        output_path = create_draft(session, args.source)

        print(
            "Draft created:\n"
            f"{output_path}\n\n"
            "Review and paraphrase it before moving "
            "content into knowledge_LT/."
        )


if __name__ == "__main__":
    main()