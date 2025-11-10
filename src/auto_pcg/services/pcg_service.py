"""High-Level-Service, der Scanner, KI und PCG-Builder orchestriert."""

from __future__ import annotations

import os
import logging
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence

import hashlib

from auto_pcg.ai.llm_manager import LLMManager
from auto_pcg.ai.prompt_engine import PromptEngine
from auto_pcg.core.asset_analyzer import AssetAnalyzer
from auto_pcg.core.asset_scanner import AssetScanner
from auto_pcg.data import AssetDatabase
from auto_pcg.data.spatial_database import SpatialAssetDatabase
from auto_pcg.models.schemas import AssetData, Classification, PCGGraph, PCGPlan
from auto_pcg.models.spatial import BoundingBox, Vector3
from auto_pcg.models.terrain import (
    HeightmapAnalysisResult,
    LandscapeLayerMask,
    LandscapeLayerPlan,
    MaterialBlueprint,
    MaterialLayerConfig,
)
from auto_pcg.pcg.graph_builder import HierarchicalPCGBuilder, PCGBuilder
from auto_pcg.pcg.unreal_exporter import UnrealPCGExporter
from auto_pcg.pcg.ue_integration import run_unreal_import
from auto_pcg.terrain import HeightmapProcessor, LayerPainter, MaterialPlanner


LOGGER = logging.getLogger(__name__)


