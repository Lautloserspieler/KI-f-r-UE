"""Materialplanung basierend auf Biomen und Texture-Library."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from auto_pcg.models.terrain import (
    HeightmapAnalysisResult,
    MaterialBlueprint,
    MaterialLayerConfig,
)

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class TextureLibraryEntry:
    biome: str
    textures: Dict[str, str]


class TextureLibrary:
    """Lädt Texturdefinitionen aus JSON (oder nutzt Defaults)."""

    def __init__(self, source: Optional[Path] = None) -> None:
        self.source = source or Path(__file__).resolve().parents[1] / "data" / "texture_library.json"
        self.entries: Dict[str, TextureLibraryEntry] = {}
        self._load()

    def _load(self) -> None:
        if not self.source.exists():
            LOGGER.warning("Texture-Library nicht gefunden: %s", self.source)
            return
        payload = json.loads(self.source.read_text(encoding="utf-8"))
        for biome, textures in payload.items():
            if not isinstance(textures, dict):
                continue
            self.entries[biome.lower()] = TextureLibraryEntry(biome=biome, textures=textures)

    def find_best_match(self, biome: str, fallback: Optional[str] = None) -> Dict[str, str]:
        biome = biome.lower()
        if biome in self.entries:
            return self.entries[biome].textures
        if fallback and fallback.lower() in self.entries:
            return self.entries[fallback.lower()].textures
        if self.entries:
            return next(iter(self.entries.values())).textures
        return {}


class MaterialPlanner:
    """Baut Master-Material-Konfigurationen für Landscape-Biome."""

    def __init__(
        self,
        texture_library: Optional[TextureLibrary] = None,
        llm_manager=None,
    ) -> None:
        self.library = texture_library or TextureLibrary()
        self._llm_manager = llm_manager

    def build_blueprint(
        self,
        analysis: HeightmapAnalysisResult,
        *,
        target_style: str = "realistic",
        performance_profile: str = "desktop",
        season: str = "default",
        enable_transitions: bool = False,
    ) -> MaterialBlueprint:
        layers: List[MaterialLayerConfig] = []
        for biome in analysis.biomes:
            texture_set = self.library.find_best_match(biome.name, fallback="forest")
            tiling = self._derive_tiling(texture_set, analysis, biome)
            blending_rules = self._build_blending_rules(biome, target_style)
            parameters = self._expose_parameters(biome, performance_profile)
            layers.append(
                MaterialLayerConfig(
                    biome=biome.name,
                    texture_set=texture_set,
                    tiling=tiling,
                    blending_rules=blending_rules,
                    exposed_parameters=parameters,
                )
            )
        global_parameters = {
            "macro_variation_intensity": 0.35 if target_style == "stylized" else 0.2,
            "triplanar_blend": 0.5 if analysis.metadata.average_slope > 0.3 else 0.3,
            "runtime_virtual_texture": 1.0 if performance_profile in {"desktop", "high_end_pc"} else 0.0,
            "seasonal_tint": self._seasonal_tint(season),
        }
        performance_notes = [
            f"{len(layers)} Layer, Section-Size {analysis.landscape_settings.section_size}",
            f"Empfohlene LOD-Distanz: {analysis.landscape_settings.lod_distance}",
            f"Saison: {season}",
        ]
        transitions: Dict[str, Dict[str, object]] = {}
        if enable_transitions and len(analysis.biomes) > 1:
            transitions = self._build_transition_map(analysis.biomes, season)
        return MaterialBlueprint(
            layers=layers,
            global_parameters=global_parameters,
            performance_notes=performance_notes,
            transitions=transitions,
        )

    def _derive_tiling(
        self,
        texture_set: Dict[str, str],
        analysis: HeightmapAnalysisResult,
        biome,
    ) -> float:
        ratio = analysis.metadata.width / max(analysis.metadata.height, 1)
        base = 2.0 if ratio > 1.2 else 1.0
        if "rock" in biome.name.lower():
            base *= 0.5
        if texture_set.get("albedo", "").lower().endswith("sand_albedo"):
            base *= 4.0
        return round(base, 2)

    def _build_blending_rules(self, biome, target_style: str) -> Dict[str, float]:
        softness = 0.35 if target_style == "stylized" else 0.2
        contrast = 1.2 if target_style == "stylized" else 0.8
        return {
            "slope_bias": sum(biome.slope_range) / 2,
            "transition_softness": softness,
            "detail_contrast": contrast,
            "height_bias": biome.elevation_range[0],
        }

    def _expose_parameters(self, biome, performance_profile: str) -> Dict[str, float]:
        detail_intensity = 0.7 if performance_profile == "high_end_pc" else 0.4
        if biome.name.lower() in {"desert", "steppe"}:
            detail_intensity *= 0.5
        return {
            "detail_normal_strength": detail_intensity,
            "roughness_min": 0.2,
            "roughness_max": 0.8,
            "micro_variation": biome.weight,
        }

    def _build_transition_map(self, biomes: Sequence, season: str) -> Dict[str, Dict[str, object]]:
        transition_map: Dict[str, Dict[str, object]] = {}
        for index in range(len(biomes) - 1):
            a = biomes[index]
            b = biomes[index + 1]
            key = f"{a.name}->{b.name}"
            transition_map[key] = {
                "mask_hint": f"/Game/AutoPCG/Transitions/{a.name}_{b.name}_mask",
                "season": season,
                "height_bias": (a.elevation_range[1] + b.elevation_range[0]) / 2,
            }
        return transition_map

    def _seasonal_tint(self, season: str) -> float:
        season = season.lower()
        mapping = {
            "winter": 0.8,
            "spring": 1.05,
            "summer": 1.0,
            "autumn": 0.9,
        }
        return mapping.get(season, 1.0)
