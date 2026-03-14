import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from backend.core.menu_intelligence import DocumentIntelligenceOCR, MenuSectionExtractor


class FakePoint:
    def __init__(self, x, y):
        self.x = x
        self.y = y


class FakeLine:
    def __init__(self, content, top, bottom):
        self.content = content
        self.polygon = [
            FakePoint(0, top),
            FakePoint(10, top),
            FakePoint(10, bottom),
            FakePoint(0, bottom),
        ]


class FakePage:
    def __init__(self, lines):
        self.lines = lines


def test_extract_preserves_visual_blocks_from_ocr_layout():
    page = FakePage([
        FakeLine("FIDEUA NEGRA DE LA CASA A LA MARINERA", 0.0, 0.2),
        FakeLine("ENSALADA MIXTA", 0.25, 0.45),
        FakeLine("CHULETA DE SAJONIA A LA RIOJANA CON PATATAS FRITAS", 1.2, 1.4),
        FakeLine("PECHUGA DE POLLO EMPANADA CON PATATAS O ENSALADA", 1.45, 1.65),
    ])

    rendered = DocumentIntelligenceOCR._page_lines_with_layout(page)

    assert rendered == [
        "FIDEUA NEGRA DE LA CASA A LA MARINERA",
        "ENSALADA MIXTA",
        "",
        "CHULETA DE SAJONIA A LA RIOJANA CON PATATAS FRITAS",
        "PECHUGA DE POLLO EMPANADA CON PATATAS O ENSALADA",
    ]


def test_extract_menu_without_headers_uses_detected_blocks():
    raw_text = """MARTES 24 DE FEBRERO DE 2026
FIDEUA NEGRA DE LA CASA A LA MARINERA
RAVIOLIS RELLENOS DE TERNERA EN SALSA FUNGHI
PARRILLADA CASERA DE VERDURAS
ESPARRAGOS SALTEADOS CON HUEVO, JAMON EN SALSA ROSA
ENSALADA DE LA CASA CON TOMATE Y ATUN
SALMOREJO CORDOBES CON HUEVO Y JAMON
ENSALADILLA RUSA DE LA CASA
CONSOME CASERO
ENSALADA MIXTA

CHULETA DE SAJONIA A LA RIOJANA CON PATATAS FRITAS
PECHUGA DE POLLO EMPANADA CON PATATAS O ENSALADA
FILETE DE TERNERA A LA PLANCHA CON PATATAS O ENSALADA
PECHUGA DE POLLO A LA PLANCHA CON PATATAS O ENSALADA
LOMOS DE VENTRESCA DE ATUN A LA PLANCHA CON ENSALADA

Incluye pan, bebida, postre o cafe
14,00 €"""

    sections = MenuSectionExtractor.extract(raw_text)

    assert sections.starter == "FIDEUA NEGRA DE LA CASA A LA MARINERA"
    assert sections.main == "CHULETA DE SAJONIA A LA RIOJANA CON PATATAS FRITAS"
    assert sections.dessert == "Sin detectar"
    assert sections.starter_options[-1] == "ENSALADA MIXTA"
    assert len(sections.main_options) == 5
    assert "14,00 €" not in sections.detected_lines
