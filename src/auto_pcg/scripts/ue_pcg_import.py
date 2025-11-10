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


def load_optional_payload(path: str | None) -> dict | None:
    if not path:
        return None
    json_path = Path(path).resolve()
    if not json_path.exists():
        unreal.log_warning(f"Konnte Datei {json_path} nicht finden.")
        return None
    try:
        return json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        unreal.log_warning(f"JSON konnte nicht geladen werden ({json_path}): {exc}")
        return None


def attach_metadata(asset: unreal.Object, key: str, payload: dict | None) -> None:
    if not payload:
        return
    try:
        serialized = json.dumps(payload)
        unreal.EditorAssetLibrary.set_metadata_tag(asset, key, serialized)
    except Exception as exc:  # pragma: no cover - Editor API spezifisch
        unreal.log_warning(f"Konnte Metadata {key} nicht setzen: {exc}")


def load_optional_payload(path: str | None) -> dict | None:
    if not path:
        return None
    json_path = Path(path).resolve()
    if not json_path.exists():
        unreal.log_warning(f"Konnte Datei {json_path} nicht finden.")
        return None
    try:
        return json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        unreal.log_warning(f"JSON konnte nicht geladen werden ({json_path}): {exc}")
        return None


def attach_metadata(asset: unreal.Object, key: str, payload: dict | None) -> None:
    if not payload:
        return
    try:
        serialized = json.dumps(payload)
        unreal.EditorAssetLibrary.set_metadata_tag(asset, key, serialized)
    except Exception as exc:  # pragma: no cover - Editor API spezifisch
        unreal.log_warning(f"Konnte Metadata {key} nicht setzen: {exc}")


def load_texture(texture_path: str | None) -> unreal.Texture | None:
    if not texture_path:
        return None
    try:
        asset = unreal.EditorAssetLibrary.load_asset(texture_path)
    except Exception:  # pragma: no cover - Editor API spezifisch
        asset = None
    if not asset:
        unreal.log_warning(f"Textur {texture_path} konnte nicht geladen werden.")
    return asset


