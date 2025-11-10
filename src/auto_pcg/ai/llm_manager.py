"""Verwaltung der LLM-Kommunikation (lokal oder via HTTP)."""

from __future__ import annotations

import json
import logging
import math
import time
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import requests

from auto_pcg.core.asset_analyzer import AssetAnalyzer
from auto_pcg.models.schemas import AssetData, Classification, PCGFilterSpec, PCGLayer, PCGPlan
from auto_pcg.models.terrain import HeightmapAnalysisResult, LandscapeLayerPlan, MaterialBlueprint

from .local_llm import LocalGGUFClient, LocalLLMError, _auto_close_json, _extract_json_block
from .prompt_engine import PromptEngine

LOGGER = logging.getLogger(__name__)


class LLMManager:
    """Kapselt sowohl lokale GGUF-Aufrufe als auch Ollama-kompatibles HTTP."""

    CLASSIFICATION_BATCH_SIZE = 10
    PCG_CONTEXT_LIMIT = 30

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "llama3",
        timeout: float = 10.0,
        prompt_engine: Optional[PromptEngine] = None,
        local_model_path: Optional[Path] = None,
        classification_batch_size: Optional[int] = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.session = requests.Session()
        self.prompt_engine = prompt_engine or PromptEngine()
        self._analyzer = AssetAnalyzer()
        self._local_client: Optional[LocalGGUFClient] = None
        self._classification_batch_size = (
            max(1, classification_batch_size) if classification_batch_size else self.CLASSIFICATION_BATCH_SIZE
        )
        if local_model_path:
            try:
                self._local_client = LocalGGUFClient(local_model_path)
                LOGGER.info("Verwende lokales GGUF-Modell: %s", local_model_path)
            except LocalLLMError as exc:
                LOGGER.warning("Lokales GGUF-Modell konnte nicht geladen werden: %s", exc)

    def setup_ollama_connection(self) -> bool:
        """Validiert, ob der Ollama-Endpunkt erreichbar ist."""
        try:
            response = self.session.get(f"{self.base_url}/api/tags", timeout=self.timeout)
            response.raise_for_status()
            return True
        except requests.RequestException as exc:  # pragma: no cover - nur Netzwerkausnahme
            LOGGER.warning("Ollama nicht erreichbar: %s", exc)
            return False

    def send_classification_request(self, assets: Sequence[AssetData]) -> List[Classification]:
        """Sendet eine Klassifikationsanfrage oder nutzt Fallback-Heuristiken."""
        results: List[Classification] = []
        total_batches = math.ceil(len(assets) / self._classification_batch_size) or 1
        for batch_index, batch in enumerate(_chunked(assets, self._classification_batch_size)):
            LOGGER.info(
                "LLM-Klassifikation Batch %s/%s (%s Assets)...",
                batch_index + 1,
                total_batches,
                len(batch),
            )
            start = time.perf_counter()
            prompt = self.prompt_engine.build_asset_classification_prompt(batch)
            parsed = self._parse_classifications(self._run_prompt(prompt), batch)
            if parsed:
                duration = time.perf_counter() - start
                LOGGER.info(
                    "LLM-Klassifikation Batch %s abgeschlossen (%.1fs, %s Ergebnisse).",
                    batch_index + 1,
                    duration,
                    len(parsed),
                )
                results.extend(parsed)
            else:
                duration = time.perf_counter() - start
                LOGGER.info("Nutze lokale Fallback-Klassifikation (Batch %s).", batch_index)
                results.extend(self._analyzer.classify_asset_semantics(asset) for asset in batch)
        return results

    def send_pcg_generation_request(
        self,
        user_prompt: str,
        assets: Sequence[AssetData],
        *,
        world_size: float | None = None,
        season: str | None = None,
    ) -> PCGPlan:
        """Generiert einen PCG-Plan über das LLM oder liefert einen simplen Fallback."""
        context_assets = assets[: self.PCG_CONTEXT_LIMIT]
        if len(assets) > self.PCG_CONTEXT_LIMIT:
            LOGGER.info(
                "Beschränke PCG-Kontext von %s auf %s Assets, um den Prompt klein zu halten.",
                len(assets),
                self.PCG_CONTEXT_LIMIT,
            )
        prompt = self.prompt_engine.build_pcg_generation_prompt(
            user_prompt,
            context_assets,
            world_size=world_size,
            season=season,
        )
        LOGGER.info("LLM-PCG-Anfrage gestartet (Prompt: %s , Assets: %s).", user_prompt, len(context_assets))
        start = time.perf_counter()
        plan = self._parse_pcg_plan(self._run_prompt(prompt), context_assets)
        if plan:
            LOGGER.info("LLM-PCG-Antwort erhalten (%.1fs).", time.perf_counter() - start)
            return plan
        LOGGER.info("Nutze lokalen PCG-Fallback.")
        return self._fallback_pcg_plan(user_prompt, assets)

    # Terrain-Workflows ----------------------------------------------------------------------

    def plan_heightmap_strategy(
        self,
        analysis: HeightmapAnalysisResult,
    ) -> Optional[Dict[str, object]]:
        """Fragt das LLM nach Optimierungen für Heightmap/Biome."""
        prompt = self.prompt_engine.build_heightmap_strategy_prompt(analysis)
        payload = self._run_prompt(prompt)
        if not payload:
            return None
        strategy = payload.get("heightmap_strategy") if isinstance(payload, dict) else None
        if not isinstance(strategy, dict):
            return None
        return strategy

    def plan_material_blueprint(
        self,
        analysis: HeightmapAnalysisResult,
        blueprint: MaterialBlueprint,
    ) -> Optional[Dict[str, object]]:
        """Lässt das LLM Material-Layer Vorschläge liefern."""
        prompt = self.prompt_engine.build_material_blueprint_prompt(analysis, blueprint)
        payload = self._run_prompt(prompt)
        if not payload:
            return None
        result = payload.get("material_blueprint") if isinstance(payload, dict) else None
        if not isinstance(result, dict):
            return None
        return result

    def plan_layer_paint(self, plan: LandscapeLayerPlan) -> Optional[Dict[str, object]]:
        """Fragt das LLM nach Layer-Mask-Optimierungen."""
        prompt = self.prompt_engine.build_layer_paint_prompt(plan)
        payload = self._run_prompt(prompt)
        if not payload:
            return None
        result = payload.get("layer_plan") if isinstance(payload, dict) else None
        if not isinstance(result, dict):
            return None
        return result

    def validate_llm_response(self, response: Dict[str, object]) -> bool:
        """Stellt sicher, dass Kernfelder vorhanden sind."""
        if "pcg_plan" in response:
            plan = response["pcg_plan"]
            return isinstance(plan, dict) and "layers" in plan
        if "classifications" in response:
            value = response["classifications"]
            return isinstance(value, list)
        return False

    # Interne Hilfen ---------------------------------------------------------------------------

    def _run_prompt(self, prompt: str) -> Optional[Dict[str, object]]:
        """Routet Prompts an lokales GGUF oder an den HTTP-Endpunkt."""
        if self._local_client:
            try:
                return self._local_client.generate_json(prompt)
            except LocalLLMError as exc:
                LOGGER.error("Lokales LLM lieferte einen Fehler: %s", exc)
                return None
        return self._post_prompt_http(prompt)

    def _post_prompt_http(self, prompt: str) -> Optional[Dict[str, object]]:
        """Sendet einen Prompt an Ollama und dekodiert JSON."""
        last_exc: Optional[Exception] = None
        for mode in ("chat", "generate"):
            try:
                if mode == "chat":
                    response = self.session.post(
                        f"{self.base_url}/api/chat",
                        json={
                            "model": self.model,
                            "messages": [
                                {"role": "system", "content": "Antwort exakt mit gültigem JSON."},
                                {"role": "user", "content": prompt},
                            ],
                            "stream": False,
                            "response_format": {"type": "json_object"},
                        },
                        timeout=self.timeout,
                    )
                    response.raise_for_status()
                    payload = response.json()
                    text = payload.get("message", {}).get("content", "").strip()
                else:
                    response = self.session.post(
                        f"{self.base_url}/api/generate",
                        json={
                            "model": self.model,
                            "prompt": prompt,
                            "stream": False,
                            "format": "json",
                        },
                        timeout=self.timeout,
                    )
                    response.raise_for_status()
                    payload = response.json()
                    text = payload.get("response", "").strip()
                if not text:
                    LOGGER.warning("Ollama-%s-Antwort enthielt keinen Text.", mode)
                    continue
                decoded = self._decode_llm_json(text)
                if decoded is None:
                    raise json.JSONDecodeError("invalid json", text, 0)
                return decoded
            except (requests.RequestException, json.JSONDecodeError, KeyError) as exc:
                last_exc = exc
                LOGGER.warning("Ollama-%s-Request fehlgeschlagen: %s", mode, exc)
        if last_exc:
            LOGGER.warning("LLM-Kommunikation fehlgeschlagen: %s", last_exc)
        return None

    def _decode_llm_json(self, text: str) -> Optional[Dict[str, object]]:
        trimmed = text.strip()
        if not trimmed:
            return None
        try:
            return json.loads(trimmed)
        except json.JSONDecodeError:
            try:
                extracted = _extract_json_block(trimmed)
                repaired = _auto_close_json(extracted)
                return json.loads(repaired)
            except json.JSONDecodeError:
                return None

    def _infer_layer_type(self, payload: Dict[str, object]) -> Optional[str]:
        """Versucht, fehlende Layer-Typen aus Feldern abzuleiten."""
        if not isinstance(payload, dict):
            return None
        layer_id = str(payload.get("layer_id", "")).lower()
        assets = payload.get("assets") or []
        has_assets = isinstance(assets, list) and bool(assets)
        if "surface" in layer_id or "ground" in layer_id:
            return "SURFACE"
        if "scatter" in layer_id or "foliage" in layer_id:
            return "SCATTER"
        if has_assets and ("count_min" in payload or "count_max" in payload):
            return "SCATTER"
        probability = payload.get("probability")
        if has_assets and probability is not None:
            return "SCATTER"
        if payload.get("template"):
            return "SCATTER"
        return None

    def _normalize_layer_type(self, layer_type: str, payload: Optional[Dict[str, object]] = None) -> str:
        value = str(layer_type).lower()
        mapping = {
            "surface": "SURFACE",
            "ground": "SURFACE",
            "terrain": "SURFACE",
            "worldmaplayer": "SURFACE",
            "worldmaplayermerged": "SURFACE",
            "scatter": "SCATTER",
            "tree": "SCATTER",
            "sapling": "SCATTER",
            "seedling": "SCATTER",
            "vegetation": "SCATTER",
            "instance": "SCATTER",
            "hlodlayerinstanced": "SCATTER",
        }
        if value in mapping:
            return mapping[value]
        if payload:
            assets = payload.get("assets") or []
            if isinstance(assets, list) and assets:
                return "SCATTER"
        return layer_type if isinstance(layer_type, str) else str(layer_type).upper()

    def _resolve_assets(self, raw_assets, context_assets: Sequence[AssetData], payload: Optional[Dict[str, object]] = None) -> List[Path]:
        """Mappt Asset-Namen aus dem Plan auf echte Pfade."""
        candidates = list(raw_assets or [])
        if payload and payload.get("template"):
            candidates.append(payload["template"])
        name_to_asset = {
            asset.asset_path.stem.lower(): asset.asset_path
            for asset in context_assets
        }
        resolved: List[Path] = []
        for entry in candidates:
            if isinstance(entry, str):
                key = entry.split("/")[-1].split("\\")[-1].split(".")[0].lower()
                match = name_to_asset.get(key)
                if match:
                    resolved.append(match)
                else:
                    resolved.append(Path(entry))
        return resolved

    def _fallback_pcg_plan(self, user_prompt: str, assets: Sequence[AssetData]) -> PCGPlan:
        """Generiert einen simplen PCG-Plan ohne LLM."""
        chosen_assets = list(assets)[:3]
        layers = [
            PCGLayer(
                layer_type="SURFACE",
                purpose="Grundflaeche fuer " + user_prompt,
                assets=[asset.asset_path for asset in chosen_assets[:1]],
                parameters={"tiling": 1.0, "roughness": 0.4},
            ),
            PCGLayer(
                layer_type="SCATTER",
                purpose="Streuung thematischer Assets",
                assets=[asset.asset_path for asset in chosen_assets],
                parameters={"density": 0.65, "scale_variation": [0.8, 1.3]},
                filters=[PCGFilterSpec(type="BySlope", params={"min": 0.1, "max": 0.7})],
            ),
        ]
        return PCGPlan(
            description=f"Fallback-Plan fuer '{user_prompt}'",
            target_biome="generic",
            layers=layers,
        )

    def _parse_classifications(
        self,
        payload: Optional[Dict[str, object]],
        assets: Sequence[AssetData],
    ) -> List[Classification]:
        """Validiert LLM-Output und wandelt ihn in Classification-Objekte um."""
        if not payload or "classifications" not in payload:
            return []
        entries = payload.get("classifications", [])
        if not isinstance(entries, list):
            LOGGER.warning("LLM-Antwort enthaelt kein Klassen-Array.")
            return []
        result: List[Classification] = []
        for index, item in enumerate(entries):
            try:
                if not isinstance(item, dict):
                    raise TypeError("Eintrag ist kein Objekt.")
                fallback_path = assets[index].asset_path if index < len(assets) else assets[0].asset_path
                asset_path = Path(item.get("asset_path") or fallback_path)
                primary_category = item.get("primary_category") or item.get("class") or "PROP"
                sub_category = item.get("sub_category") or item.get("subclass") or "Generic"
                tags = item.get("tags") or item.get("classifications") or []
                style = item.get("style") or item.get("visual_style") or "realistic"
                biomes = item.get("biomes") or item.get("biome") or []
                technical = item.get("technical") or {}
                if isinstance(biomes, str):
                    biomes = [biomes]
                if not isinstance(tags, list):
                    tags = [str(tags)]
                if not isinstance(technical, dict):
                    technical = {}
                classification = Classification(
                    asset_path=asset_path,
                    primary_category=str(primary_category),
                    sub_category=str(sub_category),
                    tags=[str(tag) for tag in tags],
                    style=str(style),
                    biomes=[str(biome) for biome in biomes],
                    technical=technical,
                )
                result.append(classification)
            except (KeyError, IndexError, TypeError, ValueError) as exc:
                LOGGER.warning("Ungültige Klassifikation im LLM-Output (ignoriert): %s", exc)
        return result

    def _parse_pcg_plan(self, payload: Optional[Dict[str, object]], context_assets: Sequence[AssetData]) -> Optional[PCGPlan]:
        """Validiert den LLM-Output für PCG-Pläne."""
        if not payload or "pcg_plan" not in payload:
            return None
        plan_data = payload["pcg_plan"]
        if not isinstance(plan_data, dict):
            LOGGER.warning("PCG-Plan ist kein Objekt.")
            return None
        raw_layers = plan_data.get("layers", [])
        if not isinstance(raw_layers, list) or not raw_layers:
            LOGGER.warning("PCG-Plan enthaelt keine Layer.")
            return None
        try:
            layers = []
            for raw in raw_layers:
                if not isinstance(raw, dict):
                    continue
                layer_type = (
                    raw.get("type")
                    or raw.get("layer_type")
                    or self._infer_layer_type(raw)
                )
                if not layer_type:
                    LOGGER.warning("PCG-Layer ohne 'type' verworfen: %s", raw)
                    continue
                layer_type = self._normalize_layer_type(layer_type, raw)
                purpose = raw.get("purpose") or raw.get("description") or layer_type
                assets = self._resolve_assets(raw.get("assets", []), context_assets, raw)
                parameters = dict(raw.get("parameters", {}))
                for key in ("count_min", "count_max", "probability", "density"):
                    if key in raw and key not in parameters:
                        parameters[key] = raw[key]
                filters = [
                    PCGFilterSpec(
                        filter_spec.get("type", "Unknown"),
                        {k: v for k, v in filter_spec.items() if k != "type"},
                    )
                    for filter_spec in raw.get("filters", [])
                    if isinstance(filter_spec, dict)
                ]
                layers.append(
                    PCGLayer(
                        layer_type=str(layer_type),
                        purpose=str(purpose),
                        assets=assets,
                        parameters=parameters,
                        filters=filters,
                    )
                )
            if not layers:
                LOGGER.warning("Keine gueltigen Layer im PCG-Plan gefunden.")
                return None
            return PCGPlan(
                description=plan_data.get("description", "LLM-Plan"),
                target_biome=plan_data.get("target_biome", "unknown"),
                layers=layers,
            )
        except (KeyError, TypeError, ValueError) as exc:
            LOGGER.warning("PCG-Plan konnte nicht geparst werden: %s", exc)
            return None


def _chunked(sequence: Sequence[AssetData], size: int):
    """Teilt eine Sequenz in handliche Teilmengen auf."""
    if size <= 0:
        yield sequence
        return
    for i in range(0, len(sequence), size):
        yield sequence[i : i + size]
