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
        if not response.content:
            return {}
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
        """Get cocktails that can be made with shelf ingredients.

        v6: makeable-from-shelf moved to the bar-level inventory endpoint.
        For a single-user bar the bar inventory IS the shelf, so this is the
        right semantic (and is consistent with get_shelf below).
        """
        return self.get(f"/api/bars/{self.bar_id}/inventory/cocktails")

    def get_favorite_cocktails(self, user_id: int = 1) -> dict[str, Any]:
        """Get user's favorite cocktails.

        v6: /users/{id}/cocktails/favorites → /members/{id}/cocktail-favorites
        ({id} is still the user id).
        """
        return self.get(f"/api/members/{user_id}/cocktail-favorites")

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
    #
    # v6 relocated the per-user shelf (/users/{id}/ingredients) into two
    # concepts: per-member named inventories AND a bar-level inventory. For a
    # single-user bar the bar inventory is the shelf — and it's the same
    # bar_ingredients table the flavor matcher's on_shelf_only reads — so the
    # MCP shelf tools target the bar inventory. The user_id param is retained
    # for signature compatibility but no longer used.

    def get_shelf(self, user_id: int = 1) -> dict[str, Any]:
        """Get the bar's shelf ingredients (v6: bar-level inventory)."""
        return self.get(f"/api/bars/{self.bar_id}/inventory/ingredients")

    def add_to_shelf(self, user_id: int, ingredient_ids: list[int]) -> dict[str, Any]:
        """Add ingredients to the bar's shelf."""
        return self.post(
            f"/api/bars/{self.bar_id}/inventory/ingredients/batch-store",
            json={"ingredients": ingredient_ids},
        )

    def remove_from_shelf(
        self, user_id: int, ingredient_ids: list[int]
    ) -> dict[str, Any]:
        """Remove ingredients from the bar's shelf."""
        return self.post(
            f"/api/bars/{self.bar_id}/inventory/ingredients/batch-delete",
            json={"ingredients": ingredient_ids},
        )

    # ===== Shopping List =====
    #
    # v6: /users/{id}/shopping-list → /members/{id}/shopping-list ({id} stays
    # the user id; shopping lists remain per-member).

    def get_shopping_list(self, user_id: int = 1) -> dict[str, Any]:
        """Get user's shopping list."""
        return self.get(f"/api/members/{user_id}/shopping-list")

    def add_to_shopping_list(
        self, user_id: int, ingredient_ids: list[int]
    ) -> dict[str, Any]:
        """Add ingredients to shopping list.

        v6: payload is now a list of {id, quantity} objects (quantity
        defaults to 1 server-side) rather than bare ingredient ids.
        """
        return self.post(
            f"/api/members/{user_id}/shopping-list/batch-store",
            json={"ingredients": [{"id": iid, "quantity": 1} for iid in ingredient_ids]},
        )

    def remove_from_shopping_list(
        self, user_id: int, ingredient_ids: list[int]
    ) -> dict[str, Any]:
        """Remove ingredients from shopping list.

        v6: batch-delete also reads `id` from each object in the list.
        """
        return self.post(
            f"/api/members/{user_id}/shopping-list/batch-delete",
            json={"ingredients": [{"id": iid} for iid in ingredient_ids]},
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
        """Get bar statistics.

        v6: the single /bars/{id}/stats endpoint was split into sub-routes
        (totals, taste, top, ingredient-distribution). `totals` carries the
        headline counts the MCP surfaced before.
        """
        bid = bar_id or self.bar_id
        return self.get(f"/api/bars/{bid}/stats/totals", include_bar=False)

    # ===== Flavor matching (Phase B — native in BA) =====
    #
    # As of the Phase B Slice 5 cut-over, flavor data lives in BA (not the MCP's
    # SQLite sidecar). These wrap the /api/flavor and per-ingredient/cocktail
    # flavor endpoints. The scoring engine runs server-side in BA.

    def get_flavor_categories(self) -> dict[str, Any]:
        return self.get("/api/flavor/categories")

    def get_flavor_profile(self, ingredient_id: int) -> dict[str, Any] | None:
        """Profile for an ingredient, or None if it has no profile (404)."""
        try:
            return self.get(f"/api/ingredients/{ingredient_id}/flavor-profile")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    def set_flavor_profile(self, ingredient_id: int, body: dict[str, Any]) -> dict[str, Any]:
        return self.put(f"/api/ingredients/{ingredient_id}/flavor-profile", json=body)

    def get_cocktail_flavor_slots(self, cocktail_id: int) -> dict[str, Any]:
        return self.get(f"/api/cocktails/{cocktail_id}/flavor-slots")

    def get_cocktail_flavor_constraints(self, cocktail_id: int) -> dict[str, Any]:
        return self.get(f"/api/cocktails/{cocktail_id}/flavor-constraints")

    def set_slot_meta(self, cocktail_id: int, sort: int, body: dict[str, Any]) -> dict[str, Any]:
        return self.put(f"/api/cocktails/{cocktail_id}/slots/{sort}/meta", json=body)

    def set_slot_constraint(self, cocktail_id: int, sort: int, axis: str, body: dict[str, Any]) -> dict[str, Any]:
        return self.put(f"/api/cocktails/{cocktail_id}/slots/{sort}/constraints/{axis}", json=body)

    def delete_slot_constraint(self, cocktail_id: int, sort: int, axis: str) -> dict[str, Any]:
        return self.delete(f"/api/cocktails/{cocktail_id}/slots/{sort}/constraints/{axis}")

    def get_slot_alternatives(
        self, cocktail_id: int, sort: int,
        on_shelf_only: bool = True, include_strays: bool = False, top_n: int = 10,
    ) -> dict[str, Any]:
        params = {
            "on_shelf_only": "true" if on_shelf_only else "false",
            "include_strays": "true" if include_strays else "false",
            "top_n": top_n,
        }
        return self.get(f"/api/cocktails/{cocktail_id}/slots/{sort}/alternatives", params=params)

    def get_ingredient_flavor_uses(self, ingredient_id: int, top_n: int = 10) -> dict[str, Any]:
        return self.get(f"/api/ingredients/{ingredient_id}/flavor-uses", params={"top_n": top_n})

    def get_flavor_gaps(self, threshold: float = 3.0, cocktail_ids: list[int] | None = None) -> dict[str, Any]:
        params: dict[str, Any] = {"threshold": threshold}
        if cocktail_ids:
            params["cocktail_ids[]"] = cocktail_ids
        return self.get("/api/flavor/gaps", params=params)

    # ===== Profile =====

    def get_profile(self) -> dict[str, Any]:
        """Get current user profile."""
        return self.get("/api/profile", include_bar=False)

    def close(self):
        """Close the HTTP client."""
        self.client.close()
