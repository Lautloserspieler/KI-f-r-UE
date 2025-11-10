"""Einfache Geometriemodelle für räumliches Asset-Indexing."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class Vector3:
    """Repräsentiert eine Position in der Welt."""

    x: float
    y: float
    z: float = 0.0


@dataclass(slots=True)
class BoundingBox:
    """Axis-aligned Bounding Box."""

    min: Vector3
    max: Vector3

    def contains(self, point: Vector3) -> bool:
        return (
            self.min.x <= point.x <= self.max.x
            and self.min.y <= point.y <= self.max.y
            and self.min.z <= point.z <= self.max.z
        )

    def expanded(self, padding: float) -> BoundingBox:
        return BoundingBox(
            Vector3(self.min.x - padding, self.min.y - padding, self.min.z - padding),
            Vector3(self.max.x + padding, self.max.y + padding, self.max.z + padding),
        )

    @classmethod
    def from_center(cls, center: Vector3, radius: float) -> BoundingBox:
        return cls(
            Vector3(center.x - radius, center.y - radius, center.z - radius),
            Vector3(center.x + radius, center.y + radius, center.z + radius),
        )
