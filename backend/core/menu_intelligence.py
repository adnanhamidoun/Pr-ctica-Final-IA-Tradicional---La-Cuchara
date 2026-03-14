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
    """
    Cliente OCR para Azure Document Intelligence.
    """

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

        # Filtrar texto decorativo del margen izquierdo (logos, texto vertical/lateral)
        page_width = getattr(page, "width", None)
        if page_width and float(page_width) > 0:
            margin_cutoff = float(page_width) * 0.18
            rendered_lines = [
                item for item in rendered_lines
                if item[1] is None or item[1] >= margin_cutoff
            ]
        elif any(min_x is not None for _, min_x, _, _ in rendered_lines):
            valid_xs = sorted(min_x for _, min_x, _, _ in rendered_lines if min_x is not None)
            if valid_xs:
                content_left = valid_xs[int(len(valid_xs) * 0.35)]
                if content_left > 0:
                    rendered_lines = [
                        item for item in rendered_lines
                        if item[1] is None or item[1] >= content_left * 0.45
                    ]

        if not rendered_lines:
            return []

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
                reference_height = max(
                    median_height,
                    previous_height or 0.0,
                    height or 0.0,
                )
                gap_threshold = reference_height * 1.9
                if center_y - previous_center_y > gap_threshold:
                    output.append("")

            output.append(content.strip())
            previous_center_y = center_y
            previous_height = height

        return output

    def extract_text(self, file_bytes: bytes, content_type: str | None = None) -> str:
        try:
            document_module = importlib.import_module("azure.ai.documentintelligence")
            core_module = importlib.import_module("azure.core.credentials")
            DocumentIntelligenceClient = getattr(document_module, "DocumentIntelligenceClient")
            AzureKeyCredential = getattr(core_module, "AzureKeyCredential")
        except ImportError as exc:
            raise RuntimeError(
                "Falta dependencia 'azure-ai-documentintelligence'. Instálala para usar OCR."
            ) from exc

        client = DocumentIntelligenceClient(
            endpoint=self.endpoint,
            credential=AzureKeyCredential(self.key),
        )

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
    STARTER_HEADERS = [
        "entrante", "entrantes",
        "primero", "primeros", "primer plato", "primeros platos",
        "para empezar", "de la huerta",
        "para picar", "aperitivo", "aperitivos",
        "frituras", "ensaladas de la casa",
    ]
    MAIN_HEADERS = [
        "principal", "principales",
        "segundo", "segundos", "segundo plato", "segundos platos",
        "plato fuerte", "platos principales", "plato principal",
        "del mar", "de la tierra", "de la parrilla",
        "carnes", "pescados", "aves",
    ]
    DESSERT_HEADERS = ["postre", "postres", "para terminar", "dulce", "dulces", "helados"]
    DESSERT_HINTS = [
        "flan", "tarta", "helado", "helados",
        "fruta", "frutas del tiempo",
        "yogur", "brownie", "coulant", "mousse",
        "natillas", "arroz con leche",
        "tiramisu", "tiramisú",
        "pastel", "bizcocho", "crepe",
        "pudín", "pudin", "merengue",
    ]

    # Patrones de ruido anclados (^) para evitar falsos positivos en nombres de platos
    # como "Tarta de café", "Pollo a la cerveza", "Sopa de pan".
    NOISE_PATTERNS = re.compile(
        # Línea que ES un precio: "14,00 €", "16€", "12,50€*"
        r"^\d{1,3}(?:[,\.]\d{1,2})?\s*€[*ºo]?\s*$"
        # Día de la semana solo o con número: "Lunes", "Martes 14"
        r"|^\s*(?:lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo)(?:\s+\d{1,2})?\s*$"
        # Línea de fecha: "MARTES 24 DE FEBRERO DE 2026", "24 de febrero de 2026"
        r"|^\s*(?:(?:lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo)\s+)?\d{1,2}\s+de\s+\w+\s+de\s+\d{4}"
        # Título "MENU DEL DIA"
        r"|^\s*men[uú]\s+del\s+d[ií]a\s*$"
        # Líneas que empiezan por "Incluye..."
        r"|^\s*incluye\b"
        # "o café + bebida", "o postre", "u otro"
        r"|^\s*[ou]\s+(?:caf[eé]|postre|bebida|refresco|copa|vino|agua|t[eé]|infusi[oó]n)"
        # "pan y bebida", "con pan y bebida"
        r"|^\s*(?:con\s+)?pan[\s,]+(?:y\s+)?bebida"
        # "bebida incluida / no incluida"
        r"|^\s*bebida\s+(?:in|no\s+in)clu"
        # IVA / impuesto
        r"|^\s*(?:iva|i\.v\.a|impuesto)\b"
        # "Medio menú con un primero 12€"
        r"|^\s*medio\s+men[uú]\b"
        # "con un segundo 12,50€*"
        r"|^\s*con\s+un\s+(?:primero|segundo)\b",
        re.IGNORECASE,
    )

    SEPARATOR_PATTERN = re.compile(r"^[-_=]{2,}$")

    @staticmethod
    def _strip_bullets(line: str) -> str:
        """Elimina marcadores de lista al inicio: •, ·, –, —, *, y guión con espacio."""
        line = re.sub(r"^\s*[•·–—\*]\s*", "", line)
        line = re.sub(r"^\s*-\s+", "", line)  # guión solo si va seguido de espacio
        return line.strip()

    @classmethod
    def _is_noise(cls, line: str) -> bool:
        return bool(cls.NOISE_PATTERNS.search(line))

    @classmethod
    def _is_separator(cls, line: str) -> bool:
        return bool(cls.SEPARATOR_PATTERN.match(line.strip()))

    @classmethod
    def _looks_like_dessert(cls, normalized_line: str) -> bool:
        return any(token in normalized_line for token in cls.DESSERT_HINTS)

    @staticmethod
    def _normalize(line: str) -> str:
        return re.sub(r"\s+", " ", line).strip().lower()

    @classmethod
    def _detect_header(cls, normalized: str) -> str | None:
        # Las cabeceras son títulos cortos; líneas largas son nombres de platos
        if len(normalized) > 45:
            return None
        if any(h in normalized for h in cls.STARTER_HEADERS):
            return "starter"
        if any(h in normalized for h in cls.MAIN_HEADERS):
            return "main"
        if any(h in normalized for h in cls.DESSERT_HEADERS):
            return "dessert"
        return None

    @classmethod
    def _is_valid_dish(cls, line: str) -> bool:
        clean = line.strip()
        return (
            len(clean) >= 4
            and not clean.isdigit()
            and not cls._is_noise(clean)
            and not cls._is_separator(clean)
        )

    @staticmethod
    def _split_inline_candidates(line: str) -> list[str]:
        separators_pattern = r"\s*[•|;]+\s*|\s{2,}|\s*/\s*"
        if re.search(separators_pattern, line):
            chunks = [chunk.strip(" -\t") for chunk in re.split(separators_pattern, line) if chunk.strip()]
            return chunks

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
            candidates = cls._split_inline_candidates(cleaned)
            prepared.extend(candidates)

        return prepared

    @staticmethod
    def _pick_representative(items: list[str]) -> str:
        return items[0] if items else "Sin detectar"

    @classmethod
    def extract(cls, raw_text: str) -> MenuSections:
        raw_lines = cls._prepare_lines(raw_text)
        lines = [line for line in raw_lines if line and not cls._is_separator(line)]
        detected_lines = [line for line in lines if cls._is_valid_dish(line)]
        buckets: dict[str, list[str]] = {"starter": [], "main": [], "dessert": []}

        current = None
        has_headers = False
        for line in lines:
            norm = cls._normalize(line)
            header = cls._detect_header(norm)
            if header:
                current = header
                has_headers = True
                continue
            if current and cls._is_valid_dish(line):
                buckets[current].append(line)

        if has_headers and any(buckets.values()):
            return MenuSections(
                starter=cls._pick_representative(buckets["starter"]),
                main=cls._pick_representative(buckets["main"]),
                dessert=cls._pick_representative(buckets["dessert"]),
                starter_options=buckets["starter"],
                main_options=buckets["main"],
                dessert_options=buckets["dessert"],
                detected_lines=detected_lines,
                raw_text=raw_text,
            )

        blocks: list[list[str]] = [[]]
        for line in raw_lines:
            if not line or cls._is_separator(line):
                blocks.append([])
            else:
                blocks[-1].append(line)

        clean_blocks = [
            [l for l in block if cls._is_valid_dish(l)]
            for block in blocks
        ]
        clean_blocks = [b for b in clean_blocks if b]

        if len(clean_blocks) >= 2:
            buckets["starter"] = clean_blocks[0]
            buckets["main"] = clean_blocks[1]
            buckets["dessert"] = clean_blocks[2] if len(clean_blocks) > 2 else []

            if not buckets["dessert"]:
                dessert_candidates = [
                    line
                    for line in buckets["starter"] + buckets["main"]
                    if cls._looks_like_dessert(cls._normalize(line))
                ]
                if dessert_candidates:
                    buckets["dessert"] = dessert_candidates
                    buckets["starter"] = [
                        line for line in buckets["starter"] if line not in dessert_candidates
                    ]
                    buckets["main"] = [
                        line for line in buckets["main"] if line not in dessert_candidates
                    ]

            return MenuSections(
                starter=cls._pick_representative(buckets["starter"]),
                main=cls._pick_representative(buckets["main"]),
                dessert=cls._pick_representative(buckets["dessert"]),
                starter_options=buckets["starter"],
                main_options=buckets["main"],
                dessert_options=buckets["dessert"],
                detected_lines=detected_lines,
                raw_text=raw_text,
            )

        valid = [l for l in lines if cls._is_valid_dish(l)]
        n = len(valid)
        if n == 0:
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

        third = max(1, n // 3)
        buckets["starter"] = valid[:third]
        buckets["main"] = valid[third:third * 2]
        buckets["dessert"] = valid[third*2:]
        return MenuSections(
            starter=cls._pick_representative(buckets["starter"]),
            main=cls._pick_representative(buckets["main"]),
            dessert=cls._pick_representative(buckets["dessert"]),
            starter_options=buckets["starter"],
            main_options=buckets["main"],
            dessert_options=buckets["dessert"],
            detected_lines=detected_lines,
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
