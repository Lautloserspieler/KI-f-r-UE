"""Implementierung des Asset Scanners für Unreal-Projekte."""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import logging
import os
from pathlib import Path
from typing import Dict, Iterable, List, Optional, TYPE_CHECKING

from auto_pcg.models.schemas import AssetData, AssetMetadata

if TYPE_CHECKING:  # pragma: no cover - nur für Typprüfungen relevant
    from auto_pcg.data.asset_database import AssetDatabase


LOGGER = logging.getLogger(__name__)


class AssetScanner:
    """Findet Assets im Projektverzeichnis und generiert Metadaten."""

    SUPPORTED_EXTENSIONS = {
        ".uasset": "Blueprint",
        ".umap": "Blueprint",
        ".fbx": "StaticMesh",
        ".obj": "StaticMesh",
        ".gltf": "StaticMesh",
        ".glb": "StaticMesh",
        ".png": "Texture",
        ".jpg": "Texture",
        ".tga": "Texture",
        ".hdr": "Texture",
        ".material": "Material",
        ".mtl": "Material",
    }

    def __init__(self, project_root: Path, database: Optional["AssetDatabase"] = None) -> None:
        self.project_root = Path(project_root)
        self.database = database

    def scan_project_assets(self, limit: Optional[int] = None) -> List[AssetData]:
        """Durchläuft das Projektverzeichnis und liefert alle gefundenen Assets.

        Args:
            limit: Optional maximale Anzahl an Assets, bevor der Scan abgebrochen wird.
        """
        if limit is not None and limit <= 0:
            return []

        asset_paths: List[Path] = []
        for asset_path in self._iter_asset_files():
            asset_paths.append(asset_path)
            if limit is not None and len(asset_paths) >= limit:
                break

        if not asset_paths:
            return []

        max_workers = min(32, max(1, (os.cpu_count() or 4) * 2))
        assets: List[AssetData] = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            for asset in executor.map(self._safe_build_asset, asset_paths):
                if not asset:
                    continue
                assets.append(asset)
                if self.database:
                    self.database.store_asset(asset)
        return assets

    def get_asset_metadata(self, asset_path: Path) -> AssetMetadata:
        """Leitet einfache Metadaten aus Dateigröße und Dateinamen ab."""
        stat = asset_path.stat()
        file_size = stat.st_size
        complexity_factor = max(file_size // 1024, 1)
        bounds = {
            "x": float(min(500, complexity_factor % 200 + 50)),
            "y": float(min(500, (complexity_factor * 2) % 200 + 50)),
            "z": float(min(500, (complexity_factor * 3) % 200 + 50)),
        }
        vertex_count = int(min(500_000, complexity_factor * 12))
        material_slots = max(1, min(8, len(asset_path.stem) % 5 + 1))
        return AssetMetadata(
            bounds=bounds,
            vertex_count=vertex_count,
            material_slots=material_slots,
            file_size=file_size,
        )

    def generate_asset_thumbnails(self, asset_paths: Optional[Iterable[Path]] = None) -> Dict[str, str]:
        """Stub für die Thumbnail-Erzeugung, erzeugt derzeit Dateiplatzhalter."""
        thumbnail_map: Dict[str, str] = {}
        paths = asset_paths or (asset.asset_path for asset in self.database.all_assets()) if self.database else []
        for path in paths:
            thumbnail_name = path.with_suffix(".thumbnail.png").name
            thumbnail_map[str(path)] = f"generated/{thumbnail_name}"
        return thumbnail_map

    def export_asset_database(self, destination: Optional[Path] = None) -> str:
        """Exportiert die aktuelle Asset-Datenbank als JSON."""
        if self.database:
            serialized = self.database.to_json()
        else:
            assets = [asset.to_dict() for asset in self.scan_project_assets()]
            serialized = json.dumps(assets, indent=2, ensure_ascii=False)
        if destination:
            destination.write_text(serialized, encoding="utf-8")
        return serialized

    def _iter_asset_files(self) -> Iterable[Path]:
        """Hilfsmethode, die über alle unterstützten Dateien iteriert."""
        if not self.project_root.exists():
            return
        for path in self.project_root.rglob("*"):
            if path.is_file() and path.suffix.lower() in self.SUPPORTED_EXTENSIONS:
                yield path.resolve()

    @staticmethod
    def _build_asset_id(asset_path: Path) -> str:
        """Erzeugt eine reproduzierbare Asset-ID anhand des Pfads."""
        digest = hashlib.md5(str(asset_path).encode("utf-8"), usedforsecurity=False).hexdigest()
        return f"asset_{digest[:12]}"

    def _safe_build_asset(self, asset_path: Path) -> Optional[AssetData]:
        """Erzeugt ein Asset-Objekt und protokolliert Dateifehler."""
        try:
            metadata = self.get_asset_metadata(asset_path)
        except OSError as exc:  # pragma: no cover - Dateisystemfehler selten
            LOGGER.warning("Konnte Metadaten für %s nicht lesen: %s", asset_path, exc)
            return None
        asset_type = self.SUPPORTED_EXTENSIONS.get(asset_path.suffix.lower(), "Unknown")
        return AssetData(
            asset_id=self._build_asset_id(asset_path),
            asset_path=asset_path,
            asset_type=asset_type,
            metadata=metadata,
        )
