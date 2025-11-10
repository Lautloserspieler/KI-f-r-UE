# Auto-PCG KI-Assistent

Der Auto-PCG KI-Assistent stellt eine vollständige Python-Referenzimplementierung für
prozedurale Workflows in Unreal Engine 5.4 bereit. Neben dem bekannten Asset-Scan und
PCG-Graph-Building deckt die aktuelle Version auch Heightmap-Analyse, Material-Blueprints
und automatische Landscape-Layer-Pläne ab – alles orchestriert über einen einzigen CLI-Call.

## Highlights

- **Asset-Pipeline:** Dateisystembasierter Scan, heuristische/LLM-gestützte Klassifikation,
  semantische Profile & Cache.
- **Spatial Asset Streaming (Phase 1):** Optionale Quadtree-Datenbank (`--use-spatial-db`)
  für große Welten inkl. sektorweisem Preloading.
- **Hierarchische PCG-Graphen (Phase 2, opt-in):** `--hierarchical-pcg` erzeugt Makro/Meso/Mikro-Knoten für riesige Weltabschnitte.
- **Heightmap-Pipeline:** KI-Heuristiken lesen PNG/RAW-Heightmaps aus, erkennen Biome,
  schlagen Section-Size/Scale vor und speichern Empfehlungen für UE.
- **Material & Layer Automation:** Texture-Library Matching, Master-Material-Blueprints,
  Layer-Mask-Planung inkl. optionalem LLM-Finetuning.
- **PCG-Graph Builder:** Kombiniert SURFACE/SCATTER-Layer aus PCG-Plänen, exportiert JSON
  und triggert (optional) UE-Imports via Python-Skript.
- **UE-Integration:** `ue_pcg_import.py` legt PCG-Graphen an, speichert Metadaten für Material,
  Layer-Plan und Heightmap-Analyse, sodass nachgelagerte Tools alle Infos im Asset finden.

## Projektstruktur

```
src/
  auto_pcg/
    ai/          # PromptEngine, LLMManager, lokale GGUF-Anbindung
    core/        # AssetScanner + Analyzer
    data/        # JSON-Datenbanken (Assets, Texture-Library)
    models/      # Dataclasses für Assets, PCG, Terrain
    pcg/         # GraphBuilder, Exporter, UE-Integration
    services/    # AutoPCGService (High-Level-API)
    terrain/     # HeightmapProcessor, MaterialPlanner, LayerPainter
    cli.py       # Kommandozeileninterface
```

## Installation

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -e .
```

## Nutzung

```bash
python -m auto_pcg ^
  --project C:\UE\MyWorld ^
  --heightmap C:\UE\Maps\world_heightmap.png ^
  --prompt "Erzeuge eine alpine Waldlandschaft" ^
  --target-style realistic_fantasy ^
  --season winter ^
  --performance-profile high_end_pc ^
  --use-spatial-db ^
  --hierarchical-pcg ^
  --world-size 10000 ^
  --sector-size 1000
```

### Desktop GUI

```bash
python -m auto_pcg.gui
```

Das Tkinter-Control-Panel bündelt die gängigsten Optionen (Projektpfad, Prompt,
Heightmap, Spatial-/Hierarchie-Flags, UE-Import) und führt die Pipeline ohne
CLI-Kenntnisse aus.

Der CLI-Lauf liefert ein JSON mit:

- `graph`: PCG-Graph (SURFACE/SCATTER-Knoten),
- `assets`: alle gescannten Assets inkl. Klassifikationen,
- `heightmap_analysis`: Biome, Section-Size, Scale,
- `material_blueprint`: Layer-Blend-Definitionen + globale Parameter,
- `layer_plan`: Mal-Reihenfolge und adaptive Regeln.

## LLM-Anbindung

- **Lokal (GGUF):** Wird automatisch gesucht (`AUTO_PCG_GGUF_MODEL=<pfad>`). Fällt zurück
  auf Heuristiken, falls das Modell nicht geladen werden kann.
- **Ollama/HTTP:** `--ollama-url`, `--ollama-model`, `--ollama-timeout`.
- Für alle Prompts gilt: JSON-only, Reparatur- und Fallback-Logik sind im `LLMManager`
  integriert.
- **Installation:** Die Kernfunktionen benötigen nur `requests`. Wer das lokale
  GGUF-Feature nutzen möchte, installiert zusätzlich `pip install -e .[llm]`
  (oder `pip install auto-pcg[llm]`) und stellt sicher, dass eine C/C++
  Toolchain für den Build von `llama-cpp-python` vorhanden ist.

## UE5-Automatisierung

1. `AutoPCGService` exportiert Graph/Material/Layer/Heightmap-JSON (wenn `--export-graph` gesetzt).
2. `UnrealEditor-Cmd.exe -run=pythonscript -script=.../ue_pcg_import.py --graph-json ...`
   erzeugt PCG-Graphen **und** baut aus dem Blueprint ein Landscape-Material inkl. Layer-Samples.
   Layer-Pläne werden als `LandscapeLayerInfo`-Assets angelegt und – sofern Landscapes im Level
   existieren – automatisch zugewiesen.
3. Alle Quelldaten werden zusätzlich als Metadaten am PCG-Graph abgelegt
   (`AutoPCG_MaterialBlueprint`, `AutoPCG_LandscapeLayers`, `AutoPCG_HeightmapAnalysis`).

Damit lassen sich Blueprint- oder Editor-Utility-Skripte direkt auf die KI-Ergebnisse stützen.

## Open-World Best Practices

Für erweiterte Biome (Regenwald, Tundra, Vulkan), dynamische LOD-Konzepte,
Workflows für 10 km²-Welten und Troubleshooting siehe
`docs/open_world_best_practices.md`.

## Asset-Cache

- Standardpfad: `<projekt>/.auto_pcg_assets.json`
- Überschreibbar via `AUTO_PCG_CACHE`.
- Cache verhindert Doppelklassifikationen; neue/angepasste Assets werden automatisch ergänzt.

## Spatial Asset Database (Phase 1)

- Aktivierung via `--use-spatial-db`. `--world-size` und `--sector-size`
  bestimmen Rasterauflösung & gestreamte Flächen.
- `AutoPCGService.get_assets_in_region(bounds, lod_level)` liefert Assets
  innerhalb einer Bounding-Box – nützlich für World-Partition- oder Streaming-Tooling.

## Tests & Weiterentwicklung

- Unit-Tests können via `pytest` (optional dependency) ergänzt werden.
- Für produktive Nutzung empfiehlt es sich, Texture-Library und UE-Skripte projektspezifisch
  anzupassen (z. B. echte Materialgraph-Generierung, Landscape-Import-Skripte).
