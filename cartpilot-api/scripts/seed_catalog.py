#!/usr/bin/env python3
"""Seed product catalog script.

Generates and seeds product catalog for merchants using
Google Product Taxonomy and deterministic generation.

Usage:
    python scripts/seed_catalog.py --mode small
    python scripts/seed_catalog.py --mode full --merchant merchant-a
    python scripts/seed_catalog.py --mode small --all-merchants
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.catalog.service import CatalogService
from app.infrastructure.database import async_session_factory, engine, Base


async def create_tables() -> None:
    """Create database tables if they don't exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def seed_merchant(
    merchant_id: str,
    mode: str,
    clear: bool = True,
) -> dict:
    """Seed catalog for a single merchant.

    Args:
        merchant_id: Merchant ID.
        mode: Catalog size (small/full).
        clear: Whether to clear existing products.

    Returns:
        Seeding result.
    """
    async with async_session_factory() as session:
        service = CatalogService(session)
        result = await service.seed_catalog(
            merchant_id=merchant_id,
            mode=mode,
            clear_existing=clear,
        )
        return result


async def main() -> None:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Seed product catalog for merchants",
    )
    parser.add_argument(
        "--mode",
        choices=["small", "full"],
        default="small",
        help="Catalog size: small (~100 products) or full (~500+ products)",
    )
    parser.add_argument(
        "--merchant",
        default="merchant-a",
        help="Merchant ID to seed (default: merchant-a)",
    )
    parser.add_argument(
        "--all-merchants",
        action="store_true",
        help="Seed all configured merchants (merchant-a and merchant-b)",
    )
    parser.add_argument(
        "--no-clear",
        action="store_true",
        help="Don't clear existing products before seeding",
    )

    args = parser.parse_args()

    print("=" * 60)
    print("CartPilot Catalog Seeder")
    print("=" * 60)
    print(f"Mode: {args.mode}")
    print(f"Clear existing: {not args.no_clear}")
    print()

    # Create tables
    print("Creating database tables...")
    await create_tables()
    print("Tables ready.")
    print()

    # Determine merchants to seed
    if args.all_merchants:
        merchants = ["merchant-a", "merchant-b"]
    else:
        merchants = [args.merchant]

    # Seed each merchant
    for merchant_id in merchants:
        print(f"Seeding catalog for {merchant_id}...")
        
        try:
            result = await seed_merchant(
                merchant_id=merchant_id,
                mode=args.mode,
                clear=not args.no_clear,
            )

            print(f"  ✓ Deleted: {result['deleted']} existing products")
            print(f"  ✓ Created: {result['products_created']} products")
            print(f"  ✓ Variants: {result['variants_created']}")
            print(f"  ✓ Categories: {result['categories_used']}")
            print(f"  ✓ Brands: {result['brands_used']}")
            print()
        except Exception as e:
            print(f"  ✗ Error: {e}")
            raise

    print("=" * 60)
    print("Seeding complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
