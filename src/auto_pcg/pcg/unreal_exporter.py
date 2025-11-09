"""Hilfsklasse, um PCG-Graphen als JSON für Unreal zu exportieren."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List

from auto_pcg.models.schemas import PCGGraph, PCGNode


class UnrealPCGExporter:
    """Schreibt PCG-Graphen in ein einfaches JSON-Format für UE-Imports/Skripte."""

    def __init__(self, export_root: Path) -> None:
        self.export_root = Path(export_root)
        self.export_root.mkdir(parents=True, exist_ok=True)

    def export(self, graph: PCGGraph, file_prefix: str = "pcg_graph") -> Path:
        """Speichert den Graphen als JSON und gibt den Pfad zurück."""
        timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
        destination = self.export_root / f"{file_prefix}_{timestamp}.json"
        payload = self._graph_to_dict(graph)
        destination.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return destination

    def _graph_to_dict(self, graph: PCGGraph) -> Dict[str, object]:
        return {
            "description": graph.description,
            "generated_at": graph.generated_at.isoformat(),
            "nodes": [self._node_to_dict(node) for node in graph.root_nodes],
        }

    def _node_to_dict(self, node: PCGNode) -> Dict[str, object]:
        return {
            "name": node.name,
            "type": node.layer_type,
            "config": node.config,
            "children": [self._node_to_dict(child) for child in node.children],
        }
