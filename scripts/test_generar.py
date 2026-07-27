#!/usr/bin/env python3
"""Suite unitaria de generar.py (stdlib unittest, sin dependencias).

Corre asi (con el Python del venv de la skill o cualquiera con la stdlib):
    python3 scripts/test_generar.py

Cubre lo critico del BRIEF LEAN (director creativo, no 'tag soup'):
- Presupuesto de tamano del prompt por debajo del umbral seguro (con y sin refs).
- Recorte automatico del estilo_visual cuando el prompt se pasa (sin tocar el COPY).
- Error claro (PromptDemasiadoLargo) cuando ni recortando cabe.
- Esenciales del brief: idioma español, copy exacto, paleta de acento, marcador consistente.
- El @ real va SOLO en portada y cierre; placeholder se omite.
- Con referencias: son SOLO estilo visual (no copiar texto/@/UI de Instagram).
- Molde: en 'auto' la portada SIEMPRE ancla la serie.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import generar as g  # noqa: E402


MARCA = {
    "negocio": "Grizly Gym",
    "colores": {"primario": "#E9B02E", "secundario": "#1A1A1A",
                "fondo": "#111111", "texto": "#FFFFFF"},
    "tipografia": "sans-serif gruesa condensada bold, ruda y legible.",
    "estilo_visual": ("mini-guia densa, fondo negro con acento amarillo. Titulo grueso condensado, "
                      "una palabra en amarillo subrayada a mano; bullets en tiras tipo washi con icono."),
    "densidad": "completa",
    "tratamiento_visual": "graficos",
    "elemento_serie": "numero",
    "molde": "auto",
    "instagram_usuario": "@grizlygym",
}

SLIDES = [
    {"number": 1, "title": "Le rompes duro y no creces",
     "content": "4 razones que frenan tu musculo.\nComes menos de lo que crees.\nLevantas el mismo peso."},
    {"number": 2, "title": "Comes poco para crecer",
     "content": "Sin comida extra no hay musculo.\n1.6-2 g de proteina por kilo.\nReparte en 4 comidas.\nPesa tu comida."},
    {"number": 6, "title": "Arreglalo y vas a CRECER",
     "content": "Comenta CRECER y te mando la guia gratis.\n@grizlygym"},
]
TOTAL = 6


def _bytes(p):
    return len(p.encode("utf-8"))


class TestPresupuesto(unittest.TestCase):
    def test_todas_las_slides_bajo_umbral(self):
        """Config real (con y sin refs): cada prompt cabe bajo el umbral seguro."""
        for n_refs, sin_molde, ancla in [(2, True, False), (0, False, True), (7, False, True)]:
            for s in SLIDES:
                role = g.slide_role(s["number"], TOTAL)
                p = g.build_prompt(s, role, MARCA, TOTAL, ancla=ancla, n_refs=n_refs, sin_molde=sin_molde)
                self.assertLessEqual(_bytes(p), g.PROMPT_SAFETY_LIMIT,
                                     f"slide {s['number']} refs={n_refs} se paso del umbral")

    def test_medir_prompt_bytes_mayor_o_igual_chars(self):
        ch, by = g.medir_prompt("acción café ñandú")   # con acentos
        self.assertGreater(by, ch, "acentos deberian pesar mas en bytes que en chars")
        ch2, by2 = g.medir_prompt("plain ascii text")
        self.assertEqual(ch2, by2, "ascii: chars == bytes")

    def test_recorta_estilo_gigante_pero_cabe(self):
        """Un estilo_visual larguisimo (acentuado) se recorta solo y el prompt cabe."""
        marca = dict(MARCA)
        marca["estilo_visual"] = "á" * 4000   # 4000 chars = 8000 bytes de puro estilo
        p = g.build_prompt(SLIDES[1], "valor", marca, TOTAL, ancla=True, n_refs=7, sin_molde=False)
        self.assertLessEqual(_bytes(p), g.PROMPT_SAFETY_LIMIT)
        # El copy NO se toca: sigue intacto en el prompt.
        self.assertIn("1.6-2 g de proteina por kilo.", p)

    def test_error_claro_si_copy_es_gigantesco(self):
        """Si ni recortando cabe (copy enorme), lanza PromptDemasiadoLargo con mensaje en español."""
        slide = {"number": 3, "title": "X", "content": "palabra " * 3000}  # copy imposible
        with self.assertRaises(g.PromptDemasiadoLargo) as ctx:
            g.build_prompt(slide, "valor", MARCA, TOTAL, ancla=True, n_refs=7, sin_molde=False)
        self.assertIn("demasiado largo", str(ctx.exception).lower())


class TestBriefLean(unittest.TestCase):
    def test_idioma_espanol(self):
        p = g.build_prompt(SLIDES[0], "gancho", MARCA, TOTAL, sin_molde=True)
        self.assertIn("ESPAÑOL", p)

    def test_idioma_espanol_con_referencias(self):
        """Aun con referencias (que pueden estar en ingles), el brief pide texto en español."""
        p = g.build_prompt(SLIDES[0], "gancho", MARCA, TOTAL, n_refs=2, sin_molde=True)
        self.assertIn("ESPAÑOL", p)

    def test_copy_exacto_presente(self):
        """El copy del usuario va literal en el prompt (el modelo lo renderiza tal cual)."""
        p = g.build_prompt(SLIDES[1], "valor", MARCA, TOTAL, sin_molde=True)
        self.assertIn(SLIDES[1]["title"], p)
        self.assertIn("1.6-2 g de proteina por kilo.", p)

    def test_paleta_de_acento_presente(self):
        p = g.build_prompt(SLIDES[1], "valor", MARCA, TOTAL, sin_molde=True)
        self.assertIn(g.color_acento(MARCA["colores"]), p)   # el acento REAL (color mas vivo)

    def test_acento_es_el_color_mas_vivo(self):
        # primario amarillo vibrante vs secundario casi-negro -> acento = amarillo (primario).
        self.assertEqual(g.color_acento({"primario": "#E9B02E", "secundario": "#1A1A1A"}), "#E9B02E")
        # primario oscuro vs secundario morado vibrante -> acento = morado (secundario).
        self.assertEqual(g.color_acento({"primario": "#131628", "secundario": "#6F00FF"}), "#6F00FF")

    def test_placeholder_usuario_se_omite(self):
        marca = dict(MARCA)
        marca["instagram_usuario"] = "@tu_usuario"
        self.assertIsNone(g.instagram_usuario_real(marca))
        p = g.build_prompt(SLIDES[0], "gancho", marca, TOTAL, sin_molde=True)
        self.assertNotIn("tu_usuario", p)

    def test_handle_real_solo_portada_y_cierre(self):
        gancho = g.build_prompt(SLIDES[0], "gancho", MARCA, TOTAL, sin_molde=True)
        valor = g.build_prompt(SLIDES[1], "valor", MARCA, TOTAL, sin_molde=True)
        cierre = g.build_prompt(SLIDES[2], "recompensa", MARCA, TOTAL, sin_molde=True)
        self.assertIn("@grizlygym", gancho)
        self.assertIn("@grizlygym", cierre)
        # En la slide de valor NO se mete el @ por su cuenta (solo si el copy lo trae, y aqui no).
        self.assertNotIn("@grizlygym", valor)

    def test_valor_pie_vacio(self):
        """El bug real (visto en produccion 2026-07-26): el @ se colaba en TODAS las slides de valor.
        El framing solo-positivo ('pie limpio y despejado') NO alcanzo: con molde ON, el modelo lee el
        @ de la portada como parte del 'look' y lo replica. Por eso el brief ahora es EXPLICITO."""
        p = g.build_prompt(SLIDES[1], "valor", MARCA, TOTAL, sin_molde=True)
        self.assertIn("COMPLETAMENTE VACIO", p)
        self.assertIn("SOLO en la portada y en el cierre", p)

    def test_molde_no_copia_el_handle(self):
        """El molde copia TOKENS de estilo de la portada, pero nunca su @usuario del pie."""
        p = g.build_prompt(SLIDES[1], "valor", MARCA, TOTAL, ancla=True, sin_molde=False)
        self.assertIn("NI el @usuario de su pie", p)

    def test_referencias_solo_estilo_visual(self):
        """Con refs: son REFERENCIA DE ESTILO (estetica), aplicada con la paleta/texto de arriba (framing positivo)."""
        p = g.build_prompt(SLIDES[1], "valor", MARCA, TOTAL, n_refs=2, sin_molde=True)
        self.assertIn("REFERENCIA DE ESTILO", p)
        self.assertIn("estetica", p)
        self.assertIn("full-bleed", p)
        # Sin refs, esa nota no aplica.
        p_sin = g.build_prompt(SLIDES[1], "valor", MARCA, TOTAL, n_refs=0, sin_molde=True)
        self.assertNotIn("REFERENCIA DE ESTILO", p_sin)

    def test_marcador_consistente_con_su_numero(self):
        """El marcador n/total va en cada slide con su numero, y se pide igual en toda la serie."""
        for n in range(1, TOTAL + 1):
            slide = {"number": n, "title": f"Titulo {n}", "content": "Uno.\nDos."}
            p = g.build_prompt(slide, g.slide_role(n, TOTAL), MARCA, TOTAL, n_refs=2, sin_molde=True)
            self.assertIn(f"{n}/{TOTAL}", p)
            self.assertIn("mismo tamaño", p)   # marcador consistente en toda la serie


class TestMolde(unittest.TestCase):
    """La portada SIEMPRE ancla la serie en 'auto' (antes se apagaba con refs y las slides derivaban)."""

    def test_auto_es_on_con_y_sin_referencias(self):
        marca = dict(MARCA)  # molde 'auto'
        self.assertTrue(g.molde_activo(marca, hay_refs=True),
                        "auto con referencias debe encender el molde (portada = ancla de la serie)")
        self.assertTrue(g.molde_activo(marca, hay_refs=False),
                        "auto sin referencias tambien enciende el molde")

    def test_off_y_on_los_manda_el_usuario(self):
        m_off = dict(MARCA); m_off["molde"] = "off"
        m_on = dict(MARCA); m_on["molde"] = "on"
        self.assertFalse(g.molde_activo(m_off, hay_refs=True))
        self.assertFalse(g.molde_activo(m_off, hay_refs=False))
        self.assertTrue(g.molde_activo(m_on, hay_refs=True))
        self.assertTrue(g.molde_activo(m_on, hay_refs=False))


class TestGuardarCopiaLocal(unittest.TestCase):
    """publicar.guardar_copia_local deja el carrusel (slides + caption + copy) en una
    carpeta facil de encontrar del HOME, ademas de publicarlo."""

    def test_copia_slides_caption_y_copy_a_destino(self):
        import tempfile
        import publicar as pub
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            bundle = tmp / "2026-07-25-tema"
            (bundle / "slides").mkdir(parents=True)
            (bundle / "slides" / "slide-01.png").write_bytes(b"\x89PNG_fake")
            (bundle / "slides" / "slide-02.png").write_bytes(b"\x89PNG_fake")
            (bundle / "caption.txt").write_text("Mi caption. Comenta FABRICA", encoding="utf-8")
            (bundle / "carrusel.md").write_text("### SLIDE 1", encoding="utf-8")
            base = tmp / "Carruseles"
            destino = pub.guardar_copia_local(bundle, destino_base=base)
            self.assertEqual(destino, base / "2026-07-25-tema")
            self.assertTrue((destino / "slides" / "slide-01.png").is_file())
            self.assertTrue((destino / "slides" / "slide-02.png").is_file())
            self.assertTrue((destino / "caption.txt").is_file())
            self.assertTrue((destino / "carrusel.md").is_file())
            destino2 = pub.guardar_copia_local(bundle, destino_base=base)  # idempotente
            self.assertEqual(destino, destino2)

    def test_base_default_es_escritorio_o_home(self):
        import publicar as pub
        base = pub._carpeta_base_default()
        self.assertEqual(base.name, "Carruseles")
        self.assertIn(base, {Path.home() / "Desktop" / "Carruseles",
                             Path.home() / "Carruseles"})


if __name__ == "__main__":
    unittest.main(verbosity=2)
