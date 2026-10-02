"""Manual single-page demo: python -m server.crawler.demo URL."""
import argparse
from pathlib import Path

from .crawl import crawl_url
from .fetch import CrawlError
from .storage import DEFAULT_OUTPUT_DIR, url_filename


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="HTTP(S) webpage to fetch")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args()
    try:
        document = crawl_url(args.url, output_dir=args.output_dir, timeout=args.timeout)
    except (CrawlError, ValueError, OSError) as exc:
        parser.exit(1, f"Crawl failed: {exc}\n")
    print(f"Title: {document['title']}")
    print(f"Extracted {len(document['text'])} characters")
    if document["is_duplicate"]:
        print("Skipped: duplicate normalized content")
    else:
        print(f"Saved: {args.output_dir / url_filename(document['url'])}")


if __name__ == "__main__":
    main()
