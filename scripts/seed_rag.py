"""
Offline batch import script for seeding the RAG vector store.

Usage:
    python scripts/seed_rag.py --file data/products.csv --image-dir images
    python scripts/seed_rag.py --file data/products.xlsx --batch-size 10

CSV/Excel required columns:
    product_id, category, style, color
Optional columns:
    material (enriches TF-IDF text embedding)
    image_url 或 image_path (product reference image)
    description (used to enrich text embedding)

Example CSV:
    product_id,category,style,color,material,image_path,description
    SKU001,maxi_dress,bohemian,pink,chiffon,SKU001.jpg,Flowing pink bohemian dress
"""

import asyncio
import csv
import io
import logging
import os
import sys
from pathlib import Path

# Allow running from project root without installing the package
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("JWT_SECRET", "seed-script")
os.environ.setdefault("OPENROUTER_API_KEY", os.environ.get("OPENROUTER_API_KEY", ""))

import mediaforge.config
mediaforge.config.clear_settings_cache()

from mediaforge.config import get_settings
from mediaforge.rag.factory import get_vector_store
from mediaforge.rag.ingest import embed_and_upsert

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("seed_rag")

REQUIRED_COLS = {"product_id", "category", "style", "color"}


def _parse_csv(content: bytes) -> list[dict]:
    text = content.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        raise ValueError("CSV is empty")
    missing = REQUIRED_COLS - set(rows[0].keys())
    if missing:
        raise ValueError(f"CSV missing required columns: {missing}")
    return rows


def _parse_excel(content: bytes) -> list[dict]:
    try:
        import openpyxl
    except ImportError:
        raise RuntimeError("openpyxl is required for Excel support: pip install openpyxl")
    import openpyxl
    wb = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    ws = wb.active
    rows_iter = ws.iter_rows(values_only=True)
    headers = [str(h).strip() for h in next(rows_iter)]
    missing = REQUIRED_COLS - set(headers)
    if missing:
        raise ValueError(f"Excel missing required columns: {missing}")
    rows = [dict(zip(headers, row)) for row in rows_iter if any(c is not None for c in row)]
    wb.close()
    return rows


def parse_file(path: Path) -> list[dict]:
    content = path.read_bytes()
    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".xls"):
        return _parse_excel(content)
    return _parse_csv(content)


async def seed(file_path: Path, batch_size: int, image_dir: Path | None) -> None:
    settings = get_settings()

    if not settings.dashscope_api_key and not settings.openrouter_api_key:
        log.error("DASHSCOPE_API_KEY or OPENROUTER_API_KEY must be set. Export before running.")
        sys.exit(1)

    image_base_dir: str | None = None
    if image_dir is not None:
        image_base_dir = str(image_dir.expanduser().resolve())
        log.info("Image base directory: %s", image_base_dir)
        if not Path(image_base_dir).is_dir():
            log.error("Image directory does not exist: %s", image_base_dir)
            sys.exit(1)

    log.info("Parsing file: %s", file_path)
    rows = parse_file(file_path)
    log.info("Found %d products", len(rows))

    # Deduplicate by product_id
    seen: set[str] = set()
    deduped = []
    for row in rows:
        pid = str(row.get("product_id", "")).strip()
        if pid and pid not in seen:
            seen.add(pid)
            deduped.append(row)
    if len(deduped) < len(rows):
        log.warning("Removed %d duplicate product_id rows", len(rows) - len(deduped))
    rows = deduped

    # Pre-flight: verify every image_path resolves to an existing file
    missing_images = 0
    if image_base_dir:
        for row in rows:
            rel = str(row.get("image_path") or row.get("image_url") or "").strip()
            if rel and not rel.startswith(("http://", "https://")):
                if not (Path(image_base_dir) / rel).exists():
                    log.warning("Image file not found: %s", Path(image_base_dir) / rel)
                    missing_images += 1
        if missing_images:
            log.warning("%d image(s) missing; those rows will be imported without image vectors.", missing_images)

    count = await embed_and_upsert(rows, batch_size=batch_size, image_base_dir=image_base_dir)
    log.info("Done. %d products imported.", count)

    vector_store = get_vector_store()
    health = await vector_store.health()
    log.info("Vector store health: %s", health)


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Seed MediaForge RAG vector store from CSV/Excel")
    parser.add_argument("--file", required=True, type=Path, help="Path to CSV or Excel file")
    parser.add_argument(
        "--image-dir",
        type=Path,
        default=None,
        help="Base directory for relative image_path values in the CSV (e.g. ./images).",
    )
    parser.add_argument("--batch-size", type=int, default=5, help="Embedding batch size (default: 5)")
    args = parser.parse_args()

    if not args.file.exists():
        log.error("File not found: %s", args.file)
        sys.exit(1)

    asyncio.run(seed(args.file, args.batch_size, args.image_dir))


if __name__ == "__main__":
    main()