def build_material_from_blueprint(
    blueprint: dict,
    asset_folder: str,
    asset_name: str,
) -> unreal.Material | None:
    layers = blueprint.get("layers") if isinstance(blueprint, dict) else None
    if not layers:
        return None
    package_path = f"{asset_folder.rstrip('/')}/Materials"
    ensure_asset_folder(package_path)
    material_name = f"{asset_name}_LandscapeMat"
    asset_path = f"{package_path}/{material_name}"
    material = unreal.EditorAssetLibrary.load_asset(asset_path)
    if not material:
        factory = unreal.MaterialFactoryNew()
        material = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
            material_name,
            package_path,
            unreal.Material,
            factory,
        )
    if not material:
        return None
    material.set_editor_property("use_with_landscape", True)
    mel = unreal.MaterialEditingLibrary
    mel.delete_all_material_expressions(material)
    mel.recompile_material(material)

    prev_expr = None
    pos_y = 0
    for layer in layers:
        if not isinstance(layer, dict):
            continue
        biome = str(layer.get("biome", f"Layer_{pos_y}"))
        texture_set = layer.get("texture_set", {})
        tiling = float(layer.get("tiling", 1.0))
        tex = load_texture(texture_set.get("albedo"))

        coord = mel.create_material_expression(
            material,
            unreal.MaterialExpressionTextureCoordinate,
            node_pos_x=-600,
            node_pos_y=pos_y,
        )
        coord.set_editor_property("utiling", tiling)
        coord.set_editor_property("vtiling", tiling)

        if tex:
            texture_expr = mel.create_material_expression(
                material,
                unreal.MaterialExpressionTextureSampleParameter2D,
                node_pos_x=-350,
                node_pos_y=pos_y,
            )
            texture_expr.texture = tex
            texture_expr.set_editor_property("parameter_name", f"{biome}_Albedo")
            mel.connect_material_expressions(coord, "", texture_expr, "Coordinates")
            color_expr = texture_expr
        else:
            const_expr = mel.create_material_expression(
                material,
                unreal.MaterialExpressionConstant3Vector,
                node_pos_x=-350,
                node_pos_y=pos_y,
            )
            color_expr = const_expr

        layer_sample = mel.create_material_expression(
            material,
            unreal.MaterialExpressionLandscapeLayerSample,
            node_pos_x=-150,
            node_pos_y=pos_y,
        )
        layer_sample.set_editor_property("parameter_name", biome)

        multiply = mel.create_material_expression(
            material,
            unreal.MaterialExpressionMultiply,
            node_pos_x=100,
            node_pos_y=pos_y,
        )
        mel.connect_material_expressions(layer_sample, "", multiply, "A")
        mel.connect_material_expressions(color_expr, "", multiply, "B")

        if tex and "normal" in texture_set:
            normal_tex = load_texture(texture_set.get("normal"))
            if normal_tex:
                normal_expr = mel.create_material_expression(
                    material,
                    unreal.MaterialExpressionTextureSampleParameter2D,
                    node_pos_x=-350,
                    node_pos_y=pos_y + 200,
                )
                normal_expr.texture = normal_tex
                normal_expr.set_editor_property("parameter_name", f"{biome}_Normal")
                mel.connect_material_property(
                    normal_expr,
                    "",
                    unreal.MaterialProperty.MP_NORMAL,
                )

        if prev_expr is None:
            prev_expr = multiply
        else:
            add_expr = mel.create_material_expression(
                material,
                unreal.MaterialExpressionAdd,
                node_pos_x=350,
                node_pos_y=pos_y,
            )
            mel.connect_material_expressions(prev_expr, "", add_expr, "A")
            mel.connect_material_expressions(multiply, "", add_expr, "B")
            prev_expr = add_expr
        pos_y += 300

    if prev_expr:
        mel.connect_material_property(prev_expr, "", unreal.MaterialProperty.MP_BASE_COLOR)

    # Roughness aus globalen Parametern ableiten
    globals_payload = blueprint.get("global_parameters", {}) if isinstance(blueprint, dict) else {}
    roughness_value = float(globals_payload.get("roughness", globals_payload.get("roughness_min", 0.5)))
    const = mel.create_material_expression(
        material,
        unreal.MaterialExpressionConstant,
        node_pos_x=200,
        node_pos_y=pos_y + 50,
    )
    const.set_editor_property("r", roughness_value)
    mel.connect_material_property(const, "", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.layout_material_expressions(material)
    mel.recompile_material(material)
    unreal.EditorAssetLibrary.save_loaded_asset(material)
    return material


def assign_material_to_landscapes(material: unreal.Material) -> None:
    if not material:
        return
    actors = unreal.EditorLevelLibrary.get_all_level_actors()
    landscapes = [
        actor
        for actor in actors
        if isinstance(actor, (unreal.LandscapeProxy, unreal.Landscape))
    ]
    if not landscapes:
        unreal.log_warning("Keine Landscape-Actors gefunden, Material wird nicht angewandt.")
        return
    for landscape in landscapes:
        try:
            landscape.set_editor_property("landscape_material", material)
            landscape.post_edit_change()
        except Exception as exc:  # pragma: no cover - Editor API spezifisch
            unreal.log_warning(f"Material konnte nicht auf {landscape.get_name()} angewandt werden: {exc}")


def create_layer_info(layer_name: str, asset_folder: str) -> unreal.LandscapeLayerInfoObject | None:
    layer_dir = f"{asset_folder.rstrip('/')}/LayerInfo"
    ensure_asset_folder(layer_dir)
    info_name = f"{layer_name}_LayerInfo"
    asset_path = f"{layer_dir}/{info_name}"
    info = unreal.EditorAssetLibrary.load_asset(asset_path)
    if info:
        return info
    factory = unreal.LandscapeLayerInfoObjectFactory()
    info = unreal.AssetToolsHelpers.get_asset_tools().create_asset(
        info_name,
        layer_dir,
        unreal.LandscapeLayerInfoObject,
        factory,
    )
    if info:
        info.set_editor_property("layer_name", layer_name)
        info.set_editor_property("hardness", 0.5)
        unreal.EditorAssetLibrary.save_loaded_asset(info)
    return info


def apply_layer_plan(layer_plan: dict | None, asset_folder: str) -> None:
    if not layer_plan:
        return
    masks = layer_plan.get("masks")
    if not isinstance(masks, list):
        return
    layer_infos = []
    for entry in masks:
        if not isinstance(entry, dict):
            continue
        biome = str(entry.get("biome", "Layer"))
        info = create_layer_info(biome, asset_folder)
        if info:
            layer_infos.append(info)
    if not layer_infos:
        return
    actors = unreal.EditorLevelLibrary.get_all_level_actors()
    landscapes = [
        actor
        for actor in actors
        if isinstance(actor, (unreal.LandscapeProxy, unreal.Landscape))
    ]
    if not landscapes:
        unreal.log_warning("Keine Landscape-Actors gefunden, Layer-Plan kann nicht angewandt werden.")
        return
    subsystem = unreal.get_editor_subsystem(unreal.LandscapeEditorSubsystem)
    for landscape in landscapes:
        for info in layer_infos:
            try:
                if hasattr(subsystem, "set_layer_info"):
                    subsystem.set_layer_info(landscape, info.get_editor_property("layer_name"), info)
                else:
                    landscape.set_layer_info(info.get_editor_property("layer_name"), info)  # type: ignore[attr-defined]
            except Exception as exc:  # pragma: no cover - Editor API spezifisch
                unreal.log_warning(f"Konnte LayerInfo auf {landscape.get_name()} nicht anwenden: {exc}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--graph-json", required=True)
    parser.add_argument("--asset-folder", default="/Game/AutoPCG")
    parser.add_argument("--asset-name", default=None)
    parser.add_argument("--spawn", action="store_true")
    parser.add_argument("--spawn-map", default=None)
    parser.add_argument("--material-json", default=None, help="Optionaler Material-Blueprint (JSON)")
    parser.add_argument("--layer-plan", default=None, help="Optionaler Layer-Plan (JSON)")
    parser.add_argument("--heightmap-json", default=None, help="Optionales Heightmap-Analyse-JSON")
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

    material_payload = load_optional_payload(args.material_json)
    material_asset = None
    if material_payload:
        material_asset = build_material_from_blueprint(material_payload, args.asset_folder, asset_name)
        if material_asset:
            assign_material_to_landscapes(material_asset)

    layer_payload = load_optional_payload(args.layer_plan)
    if layer_payload:
        apply_layer_plan(layer_payload, args.asset_folder)

    heightmap_payload = load_optional_payload(args.heightmap_json)

    # Metadaten für spätere Inspektionen beibehalten
    attach_metadata(graph_asset, "AutoPCG_MaterialBlueprint", material_payload)
    attach_metadata(graph_asset, "AutoPCG_LandscapeLayers", layer_payload)
    attach_metadata(graph_asset, "AutoPCG_HeightmapAnalysis", heightmap_payload)

    should_spawn = bool(args.spawn and map_ready)
    if args.spawn and not should_spawn:
        unreal.log_warning("PCG-Volume wird nicht gespawnt, da die Map nicht geladen werden konnte.")

    if should_spawn:
        spawn_pcg_volume(graph_asset, unreal.Vector(0.0, 0.0, 0.0))

    unreal.log(f"Auto-PCG Graph importiert nach {asset_path}")


if __name__ == "__main__":
    main()
