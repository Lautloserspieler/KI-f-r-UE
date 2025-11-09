"""Zentrale Datenmodelle für den Auto-PCG KI-Assistenten."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence


@dataclass(slots=True)
class AssetMetadata:
    """Einfaches Metadatenmodell, das grundlegende Asset-Eigenschaften enthält."""

    bounds: Dict[str, float]
    vertex_count: int
    material_slots: int
    file_size: int


@dataclass(slots=True)
class AssetData:
    """Standardisiertes Asset-Modell, das Scanner- und Analysetaten kombiniert."""

    asset_id: str
    asset_path: Path
    asset_type: str
    metadata: AssetMetadata
    semantic_tags: List[str] = field(default_factory=list)
    semantic_profile: Dict[str, object] = field(default_factory=dict)
    usage_stats: Dict[str, object] = field(
        default_factory=lambda: {
            "usage_count": 0,
            "last_used": None,
            "user_rating": 0.0,
        }
    )
    relationships: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, object]:
        """Wandelt das Asset in ein JSON-fähiges Dict um."""
        return {
            "asset_id": self.asset_id,
            "asset_path": str(self.asset_path),
            "asset_type": self.asset_type,
            "metadata": asdict(self.metadata),
            "semantic_tags": self.semantic_tags,
            "semantic_profile": self.semantic_profile,
            "usage_stats": self.usage_stats,
            "relationships": self.relationships,
        }


@dataclass(slots=True)
class Classification:
    """Ergebnis einer semantischen Asset-Analyse."""

    asset_path: Path
    primary_category: str
    sub_category: str
    tags: List[str]
    style: str
    biomes: List[str]
    technical: Dict[str, object] = field(default_factory=dict)

    def to_profile(self) -> Dict[str, object]:
        """Wandelt die Klassifikation in ein semantisches Profil um."""
        return {
            "asset_path": str(self.asset_path),
            "primary_category": self.primary_category,
            "sub_category": self.sub_category,
            "tags": self.tags,
            "style": self.style,
            "biomes": self.biomes,
            "technical": self.technical,
        }


@dataclass(slots=True)
class PCGFilterSpec:
    """Model für Filterdefinitionen in PCG-Layern."""

    type: str
    params: Dict[str, object]


@dataclass(slots=True)
class PCGLayer:
    """Beschreibung eines PCG-Layers, der im Editor erzeugt werden soll."""

    layer_type: str
    purpose: str
    assets: List[Path]
    parameters: Dict[str, object]
    filters: List[PCGFilterSpec] = field(default_factory=list)


@dataclass(slots=True)
class PCGPlan:
    """High-Level-Bauplan für einen automatisch erzeugten Graphen."""

    description: str
    target_biome: str
    layers: Sequence[PCGLayer]


@dataclass(slots=True)
class PCGNode:
    """In-Memory-Repräsentation eines PCG-Graph-Knotens."""

    name: str
    layer_type: str
    config: Dict[str, object]
    children: List["PCGNode"] = field(default_factory=list)


@dataclass(slots=True)
class PCGGraph:
    """Ergebnis des Graph Builders mit Metadaten für Debug & Export."""

    root_nodes: List[PCGNode]
    generated_at: datetime
    description: Optional[str] = None
