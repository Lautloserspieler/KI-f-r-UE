"""Automatische Planung für Landscape-Layer-Masks und Adaptive Regeln."""

from __future__ import annotations

from pathlib import Path
from random import Random
from typing import Dict, List

from auto_pcg.models.terrain import (
    HeightmapAnalysisResult,
    LandscapeLayerMask,
    LandscapeLayerPlan,
)


class LayerPainter:
    """Leitet Layer-Masken und Adaptive-Paint-Regeln aus Biomen ab."""

    def build_layer_plan(
        self,
        analysis: HeightmapAnalysisResult,
        *,
        output_dir: Path | None = None,
        season: str = "default",
    ) -> LandscapeLayerPlan:
        masks: List[LandscapeLayerMask] = []
        rng = Random(42)
        for order, biome in enumerate(analysis.biomes):
            mask_path = None
            if output_dir:
                mask_path = (output_dir / f"{analysis.metadata.path.stem}_{biome.name}_mask.png").resolve()
            base_softness = biome.transitions.get("softness", 0.25)
            variation = rng.random() * 0.1
            softness = min(0.8, base_softness + variation)
            masks.append(
                LandscapeLayerMask(
                    biome=biome.name,
                    mask_path=mask_path,
                    softness=softness,
                    recommended_order=order,
                )
            )
        adaptive_rules: Dict[str, float] = {
            "auto_reduce_resolution_fps": 50.0,
            "detail_fade_distance": analysis.landscape_settings.lod_distance * 0.75,
            "streaming_pool_ratio": 0.8,
            "seasonal_bias": 1.0 if season == "summer" else 0.9,
        }
        if analysis.metadata.average_slope > 0.35:
            adaptive_rules["slope_stabilizer"] = analysis.metadata.average_slope
        return LandscapeLayerPlan(masks=masks, adaptive_rules=adaptive_rules, season=season)
