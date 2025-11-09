"""Einfacher Wrapper um llama.cpp für lokale GGUF-Modelle."""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Dict, Optional

try:
    from llama_cpp import Llama  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    Llama = None

LOGGER = logging.getLogger(__name__)


class LocalLLMError(RuntimeError):
    """Signalisiert Fehler in der lokalen LLM-Ausführung."""


class LocalGGUFClient:
    """Hilfsklasse, die direkt ein GGUF-Modell über llama.cpp lädt."""

    def __init__(
        self,
        model_path: Path,
        context_tokens: int = 4096,
        max_tokens: int = 768,
        temperature: float = 0.15,
        chat_format: str = "llama-3",
        n_gpu_layers: Optional[int] = None,
    ) -> None:
        if Llama is None:
            raise LocalLLMError(
                "llama-cpp-python ist nicht installiert. Bitte `pip install llama-cpp-python` ausführen."
            )
        if not model_path.exists():
            raise LocalLLMError(f"GGUF-Modell nicht gefunden: {model_path}")
        self.model_path = model_path
        self.temperature = temperature
        self.max_tokens = max_tokens
        gpu_layers = self._resolve_gpu_layers(n_gpu_layers)
        self._llama = self._init_llama(
            model_path=model_path,
            context_tokens=context_tokens,
            chat_format=chat_format,
            gpu_layers=gpu_layers,
        )

    def generate_json(self, prompt: str, system_prompt: Optional[str] = None) -> Dict[str, object]:
        """Führt eine Chat Completion aus und gibt JSON zurück."""
        system_prompt = system_prompt or (
            "Du bist ein strikter JSON-Generator für den Auto-PCG KI-Assistenten. "
            "Antworte ausschließlich mit gültigem JSON."
        )
        response = self._llama.create_chat_completion(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )
        content = response["choices"][0]["message"]["content"].strip()
        content = _extract_json_block(content)
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            repaired = _auto_close_json(content)
            try:
                return json.loads(repaired)
            except json.JSONDecodeError as exc:
                LOGGER.error(
                    "LLM-Antwort konnte nicht als JSON geparst werden: %s\nAntwort: %s",
                    exc,
                    content,
                )
                raise LocalLLMError("Ungültige JSON-Antwort durch das GGUF-Modell") from exc


    def _init_llama(
        self,
        *,
        model_path: Path,
        context_tokens: int,
        chat_format: str,
        gpu_layers: int,
    ) -> "Llama":
        """Initialisiert das Llama-Objekt und fällt bei Fehlern auf CPU zurück."""
        use_gpu = gpu_layers != 0
        if use_gpu:
            LOGGER.info(
                "Initialisiere GGUF-Client mit %s GPU-Layern.",
                "allen" if gpu_layers < 0 else gpu_layers,
            )
        try:
            return Llama(
                model_path=str(model_path),
                n_ctx=context_tokens,
                chat_format=chat_format,
                n_threads=os.cpu_count() or 4,
                n_gpu_layers=gpu_layers,
            )
        except (OSError, RuntimeError) as exc:
            if use_gpu:
                LOGGER.warning(
                    "Konnte GGUF-Modell nicht mit GPU-Layern laden (%s). Fallback auf CPU.",
                    exc,
                )
                try:
                    return Llama(
                        model_path=str(model_path),
                        n_ctx=context_tokens,
                        chat_format=chat_format,
                        n_threads=os.cpu_count() or 4,
                        n_gpu_layers=0,
                    )
                except (OSError, RuntimeError) as cpu_exc:
                    raise LocalLLMError(f"LLM-Initialisierung fehlgeschlagen (CPU-Fallback): {cpu_exc}") from cpu_exc
            raise LocalLLMError(f"LLM-Initialisierung fehlgeschlagen: {exc}") from exc

    @staticmethod
    def _resolve_gpu_layers(override: Optional[int]) -> int:
        """Liest die Anzahl der GPU-Layer aus Parameter oder Umgebungsvariable."""
        if override is not None:
            return override
        env_value = os.getenv("AUTO_PCG_GPU_LAYERS")
        if env_value is None or not env_value.strip():
            return -1
        try:
            return int(env_value)
        except ValueError:
            LOGGER.warning(
                "AUTO_PCG_GPU_LAYERS=%s konnte nicht interpretiert werden. Verwende -1.",
                env_value,
            )
            return -1

