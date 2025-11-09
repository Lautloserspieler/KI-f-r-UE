"""Semantische Analyse und Klassifikation von Assets."""

from __future__ import annotations

from typing import Dict, List

from auto_pcg.models.schemas import AssetData, Classification


class AssetAnalyzer:
    """Einfache Heuristiken zur Einordnung von Assets."""

    CATEGORY_BY_TYPE = {
        "StaticMesh": ("VEGETATION", "Foliage"),
        "Material": ("PROP", "Surface"),
        "Blueprint": ("ARCHITECTURE", "Logic"),
        "Texture": ("PROP", "Detail"),
    }

    STYLE_KEYWORDS = {
        "fantasy": ("magic", "rune", "dragon", "elf"),
        "sci-fi": ("laser", "cyber", "neo", "robot"),
        "medieval": ("castle", "stone", "knight", "village"),
        "realistic": ("photogrammetry", "scan", "real", "nature"),
    }

    BIOME_KEYWORDS = {
        "forest": ("tree", "leaf", "moss", "forest"),
        "desert": ("sand", "dune", "cactus"),
        "mountain": ("rock", "stone", "cliff"),
        "tundra": ("snow", "ice", "frost"),
    }

    def classify_asset_semantics(self, asset_data: AssetData) -> Classification:
        """Berechnet eine Klassifikation inklusive Tags, Stil und Biomen."""
        tags = self._derive_tags(asset_data)
        style = self.detect_asset_style(asset_data)
        biomes = [
            biome
            for biome, keywords in self.BIOME_KEYWORDS.items()
            if any(keyword in asset_data.asset_path.stem.lower() for keyword in keywords)
        ]
        if not biomes:
            biomes = ["generic"]
        primary_category, sub_category = self.CATEGORY_BY_TYPE.get(
            asset_data.asset_type,
            ("PROP", "Generic"),
        )
        technical = self._build_technical_properties(asset_data)
        classification = Classification(
            asset_path=asset_data.asset_path,
            primary_category=primary_category,
            sub_category=sub_category,
            tags=tags,
            style=style,
            biomes=biomes,
            technical=technical,
        )
        asset_data.semantic_tags = tags
        return classification

    def detect_asset_style(self, asset: AssetData) -> str:
        """Schätzt den visuellen Stil anhand einfacher Schlagworte."""
        name = asset.asset_path.stem.lower()
        for style, keywords in self.STYLE_KEYWORDS.items():
            if any(keyword in name for keyword in keywords):
                return style
        return "realistic"

    def suggest_usage_context(self, asset: AssetData) -> List[str]:
        """Leitet Nutzungskontexte aus Tags, Dateinamen und Größe ab."""
        contexts: List[str] = []
        if asset.asset_type == "StaticMesh":
            contexts.append("Level Dressing")
        if asset.metadata.vertex_count > 200_000:
            contexts.append("Hero Asset")
        if asset.metadata.vertex_count < 20_000:
            contexts.append("Background Prop")
        if "tree" in asset.asset_path.stem.lower():
            contexts.append("Vegetation Cluster")
        return contexts or ["Generic Usage"]

    def calculate_biome_compatibility(self, asset: AssetData) -> Dict[str, float]:
        """Bewertet, wie gut ein Asset zu definierten Biomen passt."""
        name = asset.asset_path.stem.lower()
        scores: Dict[str, float] = {}
        for biome, keywords in self.BIOME_KEYWORDS.items():
            score = sum(1 for keyword in keywords if keyword in name) / len(keywords)
            scores[biome] = round(score, 2)
        scores["generic"] = 0.5
        return scores

    def _build_technical_properties(self, asset_data: AssetData) -> Dict[str, object]:
        """Leitet einfache technische Eigenschaften aus Metadaten ab."""
        polycount = int(asset_data.metadata.vertex_count)
        collision = "complex" if polycount > 100_000 else "simple"
        lod = polycount > 40_000
        material_count = int(asset_data.metadata.material_slots)
        texture_resolution = self._estimate_texture_resolution(asset_data.metadata.file_size)
        return {
            "polycount": polycount,
            "texture_resolution": texture_resolution,
            "collision": collision,
            "lod": lod,
            "material_count": material_count,
        }

    @staticmethod
    def _estimate_texture_resolution(file_size_bytes: int) -> List[int]:
        """Schätzt eine sinnvolle Texturauflösung basierend auf Dateigröße."""
        size_kb = max(1, file_size_bytes // 1024)
        if size_kb > 16_384:
            return [4096, 4096]
        if size_kb > 8_192:
            return [3072, 3072]
        if size_kb > 4_096:
            return [2048, 2048]
        if size_kb > 2_048:
            return [1024, 1024]
        if size_kb > 1_024:
            return [512, 512]
        return [256, 256]

    def _derive_tags(self, asset_data: AssetData) -> List[str]:
        """Private Heuristik zur Tag-Generierung."""
        tags = {asset_data.asset_type.lower()}
        name_parts = asset_data.asset_path.stem.replace("_", " ").split()
        tags.update(part.lower() for part in name_parts if len(part) > 2)
        size = asset_data.metadata.bounds
        if size["z"] > 400:
            tags.add("tall")
        if asset_data.metadata.vertex_count > 100_000:
            tags.add("high-detail")
        return sorted(tags)
