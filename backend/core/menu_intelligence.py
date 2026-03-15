import importlib
import re
from dataclasses import dataclass
from typing import Any

import pandas as pd


@dataclass
class MenuSections:
    starter: str
    main: str
    dessert: str
    starter_options: list[str]
    main_options: list[str]
    dessert_options: list[str]
    detected_lines: list[str]
    raw_text: str


class DocumentIntelligenceOCR:
    """Cliente OCR para Azure Document Intelligence."""

    def __init__(self, endpoint: str, key: str, model_id: str = "prebuilt-layout") -> None:
        self.endpoint = endpoint
        self.key = key
        self.model_id = model_id

    @staticmethod
    def _polygon_points(polygon: Any) -> list[tuple[float, float]]:
        if not polygon:
            return []

        if isinstance(polygon, list) and polygon and isinstance(polygon[0], (int, float)):
            return [
                (float(polygon[index]), float(polygon[index + 1]))
                for index in range(0, len(polygon) - 1, 2)
            ]

        points: list[tuple[float, float]] = []
        for point in polygon:
            x = getattr(point, "x", None)
            y = getattr(point, "y", None)
            if x is None or y is None:
                if isinstance(point, (list, tuple)) and len(point) >= 2:
                    x, y = point[0], point[1]
                else:
                    continue
            points.append((float(x), float(y)))

        return points

    @classmethod
    def _line_geometry(cls, line: Any) -> tuple[float | None, float | None, float | None]:
        polygons: list[Any] = []

        direct_polygon = getattr(line, "polygon", None)
        if direct_polygon:
            polygons.append(direct_polygon)

        for region in getattr(line, "bounding_regions", []) or []:
            region_polygon = getattr(region, "polygon", None)
            if region_polygon:
                polygons.append(region_polygon)

        points: list[tuple[float, float]] = []
        for polygon in polygons:
            points.extend(cls._polygon_points(polygon))

        if not points:
            return None, None, None

        xs = [point[0] for point in points]
        ys = [point[1] for point in points]
        return ((min(ys) + max(ys)) / 2.0, min(xs), max(ys) - min(ys))

    @classmethod
    def _page_lines_with_layout(cls, page: Any) -> list[str]:
        rendered_lines: list[tuple[float | None, float | None, float | None, str]] = []

        for line in getattr(page, "lines", []) or []:
            content = getattr(line, "content", None)
            if not content:
                continue
            center_y, min_x, height = cls._line_geometry(line)
            rendered_lines.append((center_y, min_x, height, content))

        if not rendered_lines:
            return []

        page_width = getattr(page, "width", None)
        if page_width and float(page_width) > 0:
            margin_cutoff = float(page_width) * 0.08
            margin_filtered = [
                item for item in rendered_lines
                if item[1] is None or item[1] >= margin_cutoff
            ]
            if len(margin_filtered) >= max(1, int(len(rendered_lines) * 0.6)):
                rendered_lines = margin_filtered

        if any(center_y is not None for center_y, _, _, _ in rendered_lines):
            rendered_lines.sort(
                key=lambda item: (
                    item[0] if item[0] is not None else float("inf"),
                    item[1] if item[1] is not None else float("inf"),
                )
            )

        heights = sorted(height for _, _, height, _ in rendered_lines if height and height > 0)
        median_height = heights[len(heights) // 2] if heights else None

        output: list[str] = []
        previous_center_y: float | None = None
        previous_height: float | None = None

        for center_y, _, height, content in rendered_lines:
            if (
                output
                and center_y is not None
                and previous_center_y is not None
                and median_height is not None
            ):
                reference_height = max(median_height, previous_height or 0.0, height or 0.0)
                if center_y - previous_center_y > reference_height * 1.9:
                    output.append("")

            output.append(content.strip())
            previous_center_y = center_y
            previous_height = height

        return output

    def extract_text(self, file_bytes: bytes, content_type: str | None = None) -> str:
        try:
            document_module = importlib.import_module("azure.ai.documentintelligence")
            core_module = importlib.import_module("azure.core.credentials")
            client_cls = getattr(document_module, "DocumentIntelligenceClient")
            key_cls = getattr(core_module, "AzureKeyCredential")
        except ImportError as exc:
            raise RuntimeError(
                "Falta dependencia 'azure-ai-documentintelligence'. Instálala para usar OCR."
            ) from exc

        client = client_cls(endpoint=self.endpoint, credential=key_cls(self.key))

        try:
            poller = client.begin_analyze_document(
                model_id=self.model_id,
                analyze_request=file_bytes,
                content_type=content_type,
            )
        except TypeError:
            poller = client.begin_analyze_document(self.model_id, file_bytes)

        result = poller.result()

        lines: list[str] = []
        for page in getattr(result, "pages", []) or []:
            page_lines = self._page_lines_with_layout(page)
            if page_lines:
                if lines:
                    lines.append("")
                lines.extend(page_lines)

        if lines:
            return "\n".join(lines).strip()

        if hasattr(result, "content") and result.content:
            return result.content

        return ""


class MenuSectionExtractor:
    """Extractor de platos con estrategia header-first."""

    HEADER_CHOICE_SUFFIX = r"(?:\s+(?:a|1a|1ª|1\s*a|la|l\s*a)\s+elegir(?:\s+(?:uno|una|1))?)?"
    HEADER_CHOICE_ONLY_PATTERN = re.compile(
        r"^\s*(?:(?:a|1a|1ª|1\s*a|la|l\s*a)\s+elegir(?:\s+(?:uno|una|1))?|elegir\s+(?:uno|una|1))\s*$",
        re.IGNORECASE,
    )

    HEADER_PATTERNS = {
        "starter": re.compile(
            r"^\s*(?:entrantes?|primer(?:o|os|a|as)|primer(?:os?)?\s+platos?|para\s+empezar|para\s+picar|picar|inicios?)"
            + HEADER_CHOICE_SUFFIX +
            r"\s*[:\-–—]?\s*$",
            re.IGNORECASE,
        ),
        "main": re.compile(
            r"^\s*(?:principal(?:es)?|segund(?:o|os|a|as)|segund(?:os?)?\s+platos?|plato\s+principal|carnes\s+y\s+pescados|carnes|pescados)"
            + HEADER_CHOICE_SUFFIX +
            r"\s*[:\-–—]?\s*$",
            re.IGNORECASE,
        ),
        "dessert": re.compile(
            r"^\s*(?:postres?\s+o\s+caf[eé]|postres?|dulces?|para\s+terminar|postre\s+del\s+d[ií]a)"
            + HEADER_CHOICE_SUFFIX +
            r"\s*[:\-–—]?\s*$",
            re.IGNORECASE,
        ),
    }
    HEADER_PREFIX_PATTERNS = {
        "starter": re.compile(
            r"^\s*((?:entrantes?|primer(?:o|os|a|as)|primer(?:os?)?\s+platos?|para\s+empezar|para\s+picar|picar|inicios?)"
            + HEADER_CHOICE_SUFFIX +
            r")\s*[:\-–—]?\s+(.+)$",
            re.IGNORECASE,
        ),
        "main": re.compile(
            r"^\s*((?:principal(?:es)?|segund(?:o|os|a|as)|segund(?:os?)?\s+platos?|plato\s+principal|carnes\s+y\s+pescados|carnes|pescados)"
            + HEADER_CHOICE_SUFFIX +
            r")\s*[:\-–—]?\s+(.+)$",
            re.IGNORECASE,
        ),
        "dessert": re.compile(
            r"^\s*((?:postres?\s+o\s+caf[eé]|postres?|dulces?|para\s+terminar|postre\s+del\s+d[ií]a)"
            + HEADER_CHOICE_SUFFIX +
            r")\s*[:\-–—]?\s+(.+)$",
            re.IGNORECASE,
        ),
    }

    NOISE_PATTERNS = re.compile(
        r"^\d{1,3}(?:[,\.]\d{1,2})?\s*€[*ºo]?\s*$"
        r"|^\s*(?:lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo)(?:\s+\d{1,2})?\s*$"
        r"|^\s*(?:(?:lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo)\s+)?\d{1,2}\s+de\s+\w+\s+de\s+\d{4}"
        r"|^\s*men[uú]\s+del\s+d[ií]a\s*$"
        r"|^\s*(?:el\s+precio\s+)?incluye\b"
        r"|^\s*(?:el\s+)?men[uú]\s+incluye\b"
        r"|^\s*no\s+incluye\b"
        r"|^\s*se\s+incluye\b"
        r"|^\s*(?:precio|pvp)\s+incluye\b"
        r"|^\s*[ou]\s+(?:caf[eé]|postre|bebida|refresco|copa|vino|agua|t[eé]|infusi[oó]n)"
        r"|^\s*una?\s+bebida(?:\s+y\s+caf[eé])?\s*$"
        r"|^\s*(?:con\s+)?pan[\s,]+(?:y\s+)?bebida"
        r"|^\s*bebida\s+(?:in|no\s+in)clu"
        r"|^\s*[\(\[]?(?:tercio|doble|cañ[ae]|jarra|cerveza|vino|agua|refresco|caf[eé]|infusi[oó]n)\b"
        r"|^\s*[\(\[]?\+\s*\d+(?:[,\.]\d{1,2})?\s*€\s*[\)\]]?\s*$"
        r"|^\s*(?:iva|i\.v\.a|impuesto)\b"
        r"|^\s*medio\s+men[uú]\b"
        r"|^\s*con\s+un\s+(?:primero|segundo)\b",
        re.IGNORECASE,
    )

    SEPARATOR_PATTERN = re.compile(r"^[-_=]{2,}$")
    EXTRA_PRICE_PATTERN = re.compile(r"\(\s*\+\s*\d+(?:[,\.]\d{1,2})?\s*€\s*\)", re.IGNORECASE)
    BRANDING_LINE_PATTERN = re.compile(r"^[A-ZÁÉÍÓÚÜÑ\s]{5,}$")
    DESSERT_HINTS = ["flan", "tarta", "helado", "natillas", "arroz con leche", "tiramisu", "tiramisú"]
    MAIN_HINTS = [
        "chuleta", "filete", "solomillo", "entrecot", "costilla", "pollo", "ternera", "cerdo",
        "cordero", "merluza", "bacalao", "salmón", "salmon", "lomos", "a la plancha", "a la riojana",
        "patatas", "guarnicion", "guarnición",
    ]
    STARTER_PREFIX_HINTS = (
        "ensalada", "ensaladilla", "salmorejo", "consome", "consomé", "sopa", "crema",
        "parrillada", "fideua", "fideuá", "raviolis", "gazpacho", "verduras",
    )

    @staticmethod
    def _normalize(line: str) -> str:
        return re.sub(r"\s+", " ", line).strip().lower()

    @staticmethod
    def _strip_bullets(line: str) -> str:
        line = re.sub(r"^\s*[•·–—\*]\s*", "", line)
        line = re.sub(r"^\s*-\s+", "", line)
        return line.strip()

    @classmethod
    def _clean_dish_text(cls, line: str) -> str:
        clean = cls.EXTRA_PRICE_PATTERN.sub("", line)
        clean = re.sub(r"\s{2,}", " ", clean)
        clean = re.sub(r"\s+([,.;:])", r"\1", clean)
        return clean.strip(" -\t")

    @classmethod
    def _is_separator(cls, line: str) -> bool:
        return bool(cls.SEPARATOR_PATTERN.match(line.strip()))

    @classmethod
    def _is_noise(cls, line: str) -> bool:
        return bool(cls.NOISE_PATTERNS.search(line))

    @classmethod
    def _is_probable_branding_line(cls, line: str) -> bool:
        compact = line.strip()
        if not compact:
            return False

        if not cls.BRANDING_LINE_PATTERN.match(compact):
            return False

        words = [word for word in compact.split() if word]
        if not words:
            return False

        # Marcas/logo incrustadas suelen aparecer como una sola palabra en mayúsculas.
        return len(words) == 1 and len(words[0]) >= 5

    @classmethod
    def _is_valid_dish(cls, line: str) -> bool:
        clean = cls._clean_dish_text(line)
        return (
            len(clean) >= 4
            and not clean.isdigit()
            and not cls._is_noise(clean)
            and not cls._is_probable_branding_line(clean)
            and not cls._is_separator(clean)
        )

    @classmethod
    def _is_merge_candidate(cls, line: str) -> bool:
        clean = cls._clean_dish_text(line)
        return (
            len(clean) >= 2
            and not clean.isdigit()
            and not cls._is_noise(clean)
            and not cls._is_separator(clean)
        )

    @classmethod
    def _is_collectable_line(cls, line: str) -> bool:
        clean = cls._clean_dish_text(line)
        return (
            len(clean) >= 2
            and not clean.isdigit()
            and not cls._is_noise(clean)
            and not cls._is_separator(clean)
        )

    @classmethod
    def _detect_header(cls, line: str) -> str | None:
        normalized = cls._normalize(line)
        for section, pattern in cls.HEADER_PATTERNS.items():
            if pattern.match(normalized):
                return section
        return None

    @classmethod
    def _is_header_helper_line(cls, line: str) -> bool:
        return bool(cls.HEADER_CHOICE_ONLY_PATTERN.match(cls._normalize(line)))

    @classmethod
    def _extract_inline_header_remainder(cls, line: str) -> tuple[str | None, str | None]:
        for section, pattern in cls.HEADER_PREFIX_PATTERNS.items():
            match = pattern.match(line.strip())
            if match:
                remainder = match.group(2).strip()
                return section, remainder or None
        return None, None

    @classmethod
    def _split_section_items(cls, section: str, line: str) -> list[str]:
        cleaned_line = cls._clean_dish_text(line)
        if section != "dessert":
            return [cleaned_line] if cleaned_line else []

        if cleaned_line.count(",") < 1:
            return [cleaned_line] if cleaned_line else []

        items = [chunk.strip(" .;") for chunk in cleaned_line.split(",") if chunk.strip(" .;")]
        return items or ([cleaned_line] if cleaned_line else [])

    @classmethod
    def _normalize_section_items(cls, items: list[str]) -> list[str]:
        normalized_items: list[str] = []

        for item in items:
            cleaned = cls._clean_dish_text(item)
            if not cleaned:
                continue
            if cls._is_header_helper_line(cleaned):
                continue
            if not cls._is_valid_dish(cleaned):
                continue

            if normalized_items:
                previous = normalized_items[-1]
                previous_norm = cls._normalize(previous)
                current_norm = cls._normalize(cleaned)
                previous_tokens = previous_norm.split()
                previous_last_token = previous_tokens[-1] if previous_tokens else ""
                starts_with_connector = current_norm.startswith(("y ", "en ", "con ", "al ", "a la ", "a los "))
                current_tokens = current_norm.split()
                is_short_fragment = len(current_tokens) <= 2 and len(current_norm) <= 20
                starts_with_parenthesis = current_norm.startswith(("(", "["))
                starts_with_lowercase = bool(cleaned) and cleaned[0].islower()
                previous_ends_with_comma = previous.rstrip().endswith(",")
                previous_has_parenthesis = "(" in previous or ")" in previous
                previous_ends_with_connector = previous_last_token in {"y", "e", "de", "del", "con", "en", "al", "la", "las", "los"}

                if previous_ends_with_connector and (starts_with_connector or starts_with_parenthesis or starts_with_lowercase or is_short_fragment):
                    normalized_items[-1] = f"{previous.rstrip()} {cleaned.lstrip()}"
                    continue

                if starts_with_parenthesis or starts_with_connector:
                    normalized_items[-1] = f"{previous.rstrip()} {cleaned.lstrip()}"
                    continue

                if starts_with_lowercase and (is_short_fragment or previous_ends_with_comma or previous_has_parenthesis):
                    normalized_items[-1] = f"{previous.rstrip()} {cleaned.lstrip()}"
                    continue

            normalized_items.append(cleaned)

        return normalized_items

    @staticmethod
    def _split_inline_candidates(line: str) -> list[str]:
        separators_pattern = r"\s*[•|;]+\s*|\s{2,}|\s*/\s*"
        if re.search(separators_pattern, line):
            return [chunk.strip(" -\t") for chunk in re.split(separators_pattern, line) if chunk.strip()]
        if " . " in line:
            chunks = [chunk.strip(" -\t") for chunk in line.split(" . ") if chunk.strip()]
            if len(chunks) > 1:
                return chunks
        return [line.strip()]

    @classmethod
    def _prepare_lines(cls, raw_text: str) -> list[str]:
        prepared: list[str] = []
        for original in raw_text.splitlines():
            stripped = original.strip()
            if not stripped:
                prepared.append("")
                continue
            if cls._is_separator(stripped):
                prepared.append(stripped)
                continue
            cleaned = cls._strip_bullets(stripped)
            if not cleaned:
                continue
            prepared.extend(cls._split_inline_candidates(cleaned))
        return prepared

    @staticmethod
    def _is_likely_continuation(normalized_line: str) -> bool:
        if len(normalized_line) <= 12:
            return True
        return normalized_line.startswith(("y ", "en ", "con ", "al ", "a la ", "a los "))

    @classmethod
    def _looks_like_main(cls, normalized_line: str) -> bool:
        if normalized_line.startswith(cls.STARTER_PREFIX_HINTS):
            return False
        return any(token in normalized_line for token in cls.MAIN_HINTS)

    @classmethod
    def _merge_wrapped_dishes(cls, raw_lines: list[str]) -> list[str]:
        merged: list[str] = []
        for line in raw_lines:
            if not line or cls._is_separator(line):
                merged.append(line)
                continue
            if not merged:
                merged.append(line)
                continue

            previous = merged[-1]
            if not previous or cls._is_separator(previous):
                merged.append(line)
                continue

            if cls._is_merge_candidate(previous) and cls._is_merge_candidate(line):
                prev_norm = cls._normalize(previous)
                curr_norm = cls._normalize(line)
                prev_tokens = prev_norm.split()
                previous_last_token = prev_tokens[-1] if prev_tokens else ""
                starts_with_connector = curr_norm.startswith(("y ", "en ", "con ", "al ", "a la ", "a los "))
                current_word_count = len(curr_norm.split())
                current_short_fragment = current_word_count <= 2 and len(curr_norm) <= 15

                if previous_last_token in {"de", "del", "con", "en", "al", "y", "e"} and (
                    len(curr_norm) <= 20 or starts_with_connector or current_short_fragment
                ):
                    merged[-1] = f"{previous.rstrip()} {line.lstrip()}"
                    continue

                if previous_last_token in {"la", "las", "los"} and current_short_fragment:
                    merged[-1] = f"{previous.rstrip()} {line.lstrip()}"
                    continue

                if previous_last_token in {"salsa", "salsa."} and current_short_fragment:
                    merged[-1] = f"{previous.rstrip()} {line.lstrip()}"
                    continue

                if starts_with_connector:
                    merged[-1] = f"{previous.rstrip()} {line.lstrip()}"
                    continue

            merged.append(line)

        return merged

    @classmethod
    def _infer_split_index_by_main_hints(cls, valid_lines: list[str]) -> int | None:
        for index, line in enumerate(valid_lines):
            normalized = cls._normalize(line)
            if not cls._looks_like_main(normalized):
                continue
            starters_count = index
            mains_count = len(valid_lines) - index
            if starters_count >= 3 and mains_count >= 2:
                return index
        return None

    @staticmethod
    def _pick_representative(items: list[str]) -> str:
        return items[0] if items else "Sin detectar"

    @staticmethod
    def _classified_lines(buckets: dict[str, list[str]]) -> list[str]:
        return [*buckets["starter"], *buckets["main"], *buckets["dessert"]]

    @classmethod
    def extract(cls, raw_text: str) -> MenuSections:
        raw_lines = cls._merge_wrapped_dishes(cls._prepare_lines(raw_text))
        lines = [line for line in raw_lines if line and not cls._is_separator(line)]
        detected_lines = [line for line in lines if cls._is_valid_dish(line)]
        buckets: dict[str, list[str]] = {"starter": [], "main": [], "dessert": []}

        # 1) HEADER-FIRST: si hay cabeceras, mandan.
        has_headers = False
        current_section: str | None = None
        classified_lines: list[str] = []
        for line in lines:
            header = cls._detect_header(line)
            if header:
                has_headers = True
                current_section = header
                continue

            if has_headers and current_section and cls._is_header_helper_line(line):
                continue

            inline_header, remainder = cls._extract_inline_header_remainder(line)
            if inline_header:
                has_headers = True
                current_section = inline_header
                if remainder and cls._is_collectable_line(remainder):
                    split_items = cls._split_section_items(current_section, remainder)
                    buckets[current_section].extend(split_items)
                    classified_lines.extend(split_items)
                continue

            if has_headers and current_section and cls._is_collectable_line(line):
                split_items = cls._split_section_items(current_section, line)
                buckets[current_section].extend(split_items)
                classified_lines.extend(split_items)

        if has_headers and any(buckets.values()):
            buckets["starter"] = cls._normalize_section_items(buckets["starter"])
            buckets["main"] = cls._normalize_section_items(buckets["main"])
            buckets["dessert"] = cls._normalize_section_items(buckets["dessert"])
            classified_lines = cls._classified_lines(buckets)
            return MenuSections(
                starter=cls._pick_representative(buckets["starter"]),
                main=cls._pick_representative(buckets["main"]),
                dessert=cls._pick_representative(buckets["dessert"]),
                starter_options=buckets["starter"],
                main_options=buckets["main"],
                dessert_options=buckets["dessert"],
                detected_lines=classified_lines,
                raw_text=raw_text,
            )

        # 2) Fallback por bloques visuales (línea en blanco/separador)
        blocks: list[list[str]] = [[]]
        for line in raw_lines:
            if not line or cls._is_separator(line):
                blocks.append([])
            else:
                blocks[-1].append(line)

        clean_blocks = [[item for item in block if cls._is_collectable_line(item)] for block in blocks]
        clean_blocks = [block for block in clean_blocks if block]

        if len(clean_blocks) >= 2:
            buckets["starter"] = clean_blocks[0]
            buckets["main"] = clean_blocks[1]
            buckets["dessert"] = clean_blocks[2] if len(clean_blocks) > 2 else []
            buckets["starter"] = cls._normalize_section_items(buckets["starter"])
            buckets["main"] = cls._normalize_section_items(buckets["main"])
            buckets["dessert"] = cls._normalize_section_items(buckets["dessert"])
            return MenuSections(
                starter=cls._pick_representative(buckets["starter"]),
                main=cls._pick_representative(buckets["main"]),
                dessert=cls._pick_representative(buckets["dessert"]),
                starter_options=buckets["starter"],
                main_options=buckets["main"],
                dessert_options=buckets["dessert"],
                detected_lines=cls._classified_lines(buckets),
                raw_text=raw_text,
            )

        # 3) Fallback final por inferencia de inicio de principales
        valid = [line for line in lines if cls._is_valid_dish(line)]
        if not valid:
            return MenuSections(
                starter="Sin detectar",
                main="Sin detectar",
                dessert="Sin detectar",
                starter_options=[],
                main_options=[],
                dessert_options=[],
                detected_lines=[],
                raw_text=raw_text,
            )

        inferred_main_start = cls._infer_split_index_by_main_hints(valid)
        if inferred_main_start is not None:
            buckets["starter"] = valid[:inferred_main_start]
            buckets["main"] = valid[inferred_main_start:]
            buckets["dessert"] = []
            buckets["starter"] = cls._normalize_section_items(buckets["starter"])
            buckets["main"] = cls._normalize_section_items(buckets["main"])
            return MenuSections(
                starter=cls._pick_representative(buckets["starter"]),
                main=cls._pick_representative(buckets["main"]),
                dessert="Sin detectar",
                starter_options=buckets["starter"],
                main_options=buckets["main"],
                dessert_options=[],
                detected_lines=cls._classified_lines(buckets),
                raw_text=raw_text,
            )

        third = max(1, len(valid) // 3)
        buckets["starter"] = valid[:third]
        buckets["main"] = valid[third:third * 2]
        buckets["dessert"] = valid[third * 2:]
        buckets["starter"] = cls._normalize_section_items(buckets["starter"])
        buckets["main"] = cls._normalize_section_items(buckets["main"])
        buckets["dessert"] = cls._normalize_section_items(buckets["dessert"])
        return MenuSections(
            starter=cls._pick_representative(buckets["starter"]),
            main=cls._pick_representative(buckets["main"]),
            dessert=cls._pick_representative(buckets["dessert"]),
            starter_options=buckets["starter"],
            main_options=buckets["main"],
            dessert_options=buckets["dessert"],
            detected_lines=cls._classified_lines(buckets),
            raw_text=raw_text,
        )


class MenuMLPredictor:
    BASE_FEATURE_COLUMNS = [
        "max_temp_c",
        "is_holiday",
        "is_bridge_day",
        "is_business_day",
        "cuisine_type",
        "restaurant_segment",
        "menu_price",
        "day_of_week",
        "month",
        "starter_yesterday",
        "main_yesterday",
        "dessert_yesterday",
        "starter_last_week",
        "main_last_week",
        "dessert_last_week",
    ]

    MODEL_BY_CATEGORY = {
        "starter": "azca_menu_starter_v2",
        "main": "azca_menu_main_v2",
        "dessert": "azca_menu_dessert_v2",
    }

    def __init__(self, model_provider: Any) -> None:
        self.model_provider = model_provider

    def _build_features(self, common: dict[str, Any], sections: MenuSections) -> pd.DataFrame:
        row = {
            "max_temp_c": float(common.get("max_temp_c", 20.0)),
            "is_holiday": bool(common.get("is_holiday", False)),
            "is_bridge_day": bool(common.get("is_bridge_day", False)),
            "is_business_day": bool(common.get("is_business_day", True)),
            "cuisine_type": common.get("cuisine_type", "mediterranean") or "mediterranean",
            "restaurant_segment": common.get("restaurant_segment", "casual") or "casual",
            "menu_price": float(common.get("menu_price", 15.0)),
            "day_of_week": int(common.get("day_of_week", 0)),
            "month": int(common.get("month", 1)),
            "starter_yesterday": sections.starter,
            "main_yesterday": sections.main,
            "dessert_yesterday": sections.dessert,
            "starter_last_week": sections.starter,
            "main_last_week": sections.main,
            "dessert_last_week": sections.dessert,
        }
        return pd.DataFrame([[row[col] for col in self.BASE_FEATURE_COLUMNS]], columns=self.BASE_FEATURE_COLUMNS)

    @staticmethod
    def _top3_from_model(model: Any, features: pd.DataFrame) -> list[tuple[str, float]]:
        probabilities = model.predict_proba(features)[0]
        classes = list(getattr(model, "classes_", []))
        if len(classes) != len(probabilities):
            return []
        ranked = sorted(zip(classes, probabilities), key=lambda item: item[1], reverse=True)
        return [(str(name), float(score)) for name, score in ranked[:3]]

    def predict_from_menu(self, common: dict[str, Any], sections: MenuSections) -> dict[str, list[tuple[str, float]]]:
        features = self._build_features(common, sections)
        predictions: dict[str, list[tuple[str, float]]] = {}

        for category, model_name in self.MODEL_BY_CATEGORY.items():
            try:
                model = self.model_provider.get_model(model_name)
                top3 = self._top3_from_model(model, features)
                if top3:
                    predictions[category] = top3
                    continue
            except Exception:
                pass

            fallback_value = getattr(sections, category)
            predictions[category] = [
                (fallback_value, 0.9),
                ("Sin suficiente contexto", 0.5),
                ("Sin suficiente contexto", 0.4),
            ]

        return predictions
