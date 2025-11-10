"""Räumliches Asset-Indexing für große Welten."""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Tuple

from auto_pcg.models.spatial import BoundingBox, Vector3

from .asset_database import AssetDatabase


class SpatialAssetDatabase(AssetDatabase):
    """Erweitert AssetDatabase um einfache Grid-/LOD-Abfragen."""

    def __init__(self, grid_size: float = 1000.0) -> None:
        super().__init__()
        self.grid_size = max(1.0, grid_size)
        self._grid: Dict[Tuple[int, int], set[str]] = defaultdict(set)
        self._positions: Dict[str, Vector3] = {}
        self.asset_lod_levels: Dict[str, int] = {}

    # Public API --------------------------------------------------------------------------

    def register_asset_position(self, asset_id: str, position: Vector3, lod_level: int = 0) -> None:
        """Registriert ein Asset im Spatial-Index."""
        self._positions[asset_id] = position
        self.asset_lod_levels[asset_id] = max(0, lod_level)
        self._grid[self._grid_key(position)].add(asset_id)

    def query_assets_in_region(self, bounds: BoundingBox, lod_level: int = 0) -> List[str]:
        """Liefert Asset-IDs innerhalb einer Bounding-Box."""
        ids: List[str] = []
        for key in self._grid_keys_for_bounds(bounds):
            for asset_id in self._grid.get(key, ()):
                position = self._positions.get(asset_id)
                if not position:
                    continue
                if self.asset_lod_levels.get(asset_id, 0) > lod_level:
                    continue
                if bounds.contains(position):
                    ids.append(asset_id)
        return ids

    def preload_region_assets(self, center: Vector3, radius: float, lod_level: int = 0) -> List[str]:
        """Hilfsmethode für Streaming: Assets im Umkreis eines Punkts."""
        bounds = BoundingBox.from_center(center, radius)
        return self.query_assets_in_region(bounds, lod_level=lod_level)

    def clear_spatial_index(self) -> None:
        self._grid.clear()
        self._positions.clear()
        self.asset_lod_levels.clear()

    # Overrides ----------------------------------------------------------------------------

    def store_asset(self, asset_data) -> None:  # type: ignore[override]
        super().store_asset(asset_data)
        asset_id = asset_data.asset_id
        position = self._positions.get(asset_id)
        if position:
            self._grid[self._grid_key(position)].add(asset_id)

    # Internal -----------------------------------------------------------------------------

    def _grid_key(self, position: Vector3) -> Tuple[int, int]:
        return (int(position.x // self.grid_size), int(position.y // self.grid_size))

    def _grid_keys_for_bounds(self, bounds: BoundingBox) -> Iterable[Tuple[int, int]]:
        min_key = self._grid_key(bounds.min)
        max_key = self._grid_key(bounds.max)
        for gx in range(min_key[0], max_key[0] + 1):
            for gy in range(min_key[1], max_key[1] + 1):
                yield (gx, gy)
