"""Tests for Google Product Taxonomy parser."""

import pytest

from app.catalog.taxonomy import Category, TaxonomyParser


class TestCategory:
    """Tests for Category dataclass."""

    def test_category_path_parts(self) -> None:
        """Category path can be split into parts."""
        category = Category(
            id=328,
            name="Laptops",
            full_path="Electronics > Computers > Laptops",
            level=3,
        )
        assert category.path_parts == ["Electronics", "Computers", "Laptops"]

    def test_root_category(self) -> None:
        """Root category has level 1."""
        category = Category(
            id=537,
            name="Electronics",
            full_path="Electronics",
            level=1,
        )
        assert category.level == 1
        assert category.parent_id is None


class TestTaxonomyParser:
    """Tests for TaxonomyParser."""

    @pytest.fixture
    def parser(self) -> TaxonomyParser:
        """Create parser with embedded taxonomy."""
        parser = TaxonomyParser()
        parser.parse_embedded()
        return parser

    def test_parse_embedded(self, parser: TaxonomyParser) -> None:
        """Embedded taxonomy is parsed."""
        categories = parser.get_all()
        assert len(categories) > 0

    def test_get_by_id(self, parser: TaxonomyParser) -> None:
        """Categories can be found by ID."""
        category = parser.get_by_id(537)  # Electronics
        assert category is not None
        assert category.name == "Electronics"

    def test_get_by_id_not_found(self, parser: TaxonomyParser) -> None:
        """Non-existent ID returns None."""
        category = parser.get_by_id(999999)
        assert category is None

    def test_get_by_name(self, parser: TaxonomyParser) -> None:
        """Categories can be found by name."""
        categories = parser.get_by_name("Electronics")
        assert len(categories) >= 1
        assert categories[0].name == "Electronics"

    def test_get_root_categories(self, parser: TaxonomyParser) -> None:
        """Root categories are level 1."""
        roots = parser.get_root_categories()
        assert len(roots) > 0
        assert all(c.level == 1 for c in roots)

    def test_get_leaf_categories(self, parser: TaxonomyParser) -> None:
        """Leaf categories have no children."""
        leaves = parser.get_leaf_categories()
        assert len(leaves) > 0
        assert all(len(c.children) == 0 for c in leaves)

    def test_search(self, parser: TaxonomyParser) -> None:
        """Categories can be searched by name."""
        results = parser.search("laptop")
        assert len(results) >= 1
        assert any("Laptop" in c.name for c in results)

    def test_search_case_insensitive(self, parser: TaxonomyParser) -> None:
        """Search is case-insensitive."""
        results1 = parser.search("ELECTRONICS")
        results2 = parser.search("electronics")
        assert len(results1) == len(results2)

    def test_parent_child_relationships(self, parser: TaxonomyParser) -> None:
        """Parent-child relationships are established."""
        laptops = parser.get_by_id(328)  # Laptops
        computers = parser.get_by_id(543)  # Computers
        
        assert laptops is not None
        assert computers is not None
        assert laptops.parent_id == computers.id
        assert laptops in computers.children
