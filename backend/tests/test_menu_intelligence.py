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
    def __init__(self, lines, width=None):
        self.lines = lines
        self.width = width


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


def test_extract_layout_with_page_width_keeps_centered_content():
    page = FakePage(
        [
            FakeLine("AZCA", 0.20, 0.35),
            FakeLine("FIDEUA NEGRA DE LA CASA A LA MARINERA", 1.20, 1.35),
            FakeLine("ENSALADA MIXTA", 1.22, 1.37),
        ],
        width=10.0,
    )

    rendered = DocumentIntelligenceOCR._page_lines_with_layout(page)

    assert "FIDEUA NEGRA DE LA CASA A LA MARINERA" in rendered
    assert "ENSALADA MIXTA" in rendered


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


def test_extract_menu_without_separators_infers_main_start_and_merges_wrapped_lines():
    raw_text = """MARTES 24 DE FEBRERO DE 2026
FIDEUA NEGRA DE LA CASA A LA MARINERA
RAVIOLIS RELLENOS DE TERNERA EN SALSA FUNGHI
PARRILLADA CASERA DE
VERDURAS
ESPARRAGOS SALTEADOS CON HUEVO Y JAMON
EN SALSA ROSA
ENSALADA MIXTA
CHULETA DE SAJONIA A LA RIOJANA CON PATATAS FRITAS
PECHUGA DE POLLO EMPANADA CON PATATAS O ENSALADA
FILETE DE TERNERA A LA PLANCHA CON PATATAS O ENSALADA
Incluye pan, bebida, postre o cafe
(Tercio o doble de cerveza +0,50 €)
14,00 €"""

    sections = MenuSectionExtractor.extract(raw_text)

    assert "PARRILLADA CASERA DE VERDURAS" in sections.starter_options
    assert "ESPARRAGOS SALTEADOS CON HUEVO Y JAMON EN SALSA ROSA" in sections.starter_options
    assert sections.main_options[0] == "CHULETA DE SAJONIA A LA RIOJANA CON PATATAS FRITAS"
    assert sections.dessert == "Sin detectar"
    assert all("tercio" not in line.lower() for line in sections.detected_lines)


def test_extract_does_not_split_main_on_starter_with_tuna():
    raw_text = """FIDEUA NEGRA DE LA CASA
A LA MARINERA
RAVIOLIS RELLENOS DE
TERNERA EN SALSA
FUNGHI
ENSALADA DE LA CASA
CON TOMATE Y ATUN
SALMOREJO CORDOBES
CON HUEVO Y JAMON
ENSALADILLA RUSA DE LA
CASA
CHULETA DE SAJONIA A LA RIOJANA CON PATATAS FRITAS
PECHUGA DE POLLO EMPANADA CON PATATAS O ENSALADA"""

    sections = MenuSectionExtractor.extract(raw_text)

    assert "RAVIOLIS RELLENOS DE TERNERA EN SALSA FUNGHI" in sections.starter_options
    assert "ENSALADILLA RUSA DE LA CASA" in sections.starter_options
    assert sections.main_options[0] == "CHULETA DE SAJONIA A LA RIOJANA CON PATATAS FRITAS"
    assert all("ENSALADA DE LA CASA CON TOMATE Y ATUN" != item for item in sections.main_options)


def test_extract_header_first_with_primeros_segundos_postres():
    raw_text = """MENÚ DEL DÍA
PRIMEROS:
Ensalada mixta
Salmorejo cordobés

SEGUNDOS:
Chuleta de sajonia a la riojana
Merluza a la plancha

POSTRES:
Flan casero
Yogur natural
14,00 €"""

    sections = MenuSectionExtractor.extract(raw_text)

    assert sections.starter_options == ["Ensalada mixta", "Salmorejo cordobés"]
    assert sections.main_options == ["Chuleta de sajonia a la riojana", "Merluza a la plancha"]
    assert sections.dessert_options == ["Flan casero", "Yogur natural"]
    assert sections.starter == "Ensalada mixta"
    assert sections.main == "Chuleta de sajonia a la riojana"
    assert sections.dessert == "Flan casero"


def test_extract_header_first_ignores_text_before_first_header():
    raw_text = """MARTES 24 DE FEBRERO DE 2026
Texto promocional del restaurante
PRIMEROS
Ensaladilla rusa
SEGUNDOS
Filete de ternera
POSTRE
Tarta de queso"""

    sections = MenuSectionExtractor.extract(raw_text)

    assert "Texto promocional del restaurante" not in sections.starter_options
    assert sections.starter_options == ["Ensaladilla rusa"]
    assert sections.main_options == ["Filete de ternera"]
    assert sections.dessert_options == ["Tarta de queso"]


