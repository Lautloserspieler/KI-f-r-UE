"""UE Editor Python script to build a PCG Graph + optional placement from Auto-PCG JSON."""

import argparse
import json
from pathlib import Path

import unreal


def load_json_graph(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if "graph" not in data:
        raise RuntimeError("JSON enthaelt kein 'graph'-Objekt.")
    return data["graph"]


def ensure_pcg_plugin_enabled() -> None:
    required_attrs = [
        "PCGGraph",
        "PCGGraphFactory",
        "PCGVolume",
        "PCGScatterSettings",
        "PCGSurfaceSamplerSettings",
    ]
    missing = [name for name in required_attrs if not hasattr(unreal, name)]
    if missing:
        missing_str = ", ".join(missing)
        raise RuntimeError(
            "PCG-Plugin (Procedural Content Generation Framework) ist nicht aktiviert "
            f"oder nicht installiert. Fehlende Klassen: {missing_str}"
        )


def ensure_asset_folder(package_path: str) -> None:
    if not unreal.EditorAssetLibrary.does_directory_exist(package_path):
        unreal.EditorAssetLibrary.make_directory(package_path)


def create_or_load_graph(asset_path: str) -> unreal.PCGGraph:
    if unreal.EditorAssetLibrary.does_asset_exist(asset_path):
        asset = unreal.EditorAssetLibrary.load_asset(asset_path)
        if not isinstance(asset, unreal.PCGGraph):
            raise RuntimeError(f"Asset {asset_path} existiert, ist aber kein PCGGraph.")
        return asset
    ensure_asset_folder("/".join(asset_path.split("/")[:-1]))
    factory = unreal.PCGGraphFactory()
    asset_name = asset_path.split("/")[-1]
    package_path = "/".join(asset_path.split("/")[:-1])
    graph = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        asset_name, package_path, unreal.PCGGraph, factory
    )
    return graph


def add_surface_node(graph: unreal.PCGGraph, node_data: dict, position_x: float) -> None:
    settings = unreal.PCGSurfaceSamplerSettings()
    material_path = node_data.get("config", {}).get("material_asset")
    if material_path:
        settings.surface = unreal.SoftObjectPath(material_path)
    settings.tiling = float(node_data.get("config", {}).get("tiling", 1.0))
    node = graph.add_node(settings, unreal.Vector2D(position_x, 0.0))
    node.set_node_name(node_data.get("name", "Surface"))


def add_scatter_node(graph: unreal.PCGGraph, node_data: dict, position_x: float) -> None:
    settings = unreal.PCGScatterSettings()
    config = node_data.get("config", {})
    density = config.get("density") or config.get("probability") or 0.5
    settings.point_density = float(density)
    node = graph.add_node(settings, unreal.Vector2D(position_x, 0.0))
    node.set_node_name(node_data.get("name", "Scatter"))
    assets = config.get("assets", [])
    if assets:
        node_graph = node.get_graph()
        node_graph.set_metadata_entry("AutoPCGAssets", ",".join(str(a) for a in assets))


def rebuild_graph(graph: unreal.PCGGraph, graph_spec: dict) -> None:
    graph.remove_all_nodes()
    nodes = graph_spec.get("nodes", [])
    spacing = 450.0
    for index, node_data in enumerate(nodes):
        node_type = node_data.get("type", "").upper()
        pos = index * spacing
        if node_type == "SURFACE":
            add_surface_node(graph, node_data, pos)
        else:
            add_scatter_node(graph, node_data, pos)
    graph.mark_package_dirty()


def spawn_pcg_volume(graph_asset: unreal.PCGGraph, location: unreal.Vector) -> None:
    pcg_volume_class = unreal.PCGVolume
    volume = unreal.EditorLevelLibrary.spawn_actor_from_class(pcg_volume_class, location)
    volume.set_graph(graph_asset)
    volume.get_pcg_component().generate()


def load_target_map(map_path: str) -> bool:
    result = unreal.EditorLoadingAndSavingUtils.load_map(map_path)
    if not result:
        unreal.log_error(f"Konnte Map {map_path} nicht laden. Bitte Pfad pruefen.")
    return bool(result)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--graph-json", required=True)
    parser.add_argument("--asset-folder", default="/Game/AutoPCG")
    parser.add_argument("--asset-name", default=None)
    parser.add_argument("--spawn", action="store_true")
    parser.add_argument("--spawn-map", default=None)
    args = parser.parse_args()

    ensure_pcg_plugin_enabled()

    json_path = Path(args.graph_json).resolve()
    graph_spec = load_json_graph(json_path)

    asset_name = args.asset_name or json_path.stem
    asset_path = f"{args.asset_folder.rstrip('/')}/{asset_name}"

    map_ready = True
    if args.spawn_map:
        map_ready = load_target_map(args.spawn_map)

    graph_asset = create_or_load_graph(asset_path)
    rebuild_graph(graph_asset, graph_spec)
    unreal.EditorAssetLibrary.save_loaded_asset(graph_asset)

    should_spawn = bool(args.spawn and map_ready)
    if args.spawn and not should_spawn:
        unreal.log_warning("PCG-Volume wird nicht gespawnt, da die Map nicht geladen werden konnte.")

    if should_spawn:
        spawn_pcg_volume(graph_asset, unreal.Vector(0.0, 0.0, 0.0))

    unreal.log(f"Auto-PCG Graph importiert nach {asset_path}")


if __name__ == "__main__":
    main()
