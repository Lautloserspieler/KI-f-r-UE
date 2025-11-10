# Best Practices für 10 km² Open-World-Generierung

Dieser Leitfaden fasst Empfehlungen für großflächige Auto-PCG-Pipelines
zusammen. Alle Hinweise lassen sich ohne Codeänderungen anwenden, sofern
nicht ausdrücklich auf Parameter im Code verwiesen wird.

## Erweiterte Biome

- Ergänze Heightmap-Analysen mit feineren Biomen, z. B. Regenwald, Tundra,
  Vulkan. In `HeightmapProcessor._derive_biome_layers` lassen sich dafür
  zusätzliche Layer ableiten (z. B. basierend auf Wasseranteil > 0.4 →
  Regenwald).
- Pflege Material/Textur-Zuordnungen in `src/auto_pcg/data/texture_library.json`
  nach. Für jedes neue Biom Albedo/Normal/Roughness definieren.
- Nutze LLM-Prompts (`PromptEngine.build_material_blueprint_prompt`) um die KI
  gezielt auf spezielle Layer-Übergänge hinzuweisen.

## Dynamische LOD-Systeme

- Für große Welten empfiehlt sich eine höhere Kontexttiefe:
  - `LLMManager.PCG_CONTEXT_LIMIT = 50`
  - `LLMManager.CLASSIFICATION_BATCH_SIZE = 5`
- Füge (falls nötig) eine adaptive LOD-Pipeline hinzu, z. B.:
  ```python
  performance_metrics = gather_performance_stats()
  adaptive_lod = ki_optimize_lod_based_on_distance(performance_metrics)
  ```
- Die resultierenden Parameter lassen sich in `LandscapeSettings.lod_distance`
  oder in UE per `PCGVolume`/Materialparametern übernehmen.

## Echtzeit-Anpassung

- Ergänze Telemetrie, um Spielerbewegungen zu verfolgen:
  ```python
  player_position = ki_track_player_movement()
  predicted_path = ki_predict_player_movement(player_position)
  preload_biomes_along_path(predicted_path)
  ```
- Nutze `AutoPCGService.run_full_pipeline` iterativ pro Sektor (siehe
  Skalierungs-Empfehlungen), um Biome vorzubereiten, bevor der Spieler sie
  erreicht.

## Workflow-Optimierung (Beispiel)

```bash
python -m auto_pcg ^
  --prompt "Realistische Waldgebirgslandschaft" ^
  --performance-profile high_end_pc ^
  --max-assets 500 ^
  --batch-size 5 ^
  --export-graph ./exports
```

- `--max-assets`: reduziert Scan-Zeit für riesige Content-Verzeichnisse.
- `--batch-size`: kleinere LLM-Batches sorgen für stabilere Antworten.
- `--export-graph`: zentralisiert alle JSONs (Graph, Material, Layer, Heightmap).

## Performance-kritische Einstellungen

- Passe Konstante in `LLMManager` an (Zeilenhinweise siehe Code):
  - `PCG_CONTEXT_LIMIT = 50` (mehr Kontext-Assets je Plan)
  - `CLASSIFICATION_BATCH_SIZE = 5` (stabilere JSON-Antworten)
- Material/Landscape:
  - `analysis.landscape_settings.section_size`: verkleinern für höhere Dichte,
    vergrößern für Performance.
  - `MaterialPlanner`-Parameter (z. B. `macro_variation_intensity`) als globale
    Material-Switches verwenden.

## World-Partition & Streaming

1. Vor der Generierung World Partition aktivieren.
2. Streaming-Pool in `DefaultEngine.ini` auf 4–8 GB erhöhen.
3. HLOD-System einschalten, damit weit entfernte Biome über Hierarchical LODs
   gerendert werden.
4. Große Welten in Sektoren aufteilen:
   ```python
   sector_size_km = 2.0
   for sector in iterate_world(sector_size_km):
       generate_sector(sector, sector_prompt)
   ```

## Fehlerbehebungs-Checkliste

| Problem | Lösung |
| --- | --- |
| LLM nicht erreichbar | `--heuristic-only` setzen, später Verbindung prüfen |
| PCG-Plugin deaktiviert | UE → Plugins → Procedural Content Generation Framework; `ensure_pcg_plugin_enabled()` meldet fehlende Klassen |
| Performance bricht ein | `--performance-profile mobile` für Testläufe, `--max-assets 100`, Material-Layer reduzieren |

## Logging

```python
import logging
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
```

- Aktiviert detaillierte Pipeline-Logs (Scan, LLM-Batches, Exporte).
- Für tieferes Debugging temporär auf `DEBUG` erhöhen.

## Skalierungs-Empfehlungen

- **Inkrementelle Generierung:** Welt in 2×2 km-Sektoren teilen.
- **Dynamisches Asset-Loading:** Biome nur für den aktuellen/benachbarten
  Sektor laden, z. B. `ki_preload_biome_materials(current_region)`.
- **Verteilte Verarbeitung:** Mehrere Auto-PCG-Services/Worker über einen
  Koordinator betreiben (REST/WebSockets oder Message Queue), die jeweils
  verschiedene Welt-Sektoren bearbeiten.
