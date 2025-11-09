"""Erstellt PCG-Graphen aus abstrakten Plänen."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Sequence

from auto_pcg.models.schemas import PCGFilterSpec, PCGGraph, PCGLayer, PCGNode, PCGPlan


class PCGBuilder:
    """Konvertiert PCG-Pläne in eine Graphstruktur, die später nach UE exportiert werden kann."""

    def create_pcg_graph_from_plan(self, plan: PCGPlan) -> PCGGraph:
        """Überführt alle Layer in PCG-Knoten."""
        nodes = [self._layer_to_node(layer, index) for index, layer in enumerate(plan.layers)]
        return PCGGraph(root_nodes=nodes, generated_at=datetime.utcnow(), description=plan.description)

    def build_surface_layer(self, spec: PCGLayer) -> PCGNode:
        """Erzeugt einen SURFACE-Knoten inkl. Parameter."""
        config = {
            "material_asset": str(spec.assets[0]) if spec.assets else None,
            **spec.parameters,
        }
        return PCGNode(name="SurfaceLayer", layer_type="SURFACE", config=config)

    def build_scatter_layer(self, assets: Sequence[Path], density: float) -> PCGNode:
        """Erzeugt einen SCATTER-Knoten basierend auf Assets und Dichte."""
        config = {
            "assets": [str(asset) for asset in assets],
            "density": density,
        }
        return PCGNode(name="ScatterLayer", layer_type="SCATTER", config=config)

    def apply_filters(self, node: PCGNode, filter_spec: Iterable[PCGFilterSpec]) -> PCGNode:
        """Fügt Filterinformationen in den Knotenkonfig an."""
        node.config.setdefault("filters", [])
        for spec in filter_spec:
            entry = {"type": spec.type, **spec.params}
            node.config["filters"].append(entry)
        return node

    # Hilfsfunktionen -------------------------------------------------------------------------

    def _layer_to_node(self, layer: PCGLayer, index: int) -> PCGNode:
        """Wandelt einen Layer in einen Knoten mit eindeutigen Namen um."""
        if layer.layer_type == "SURFACE":
            node = self.build_surface_layer(layer)
        elif layer.layer_type == "SCATTER":
            node = self.build_scatter_layer(layer.assets, float(layer.parameters.get("density", 0.5)))
        else:
            node = PCGNode(name="GenericLayer", layer_type=layer.layer_type, config=dict(layer.parameters))
        node.name = f"{layer.layer_type}_{index}"
        return self.apply_filters(node, layer.filters)
