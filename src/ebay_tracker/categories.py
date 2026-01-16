"""eBay category definitions for the category selection wizard."""

MENS_CATEGORIES = {
    57990: "Casual Shirts",
    57991: "Dress Shirts",
    15687: "T-Shirts",
    11483: "Jeans",
    11484: "Pants",
    57988: "Coats & Jackets",
    11511: "Sweaters",
    57989: "Shorts",
    3001: "Suits & Blazers",
    93427: "Shoes",
    137084: "Activewear",
}

WOMENS_CATEGORIES = {
    53159: "Tops & Blouses",
    11554: "Jeans",
    63863: "Pants & Capris",
    63862: "Dresses",
    63866: "Coats & Jackets",
    63864: "Shorts",
    63865: "Skirts",
    63869: "Sweaters",
    3034: "Shoes",
    185101: "Activewear",
}


def get_categories_for_preference(pref: str) -> dict[int, str]:
    """Get category dict based on gender preference."""
    if pref == "mens":
        return MENS_CATEGORIES
    elif pref == "womens":
        return WOMENS_CATEGORIES
    else:  # both
        return {**MENS_CATEGORIES, **WOMENS_CATEGORIES}


def search_categories(query: str, pref: str) -> dict[int, str]:
    """Search categories by keyword."""
    cats = get_categories_for_preference(pref)
    query_lower = query.lower()
    return {k: v for k, v in cats.items() if query_lower in v.lower()}