def test_extract_header_variants_a_elegir_uno_and_excludes_branding():
    raw_text = """La Abadía
BRASSERIE
Entrantes a elegir uno
Tomate Raf con ventresca
Lomito ibérico 100%

Principal a elegir uno
Presa ibérica 100%
Bacalao confitado

Postres a elegir uno
Tarta de manzana Don Camilo
Crème brûlée a la murciana

Una bebida y café
25€"""

    sections = MenuSectionExtractor.extract(raw_text)

    assert sections.starter_options == ["Tomate Raf con ventresca", "Lomito ibérico 100%"]
    assert sections.main_options == ["Presa ibérica 100%", "Bacalao confitado"]
    assert sections.dessert_options == ["Tarta de manzana Don Camilo", "Crème brûlée a la murciana"]
    assert "La Abadía" not in sections.starter_options
    assert "La Abadía" not in sections.detected_lines


def test_extract_header_variants_a_elegir_and_postre_o_cafe():
    raw_text = """BONA VISTA
MENÚ MIÉRCOLES
PRIMEROS A ELEGIR
Acelgas salteadas con ajo, piñones y huevo frito
Sopa de ajo
Tomate con capellán

SEGUNDOS A ELEGIR
Arroz de conejo y serranas a la leña (+4€)
Codillo al horno (+1€)
Sardinas a la plancha

POSTRE O CAFÉ
Tarta de queso, tarta de la abuela, arroz con leche

15,90 €
Incluye tercio Estrella Damm, tinto de verano, vino de mesa, refresco o agua"""

    sections = MenuSectionExtractor.extract(raw_text)

    assert sections.starter_options == [
        "Acelgas salteadas con ajo, piñones y huevo frito",
        "Sopa de ajo",
        "Tomate con capellán",
    ]
    assert sections.main_options == [
        "Arroz de conejo y serranas a la leña",
        "Codillo al horno",
        "Sardinas a la plancha",
    ]
    assert sections.dessert_options == ["Tarta de queso", "tarta de la abuela", "arroz con leche"]
    assert "BONA VISTA" not in sections.detected_lines
    assert all("Incluye" not in line for line in sections.detected_lines)


def test_extract_inline_header_with_first_dish_attached():
    raw_text = """MENÚ MIÉRCOLES
PRIMEROS A ELEGIR Acelgas salteadas con ajo, piñones y huevo frito
Sopa de ajo
SEGUNDOS A ELEGIR Codillo al horno (+1€)
Sardinas a la plancha
POSTRE O CAFÉ Tarta de queso, arroz con leche"""

    sections = MenuSectionExtractor.extract(raw_text)

    assert sections.starter_options == [
        "Acelgas salteadas con ajo, piñones y huevo frito",
        "Sopa de ajo",
    ]
    assert sections.main_options == [
        "Codillo al horno",
        "Sardinas a la plancha",
    ]
    assert sections.dessert_options == ["Tarta de queso", "arroz con leche"]


def test_extract_header_variant_1a_elegir_and_strip_extra_price_from_dishes():
    raw_text = """VIERNES
Entrantes 1a elegir
Crema de apionabo con manzana verde y avellanas tostadas
Judías verdes rehogadas estilo sichuan
Hummus casero de garbanzos con sticks de zanahoria y totopos

Principales 1a elegir
Ensalada de lentejas con boniato asado, espinacas frescas, nueces, queso cottage y vinagreta casera de mostaza-miel
Arroz chaufa de pollo a baja temperatura con verduras y huevo revuelto
Codillo al horno (+1€)"""

    sections = MenuSectionExtractor.extract(raw_text)

    assert sections.starter_options == [
        "Crema de apionabo con manzana verde y avellanas tostadas",
        "Judías verdes rehogadas estilo sichuan",
        "Hummus casero de garbanzos con sticks de zanahoria y totopos",
    ]
    assert sections.main_options == [
        "Ensalada de lentejas con boniato asado, espinacas frescas, nueces, queso cottage y vinagreta casera de mostaza-miel",
        "Arroz chaufa de pollo a baja temperatura con verduras y huevo revuelto",
        "Codillo al horno",
    ]
    assert all("(+1€)" not in item for item in sections.main_options)
    assert "Entrantes 1a elegir" not in sections.starter_options


def test_extract_split_header_helper_line_is_not_classified_as_dish():
    raw_text = """MARTES
Entrantes
1a elegir
Crema de lombarda y boniato
Berenjena a la parmesana

Principales
1a elegir
Ensalada de pasta al aceite de albahaca
Salmón al horno"""

    sections = MenuSectionExtractor.extract(raw_text)

    assert sections.starter_options == [
        "Crema de lombarda y boniato",
        "Berenjena a la parmesana",
    ]
    assert sections.main_options == [
        "Ensalada de pasta al aceite de albahaca",
        "Salmón al horno",
    ]
    assert "1a elegir" not in sections.starter_options
    assert "1a elegir" not in sections.main_options


