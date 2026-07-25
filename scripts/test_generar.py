#!/usr/bin/env python3
"""Suite unitaria de generar.py (stdlib unittest, sin dependencias).

Corre asi (con el Python del venv de la skill o cualquiera con la stdlib):
    python3 scripts/test_generar.py

Cubre lo critico que ya nos ha mordido:
- Presupuesto de tamano del prompt (chars Y bytes) por debajo del umbral seguro.
- Recorte automatico del estilo_visual cuando el prompt se pasa (sin tocar copy ni candados).
- Error claro (PromptDemasiadoLargo) cuando ni recortando cabe.
- Candado de idioma presente y placeholder de @usuario blindado.
- El @ real va SOLO en portada y cierre, nunca en las slides de valor.
"""
import os
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
        for n_refs, sin_molde, ancla in [(2, True, False), (0, False, True)]:
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


class TestCandados(unittest.TestCase):
    def test_candado_idioma_presente(self):
        p = g.build_prompt(SLIDES[0], "gancho", MARCA, TOTAL, sin_molde=True)
        self.assertIn("EN ESPAÑOL", p)
        self.assertIn("IDIOMA", p)

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

    def test_prohibiciones_criticas_presentes(self):
        p = g.build_prompt(SLIDES[1], "valor", MARCA, TOTAL, n_refs=2, sin_molde=True)
        self.assertIn("PowerPoint", p)          # veto layout diapositiva
        self.assertIn("PALETA del usuario", p)  # no recolorear refs / paleta del usuario manda

    def test_veto_copiar_handle_de_referencias(self):
        """Con refs, el prompt prohibe explicitamente copiar el @usuario/handle/URL de las referencias
        (bug real: slides de valor sacaban el @ del gimnasio de la referencia en el footer)."""
        p = g.build_prompt(SLIDES[1], "valor", MARCA, TOTAL, n_refs=2, sin_molde=True)
        self.assertIn("NUNCA inventes ni copies un @usuario", p)
        self.assertIn("@usuario/handle/URL", p)


if __name__ == "__main__":
    unittest.main(verbosity=2)
