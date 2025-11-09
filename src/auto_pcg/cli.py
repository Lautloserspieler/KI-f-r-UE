"""Kommandozeilen-Einstiegspunkt für das Auto-PCG System."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from auto_pcg.services.pcg_service import AutoPCGService

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Auto-PCG KI-Assistent")
    parser.add_argument(
        "--project",
        type=Path,
        default=Path("."),
        help="Wurzelverzeichnis des Unreal-Projekts",
    )
    parser.add_argument(
        "--prompt",
        type=str,
        default="Erstelle einen dichten Wald",
        help="Natürlicher Sprachbefehl",
    )
    parser.add_argument(
        "--max-assets",
        type=int,
        default=None,
        help="Begrenzt den Asset-Scan auf die angegebene Anzahl Dateien",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Anzahl Assets pro LLM-Klassifikationsbatch (kleiner = kürzere Prompts)",
    )
    parser.add_argument(
        "--heuristic-only",
        action="store_true",
        help="Überspringt das LLM und nutzt nur heuristische Klassifikation (am schnellsten)",
    )
    parser.add_argument(
        "--export-graph",
        type=Path,
        default=None,
        help="Optionales Zielverzeichnis, in das der PCG-Graph als JSON für UE exportiert wird",
    )
    parser.add_argument(
        "--ollama-url",
        type=str,
        default=None,
        help="Optionaler Ollama-Endpunkt (z. B. http://localhost:11434)",
    )
    parser.add_argument(
        "--ollama-model",
        type=str,
        default=None,
        help="Name des Ollama-Modells (z. B. llama3)",
    )
    parser.add_argument(
        "--no-local-model",
        action="store_true",
        help="Deaktiviert das lokale GGUF-Modell und nutzt ausschließlich Ollama",
    )
    parser.add_argument(
        "--ollama-timeout",
        type=float,
        default=None,
        help="HTTP-Timeout für Ollama-Requests in Sekunden (Standard 10)",
    )
    parser.add_argument(
        "--ue-editor",
        type=Path,
        default=None,
        help="Pfad zur UnrealEditor-Cmd.exe für automatischen Import",
    )
    parser.add_argument(
        "--ue-map",
        type=str,
        default=None,
        help="Optionaler Map-Pfad (/Game/Maps/XYZ), der vor dem Platzieren geladen wird",
    )
    parser.add_argument(
        "--ue-asset-folder",
        type=str,
        default="/Game/AutoPCG",
        help="Content-Browser-Pfad für importierte PCG-Graphen",
    )
    parser.add_argument(
        "--ue-no-spawn",
        action="store_true",
        help="Nur Graph importieren, kein PCG-Volume im Level anlegen",
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
        ue_editor=args.ue_editor,
        ue_map=args.ue_map,
        ue_asset_folder=args.ue_asset_folder,
        ue_spawn=not args.ue_no_spawn,
    )

    logging.info("Scanne Assets...")
    assets = service.scan_and_classify_assets()
    logging.info("Gefundene Assets: %s", len(assets))

    logging.info("Generiere PCG-Graphen...")
    graph = service.build_graph_for_prompt(args.prompt)
    print(json.dumps({"graph": _graph_to_dict(graph)}, indent=2, ensure_ascii=False))


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
