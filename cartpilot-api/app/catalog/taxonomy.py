"""Google Product Taxonomy parser.

Google Product Taxonomy is a hierarchical categorization system used for
product classification. This module provides parsing and category management.

Taxonomy format example:
    1 - Animals & Pet Supplies
    2 - Animals & Pet Supplies > Live Animals
    3 - Animals & Pet Supplies > Pet Supplies
    4 - Animals & Pet Supplies > Pet Supplies > Bird Supplies
"""

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Category:
    """A product category from Google Product Taxonomy.

    Attributes:
        id: Category ID (from taxonomy file).
        name: Category name (leaf part).
        full_path: Full category path (e.g., "Electronics > Computers > Laptops").
        parent_id: ID of parent category (None for root).
        level: Depth in taxonomy tree (1 = root).
    """

    id: int
    name: str
    full_path: str
    parent_id: int | None = None
    level: int = 1
    children: list["Category"] = field(default_factory=list, repr=False)

    @property
    def path_parts(self) -> list[str]:
        """Get list of path components.

        Returns:
            List of category names from root to this category.
        """
        return [part.strip() for part in self.full_path.split(">")]


class TaxonomyParser:
    """Parser for Google Product Taxonomy files.

    The taxonomy file contains lines in format:
        ID - Category > Subcategory > Sub-subcategory

    Example usage:
        parser = TaxonomyParser()
        categories = parser.parse_file("taxonomy.txt")
        electronics = parser.get_by_name("Electronics")
    """

    # Embedded subset of Google Product Taxonomy for offline use
    # Full taxonomy: https://www.google.com/basepages/producttype/taxonomy-with-ids.en-US.txt
    EMBEDDED_TAXONOMY = '''
1 - Animals & Pet Supplies
3 - Animals & Pet Supplies > Pet Supplies
4 - Animals & Pet Supplies > Pet Supplies > Bird Supplies
5 - Animals & Pet Supplies > Pet Supplies > Cat Supplies
6 - Animals & Pet Supplies > Pet Supplies > Dog Supplies
222 - Apparel & Accessories
1604 - Apparel & Accessories > Clothing
5322 - Apparel & Accessories > Clothing > Shirts & Tops
1581 - Apparel & Accessories > Clothing > Pants
2271 - Apparel & Accessories > Clothing > Dresses
1594 - Apparel & Accessories > Clothing > Outerwear
5182 - Apparel & Accessories > Clothing > Outerwear > Coats & Jackets
167 - Apparel & Accessories > Shoes
178 - Arts & Entertainment
499713 - Arts & Entertainment > Hobbies & Creative Arts
216 - Baby & Toddler
537 - Electronics
264 - Electronics > Audio
3622 - Electronics > Audio > Headphones
505766 - Electronics > Audio > Speakers
543 - Electronics > Computers
5254 - Electronics > Computers > Desktop Computers
328 - Electronics > Computers > Laptops
1928 - Electronics > Computers > Tablets
2082 - Electronics > Mobile Phones
3356 - Electronics > Video Game Consoles
412 - Food, Beverages & Tobacco
422 - Food, Beverages & Tobacco > Beverages
2887 - Food, Beverages & Tobacco > Food Items
436 - Furniture
6356 - Furniture > Beds & Accessories
443 - Furniture > Chairs
442 - Furniture > Tables
451 - Health & Beauty
2915 - Health & Beauty > Personal Care
469 - Home & Garden
500040 - Home & Garden > Home Decor
2334 - Home & Garden > Kitchen & Dining
536 - Luggage & Bags
110 - Luggage & Bags > Backpacks
100 - Office Supplies
922 - Office Supplies > Writing Instruments
632 - Software
783 - Sporting Goods
499844 - Sporting Goods > Exercise & Fitness
1011 - Sporting Goods > Outdoor Recreation
772 - Toys & Games
1253 - Toys & Games > Games
1266 - Toys & Games > Games > Board Games
2743 - Toys & Games > Games > Video Games
3867 - Toys & Games > Puzzles
1239 - Toys & Games > Toys
2546 - Vehicles & Parts
'''.strip()

    def __init__(self) -> None:
        """Initialize parser with empty category storage."""
        self._categories: dict[int, Category] = {}
        self._by_name: dict[str, list[Category]] = {}
        self._root_categories: list[Category] = []

    def parse_embedded(self) -> list[Category]:
        """Parse embedded taxonomy subset.

        Returns:
            List of all categories.
        """
        return self._parse_lines(self.EMBEDDED_TAXONOMY.splitlines())

    def parse_file(self, path: str | Path) -> list[Category]:
        """Parse taxonomy from file.

        Args:
            path: Path to taxonomy file.

        Returns:
            List of all categories.
        """
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
        return self._parse_lines(lines)

    def _parse_lines(self, lines: list[str]) -> list[Category]:
        """Parse taxonomy from lines.

        Args:
            lines: Lines from taxonomy file.

        Returns:
            List of all categories.
        """
        self._categories.clear()
        self._by_name.clear()
        self._root_categories.clear()

        # First pass: create all categories
        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            # Parse "ID - Category > Subcategory > ..."
            if " - " not in line:
                continue

            id_part, path_part = line.split(" - ", 1)
            try:
                cat_id = int(id_part.strip())
            except ValueError:
                continue

            full_path = path_part.strip()
            parts = [p.strip() for p in full_path.split(">")]
            name = parts[-1]
            level = len(parts)

            category = Category(
                id=cat_id,
                name=name,
                full_path=full_path,
                level=level,
            )
            self._categories[cat_id] = category

            # Index by name
            if name not in self._by_name:
                self._by_name[name] = []
            self._by_name[name].append(category)

        # Second pass: establish parent-child relationships
        for category in self._categories.values():
            if category.level == 1:
                self._root_categories.append(category)
            else:
                # Find parent by path
                parent_path = " > ".join(category.path_parts[:-1])
                for potential_parent in self._categories.values():
                    if potential_parent.full_path == parent_path:
                        category.parent_id = potential_parent.id
                        potential_parent.children.append(category)
                        break

        return list(self._categories.values())

    def get_by_id(self, category_id: int) -> Category | None:
        """Get category by ID.

        Args:
            category_id: Category ID.

        Returns:
            Category if found, None otherwise.
        """
        return self._categories.get(category_id)

    def get_by_name(self, name: str) -> list[Category]:
        """Get categories by name.

        Multiple categories can have the same name at different levels.

        Args:
            name: Category name to search.

        Returns:
            List of matching categories.
        """
        return self._by_name.get(name, [])

    def get_root_categories(self) -> list[Category]:
        """Get top-level categories.

        Returns:
            List of root categories.
        """
        return self._root_categories

    def get_all(self) -> list[Category]:
        """Get all categories.

        Returns:
            List of all categories.
        """
        return list(self._categories.values())

    def get_leaf_categories(self) -> list[Category]:
        """Get categories with no children (leaf nodes).

        These are the most specific categories, best for product assignment.

        Returns:
            List of leaf categories.
        """
        return [c for c in self._categories.values() if not c.children]

    def search(self, query: str) -> list[Category]:
        """Search categories by name (case-insensitive).

        Args:
            query: Search query.

        Returns:
            List of matching categories.
        """
        query_lower = query.lower()
        return [
            c for c in self._categories.values()
            if query_lower in c.name.lower() or query_lower in c.full_path.lower()
        ]
