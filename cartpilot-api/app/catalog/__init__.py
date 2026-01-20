"""Product Catalog Service.

Provides product generation, taxonomy management, and catalog operations
using Google Product Taxonomy for realistic category structure.
"""

from app.catalog.generator import GeneratorConfig, ProductGenerator
from app.catalog.models import Product, ProductVariant
from app.catalog.repository import ProductRepository
from app.catalog.service import CatalogService, PaginatedResult, PaginationParams, ProductFilter
from app.catalog.taxonomy import Category, TaxonomyParser

__all__ = [
    # Taxonomy
    "Category",
    "TaxonomyParser",
    # Models
    "Product",
    "ProductVariant",
    # Generator
    "GeneratorConfig",
    "ProductGenerator",
    # Repository
    "ProductRepository",
    # Service
    "CatalogService",
    "PaginatedResult",
    "PaginationParams",
    "ProductFilter",
]