class AutoPCGService:
    """Öffnet eine einfache Python-API für das Auto-PCG-System."""

    def __init__(
        self,
        project_root: Path,
        *,
        max_assets: Optional[int] = None,
        prefer_heuristics: bool = False,
        classification_batch_size: Optional[int] = None,
        ollama_url: Optional[str] = None,
        ollama_model: Optional[str] = None,
        ollama_timeout: Optional[float] = None,
        use_local_model: bool = True,
        export_directory: Optional[Path] = None,
        heightmap: Optional[Path] = None,
        performance_profile: str = "desktop",
        target_style: str = "realistic",
        auto_layer_paint: bool = True,
        use_spatial_database: bool = False,
        world_size: float = 2048.0,
        sector_size: float = 512.0,
        season: str = "summer",
        hierarchical_pcg: bool = False,
        ue_editor: Optional[Path] = None,
        ue_map: Optional[str] = None,
        ue_asset_folder: str = "/Game/AutoPCG",
        ue_spawn: bool = True,
    ) -> None:
        self._world_size = max(1.0, world_size)
        self._sector_size = max(64.0, sector_size)
        self._use_spatial_database = use_spatial_database
        self.database: AssetDatabase = (
            SpatialAssetDatabase(grid_size=self._sector_size)
            if self._use_spatial_database
            else AssetDatabase()
        )
        self._has_scanned = False
        self._max_assets = max_assets
        self._prefer_heuristics = prefer_heuristics
        self._project_root = Path(project_root)
        self._export_directory = export_directory
        self._heightmap_path = Path(heightmap).resolve() if heightmap else None
        self._performance_profile = performance_profile
        self._target_style = target_style
        self._auto_layer_paint = auto_layer_paint
        self._season = season
        self._use_hierarchical_pcg = hierarchical_pcg
        self._ue_editor = Path(ue_editor) if ue_editor else None
        self._ue_map = ue_map
        self._ue_asset_folder = ue_asset_folder
        self._ue_spawn = ue_spawn
        self._ue_script = Path(__file__).resolve().parents[1] / "scripts" / "ue_pcg_import.py"
        self.cache_path = self._resolve_cache_path(project_root)
        if self.cache_path and self.cache_path.exists():
            try:
                self.database.load_from_json(self.cache_path)
                LOGGER.info("Geladene Asset-Datenbank: %s", self.cache_path)
            except Exception as exc:  # pragma: no cover - Dateifehler
                LOGGER.warning("Konnte Asset-Cache nicht laden (%s): %s", self.cache_path, exc)
        position_resolver = self._resolve_asset_position if self._use_spatial_database else None
        lod_resolver = self._estimate_asset_lod if self._use_spatial_database else None
        self.scanner = AssetScanner(
            project_root,
            self.database,
            position_resolver=position_resolver,
            lod_resolver=lod_resolver,
        )
        self.analyzer = AssetAnalyzer()
        self.prompt_engine = PromptEngine()
        self.llm_manager = LLMManager(
            prompt_engine=self.prompt_engine,
            local_model_path=self._resolve_local_model_path() if use_local_model else None,
            classification_batch_size=classification_batch_size,
            base_url=ollama_url or "http://localhost:11434",
            model=ollama_model or "llama3",
            timeout=ollama_timeout or 10.0,
        )
        if self._use_hierarchical_pcg:
            self.graph_builder: PCGBuilder = HierarchicalPCGBuilder()
        else:
            self.graph_builder = PCGBuilder()
        self.heightmap_processor = HeightmapProcessor()
        self.material_planner = MaterialPlanner(llm_manager=self.llm_manager)
        self.layer_painter = LayerPainter()
        self.heightmap_analysis: Optional[HeightmapAnalysisResult] = None
        self.material_blueprint: Optional[MaterialBlueprint] = None
        self.layer_plan: Optional[LandscapeLayerPlan] = None
        self._exporter = (
            UnrealPCGExporter(self._export_directory) if self._export_directory else None
        )
        self._uproject_path = self._find_uproject(self._project_root)
        if not self.llm_manager._local_client:
            self.llm_manager.setup_ollama_connection()

    def scan_and_classify_assets(self) -> List[AssetData]:
        """Führt den Asset-Scan durch und klassifiziert jedes Asset."""
        assets = self.scanner.scan_project_assets(limit=self._max_assets)
        if self._max_assets is not None:
            LOGGER.info(
                "Asset-Scan auf maximal %s Dateien begrenzt (gefunden: %s).",
                self._max_assets,
                len(assets),
            )
        assets_to_classify: List[AssetData] = []
        for asset in assets:
            cached = self.database.get_asset(asset.asset_id)
            if cached and cached.semantic_tags:
                asset.semantic_tags = cached.semantic_tags
                asset.semantic_profile = cached.semantic_profile
                self.database.store_asset(asset)
            else:
                assets_to_classify.append(asset)

        if assets_to_classify:
            if self._prefer_heuristics:
                LOGGER.info(
                    "Überspringe LLM-Klassifikation und nutze heuristischen Schnellmodus (%s Assets).",
                    len(assets_to_classify),
                )
                for asset in assets_to_classify:
                    classification = self.analyzer.classify_asset_semantics(asset)
                    self._apply_classification(asset, classification)
                    self.database.store_asset(asset)
            else:
                classifications = self.llm_manager.send_classification_request(assets_to_classify)
                by_path = {
                    classification.asset_path.resolve(): classification
                    for classification in classifications
                }
                for asset in assets_to_classify:
                    classification = by_path.get(asset.asset_path.resolve())
                    if classification:
                        self._apply_classification(asset, classification)
                    self.database.store_asset(asset)

        self._persist_database()
        self._has_scanned = True
        return assets

    def generate_pcg_plan(self, user_prompt: str, asset_subset: Sequence[AssetData] | None = None) -> PCGPlan:
        """Erstellt einen PCG-Plan für den angegebenen Textbefehl."""
        if not self._has_scanned:
            LOGGER.info("Starte automatischen Asset-Scan vor der Planerstellung.")
            self.scan_and_classify_assets()
        context_assets = list(asset_subset or self._choose_context_assets(user_prompt))
        if not context_assets:
            context_assets = list(self.database.all_assets())
        return self.llm_manager.send_pcg_generation_request(
            user_prompt,
            context_assets,
            world_size=self._world_size,
            season=self._season,
        )
        return self.llm_manager.send_pcg_generation_request(
            user_prompt,
            context_assets,
            world_size=self._world_size,
            season=self._season,
        )

    def build_graph_for_prompt(self, user_prompt: str) -> PCGGraph:
        """Kompletter Workflow von Text zu PCG-Graph."""
        if not self._has_scanned:
            LOGGER.info("Assets wurden noch nicht gescannt – führe Scan jetzt aus.")
            self.scan_and_classify_assets()
        plan = self.generate_pcg_plan(user_prompt)
        world_bounds = self._world_bounds()
        if isinstance(self.graph_builder, HierarchicalPCGBuilder):
            graph = self.graph_builder.create_hierarchical_graph(plan, world_bounds=world_bounds)
        else:
            graph = self.graph_builder.create_pcg_graph_from_plan(plan)
        export_path = None
        if self._exporter:
            export_path = self._exporter.export(graph)
            LOGGER.info("PCG-Graph nach %s exportiert.", export_path)
        if self._ue_editor and export_path:
            self._trigger_unreal_import(export_path)
        return graph

    def run_full_pipeline(self, user_prompt: str) -> Dict[str, object]:
        """Führt Heightmap-, Asset-, PCG- und Material-Schritte automatisch aus."""
        analysis = self._ensure_heightmap_analysis()
        assets = self.scan_and_classify_assets()
        graph = self.build_graph_for_prompt(user_prompt)
        blueprint = self._ensure_material_blueprint()
        layer_plan = self._ensure_layer_plan()
        return {
            "graph": graph,
            "assets": assets,
            "heightmap_analysis": analysis,
            "material_blueprint": blueprint,
            "layer_plan": layer_plan,
        }

    # Private Hilfen ----------------------------------------------------------------------------

    def _ensure_heightmap_analysis(self) -> Optional[HeightmapAnalysisResult]:
        if self.heightmap_analysis or not self._heightmap_path:
            return self.heightmap_analysis
        try:
            analysis = self.heightmap_processor.process_heightmap(
                self._heightmap_path,
                target_style=self._target_style,
                performance_profile=self._performance_profile,
            )
        except FileNotFoundError as exc:
            LOGGER.warning("Heightmap konnte nicht verarbeitet werden: %s", exc)
            return None
        strategy = self.llm_manager.plan_heightmap_strategy(analysis)
        if strategy:
            self._apply_heightmap_strategy(analysis, strategy)
        self.heightmap_analysis = analysis
        return analysis

    def _apply_heightmap_strategy(self, analysis: HeightmapAnalysisResult, strategy: Dict[str, object]) -> None:
        notes = strategy.get("notes")
        if isinstance(notes, list):
            analysis.notes.extend(str(entry) for entry in notes)
        scale = strategy.get("scale")
        if isinstance(scale, (list, tuple)) and len(scale) == 3:
            analysis.scale = tuple(float(value) for value in scale)  # type: ignore[assignment]
        settings = strategy.get("landscape_settings")
        if isinstance(settings, dict):
            cast_map = {
                "section_size": int,
                "components_x": int,
                "components_y": int,
                "lod_distance": float,
            }
            for field, caster in cast_map.items():
                if field in settings:
                    try:
                        setattr(analysis.landscape_settings, field, caster(settings[field]))
                    except (TypeError, ValueError):
                        continue
        recommended = strategy.get("recommended_biomes")
        if isinstance(recommended, list):
            for biome, suggestion in zip(analysis.biomes, recommended):
                if not isinstance(suggestion, dict):
                    continue
                biome.name = str(suggestion.get("name", biome.name))
                if "elevation_range" in suggestion:
                    values = suggestion["elevation_range"]
                    if isinstance(values, (list, tuple)) and len(values) == 2:
                        biome.elevation_range = (float(values[0]), float(values[1]))
                if "slope_range" in suggestion:
                    values = suggestion["slope_range"]
                    if isinstance(values, (list, tuple)) and len(values) == 2:
                        biome.slope_range = (float(values[0]), float(values[1]))

    def _ensure_material_blueprint(self) -> Optional[MaterialBlueprint]:
        if self.material_blueprint:
            return self.material_blueprint
        analysis = self._ensure_heightmap_analysis()
        if not analysis:
            return None
        blueprint = self.material_planner.build_blueprint(
            analysis,
            target_style=self._target_style,
            performance_profile=self._performance_profile,
            season=self._season,
            enable_transitions=True,
        )
        suggestion = self.llm_manager.plan_material_blueprint(analysis, blueprint)
        if suggestion:
            blueprint = self._merge_material_blueprint(blueprint, suggestion)
        self.material_blueprint = blueprint
        return blueprint

    def _merge_material_blueprint(
        self,
        blueprint: MaterialBlueprint,
        payload: Dict[str, object],
    ) -> MaterialBlueprint:
        layers_payload = payload.get("layers")
        if isinstance(layers_payload, list) and layers_payload:
            new_layers: List[MaterialLayerConfig] = []
            for entry in layers_payload:
                layer = self._layer_config_from_payload(entry)
                if layer:
                    new_layers.append(layer)
            if new_layers:
                blueprint.layers = new_layers
        global_parameters = payload.get("global_parameters")
        if isinstance(global_parameters, dict):
            blueprint.global_parameters.update(
                {str(key): float(value) for key, value in global_parameters.items() if isinstance(value, (int, float))}
            )
        notes = payload.get("performance_notes")
        if isinstance(notes, list):
            blueprint.performance_notes.extend(str(note) for note in notes)
        return blueprint

    def _layer_config_from_payload(self, entry: object) -> Optional[MaterialLayerConfig]:
        if not isinstance(entry, dict):
            return None
        biome = str(entry.get("biome") or entry.get("name") or "biome")
        texture_set = entry.get("texture_set") or entry.get("textures") or {}
        if not isinstance(texture_set, dict):
            texture_set = {}
        tiling = float(entry.get("tiling", 1.0))
        blending = entry.get("blending_rules") or entry.get("blending") or {}
        if not isinstance(blending, dict):
            blending = {}
        parameters = entry.get("exposed_parameters") or entry.get("parameters") or {}
        if not isinstance(parameters, dict):
            parameters = {}
        return MaterialLayerConfig(
            biome=biome,
            texture_set={str(key): str(value) for key, value in texture_set.items()},
            tiling=tiling,
            blending_rules={str(key): float(value) for key, value in blending.items() if isinstance(value, (int, float))},
            exposed_parameters={
                str(key): float(value) for key, value in parameters.items() if isinstance(value, (int, float))
            },
        )

    def _ensure_layer_plan(self) -> Optional[LandscapeLayerPlan]:
        if self.layer_plan or not self._auto_layer_paint:
            return self.layer_plan
        analysis = self._ensure_heightmap_analysis()
        if not analysis:
            return None
        plan = self.layer_painter.build_layer_plan(
            analysis,
            output_dir=self._export_directory,
            season=self._season,
        )
        suggestion = self.llm_manager.plan_layer_paint(plan)
        if suggestion:
            plan = self._merge_layer_plan(plan, suggestion)
        self.layer_plan = plan
        return plan

    def _merge_layer_plan(
        self,
        plan: LandscapeLayerPlan,
        payload: Dict[str, object],
    ) -> LandscapeLayerPlan:
        masks = payload.get("masks")
        if isinstance(masks, list) and masks:
            new_masks: List[LandscapeLayerMask] = []
            for entry in masks:
                if not isinstance(entry, dict):
                    continue
                biome = str(entry.get("biome", "layer"))
                mask_path = entry.get("mask_path")
                path_obj = Path(mask_path) if isinstance(mask_path, str) else None
                softness = float(entry.get("softness", 0.25))
                order = int(entry.get("recommended_order", len(new_masks)))
                new_masks.append(
                    LandscapeLayerMask(
                        biome=biome,
                        mask_path=path_obj,
                        softness=softness,
                        recommended_order=order,
                    )
                )
            if new_masks:
                plan.masks = new_masks
        adaptive = payload.get("adaptive_rules")
        if isinstance(adaptive, dict):
            plan.adaptive_rules.update(
                {str(key): float(value) for key, value in adaptive.items() if isinstance(value, (int, float))}
            )
        return plan

    def _world_bounds(self) -> BoundingBox:
        half = self._world_size
        height = max(256.0, self._world_size * 0.1)
        return BoundingBox(
            Vector3(0.0, 0.0, 0.0),
            Vector3(half, half, height),
        )

    def get_assets_in_region(self, bounds: BoundingBox, lod_level: int = 0) -> List[AssetData]:
        """Liefert Assets innerhalb einer Region (nur bei Spatial DB sinnvoll)."""
        if not isinstance(self.database, SpatialAssetDatabase):
            return list(self.database.all_assets())
        asset_ids = self.database.query_assets_in_region(bounds, lod_level)
        assets: List[AssetData] = []
        for asset_id in asset_ids:
            asset = self.database.get_asset(asset_id)
            if asset:
                assets.append(asset)
        return assets

    def _choose_context_assets(self, user_prompt: str) -> Iterable[AssetData]:
        """Nutzt einfache Keyword-Extraktion, um relevante Assets zu finden."""
        keywords = [
            token.lower()
            for token in user_prompt.replace(",", " ").split()
            if len(token) > 3
        ]
        if not keywords:
            return self.database.all_assets()
        recommendations = self.database.get_asset_recommendations(keywords, limit=5)
        if recommendations:
            return recommendations
        return self.database.all_assets()

    def _resolve_asset_position(self, asset_path: Path) -> Optional[Vector3]:
        try:
            digest = hashlib.md5(str(asset_path).encode("utf-8"), usedforsecurity=False).digest()
        except ValueError:
            return None
        span = self._world_size
        x = float(int.from_bytes(digest[0:4], "little") % int(span))
        y = float(int.from_bytes(digest[4:8], "little") % int(span))
        z = float(int.from_bytes(digest[8:12], "little") % int(max(256.0, span * 0.05)))
        return Vector3(x, y, z)

    def _estimate_asset_lod(self, asset_path: Path) -> int:
        try:
            size = asset_path.stat().st_size
        except OSError:
            size = 0
        if size > 20_000_000:
            return 0
        if size > 5_000_000:
            return 1
        return 2

    def _resolve_local_model_path(self) -> Optional[Path]:
        """Sucht nach einem GGUF-Modell im Projekt oder über Umgebungsvariable."""
        env_path = os.getenv("AUTO_PCG_GGUF_MODEL")
        if env_path:
            candidate = Path(env_path).expanduser()
            if candidate.exists():
                return candidate
        module_path = Path(__file__).resolve()
        repo_root = module_path.parent
        try:
            repo_root = module_path.parents[3]
        except IndexError:
            repo_root = module_path.parent
        search_roots = [
            Path.cwd(),
            repo_root,
        ]
        for root in search_roots:
            for match in root.glob("*.gguf"):
                return match
        return None

    def _resolve_cache_path(self, project_root: Path) -> Optional[Path]:
        """Bestimmt, wo die Asset-Datenbank zwischengespeichert wird."""
        env_cache = os.getenv("AUTO_PCG_CACHE")
        if env_cache:
            return Path(env_cache).expanduser()
        try:
            project_root = Path(project_root).resolve()
        except OSError:
            project_root = Path.cwd()
        return project_root / ".auto_pcg_assets.json"

    def _persist_database(self) -> None:
        """Schreibt die aktuelle Datenbank auf die Platte."""
        if not self.cache_path:
            return
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.database.save_to_file(self.cache_path)
        except Exception as exc:  # pragma: no cover - Dateifehler
            LOGGER.warning("Konnte Asset-Cache nicht speichern (%s): %s", self.cache_path, exc)

    def _apply_classification(self, asset: AssetData, classification: Classification) -> None:
        """Aktualisiert ein Asset anhand einer Klassifikation."""
        asset.semantic_tags = classification.tags
        asset.semantic_profile = classification.to_profile()

    def _find_uproject(self, start_path: Path) -> Optional[Path]:
        """Sucht im angegebenen Pfad und darüber nach einer .uproject Datei."""
        current = start_path
        for _ in range(4):
            matches = list(current.glob("*.uproject"))
            if matches:
                return matches[0]
            if current.parent == current:
                break
            current = current.parent
        LOGGER.warning("Keine .uproject Datei im Pfad %s gefunden.", start_path)
        return None

    def _trigger_unreal_import(self, json_path: Path) -> None:
        if not self._ue_editor or not self._uproject_path:
            LOGGER.warning("UE-Editor oder .uproject Pfad nicht gesetzt – Import wird übersprungen.")
            return
        try:
            run_unreal_import(
                editor_exe=self._ue_editor,
                uproject=self._uproject_path,
                graph_path=json_path,
                script_path=self._ue_script,
                asset_folder=self._ue_asset_folder,
                asset_name=json_path.stem,
                map_path=self._ue_map,
                spawn=self._ue_spawn,
            )
        except Exception as exc:
            LOGGER.warning("Unreal-Import fehlgeschlagen: %s", exc)
