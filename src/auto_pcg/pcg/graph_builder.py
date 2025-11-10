"""Erstellt PCG-Graphen aus abstrakten Plänen."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

from auto_pcg.models.schemas import PCGFilterSpec, PCGGraph, PCGLayer, PCGNode, PCGPlan
from auto_pcg.models.spatial import BoundingBox, Vector3


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


class HierarchicalPCGBuilder(PCGBuilder):
    """Baut PCG-Graphen mit Makro-/Meso-/Mikro-Hierarchie für große Welten."""

    def __init__(
        self,
        macro_threshold: float = 0.55,
        micro_threshold: float = 0.2,
    ) -> None:
        self.macro_threshold = macro_threshold
        self.micro_threshold = micro_threshold

    def create_hierarchical_graph(
        self,
        plan: PCGPlan,
        world_bounds: Optional[BoundingBox] = None,
    ) -> PCGGraph:
        """Teilt Layer in Hierarchieebenen und erstellt ein Baum-Layout."""
        macro_nodes: List[PCGNode] = []
        meso_nodes: List[PCGNode] = []
        micro_nodes: List[PCGNode] = []
        for index, layer in enumerate(plan.layers):
            tier = self._classify_layer(layer)
            node = self._layer_to_node(layer, index)
            node.config.setdefault("lod_tier", tier)
            if world_bounds:
                node.config.setdefault("world_bounds", self._bounds_to_dict(world_bounds))
            if tier == "macro":
                macro_nodes.append(node)
            elif tier == "meso":
                meso_nodes.append(node)
            else:
                micro_nodes.append(node)

        if not macro_nodes and meso_nodes:
            macro_nodes = meso_nodes
            meso_nodes = []
        if not macro_nodes:
            macro_nodes = micro_nodes
            micro_nodes = []

        self._attach_children(meso_nodes, macro_nodes)
        self._attach_children(micro_nodes, meso_nodes or macro_nodes)

        return PCGGraph(root_nodes=macro_nodes, generated_at=datetime.utcnow(), description=plan.description)

    # Intern ----------------------------------------------------------------------------

    def _classify_layer(self, layer: PCGLayer) -> str:
        if layer.layer_type == "SURFACE":
            return "macro"
        density = float(layer.parameters.get("density", 0.5))
        asset_count = len(layer.assets)
        if density >= self.macro_threshold or asset_count >= 8:
            return "macro"
        if density <= self.micro_threshold or asset_count <= 2:
            return "micro"
        return "meso"

    def _attach_children(self, children: List[PCGNode], parents: List[PCGNode]) -> None:
        if not parents:
            return
        for index, child in enumerate(children):
            parent = parents[index % len(parents)]
            parent.children.append(child)

    @staticmethod
    def _bounds_to_dict(bounds: BoundingBox) -> dict:
        return {
            "min": {"x": bounds.min.x, "y": bounds.min.y, "z": bounds.min.z},
            "max": {"x": bounds.max.x, "y": bounds.max.y, "z": bounds.max.z},
        }