def test_extract_helper_line_a_elegir_is_not_classified_as_dish():
    raw_text = """MARTES
Entrantes
a elegir
Crema de lombarda y boniato
Hummus casero de garbanzos

Principales
1 a elegir
Ensalada de pasta al aceite de albahaca
Salmón al horno"""

    sections = MenuSectionExtractor.extract(raw_text)

    assert sections.starter_options == [
        "Crema de lombarda y boniato",
        "Hummus casero de garbanzos",
    ]
    assert sections.main_options == [
        "Ensalada de pasta al aceite de albahaca",
        "Salmón al horno",
    ]
    assert "a elegir" not in sections.starter_options
    assert "a elegir" not in sections.main_options


def test_extract_excludes_price_includes_disclaimer_lines():
    raw_text = """POSTRES
Arroz con leche
Torta de queso
Fruta del tiempo
Profiteroles
El precio incluye bebida
Se incluye pan, agua y refresco"""

    sections = MenuSectionExtractor.extract(raw_text)

    assert sections.dessert_options == [
        "Arroz con leche",
        "Torta de queso",
        "Fruta del tiempo",
        "Profiteroles",
    ]
    assert all("incluye" not in item.lower() for item in sections.dessert_options)


def test_extract_excludes_el_menu_incluye_line():
    raw_text = """POSTRES
Arroz con leche
Fruta del tiempo
El menú incluye una bebida y postre o café"""

    sections = MenuSectionExtractor.extract(raw_text)

    assert sections.dessert_options == [
        "Arroz con leche",
        "Fruta del tiempo",
    ]
    assert all("menú incluye" not in item.lower() for item in sections.dessert_options)


def test_extract_merges_multiline_dishes_and_excludes_no_incluye():
    raw_text = """MENÚ
PRIMEROS:
Corazones de alcachofas salteados con
chipirones ,ajos y sepia baby
Espaguetis negros con salsa Alfredo (nata y parmesano) y torreznos de Soria
Ensalada con trio de queso rulo
(natural,pimienta,pimentón),beicon
tomate , nueces,aros de cebolla y balsámico de Modena

SEGUNDOS:
Cachopito de ternera con jamón y queso y
patatas gajo al pimentón con salsa Deluxe
Chuletas y costillas de ternasco a la
parrilla con patata asada y alioli
Suprema de salmón de Noruega a la
plancha con Teriyaki y arroz basmati al estilo chino

NO INCLUYE CAFE"""

    sections = MenuSectionExtractor.extract(raw_text)

    assert sections.starter_options == [
        "Corazones de alcachofas salteados con chipirones,ajos y sepia baby",
        "Espaguetis negros con salsa Alfredo (nata y parmesano) y torreznos de Soria",
        "Ensalada con trio de queso rulo (natural,pimienta,pimentón),beicon tomate, nueces,aros de cebolla y balsámico de Modena",
    ]
    assert sections.main_options == [
        "Cachopito de ternera con jamón y queso y patatas gajo al pimentón con salsa Deluxe",
        "Chuletas y costillas de ternasco a la parrilla con patata asada y alioli",
        "Suprema de salmón de Noruega a la plancha con Teriyaki y arroz basmati al estilo chino",
    ]
    assert all("incluye" not in item.lower() for item in sections.main_options)


def test_extract_excludes_branding_line_inside_section():
    raw_text = """MENU DEL DIA
PRIMEROS
Crema de verduras
Pasta a la carbonara

SEGUNDOS
ENVASIUM
Redondo de ternera asado
Presa de Duroc a la plancha"""

    sections = MenuSectionExtractor.extract(raw_text)

    assert sections.starter_options == ["Crema de verduras", "Pasta a la carbonara"]
    assert sections.main_options == ["Redondo de ternera asado", "Presa de Duroc a la plancha"]
    assert "ENVASIUM" not in sections.main_options


def test_extract_merges_orphan_fragment_into_previous_dish():
    raw_text = """MENÚ DEL DÍA
ENTRANTES
Lentejas estofadas
Revuelto de espinacas
Ensalada de lechugas variadas con queso fresco y
aceitunas
PRINCIPALES
Rollito de ternera rellenos de verduras con patatas
Gallo frito con ensalada
POSTRES
Brownie con helado"""

    sections = MenuSectionExtractor.extract(raw_text)

    assert sections.starter_options == [
        "Lentejas estofadas",
        "Revuelto de espinacas",
        "Ensalada de lechugas variadas con queso fresco y aceitunas",
    ]
    assert "aceitunas" not in sections.starter_options
