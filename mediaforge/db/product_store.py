from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import uuid

from sqlalchemy.dialects.postgresql import insert

from mediaforge.db.engine import get_engine
from mediaforge.db.tables import ProductTable


def _decimal_or_none(value) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except InvalidOperation:
        return None


def build_product_record(
    row: dict,
    *,
    document_id: str,
    tenant_id: str | None,
    visibility: str,
    source_type: str,
    search_text: str,
    image_url: str = "",
    index_status: str = "pending",
    index_error: str | None = None,
) -> dict:
    now = datetime.now(timezone.utc)
    return {
        "document_id": document_id,
        "tenant_id": uuid.UUID(tenant_id) if tenant_id else None,
        "sku_code": str(row["product_id"]).strip(),
        "visibility": visibility,
        "source_type": source_type,
        "category": str(row.get("category", "")).strip(),
        "style": str(row.get("style", "")).strip(),
        "color": str(row.get("color", "")).strip(),
        "material": str(row.get("material", "")).strip(),
        "season": str(row.get("season", "")).strip(),
        "description": str(row.get("description", "")).strip(),
        "sales_count": int(row.get("sales_count") or 0),
        "price": _decimal_or_none(row.get("price")),
        "image_url": image_url,
        "search_text": search_text,
        "index_status": index_status,
        "index_error": index_error,
        "indexed_at": now if index_status == "indexed" else None,
        "created_at": now,
        "updated_at": now,
    }


async def upsert_products(records: list[dict]) -> None:
    if not records:
        return
    table = ProductTable.__table__
    statement = insert(table).values(records)
    excluded = statement.excluded
    statement = statement.on_conflict_do_update(
        index_elements=[table.c.document_id],
        set_={
            "tenant_id": excluded.tenant_id,
            "sku_code": excluded.sku_code,
            "visibility": excluded.visibility,
            "source_type": excluded.source_type,
            "category": excluded.category,
            "style": excluded.style,
            "color": excluded.color,
            "material": excluded.material,
            "season": excluded.season,
            "description": excluded.description,
            "sales_count": excluded.sales_count,
            "price": excluded.price,
            "image_url": excluded.image_url,
            "search_text": excluded.search_text,
            "index_status": excluded.index_status,
            "index_error": excluded.index_error,
            "indexed_at": excluded.indexed_at,
            "updated_at": excluded.updated_at,
        },
    )
    async with get_engine().begin() as connection:
        await connection.execute(statement)
