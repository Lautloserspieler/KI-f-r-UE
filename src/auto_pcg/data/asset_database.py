"""Einfache In-Memory-Datenbank für Asset-Daten."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

from auto_pcg.models.schemas import AssetData, AssetMetadata


class AssetDatabase:
    """Verwaltet Assets, Tags und Statistiken."""

    def __init__(self) -> None:
        self._assets: Dict[str, AssetData] = {}

    def store_asset(self, asset_data: AssetData) -> None:
        """Speichert oder aktualisiert ein Asset."""
        existing = self._assets.get(asset_data.asset_id)
        if existing:
            if not asset_data.semantic_tags and existing.semantic_tags:
                asset_data.semantic_tags = existing.semantic_tags
            if not asset_data.semantic_profile and existing.semantic_profile:
                asset_data.semantic_profile = existing.semantic_profile
            if not asset_data.usage_stats:
                asset_data.usage_stats = existing.usage_stats
        self._assets[asset_data.asset_id] = asset_data

    def get_asset(self, asset_id: str) -> AssetData | None:
        """Liefert ein Asset anhand seiner ID."""
        return self._assets.get(asset_id)

    def remove_asset(self, asset_id: str) -> None:
        """Entfernt ein Asset aus der Datenbank."""
        self._assets.pop(asset_id, None)

    def query_assets_by_tags(self, tags: Sequence[str]) -> List[AssetData]:
        """Liefert alle Assets, die mindestens einen der Tags besitzen."""
        tags_lower = {tag.lower() for tag in tags}
        return [
            asset
            for asset in self._assets.values()
            if tags_lower.intersection({tag.lower() for tag in asset.semantic_tags})
        ]

    def update_usage_stats(self, asset_path: str) -> None:
        """Erhöht den Nutzungszähler eines Assets."""
        for asset in self._assets.values():
            if str(asset.asset_path) == asset_path:
                asset.usage_stats["usage_count"] = int(asset.usage_stats.get("usage_count", 0)) + 1
                asset.usage_stats["last_used"] = "auto"
                break

    def get_asset_recommendations(self, context: Sequence[str], limit: int = 5) -> List[AssetData]:
        """Empfiehlt Assets basierend auf kontextuellen Tags."""
        context_set = set(tag.lower() for tag in context)
        scored = []
        for asset in self._assets.values():
            asset_tags = {tag.lower() for tag in asset.semantic_tags}
            overlap = len(context_set.intersection(asset_tags))
            scored.append((overlap, asset))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [asset for score, asset in scored if score > 0][:limit]

    def all_assets(self) -> Iterable[AssetData]:
        """Iterator über alle Assets."""
        return self._assets.values()

    def to_json(self) -> str:
        """Serialisiert die Datenbank."""
        return json.dumps([asset.to_dict() for asset in self._assets.values()], indent=2, ensure_ascii=False)

    def save_to_file(self, destination: Path) -> None:
        """Schreibt die Datenbank als JSON auf die Platte."""
        destination.write_text(self.to_json(), encoding="utf-8")

    def load_from_json(self, source: Path) -> None:
        """Lädt Assets aus einer JSON-Datei."""
        payload = json.loads(source.read_text(encoding="utf-8"))
        if not isinstance(payload, list):
            return
        self._assets.clear()
        for entry in payload:
            metadata = entry["metadata"]
            asset = AssetData(
                asset_id=entry["asset_id"],
                asset_path=Path(entry["asset_path"]),
                asset_type=entry["asset_type"],
                metadata=AssetMetadata(
                    bounds=metadata["bounds"],
                    vertex_count=metadata["vertex_count"],
                    material_slots=metadata["material_slots"],
                    file_size=metadata["file_size"],
                ),
                semantic_tags=entry.get("semantic_tags", []),
                semantic_profile=entry.get("semantic_profile", {}),
                usage_stats=entry.get("usage_stats", {}),
                relationships=entry.get("relationships", []),
            )
            self.store_asset(asset)
