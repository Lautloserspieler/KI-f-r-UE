# Auto-PCG KI-Assistent

Dieses Repository enthält eine in Python geschriebene Referenzimplementierung des "Auto-PCG AI Assistant" für Unreal Engine 5.4.

## Features
- Automatisches Scannen von Projekt-Assets (Dateisystem-basierte Heuristiken)
- Semantische Analyse und Tagging
- Prompt-Generierung für lokale LLMs (z. B. Ollama)
- PCG-Plan-Erstellung inklusive Fallback ohne LLM
- Graph-Builder, der Layer in interne Knotenstrukturen überführt

## Verzeichnisstruktur
```
src/
  auto_pcg/
    core/        # Scanner und Analyzer
    ai/          # LLM-Manager + Prompt-Engine
    data/        # Asset-Datenbank
    pcg/         # Graph-Builder
    services/    # High-Level-Service
    cli.py       # CLI-Einstiegspunkt
    __main__.py  # python -m auto_pcg
```

## Installation
```bash
pip install -e .
```

### Optionale virtuelle Umgebung
```powershell
py -3.11 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
```

## Nutzung
```bash
python -m auto_pcg --project <PFAD_ZUM_UNREAL_PROJEKT> --prompt "Erstelle einen dichten Wald"
```

> Ohne laufende LLM-Instanz greift das System automatisch auf deterministische Fallbacks zurück.

## Lokales LLM (GGUF)
- Das Repository unterstützt GGUF-Modelle (z. B. `Meta-Llama-3-8B-Instruct.Q4_K_M.gguf`) via `llama-cpp-python`.
- Lege das Modell ins Projektverzeichnis oder definiere `AUTO_PCG_GGUF_MODEL=<pfad_zum_model>`; der Service findet die Datei automatisch.
- Stelle sicher, dass deine Python-Version ≥3.10 ist und `pip install llama-cpp-python` erfolgreich war (CPU-Build).
- Zur Vermeidung von Kontextüberläufen werden Assets für Klassifikationen in Batches von max. 25 Objekten verarbeitet und PCG-Prompts auf 30 Assets begrenzt.

## Asset-Cache
- Bereits gescannte und klassifizierte Assets werden automatisch in `.auto_pcg_assets.json` im Projektordner zwischengespeichert.
- Der Cache wird beim Start geladen, sodass nur neue oder geänderte Assets erneut klassifiziert werden müssen.
- Eigener Speicherort möglich über `AUTO_PCG_CACHE=<pfad_zur_json>`.
