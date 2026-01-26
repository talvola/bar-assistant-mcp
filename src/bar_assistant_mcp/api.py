"""Bar Assistant API Client."""

import httpx
from typing import Any


class BarAssistantAPI:
    """HTTP client for Bar Assistant API."""

    def __init__(self, base_url: str, api_token: str, bar_id: int = 1):
        self.base_url = base_url.rstrip("/")
        self.bar_id = bar_id
        self.client = httpx.Client(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {api_token}",
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Bar-Assistant-Bar-Id": str(bar_id),
            },
            timeout=30.0,
        )

    def _request(
        self,
        method: str,
        endpoint: str,
        params: dict | None = None,
        json: dict | None = None,
        include_bar: bool = True,
    ) -> dict[str, Any]:
        """Make an API request."""
        if params is None:
            params = {}

        response = self.client.request(method, endpoint, params=params, json=json)
        response.raise_for_status()
        return response.json()

    def get(
        self, endpoint: str, params: dict | None = None, include_bar: bool = True
    ) -> dict[str, Any]:
        return self._request("GET", endpoint, params=params, include_bar=include_bar)

    def post(
        self,
        endpoint: str,
        json: dict | None = None,
        params: dict | None = None,
        include_bar: bool = True,
    ) -> dict[str, Any]:
        return self._request(
            "POST", endpoint, params=params, json=json, include_bar=include_bar
        )

    def put(
        self,
        endpoint: str,
        json: dict | None = None,
        params: dict | None = None,
        include_bar: bool = True,
    ) -> dict[str, Any]:
        return self._request(
            "PUT", endpoint, params=params, json=json, include_bar=include_bar
        )

    def delete(
        self, endpoint: str, params: dict | None = None, include_bar: bool = True
    ) -> dict[str, Any]:
        return self._request("DELETE", endpoint, params=params, include_bar=include_bar)

    # ===== Cocktails =====

    def list_cocktails(
        self,
        limit: int = 25,
        page: int = 1,
        filter_favorites: bool | None = None,
        filter_tag: str | None = None,
        filter_ingredient: int | None = None,
        filter_method: int | None = None,
        filter_glass: int | None = None,
        sort: str | None = None,
    ) -> dict[str, Any]:
        """List cocktails with optional filters."""
        params: dict[str, Any] = {"per_page": limit, "page": page}
        if filter_favorites is not None:
            params["filter[favorites]"] = "1" if filter_favorites else "0"
        if filter_tag:
            params["filter[tag_id]"] = filter_tag
        if filter_ingredient:
            params["filter[ingredient_id]"] = filter_ingredient
        if filter_method:
            params["filter[method_id]"] = filter_method
        if filter_glass:
            params["filter[glass_id]"] = filter_glass
        if sort:
            params["sort"] = sort
        return self.get("/api/cocktails", params=params)

    def get_cocktail(self, id_or_slug: str | int) -> dict[str, Any]:
        """Get a specific cocktail by ID or slug."""
        return self.get(f"/api/cocktails/{id_or_slug}")

    def search_cocktails(self, query: str, limit: int = 10) -> dict[str, Any]:
        """Search cocktails by name."""
        params = {"filter[name]": query, "per_page": limit}
        return self.get("/api/cocktails", params=params)

    def create_cocktail(self, cocktail_data: dict[str, Any]) -> dict[str, Any]:
        """Create a new cocktail."""
        return self.post("/api/cocktails", json=cocktail_data)

    def update_cocktail(self, id_or_slug: str | int, cocktail_data: dict[str, Any]) -> dict[str, Any]:
        """Update an existing cocktail."""
        return self.put(f"/api/cocktails/{id_or_slug}", json=cocktail_data)

    def delete_cocktail(self, id_or_slug: str | int) -> dict[str, Any]:
        """Delete a cocktail."""
        return self.delete(f"/api/cocktails/{id_or_slug}")

    def get_makeable_cocktails(self, user_id: int = 1) -> dict[str, Any]:
        """Get cocktails that can be made with shelf ingredients."""
        return self.get(f"/api/users/{user_id}/cocktails")

    def get_favorite_cocktails(self, user_id: int = 1) -> dict[str, Any]:
        """Get user's favorite cocktails."""
        return self.get(f"/api/users/{user_id}/cocktails/favorites")

    # ===== Ingredients =====

    def list_ingredients(
        self,
        limit: int = 50,
        page: int = 1,
        filter_category: int | None = None,
        filter_on_shelf: bool | None = None,
        sort: str | None = None,
    ) -> dict[str, Any]:
        """List ingredients with optional filters."""
        params: dict[str, Any] = {"per_page": limit, "page": page}
        if filter_category:
            params["filter[category_id]"] = filter_category
        if filter_on_shelf is not None:
            params["filter[on_shelf]"] = "1" if filter_on_shelf else "0"
        if sort:
            params["sort"] = sort
        return self.get("/api/ingredients", params=params)

    def get_ingredient(self, id_or_slug: str | int) -> dict[str, Any]:
        """Get a specific ingredient by ID or slug."""
        return self.get(f"/api/ingredients/{id_or_slug}")

    def search_ingredients(self, query: str, limit: int = 10) -> dict[str, Any]:
        """Search ingredients by name."""
        params = {"filter[name]": query, "per_page": limit}
        return self.get("/api/ingredients", params=params)

    def create_ingredient(self, ingredient_data: dict[str, Any]) -> dict[str, Any]:
        """Create a new ingredient."""
        return self.post("/api/ingredients", json=ingredient_data)

    def update_ingredient(self, id_or_slug: str | int, ingredient_data: dict[str, Any]) -> dict[str, Any]:
        """Update an existing ingredient."""
        return self.put(f"/api/ingredients/{id_or_slug}", json=ingredient_data)

    def delete_ingredient(self, id_or_slug: str | int) -> dict[str, Any]:
        """Delete an ingredient."""
        return self.delete(f"/api/ingredients/{id_or_slug}")

    def upload_images(self, images: list[dict[str, Any]]) -> dict[str, Any]:
        """Upload images from URLs or base64 data.

        Each image dict should have:
        - image: URL string or base64 data
        - copyright: optional copyright string
        - sort: optional sort order (int)
        """
        return self.post("/api/images", json={"images": images})

    def get_ingredient_cocktails(self, id_or_slug: str | int) -> dict[str, Any]:
        """Get cocktails that use this ingredient."""
        return self.get(f"/api/ingredients/{id_or_slug}/cocktails")

    # ===== Shelf =====

    def get_shelf(self, user_id: int = 1) -> dict[str, Any]:
        """Get user's shelf ingredients."""
        return self.get(f"/api/users/{user_id}/ingredients")

    def add_to_shelf(self, user_id: int, ingredient_ids: list[int]) -> dict[str, Any]:
        """Add ingredients to user's shelf."""
        return self.post(
            f"/api/users/{user_id}/ingredients/batch-store",
            json={"ingredient_ids": ingredient_ids},
        )

    def remove_from_shelf(
        self, user_id: int, ingredient_ids: list[int]
    ) -> dict[str, Any]:
        """Remove ingredients from user's shelf."""
        return self.post(
            f"/api/users/{user_id}/ingredients/batch-delete",
            json={"ingredient_ids": ingredient_ids},
        )

    # ===== Shopping List =====

    def get_shopping_list(self, user_id: int = 1) -> dict[str, Any]:
        """Get user's shopping list."""
        return self.get(f"/api/users/{user_id}/shopping-list")

    def add_to_shopping_list(
        self, user_id: int, ingredient_ids: list[int]
    ) -> dict[str, Any]:
        """Add ingredients to shopping list."""
        return self.post(
            f"/api/users/{user_id}/shopping-list/batch-store",
            json={"ingredient_ids": ingredient_ids},
        )

    def remove_from_shopping_list(
        self, user_id: int, ingredient_ids: list[int]
    ) -> dict[str, Any]:
        """Remove ingredients from shopping list."""
        return self.post(
            f"/api/users/{user_id}/shopping-list/batch-delete",
            json={"ingredient_ids": ingredient_ids},
        )

    # ===== Collections =====

    def list_collections(self) -> dict[str, Any]:
        """List cocktail collections."""
        return self.get("/api/collections")

    def get_collection(self, collection_id: int) -> dict[str, Any]:
        """Get a specific collection."""
        return self.get(f"/api/collections/{collection_id}")

    # ===== Tags =====

    def list_tags(self) -> dict[str, Any]:
        """List all tags."""
        return self.get("/api/tags")

    # ===== Glasses =====

    def list_glasses(self) -> dict[str, Any]:
        """List all glasses."""
        return self.get("/api/glasses")

    # ===== Methods =====

    def list_methods(self) -> dict[str, Any]:
        """List cocktail methods."""
        return self.get("/api/cocktail-methods")

    # ===== Stats =====

    def get_bar_stats(self, bar_id: int | None = None) -> dict[str, Any]:
        """Get bar statistics."""
        bid = bar_id or self.bar_id
        return self.get(f"/api/bars/{bid}/stats", include_bar=False)

    # ===== Profile =====

    def get_profile(self) -> dict[str, Any]:
        """Get current user profile."""
        return self.get("/api/profile", include_bar=False)

    def close(self):
        """Close the HTTP client."""
        self.client.close()
