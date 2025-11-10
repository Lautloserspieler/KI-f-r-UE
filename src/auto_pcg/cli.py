"""Command line entry point for the Auto-PCG system."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any, Dict

from auto_pcg.services.pcg_service import AutoPCGService

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Auto-PCG KI-Assistent")
    parser.add_argument("--project", type=Path, default=Path("."), help="Wurzelverzeichnis des Unreal-Projekts")
    parser.add_argument("--prompt", type=str, default="Erstelle einen dichten Wald", help="Natürlicher Sprachbefehl")
    parser.add_argument("--max-assets", type=int, default=None, help="Maximale Anzahl an Assets für den Scan")
    parser.add_argument("--batch-size", type=int, default=None, help="Anzahl Assets pro LLM-Klassifikationsbatch")
    parser.add_argument(
        "--heuristic-only",
        action="store_true",
        help="Überspringt das LLM und nutzt nur heuristische Klassifikation (am schnellsten)",
    )
    parser.add_argument(
        "--export-graph",
        type=Path,
        default=None,
        help="Optionales Zielverzeichnis, in das Graph-/Materialdaten exportiert werden",
    )
    parser.add_argument("--heightmap", type=Path, default=None, help="Pfad zu einer Heightmap-Datei")
    parser.add_argument(
        "--performance-profile",
        type=str,
        default="desktop",
        choices=["mobile", "desktop", "console", "high_end_pc"],
        help="Optimierungsziel für Landscape-/Material-Parameter",
    )
    parser.add_argument(
        "--target-style",
        type=str,
        default="realistic",
        help="Zielstil der Landschaft (z. B. realistic, stylized, tundra, desert)",
    )
    parser.add_argument(
        "--season",
        type=str,
        default="summer",
        help="Saisonaler Kontext (z. B. summer, autumn, winter, spring)",
    )
    parser.add_argument("--ollama-url", type=str, default=None, help="Optionaler Ollama-Endpunkt")
    parser.add_argument("--ollama-model", type=str, default=None, help="Name des Ollama-Modells (z. B. llama3)")
    parser.add_argument(
        "--ollama-timeout",
        type=float,
        default=None,
        help="HTTP-Timeout für Ollama-Requests in Sekunden (Standard 10)",
    )
    parser.add_argument(
        "--no-local-model",
        action="store_true",
        help="Deaktiviert das lokale GGUF-Modell und nutzt ausschließlich Ollama",
    )
    parser.add_argument(
        "--no-layer-paint",
        action="store_true",
        help="Deaktiviert automatische Landscape-Layer-Planung",
    )
    parser.add_argument(
        "--use-spatial-db",
        action="store_true",
        help="Aktiviert die räumliche Asset-Datenbank für große Welten",
    )
    parser.add_argument(
        "--hierarchical-pcg",
        action="store_true",
        help="Nutze Makro/Meso/Mikro-PCG-Graphen für große Welten",
    )
    parser.add_argument(
        "--world-size",
        type=float,
        default=2048.0,
        help="Ausdehnung der Welt in Metern (für Spatial Indexing)",
    )
    parser.add_argument(
        "--sector-size",
        type=float,
        default=512.0,
        help="Rastergröße für Spatial Asset Streaming",
    )
    parser.add_argument("--ue-editor", type=Path, default=None, help="Pfad zur UnrealEditor-Cmd.exe")
    parser.add_argument("--ue-map", type=str, default=None, help="Optionaler Map-Pfad (z. B. /Game/Maps/Example)")
    parser.add_argument(
        "--ue-asset-folder",
        type=str,
        default="/Game/AutoPCG",
        help="Content-Browser-Pfad für importierte Assets",
    )
    parser.add_argument(
        "--ue-no-spawn",
        action="store_true",
        help="Nur Graphen importieren, kein PCG-Volume im Level anlegen",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    service = AutoPCGService(
        args.project,
        max_assets=args.max_assets,
        prefer_heuristics=args.heuristic_only,
        classification_batch_size=args.batch_size,
        ollama_url=args.ollama_url,
        ollama_model=args.ollama_model,
        ollama_timeout=args.ollama_timeout,
        use_local_model=not args.no_local_model,
        export_directory=args.export_graph,
        heightmap=args.heightmap,
        performance_profile=args.performance_profile,
        target_style=args.target_style,
        auto_layer_paint=not args.no_layer_paint,
        ue_editor=args.ue_editor,
        ue_map=args.ue_map,
        ue_asset_folder=args.ue_asset_folder,
        ue_spawn=not args.ue_no_spawn,
        use_spatial_database=args.use_spatial_db,
        world_size=args.world_size,
        sector_size=args.sector_size,
        season=args.season,
        hierarchical_pcg=args.hierarchical_pcg,
    )

    logging.info("Starte vollautomatische KI-Pipeline...")
    result = service.run_full_pipeline(args.prompt)
    logging.info("Pipeline abgeschlossen.")
    payload = _serialize_result(result)
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def _serialize_result(result: Dict[str, Any]) -> Dict[str, Any]:
    graph = result.get("graph")
    assets = result.get("assets") or []
    analysis = result.get("heightmap_analysis")
    blueprint = result.get("material_blueprint")
    layer_plan = result.get("layer_plan")
    return {
        "graph": _graph_to_dict(graph) if graph else None,
        "assets": [asset.to_dict() for asset in assets],
        "heightmap_analysis": analysis.to_dict() if analysis else None,
        "material_blueprint": blueprint.to_dict() if blueprint else None,
        "layer_plan": layer_plan.to_dict() if layer_plan else None,
    }


def _graph_to_dict(graph):
    return {
        "generated_at": graph.generated_at.isoformat(),
        "description": graph.description,
        "nodes": [_node_to_dict(node) for node in graph.root_nodes],
    }


def _node_to_dict(node):
    return {
        "name": node.name,
        "type": node.layer_type,
        "config": node.config,
        "children": [_node_to_dict(child) for child in node.children],
    }


if __name__ == "__main__":
    main()
