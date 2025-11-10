"""Prompt generation for classifications, PCG plans and terrain workflows."""

from __future__ import annotations

import json
import textwrap
from dataclasses import asdict
from typing import Iterable, Sequence

from auto_pcg.models.schemas import AssetData
from auto_pcg.models.terrain import (
    HeightmapAnalysisResult,
    LandscapeLayerPlan,
    MaterialBlueprint,
)


class PromptEngine:
    """Produces JSON-only prompts tailored to the Auto-PCG workflow."""

    # Asset & PCG Prompts --------------------------------------------------------------------

    def build_asset_classification_prompt(self, assets: Sequence[AssetData]) -> str:
        """Creates a JSON-centric prompt requesting semantic asset categories."""
        asset_snippets = [
            {
                "asset_path": str(asset.asset_path),
                "asset_type": asset.asset_type,
                "metadata": asdict(asset.metadata),
            }
            for asset in assets
        ]
        asset_json = json.dumps(asset_snippets, ensure_ascii=False, indent=2)
        instructions = textwrap.dedent(
            """
ROLLE: Du bist ein Asset-Klassifikator für Unreal Engine 5.4.
AUFGABE: Ordne jedes Asset mehreren Ebenen zu.

Hauptkategorien (Primary Categories):
- LANDSCAPE (Terrain, Wasser, Höhlen, Klippen, Pfade)
- VEGETATION (Bäume, Büsche, Gräser, Blumen, Pilze, Pflanzen)
- ARCHITECTURE (Gebäude, Ruinen, Brücken, Mauern, Böden, Dächer)
- PROP (Möbel, Container, Waffen, Werkzeuge, Dekoration, Licht)
- CHARACTER (Menschen, Tiere, Kreaturen, Monster)
- EFFECTS (Partikel, Licht, Sound)
- MATERIAL (Oberflächen/Materialdefinitionen)
- BLUEPRINT (Interaktive/technische Blueprints)

Unterkategorien: Wähle passende Begriffe aus den obigen Beispielen (z.B. Tree, Bush,
Terrain, Cliff, Building, Bridge, Furniture, Weapon, Particle, Ground, Interactive).

Tags: Liste aus beschreibenden Begriffen wie Größe (small/medium/large/huge),
Farbe (red/green/dark/bright), Zustand (new/old/broken), Jahreszeit, Umgebung
(indoor/outdoor/underground/underwater), Genre (magical, futuristic, medieval usw.).

Stil (Style): wähle aus {realistic, fantasy, sci-fi, medieval, modern, cartoon,
low-poly, stylized}.

Biomes: kombiniere die am besten passenden aus {forest, desert, mountain, grassland,
tundra, jungle, urban, aquatic, arctic, volcanic}.

Technische Eigenschaften (technical):
- polycount (Ganzzahl, z.B. Vertex-Anzahl)
- texture_resolution (Array [width, height], Ableitung aus Metadaten)
- collision ("simple", "complex" oder "none")
- lod (true/false)
- material_count (Ganzzahl)
Nutze die gelieferten Asset-Metadaten, um vernünftige Werte vorzuschlagen. Wenn
Informationen fehlen, triff eine begründete Schätzung.

ANTWORTFORMAT: Gib ausschließlich valides JSON ohne Markdown zurück:
{"classifications": [ ... ]}. Falls keine Klassifikation möglich ist, antworte mit
{"classifications": []}.
"""
        ).strip()
        return f"{instructions}\nASSETS:\n{asset_json}"

    def build_pcg_generation_prompt(
        self,
        user_input: str,
        context: Sequence[AssetData],
        *,
        world_size: float | None = None,
        season: str | None = None,
    ) -> str:
        """Creates the LLM prompt for PCG layer planning."""
        asset_list = ", ".join(asset.asset_path.stem for asset in context)
        metadata_lines = []
        if world_size:
            metadata_lines.append(f"WELTGRÖSSE: {world_size:.0f}m")
        if season:
            metadata_lines.append(f"SAISON: {season}")
        metadata = "\n".join(metadata_lines)
        parts = [
            "ROLLE: Du bist ein PCG-Architekt für Unreal Engine 5.4.\n",
            f"AUFGABE: Erstelle einen PCG-Plan für den Befehl: {user_input}.\n",
        ]
        if metadata:
            parts.append(metadata + "\n")
        parts.extend(
            [
                f"VERFÜGBARE ASSETS: {asset_list}.\n",
                "ANTWORTFORMAT: Gib ausschließlich reines JSON mit dem Objekt 'pcg_plan' zurück. ",
                "Kein erläuternder Text, keine Codeblöcke. Falls nicht möglich, antworte mit ",
                '{"pcg_plan": {"description": "", "target_biome": "unknown", "layers": []}}.',
            ]
        )
        return "".join(parts)

    def build_asset_selection_prompt(self, biome_type: str, available_assets: Iterable[AssetData]) -> str:
        """Creates a helper prompt for biome-specific asset recommendations."""
        candidates = [
            {
                "path": str(asset.asset_path),
                "tags": asset.semantic_tags,
                "biomes": asset.semantic_tags,
            }
            for asset in available_assets
        ]
        candidates_json = json.dumps(candidates, ensure_ascii=False, indent=2)
        return (
            "Bitte schlage passende Assets für das folgende Biom vor.\n"
            f"BIOM: {biome_type}\n"
            f"KANDIDATEN:\n{candidates_json}\n"
            "ANTWORT: Nur JSON ohne zusätzlichen Text."
        )

    # Terrain & Material Prompts --------------------------------------------------------------

    def build_heightmap_strategy_prompt(self, analysis: HeightmapAnalysisResult) -> str:
        """Describes the heightmap state and asks for strategic improvements."""
        payload = analysis.to_dict()
        return textwrap.dedent(
            f"""
ROLLE: Du bist ein Landscape Technical Director für Unreal Engine 5.4.
AUFGABE: Analysiere die gelieferten Heightmap-Daten und liefere Empfehlungen
für Landscape-Settings, Biome-Zuordnung und Skalierung.

VORGABEN:
- Antworte ausschließlich mit JSON im Format {{"heightmap_strategy": {{...}}}}
- Füge Felder wie "recommended_biomes", "landscape_settings" und "notes" hinzu.
- Ergänze Werte nur wenn du dir sicher bist, ansonsten lasse sie weg.

DATEN:
{json.dumps(payload, ensure_ascii=False, indent=2)}
"""
        ).strip()

    def build_material_blueprint_prompt(
        self,
        analysis: HeightmapAnalysisResult,
        blueprint: MaterialBlueprint,
    ) -> str:
        """Requests Material-Graph improvements for the detected biomes."""
        payload = {
            "analysis": analysis.to_dict(),
            "current_blueprint": blueprint.to_dict(),
        }
        return textwrap.dedent(
            f"""
ROLLE: Du bist ein UE5-Materialguru.
AUFGABE: Verbessere den Material-Blueprint für die erkannten Biome.
ANTWORTFORMAT: {{"material_blueprint": {{"layers": [...], "global_parameters": {{...}} }} }}
EINTRÄGE SOLLEN MIT LANDSCAPE LAYER BLEND KOMPATIBEL SEIN.

DATEN:
{json.dumps(payload, ensure_ascii=False, indent=2)}
"""
        ).strip()

    def build_layer_paint_prompt(self, plan: LandscapeLayerPlan) -> str:
        """Asks the LLM to optimise mask ordering and adaptive rules."""
        payload = plan.to_dict()
        return textwrap.dedent(
            f"""
ROLLE: Du bist eine Echtzeit-Painting-KI für UE Landscapes.
AUFGABE: Optimiere Layer-Masken und adaptive Regeln.
ANTWORTFORMAT: {{"layer_plan": {{"masks": [...], "adaptive_rules": {{...}} }} }}

PLAN:
{json.dumps(payload, ensure_ascii=False, indent=2)}
"""
        ).strip()
