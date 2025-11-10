"""Datenmodelle für Heightmap-, Biome- und Material-Pipelines."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple


@dataclass(slots=True)
class HeightmapMetadata:
    """Beschreibt grundlegende Eigenschaften einer Heightmap."""

    path: Path
    width: int
    height: int
    min_elevation: float
    max_elevation: float
    average_slope: float
    water_ratio: float

    def to_dict(self) -> Dict[str, object]:
        payload = asdict(self)
        payload["path"] = str(self.path)
        return payload


@dataclass(slots=True)
class LandscapeSettings:
    """Empfohlene Landscape-Konfiguration für UE."""

    section_size: int
    components_x: int
    components_y: int
    lod_distance: float
    performance_profile: str

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class BiomeLayer:
    """Beschreibung eines automatisch erkannten Bioms."""

    name: str
    elevation_range: Tuple[float, float]
    slope_range: Tuple[float, float]
    water_coverage: float
    mask_path: Optional[Path] = None
    weight: float = 1.0
    transitions: Dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        payload = asdict(self)
        if self.mask_path:
            payload["mask_path"] = str(self.mask_path)
        return payload


@dataclass(slots=True)
class HeightmapAnalysisResult:
    """Aggregiertes Analyseergebnis inklusive Biome und Settings."""

    metadata: HeightmapMetadata
    biomes: List[BiomeLayer]
    landscape_settings: LandscapeSettings
    scale: Tuple[float, float, float]
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        return {
            "metadata": self.metadata.to_dict(),
            "biomes": [biome.to_dict() for biome in self.biomes],
            "landscape_settings": self.landscape_settings.to_dict(),
            "scale": list(self.scale),
            "notes": self.notes,
        }


@dataclass(slots=True)
class MaterialLayerConfig:
    """Konfiguration einer Material-Layer-Kombination."""

    biome: str
    texture_set: Dict[str, str]
    tiling: float
    blending_rules: Dict[str, float]
    exposed_parameters: Dict[str, float]

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class MaterialBlueprint:
    """Kompletter Material-Blueprint, bereit für UE Master Materials."""

    layers: List[MaterialLayerConfig]
    global_parameters: Dict[str, float]
    performance_notes: List[str] = field(default_factory=list)
    transitions: Dict[str, Dict[str, object]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, object]:
        return {
            "layers": [layer.to_dict() for layer in self.layers],
            "global_parameters": self.global_parameters,
            "performance_notes": self.performance_notes,
            "transitions": self.transitions,
        }


@dataclass(slots=True)
class LandscapeLayerMask:
    """Beschreibt eine zu erzeugende Layer-Maske inkl. Übergangs-Infos."""

    biome: str
    mask_path: Optional[Path]
    softness: float
    recommended_order: int

    def to_dict(self) -> Dict[str, object]:
        payload = asdict(self)
        if self.mask_path:
            payload["mask_path"] = str(self.mask_path)
        return payload


@dataclass(slots=True)
class LandscapeLayerPlan:
    """Plan für automatisches Landscape-Painting."""

    masks: List[LandscapeLayerMask]
    adaptive_rules: Dict[str, float]
    season: str = "default"

    def to_dict(self) -> Dict[str, object]:
        return {
            "masks": [mask.to_dict() for mask in self.masks],
            "adaptive_rules": self.adaptive_rules,
            "season": self.season,
        }
