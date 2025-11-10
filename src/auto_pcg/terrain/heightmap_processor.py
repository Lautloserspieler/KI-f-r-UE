"""Heightmap-Auswertung inklusive Biome- und Settings-Empfehlungen."""

from __future__ import annotations

import io
import logging
import math
import os
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

from auto_pcg.models.terrain import (
    BiomeLayer,
    HeightmapAnalysisResult,
    HeightmapMetadata,
    LandscapeSettings,
)

LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class _HeightStatistics:
    min_value: float
    max_value: float
    avg_value: float
    slope_index: float
    water_ratio: float


class HeightmapProcessor:
    """Analysiert Heightmaps und erzeugt Biome-Informationen."""

    DEFAULT_SECTION_SIZE = 63
    PERFORMANCE_SECTION_SIZE = {
        "mobile": 31,
        "desktop": 63,
        "console": 63,
        "high_end_pc": 127,
    }

    def __init__(self) -> None:
        self._cached_stats: dict[Path, HeightmapAnalysisResult] = {}

    def process_heightmap(
        self,
        heightmap_path: Path,
        *,
        target_style: str = "realistic",
        performance_profile: str = "desktop",
    ) -> HeightmapAnalysisResult:
        heightmap_path = Path(heightmap_path)
        if not heightmap_path.exists():
            raise FileNotFoundError(f"Heightmap nicht gefunden: {heightmap_path}")
        cached = self._cached_stats.get(heightmap_path)
        if cached:
            return cached
        metadata = self._build_metadata(heightmap_path)
        biome_layers = self._derive_biome_layers(metadata, target_style)
        settings = self._calculate_landscape_settings(metadata, performance_profile)
        scale = self._calculate_scale(metadata)
        notes = [
            f"Heightmap {metadata.width}x{metadata.height} @ Δh {metadata.min_elevation:.1f}-{metadata.max_elevation:.1f}",
            f"Durchschnittliche Steigung: {metadata.average_slope:.2f}",
            f"Wasseranteil (niedrige Höhen): {metadata.water_ratio:.2%}",
        ]
        result = HeightmapAnalysisResult(
            metadata=metadata,
            biomes=biome_layers,
            landscape_settings=settings,
            scale=scale,
            notes=notes,
        )
        self._cached_stats[heightmap_path] = result
        return result

    # ---------------------------------------------------------------------------------- intern

    def _build_metadata(self, path: Path) -> HeightmapMetadata:
        width, height = self._extract_dimensions(path)
        stats = self._sample_height_values(path, width, height)
        return HeightmapMetadata(
            path=path,
            width=width,
            height=height,
            min_elevation=stats.min_value,
            max_elevation=stats.max_value,
            average_slope=stats.slope_index,
            water_ratio=stats.water_ratio,
        )

    def _extract_dimensions(self, path: Path) -> Tuple[int, int]:
        if path.suffix.lower() == ".png":
            try:
                with path.open("rb") as stream:
                    signature = stream.read(8)
                    if signature != b"\x89PNG\r\n\x1a\n":
                        raise ValueError("keine PNG-Signatur")
                    ihdr = stream.read(25)
                    if len(ihdr) < 25:
                        raise ValueError("ungültige IHDR-Länge")
                    width, height = struct.unpack(">II", ihdr[8:16])
                    return max(8, width), max(8, height)
            except Exception as exc:  # pragma: no cover - Headerfehler selten
                LOGGER.warning("Konnte PNG-Dimensionen nicht lesen: %s", exc)
        # Fallback: Quadratwurzel aus Dateigröße (16-bit Heightmap angenommen)
        file_size = path.stat().st_size
        pixels = max(1, file_size // 2)
        edge = int(math.sqrt(pixels))
        return max(8, edge), max(8, edge)

    def _sample_height_values(
        self,
        path: Path,
        width: int,
        height: int,
        sample_count: int = 4096,
    ) -> _HeightStatistics:
        data = path.read_bytes()
        if len(data) < 2:
            return _HeightStatistics(0.0, 0.0, 0.0, 0.0, 0.0)
        step = max(2, len(data) // sample_count)
        samples: List[int] = []
        for index in range(0, len(data) - 1, step):
            value = int.from_bytes(data[index : index + 2], "little")
            samples.append(value)
        if not samples:
            samples.append(0)
        min_value = min(samples) / 65535.0
        max_value = max(samples) / 65535.0
        avg_value = sum(samples) / (len(samples) * 65535.0)
        slope_index = self._estimate_slope(samples)
        water_threshold = min_value + (max_value - min_value) * 0.1
        water_ratio = sum(1 for value in samples if value / 65535.0 <= water_threshold) / len(samples)
        return _HeightStatistics(min_value, max_value, avg_value, slope_index, water_ratio)

    @staticmethod
    def _estimate_slope(samples: Sequence[int]) -> float:
        if len(samples) < 2:
            return 0.0
        diffs = [
            abs(samples[index] - samples[index - 1]) / 65535.0
            for index in range(1, len(samples))
        ]
        return sum(diffs) / len(diffs)

    def _derive_biome_layers(self, metadata: HeightmapMetadata, target_style: str) -> List[BiomeLayer]:
        low = (metadata.min_elevation, metadata.min_elevation + (metadata.max_elevation - metadata.min_elevation) * 0.25)
        mid = (low[1], metadata.min_elevation + (metadata.max_elevation - metadata.min_elevation) * 0.6)
        high = (mid[1], metadata.max_elevation)
        biomes = [
            BiomeLayer(
                name="water" if metadata.water_ratio > 0.15 else "valley",
                elevation_range=low,
                slope_range=(0.0, 0.3),
                water_coverage=metadata.water_ratio,
                weight=0.8,
                transitions={"forest": 0.6, "swamp": 0.2},
            ),
            BiomeLayer(
                name="forest" if target_style != "desert" else "steppe",
                elevation_range=mid,
                slope_range=(0.1, 0.6),
                water_coverage=max(0.05, metadata.water_ratio * 0.5),
                weight=1.0,
                transitions={"mountain": 0.4},
            ),
            BiomeLayer(
                name="mountain" if metadata.average_slope > 0.25 else "plateau",
                elevation_range=high,
                slope_range=(0.3, 1.0),
                water_coverage=0.05,
                weight=0.6,
                transitions={"snow": 0.3 if target_style == "tundra" else 0.1},
            ),
        ]
        return biomes

    def _calculate_landscape_settings(
        self,
        metadata: HeightmapMetadata,
        performance_profile: str,
    ) -> LandscapeSettings:
        section_size = self.PERFORMANCE_SECTION_SIZE.get(performance_profile, self.DEFAULT_SECTION_SIZE)
        components_x = max(1, metadata.width // section_size)
        components_y = max(1, metadata.height // section_size)
        lod_distance = 2000.0
        if performance_profile == "mobile":
            lod_distance = 1000.0
        elif performance_profile == "high_end_pc":
            lod_distance = 4000.0
        return LandscapeSettings(
            section_size=section_size,
            components_x=components_x,
            components_y=components_y,
            lod_distance=lod_distance,
            performance_profile=performance_profile,
        )

    def _calculate_scale(self, metadata: HeightmapMetadata) -> Tuple[float, float, float]:
        z_range = max(0.01, metadata.max_elevation - metadata.min_elevation)
        z_scale = min(256.0, max(32.0, z_range * 512.0))
        xy_scale = 100.0 if metadata.width > 2048 else 50.0
        return (xy_scale, xy_scale, z_scale)