def _extract_json_block(text: str) -> str:
    """Entfernt Code-Fences und versucht, nur den JSON-Teil zu extrahieren."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?", "", stripped, flags=re.IGNORECASE).strip()
        stripped = re.sub(r"```$", "", stripped).strip()
    if stripped.startswith("{") or stripped.startswith("["):
        return stripped
    match = re.search(r"(\{.*\})", stripped, re.DOTALL)
    if match:
        return match.group(1)
    match = re.search(r"(\[.*\])", stripped, re.DOTALL)
    if match:
        return match.group(1)
    return stripped



def _append_missing_closers(text: str) -> str:
    """Hängt fehlende schließende Klammern basierend auf einer Stack-Analyse an."""
    stack: list[str] = []
    in_string = False
    escape = False
    for char in text:
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char in "{[":
            stack.append(char)
        elif char in "}]":
            if stack and ((char == "}" and stack[-1] == "{") or (char == "]" and stack[-1] == "[")):
                stack.pop()
            else:
                break
    closing = "".join("}" if ch == "{" else "]" for ch in reversed(stack))
    return text + closing


def _auto_close_json(text: str) -> str:
    """Versucht, fehlende Klammern am Ende zu ergänzen."""
    candidate = _append_missing_closers(text)
    try:
        json.loads(candidate)
        return candidate
    except json.JSONDecodeError:
        return _repair_json_lines(candidate)


def _repair_json_lines(text: str) -> str:
    """Versucht, abgeschnittene JSON-Dokumente aggressiver zu reparieren."""
    parsed = _try_parse_with_trimming(text)
    if parsed is not None:
        return json.dumps(_prune_classifications(parsed), ensure_ascii=False)

    if '"asset_path"' in text:
        entries = _extract_objects_with_key(text, "asset_path")
        if entries:
            payload = {"classifications": entries}
            return json.dumps(_prune_classifications(payload), ensure_ascii=False)

    return text


def _try_parse_with_trimming(text: str) -> Optional[object]:
    """Schneidet sukzessive ungültige Enden ab und versucht nach jedem Schritt zu parsen."""
    candidate = text
    while candidate:
        try:
            return json.loads(candidate)
        except json.JSONDecodeError as exc:
            trim_point = _find_trim_point(candidate, exc.pos)
            if trim_point is None:
                break
            trimmed = candidate[:trim_point].rstrip()
            if not trimmed:
                break
            sanitized = _strip_dangling_openers(_strip_trailing_comma(trimmed)).rstrip()
            if not sanitized:
                break
            candidate = _append_missing_closers(sanitized)
    return None


def _find_trim_point(text: str, error_pos: int) -> Optional[int]:
    """Bestimmt die Position, bis zu der Text abgeschnitten werden soll."""
    if error_pos <= 0:
        return None
    newline_index = text.rfind("\n", 0, error_pos)
    if newline_index != -1:
        return newline_index
    return error_pos - 1 if error_pos > 0 else None


def _strip_trailing_comma(text: str) -> str:
    """Entfernt ein finales Komma inklusive Leerraum."""
    return re.sub(r",\s*$", "", text)


def _strip_dangling_openers(text: str) -> str:
    """Entfernt offene geschweifte oder eckige Klammern am Ende."""
    return re.sub(r"[\t ]*[\{\[]\s*$", "", text)


def _extract_objects_with_key(text: str, key: str) -> list[Dict[str, object]]:
    """Extrahiert vollständige JSON-Objekte, die den angegebenen Schlüssel enthalten."""
    results: list[Dict[str, object]] = []
    brace_stack: list[int] = []
    in_string = False
    escape = False
    for idx, char in enumerate(text):
        if in_string:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
            continue
        if char == "{":
            brace_stack.append(idx)
        elif char == "}" and brace_stack:
            start = brace_stack.pop()
            chunk = text[start : idx + 1]
            if f'"{key}"' not in chunk:
                continue
            try:
                obj = json.loads(chunk)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict) and key in obj:
                results.append(obj)
    return results


def _prune_classifications(payload: object) -> object:
    """Entfernt Klassifikationsobjekte ohne asset_path, falls vorhanden."""
    if isinstance(payload, dict):
        entries = payload.get("classifications")
        if isinstance(entries, list):
            payload = payload.copy()
            payload["classifications"] = [
                entry for entry in entries if isinstance(entry, dict) and entry.get("asset_path")
            ]
    return payload
