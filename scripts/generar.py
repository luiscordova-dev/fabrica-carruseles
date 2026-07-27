#!/usr/bin/env python3
"""
generar.py - Genera las slides de un carrusel de Instagram con Kie AI (nano-banana-pro).

Toma la MARCA del usuario (config/marca.json) y el COPY del carrusel
(un archivo carrusel.md con la estructura Gancho -> Valor -> Cierre)
y produce las imagenes PNG, todas en paralelo.

Uso:
    python3 generar.py <ruta-carpeta-bundle>
    python3 generar.py <ruta-carpeta-bundle> --dry-run
    python3 generar.py <ruta-carpeta-bundle> --regenerar "2,4"

La carpeta bundle debe contener un archivo "carrusel.md" con las slides.
Las imagenes se guardan en <ruta-carpeta-bundle>/slides/slide-01.png, etc.
(Retrocompat: outputs viejos con laminas/lamina-01.png y clave "laminas" se siguen leyendo.)

Requiere:
    - KIE_API_KEY (o KIE_AI_API_KEY) en el entorno o en el .env de la skill.
    - config/marca.json con la identidad de marca.
"""

import os
import sys
import json
import time
import re
import base64
import argparse
import requests
from pathlib import Path
from typing import Optional, Dict, List
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

try:
    from dotenv import load_dotenv
    # .env vive en la raiz de la skill (un nivel arriba de scripts/)
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass  # dotenv es opcional; la key puede venir del entorno

# --- Rutas de la skill ---
SKILL_ROOT = Path(__file__).resolve().parent.parent
MARCA_FILE = SKILL_ROOT / "config" / "marca.json"
# Referencias visuales del usuario (capturas de carruseles que le gustan). Se guardan una vez y se
# suben FRESCAS a Kie en cada corrida (las URLs de archivos de Kie expiran ~24h).
REFERENCIAS_DIR = SKILL_ROOT / "config" / "referencias"
REF_EXTS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_REF_BYTES = 10 * 1024 * 1024   # 10MB por archivo (limite de la File Upload API)

# --- API Kie AI (nano-banana-pro) ---
KIE_API_BASE = "https://api.kie.ai/api/v1/jobs"
KIE_CREATE_TASK = f"{KIE_API_BASE}/createTask"
KIE_RECORD_INFO = f"{KIE_API_BASE}/recordInfo"
KIE_FILE_UPLOAD = "https://kieai.redpandaai.co/api/file-base64-upload"  # sube archivos (no gasta creditos de generacion)
MODEL = "nano-banana-pro"
ASPECT_RATIO = "4:5"   # Instagram carrusel (vertical). El encuadre va SOLO por este parametro,
RESOLUTION = "1K"      # nunca en el prompt. 1K (~1024px) basta para IG y es mas rapido/barato que 2K/4K.
FORMAT = "png"
MAX_POLL_ATTEMPTS = 120   # ~10 min por slide: Kie AI a veces encola y tarda varios minutos
POLL_INTERVAL = 5
MAX_IMAGE_INPUT = 8       # tope de imagenes de referencia por tarea (nano-banana-pro)

# --- Presupuesto de tamano del campo `prompt` de Kie ---
# Hallazgos empiricos (createTask + polling, nano-banana-pro, 2026-07):
#   - createTask ACEPTA cualquier tamano; si algo esta mal, el fallo aparece al GENERAR (state=fail).
#   - Prompts de 5k, 10k y 15k caracteres GENERARON bien; uno de 20k fallo con
#     failMsg "Your prompt cannot exceed 5000 characters" (failCode 400).
#   - O sea: Kie declara 5000 en su error pero NO lo aplica de forma consistente; tolera >=15k.
# Elegimos 10000 como TECHO conservador del assert: por debajo del punto real de fallo (~15-20k)
# y muy por encima de nuestro tamano normal (~4k). Ademas el andamiaje se compacto para que un
# carrusel normal quede ~4k chars, con margen aun si Kie llegara a exigir 5000.
# Medimos chars Y bytes (el espanol acentuado infla los bytes en UTF-8) y aplicamos el limite
# sobre los BYTES (siempre >= chars), la medida mas conservadora.
KIE_PROMPT_LIMIT = 10000  # limite oficial del spec de Kie para nano-banana-pro (prompt maxLength: 10000)
PROMPT_SAFETY_RATIO = 0.95
PROMPT_SAFETY_LIMIT = int(KIE_PROMPT_LIMIT * PROMPT_SAFETY_RATIO)  # 9500 (con el brief lean ~1700, sobra muchisimo)


def medir_prompt(prompt: str):
    """Tamano de un prompt como (chars, bytes). El limite se aplica sobre bytes (>= chars)."""
    return len(prompt), len(prompt.encode("utf-8"))


def _recortar(texto: str, max_chars: int) -> str:
    """Recorta un texto a max_chars con elipsis, sin cortar a media palabra cuando se puede."""
    t = (texto or "").strip()
    if len(t) <= max_chars:
        return t
    corte = t[:max_chars].rsplit(" ", 1)[0].rstrip(" ,.;:")
    return (corte or t[:max_chars]) + "…"


class PromptDemasiadoLargo(Exception):
    """El prompt no cabe en el presupuesto ni recortando los campos de menor prioridad."""


def get_api_key() -> str:
    key = os.environ.get("KIE_API_KEY") or os.environ.get("KIE_AI_API_KEY")
    if not key:
        print("❌ Falta la llave de Kie AI. Ponla en el .env de la skill como KIE_API_KEY=...")
        print("   (Sigue el walkthrough 01-kie-ai.md si aun no la tienes.)")
        sys.exit(1)
    return key


def load_marca() -> Dict:
    """Carga la marca del usuario desde config/marca.json. La ruta es SIEMPRE relativa a la
    ubicacion del script (SKILL_ROOT = carpeta de la skill), nunca al directorio de trabajo, asi
    que da igual desde donde se corra generar.py.

    Si marca.json NO existe, ABORTA con un mensaje claro en español y NO inventa valores neutros.
    Generar con un dict de ejemplo fue justo la causa del bug: sacaba '@tu_usuario' literal,
    densidad 'media' y tipografia generica todos a la vez, pisando la marca real del usuario."""
    if not MARCA_FILE.exists():
        print(f"❌ No encontré tu marca en {MARCA_FILE}.")
        print("   Antes de generar hay que configurarla: corre el onboarding de la skill")
        print("   (te hace unas preguntas rápidas y crea tu marca.json).")
        print("   Sin marca NO genero, para no sacar slides con datos de ejemplo")
        print("   (@tu_usuario, densidad y tipografía genéricas en vez de las tuyas).")
        sys.exit(1)
    with open(MARCA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


# --- Blindaje contra placeholders del onboarding ---
# El onboarding puede dejar campos con su valor de ejemplo/placeholder si el usuario no los
# llenó. JAMÁS deben llegar al modelo (en la prueba real "@tu_usuario" se renderizó literal en
# 5 de 6 slides). El nucleo se compara normalizado (minusculas, sin @, sin espacios).
PLACEHOLDERS_USUARIO = {"tu_usuario", "usuario", "tuusuario", ""}


def instagram_usuario_real(marca: Dict) -> Optional[str]:
    """Devuelve el @ REAL del usuario, o None si el campo esta vacio o trae un placeholder.
    Placeholders que se tratan como SIN usuario (comparando el nucleo normalizado):
    '@tu_usuario', 'tu_usuario', '@usuario', 'usuario', '@tuusuario', '' y None.
    Cuando devuelve None, los prompts OMITEN por completo cualquier mencion de @/usuario."""
    raw = marca.get("instagram_usuario")
    if raw is None:
        return None
    limpio = str(raw).strip()
    nucleo = limpio.lstrip("@").strip().lower()
    if nucleo in PLACEHOLDERS_USUARIO:
        return None
    return limpio if limpio.startswith("@") else "@" + limpio


# --- Retrocompat de artefactos ---
# La skill nombra las imagenes slide-NN.png dentro de slides/ y guarda la clave "slides"
# en el manifest. Los outputs viejos usan lamina-NN.png dentro de laminas/ y clave "laminas";
# estas ayudas los siguen leyendo sin fallar.
def slides_dir_for(bundle_path: Path) -> Path:
    """Carpeta de imagenes del bundle. Nueva: slides/. Si solo existe la vieja laminas/, la usa
    para no romper --regenerar sobre outputs anteriores."""
    new_dir = bundle_path / "slides"
    legacy_dir = bundle_path / "laminas"
    if new_dir.exists():
        return new_dir
    if legacy_dir.exists():
        return legacy_dir
    return new_dir


def manifest_slides(data: Dict) -> List[Dict]:
    """Lee la lista de slides de un manifest, aceptando la clave nueva 'slides' o la vieja 'laminas'."""
    return data.get("slides") or data.get("laminas") or []


DENSIDADES_VALIDAS = {"aireada", "media", "completa"}


def densidad_de(marca: Dict) -> str:
    """Densidad de contenido por slide (aireada|media|completa). Default 'media' si falta o es invalida."""
    d = str(marca.get("densidad", "media")).strip().lower()
    return d if d in DENSIDADES_VALIDAS else "media"


TRATAMIENTOS_VISUALES = {"escena-fotografica", "ilustracion", "graficos"}


def tratamiento_visual_de(marca: Dict) -> str:
    """Como se resuelve el elemento visual (atributo de la ESTETICA del usuario):
    'escena-fotografica' (producto/objeto real en escena con luz y sombras),
    'ilustracion' (dibujo/caricatura/vector fundido con el diseño), o
    'graficos' (esquemas/diagramas con iconos, flechas y anotaciones, estilo educativo).
    Si el campo no viene, se infiere del estilo_visual; ante empate, 'ilustracion'
    (coincide con el estilo por defecto de la skill)."""
    t = str(marca.get("tratamiento_visual", "")).strip().lower()
    if t in TRATAMIENTOS_VISUALES:
        return t
    estilo = str(marca.get("estilo_visual", "")).lower()
    foto_signals = ["foto", "fotograf", "luz natural", "escena", "producto en primer plano",
                    "editorial", "stock", "primer plano"]
    graf_signals = ["esquema", "diagrama", "icono", "iconos", "infografia", "infografía",
                    "flecha", "grafico educativo", "educativo", "mapa mental"]
    ilus_signals = ["ilustracion", "ilustración", "caricatura", "flat", "vector", "dibujo", "3d",
                    "render", "acuarela", "isometric"]
    foto = sum(1 for s in foto_signals if s in estilo)
    graf = sum(1 for s in graf_signals if s in estilo)
    ilus = sum(1 for s in ilus_signals if s in estilo)
    if foto > graf and foto > ilus:
        return "escena-fotografica"
    if graf > foto and graf > ilus:
        return "graficos"
    return "ilustracion"


MOLDES_VALIDOS = {"auto", "on", "off"}


def molde_de(marca: Dict) -> str:
    """Modo del molde-portada: 'auto' (default) | 'on' | 'off'."""
    m = str(marca.get("molde", "auto")).strip().lower()
    return m if m in MOLDES_VALIDOS else "auto"


def molde_activo(marca: Dict, hay_refs: bool) -> bool:
    """Decide si se usa la portada como molde de las demas slides.
    auto (default): molde SIEMPRE ON -> la portada ancla la serie y le da su ADN visual al resto.
    CON referencias, la portada primero las MODELA y luego ancla a las demas (cohesion fuerte:
    evita que cada slide derive de estilo por su cuenta, el bug real con 1 sola referencia debil).
    'on'/'off': manda el usuario ('off' = todas en paralelo, sin ancla comun; util solo por velocidad).
    hay_refs se conserva en la firma por compatibilidad con quien la llama."""
    m = molde_de(marca)
    if m == "on":
        return True
    if m == "off":
        return False
    return True  # auto: la portada SIEMPRE ancla la serie (cohesion > velocidad)


# --- Referencias visuales del usuario -> Kie File Upload API ---
def listar_referencias() -> List[Path]:
    """Archivos de imagen en config/referencias/ (ordenados). Vacio si no hay carpeta."""
    if not REFERENCIAS_DIR.exists():
        return []
    return sorted(p for p in REFERENCIAS_DIR.iterdir()
                  if p.is_file() and p.suffix.lower() in REF_EXTS)


def _mime_de(path: Path) -> str:
    return {".jpg": "image/jpeg", ".jpeg": "image/jpeg",
            ".png": "image/png", ".webp": "image/webp"}.get(path.suffix.lower(), "image/png")


def subir_referencia(api_key: str, path: Path) -> Optional[str]:
    """Sube UNA referencia a Kie (File Upload API) y regresa su fileUrl. None si falla (avisa)."""
    try:
        raw = path.read_bytes()
        if len(raw) > MAX_REF_BYTES:
            print(f"   ⚠️  La referencia {path.name} pesa más de 10MB; la salto.")
            return None
        data_uri = f"data:{_mime_de(path)};base64," + base64.b64encode(raw).decode("ascii")
        headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
        payload = {"base64Data": data_uri, "uploadPath": "images/carrusel-refs", "fileName": path.name}
        r = requests.post(KIE_FILE_UPLOAD, headers=headers, json=payload, timeout=60)
        r.raise_for_status()
        data = r.json()
        d = data.get("data") or {}
        url = d.get("fileUrl") or d.get("downloadUrl") or d.get("url")
        if url:
            return url
        print(f"   ⚠️  No pude subir la referencia {path.name}: {data.get('msg', data)}")
    except Exception as e:
        print(f"   ⚠️  Error subiendo la referencia {path.name}: {e}")
    return None


def subir_referencias(api_key: str) -> List[str]:
    """Sube TODAS las referencias de config/referencias/ a Kie y regresa sus URLs FRESCAS (expiran ~24h,
    por eso se suben en cada corrida). Si una falla, avisa y CONTINUA; nunca bloquea la generacion."""
    refs = listar_referencias()
    if not refs:
        return []
    print(f"   🖼️  Subiendo {len(refs)} referencia(s) de estilo a Kie…")
    urls = [u for u in (subir_referencia(api_key, p) for p in refs) if u]
    if urls:
        print(f"   ✅ {len(urls)} referencia(s) del usuario listas como guía visual.")
    else:
        print("   ⚠️  No se pudo subir ninguna referencia; sigo sin ellas.")
    return urls


def ensamblar_image_input(cover_url: Optional[str], ref_urls: List[str]) -> List[str]:
    """Arma la lista image_input (max 8): la PORTADA siempre primera (si hay molde), luego las
    referencias. Si portada+refs excede 8, recorta referencias."""
    imgs = ([cover_url] if cover_url else []) + list(ref_urls or [])
    return imgs[:MAX_IMAGE_INPUT]


def parse_carrusel(bundle_path: Path) -> Optional[List[Dict]]:
    """
    Lee carrusel.md y extrae las slides.

    Formato esperado (una slide = encabezado + bloque de texto entre ```):
        ### SLIDE 1 - Titulo del gancho
        ```
        Texto que va en la slide.
        ```
    """
    carrusel_file = bundle_path / "carrusel.md"
    if not carrusel_file.exists():
        print(f"❌ No encontre {carrusel_file}")
        print("   Este archivo lo escribe la skill con el copy del carrusel.")
        return None

    content = carrusel_file.read_text(encoding="utf-8")
    # Limpia caracteres invisibles que rompen el parseo (p.ej. zero-width space).
    content = content.replace("​", "").replace("﻿", "")

    # Acepta "LAMINA"/"SLIDE" (con o sin acento), guion normal o largo (- – —),
    # y el bloque ``` con o sin etiqueta de lenguaje (```text, etc.).
    pattern = r'###\s+(?:L[AÁ]MINA|SLIDE)\s+(\d+)\s*[-–—]\s*([^\n]+?)\s*\n```[^\n]*\n(.*?)\n```'
    matches = list(re.finditer(pattern, content, re.DOTALL | re.IGNORECASE))

    slides = []
    for m in matches:
        slides.append({
            "number": int(m.group(1)),
            "title": m.group(2).strip(),
            "content": m.group(3).strip(),
        })
    slides.sort(key=lambda s: s["number"])

    if not slides:
        print("❌ No pude extraer slides de carrusel.md.")
        print("   Revisa que cada slide tenga el formato '### SLIDE N - Titulo' + bloque ```.")
        return None

    print(f"   ✅ {len(slides)} slides encontradas")
    return slides


def slide_role(num: int, total: int) -> str:
    """Gancho (primera) / Valor (medias) / Recompensa (ultima)."""
    if num == 1:
        return "gancho"
    if num == total:
        return "recompensa"
    return "valor"


ELEMENTOS_SERIE_VALIDOS = {"numero", "badge", "barra", "numero+flecha-footer"}


def elemento_serie_de(marca: Dict) -> str:
    """Convencion de serie elegida por el usuario (modelada de sus referencias).
    Default 'numero' (n/total discreto abajo-derecha) si falta o es invalida.
    UNA sola convencion por carrusel, con posicion fija e identica en todas las slides."""
    e = str(marca.get("elemento_serie", "numero")).strip().lower()
    return e if e in ELEMENTOS_SERIE_VALIDOS else "numero"


def numero_serie_instr(num: int, total: int, elemento: str = "numero", hay_refs: bool = False) -> str:
    """Instruccion del UNICO elemento de serie del carrusel. El texto es IDENTICO en todas las
    slides (solo cambia el valor n/total) para minimizar la variacion entre imagenes: misma
    posicion, mismo tamano, mismo tratamiento en toda la serie.

    MARCADOR CONSISTENTE aun CON referencias (hay_refs): las slides se generan por separado (en
    paralelo), asi que "sigue la convencion de las refs" NO basta — cada slide elige por su cuenta y
    el marcador DERIVA (una slide lo pone en un ovalo arriba, otra en una pastilla abajo, otra en un
    engrane). Por eso, aunque haya referencias, aqui se CLAVA UNA sola convencion FIJA, concreta e
    IDENTICA en las N slides: misma forma, mismo tamano, misma POSICION y mismo color/tipografia. Las
    referencias informan el ESTILO del marcador (numero simple vs badge, tratamiento a mano), pero esa
    eleccion se toma UNA vez y se redacta byte-identica en cada prompt (solo cambia "n/total"). Sin
    referencias, el usuario modela su convencion via elemento_serie ('numero'|'badge'|'barra'|
    'numero+flecha-footer'), tambien clavada e identica en toda la serie."""
    if hay_refs:
        # Convencion FIJA modelada del estilo de las referencias (numero de progreso simple con trazo a
        # mano), clavada identica en las N slides. Se veta explicitamente encerrarlo en ovalo/pastilla/
        # engrane: son justo las formas en que derivaba entre slides. El texto es byte-identico salvo el
        # valor "n/total" (que refleja el avance), para que N generaciones independientes lo repitan igual.
        return (f'MARCADOR DE SERIE (ancla fija): numero "{num}/{total}" SIEMPRE en la ESQUINA SUPERIOR '
                f'DERECHA, pequeno (folio de pagina), color de acento, trazo a mano debajo. Numero simple, SIN '
                f'recuadro/pastilla/badge/circulo/ovalo/engrane. IDENTICO en las {total} slides — MISMO tamano '
                f'(ni mas grande ni mas chico entre slides), forma, posicion, tipografia, color; lo UNICO que '
                f'cambia es el numero.')
    if elemento == "badge":
        return (f'SERIE: numero "{num}/{total}" en una pastilla/badge en la ESQUINA SUPERIOR DERECHA, '
                f'mismo estilo, tipografia, color, posicion y tamano en toda la serie.')
    if elemento == "barra":
        return (f'SERIE: en el FOOTER, barra de progreso horizontal con "{num}/{total}" al lado, mismo estilo, '
                f'grosor, tipografia, color y posicion en toda la serie (refleja el avance {num} de {total}).')
    if elemento == "numero+flecha-footer":
        base_desliza = ('con una flecha "SWIPE ->" pequena INTEGRADA en el footer (nunca flotando a media slide)'
                        if num < total else 'sin flecha de deslizar (es la ultima)')
        return (f'SERIE: numero "{num}/{total}" en la ESQUINA INFERIOR DERECHA, pequeno y discreto, misma '
                f'tipografia, color y posicion en toda la serie, {base_desliza}.')
    return (f'SERIE: numero "{num}/{total}" en la ESQUINA INFERIOR DERECHA, pequeno y discreto (como el folio '
            f'de una pagina), MISMO TAMANO EXACTO en las {total} slides (ni mas grande ni mas chico entre una y '
            f'otra), misma tipografia, color y posicion en toda la serie.')


def extras_prohibidos(elemento_serie: str, hay_refs: bool = False) -> str:
    """Prohibe los recursos que NO son parte de la anatomia default (mas elementos = mas deriva de
    posicion y mas typos). Solo entran cuando el usuario los trae en sus referencias; la skill nunca
    los agrega sola. Se omite de la lista el que sea la convencion de serie elegida, para no contradecirla.

    JERARQUIA referencias > defaults: CON referencias adjuntas (hay_refs) esta lista fija NO manda —
    el usuario ya trajo su lenguaje visual; se sigue lo que muestran las referencias y solo se veta
    agregar cosas que ELLAS no usan."""
    if hay_refs:
        swipe = ("" if elemento_serie == "numero+flecha-footer"
                 else ' NUNCA flechas "desliza ->"/"DESLIZA" aunque la ref las traiga (salen inconsistentes).')
        return ("Usa SOLO recursos de serie/decoracion que aparezcan en las REFERENCIAS (numero, badge, barra, "
                "dots): no inventes otros. Una sola convencion identica en toda la serie." + swipe)
    extras = ["numeros fantasma", "barras de progreso", "badges o pastillas",
              "tarjetas comparativas", "stickers o washi tape", "footer de swipe"]
    if elemento_serie == "badge":
        extras.remove("badges o pastillas")
    elif elemento_serie == "barra":
        extras.remove("barras de progreso")
    elif elemento_serie == "numero+flecha-footer":
        extras.remove("footer de swipe")
    return ("NO agregues por tu cuenta " + ", ".join(extras) +
            ": no son parte de la anatomia default (solo si el usuario los trae en sus referencias).")


def contar_bullets(body: str) -> int:
    """Cuenta las lineas no vacias del cuerpo = cuantos bullets/ideas trae la slide."""
    return len([ln for ln in (body or "").splitlines() if ln.strip()])


def slides_copy_corto(slides: List[Dict], total: int, densidad: str) -> List[int]:
    """Densidad 'completa' = mini-guia real: cada slide de VALOR deberia traer 3-5 bullets. Devuelve
    los numeros de las slides de valor cuyo copy viene CORTO (<3 bullets) para avisar en el dry-run
    (el copy se escribe segun la densidad; si quedo corto para 'completa', hay que reescribirlo)."""
    if densidad != "completa":
        return []
    cortas = []
    for s in slides:
        if slide_role(s["number"], total) == "valor" and contar_bullets(s.get("content", "")) < 3:
            cortas.append(s["number"])
    return sorted(cortas)


def tratamiento_visual_instr(tratamiento: str) -> str:
    """Instruccion de COMO se integra el elemento visual. Redactada en positivo (lo que SI debe pasar)
    + veto explicito, porque los modelos obedecen mejor lo generativo que la sola prohibicion.
    El visual SIEMPRE vive dentro de la composicion, jamas como bloque recortado tipo diapositiva."""
    if tratamiento == "escena-fotografica":
        positivo = ("el producto/objeto vive DENTRO de una escena fotografica real (sobre una superficie, luz natural "
                    "y sombras suaves que lo anclan al mismo fondo); el texto va sobre las zonas limpias de esa foto")
    elif tratamiento == "graficos":
        positivo = ("el visual es un ESQUEMA/DIAGRAMA educativo (iconos simples, flechas, etiquetas y anotaciones) con "
                    "la misma paleta y trazo, sin recuadro propio, conectado al texto (estilo carrusel educativo)")
    else:
        positivo = ("la ilustracion/caricatura esta FUNDIDA con el diseño: mismo fondo, paleta y trazo, sin recuadro "
                    "propio, parte de la composicion")
    return ("VISUAL: " + positivo + ". Integrado, sin marcos ni bordes duros. PROHIBIDO: foto recortada en rectangulo, "
            "collage pegado, o layout 'texto a un lado + imagen al otro' tipo diapositiva de PowerPoint.")


def anatomia_valor(densidad: str) -> str:
    """Como se resuelve el cuerpo de una slide de valor segun la densidad. La densidad regula CUANTA
    info por slide; la estetica la pone la marca, no esta funcion."""
    if densidad == "aireada":
        return "- AIREADA: 1-2 bullets muy cortos (o visual protagonista con 0-1 bullet). Mucho aire, una idea respirando."
    if densidad == "completa":
        return ("- MINI-GUIA: 3-5 bullets con punto (keyword en negrita), opcional 1 anotacion. El TEXTO manda, en "
                "jerarquia clara con AIRE entre bloques; el visual es pequeno (ambiente o esquina), NUNCA dominante.")
    return "- MEDIA: 2-3 bullets cortos con punto (keyword en negrita). Equilibrio informacion/aire, escaneable."


def presupuesto_texto(densidad: str) -> str:
    """Presupuesto de texto POR DENSIDAD (v2.3): 'completa' es una mini-guia real (mas texto), no se
    capa a ~30 palabras. Se mantiene el aviso anti-typos en todas."""
    if densidad == "completa":
        return ("- Texto (MINI-GUIA): titulo <=8, subtitulo <=12, 3-5 bullets <=10 palabras + opcional 1 anotacion; "
                "bien escrito, sin faltas, alto contraste.")
    if densidad == "aireada":
        return ("- Texto ESTRICTO (AIREADA): titulo <=8, subtitulo <=10, 0-2 bullets <=7 palabras (~30). "
                "Mucho aire; menos texto = menos errores.")
    return ("- Texto ESTRICTO (MEDIA): titulo <=8, subtitulo <=10, 2-3 bullets <=7 palabras (~30). "
            "Cero parrafos; mas texto y mas elementos = mas deriva y mas errores.")


def anatomia_header(densidad: str) -> str:
    """Encabezado del bloque de anatomia, segun densidad."""
    if densidad == "completa":
        return "ANATOMIA (MINI-GUIA: el TEXTO manda, jerarquia clara con aire entre bloques):"
    return "ANATOMIA (maximo 5 elementos, ~30 palabras — equilibrio, no espectaculo):"


# Rol interno -> como se nombra al modelar por rol contra la referencia.
ROL_A_TEXTO = {"gancho": "la PORTADA", "valor": "las slides de VALOR (las de en medio)",
               "recompensa": "el CIERRE / CTA"}


def bloque_referencias(ancla: bool, n_refs: int, sin_molde: bool, role: str = "valor") -> str:
    """Texto que explica los ROLES de las imagenes adjuntas (image_input):
    - ancla: la PRIMERA imagen es la portada-molde (solo tokens de estilo, no composicion/sujeto).
    - n_refs: hay N referencias del usuario adjuntas (modelar su lenguaje visual, adaptado a la marca).
    - sin_molde: el carrusel corre sin molde-portada -> refuerza la consistencia de serie por texto.
    - role: el rol de ESTA slide (gancho/valor/recompensa) para modelar ROL->ROL contra la referencia."""
    partes = []
    if ancla:
        partes.append(
            "MOLDE: la 1a imagen adjunta es la PORTADA. Copia solo sus TOKENS de estilo (paleta, tipografia, luz, "
            "texturas). NO su composicion/layout, NI su sujeto, NI el @usuario de su pie: esta slide sigue SU "
            "estructura (abajo), su propio sujeto, y su pie es el que diga esa estructura.")
    if n_refs > 0:
        cual = "Las DEMAS imagenes adjuntas" if ancla else "Las imagenes adjuntas"
        rol_txt = ROL_A_TEXTO.get(role, "las slides de VALOR (las de en medio)")
        partes.append(
            f"{cual} son REFERENCIAS del usuario. Modela sus PRINCIPIOS (composicion, densidad, jerarquia, tipo de "
            "elementos, serie/footer, tipografia, energia) POR ROL: portada->portada, medias->valor, ultima->cierre; "
            f"esta slide es {rol_txt}. NO copies su layout, textos, @/handle/URL, ilustraciones, logos ni COLORES: manda "
            "la PALETA del usuario (solo se modela la tipografia). Pieza ORIGINAL. Las capturas traen la UI de Instagram "
            "(avatares, flechas, like/comentar, historias, puntos): NUNCA la dibujes; el diseño ocupa TODO el lienzo.")
    if sin_molde:
        partes.append("SERIE: manten identica paleta, tipografias y tratamiento en TODAS las slides.")
    return ("\n".join(partes) + "\n\n") if partes else ""


def _saturacion_hex(hexcol: str) -> int:
    """Aprox de 'que tan vivo' es un color: max-min de sus canales RGB (0 = gris/negro/blanco)."""
    h = str(hexcol or "").lstrip("#")
    if len(h) != 6:
        return 0
    try:
        r, gg, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    except ValueError:
        return 0
    return max(r, gg, b) - min(r, gg, b)


def color_acento(colores: Dict) -> str:
    """El ACENTO (el color que RESALTA) = el mas vivo entre primario y secundario. Robusto ante configs
    donde el vibrante es el 'primario' (naranja/amarillo) o donde lo es el 'secundario' (morado). Antes
    se asumia siempre 'secundario' -> el marcador/acento salia oscuro en marcas con primario vibrante."""
    prim = colores.get("primario", "#111111")
    sec = colores.get("secundario", "#6F00FF")
    return prim if _saturacion_hex(prim) >= _saturacion_hex(sec) else sec


def build_prompt(slide: Dict, role: str, marca: Dict, total: int,
                 ancla: bool = False, n_refs: int = 0, sin_molde: bool = False) -> str:
    """Construye un BRIEF de director creativo (lean) para una slide — descriptivo y POSITIVO, no una
    pila de prohibiciones: los modelos de imagen se saturan con 'tag soup' (guia oficial de nano-banana:
    'act like a creative director'). total = numero de slides; ancla = la 1a imagen adjunta es la
    portada-molde; n_refs = referencias del usuario adjuntas.

    Si el prompt excede el umbral seguro (PROMPT_SAFETY_LIMIT bytes) recorta SOLO estilo/tipografia
    (los de menor prioridad) — nunca el COPY — y re-mide. Si aun asi no cabe, lanza PromptDemasiadoLargo."""
    colores = marca.get("colores", {})
    c_sec = color_acento(colores)  # ACENTO real (el color mas vivo), no siempre 'secundario'
    c_fondo = colores.get("fondo", "#FFFFFF")
    c_texto = colores.get("texto", "#111111")
    tipografia_full = str(marca.get("tipografia", "sans-serif bold, limpia y moderna")).strip().rstrip(".")
    estilo_full = str(marca.get("estilo_visual", "ilustracion flat minimalista, alto contraste")).strip()
    # @ REAL del usuario o None si esta vacio/placeholder. Si es None, NINGUN prompt menciona @/usuario.
    handle = instagram_usuario_real(marca)
    num = slide["number"]
    title = slide["title"]
    body = slide["content"]
    hay_refs = n_refs > 0

    # Nota de referencias: SOLO estilo VISUAL (positiva y corta; nada de "tag soup").
    if hay_refs:
        ref_nota = ("\n\nLas imagenes adjuntas son tu REFERENCIA DE ESTILO: toma de ellas SOLO la estetica "
                    "(composicion, tipografia, tratamiento, aire) y aplicala con la PALETA y el texto de arriba. "
                    "Diseño full-bleed: ocupa TODO el lienzo, limpio hasta el borde.")
        if ancla:
            ref_nota += " La 1a imagen es la PORTADA de esta serie: conserva su mismo look de estilo."
    else:
        ref_nota = ""

    # El @ del usuario va SOLO en portada y cierre, y solo si es real (nunca un placeholder).
    handle_portada = (f'\n- Abajo, el usuario "{handle}" pequeno y discreto en el footer.' if handle else "")
    handle_cierre = (f'\n- El usuario "{handle}" integrado en el footer.' if handle else "")

    def render(estilo: str, tipografia: str) -> str:
        cabecera = (
            f"Slide vertical 4:5 (mas alto que ancho) para un carrusel de Instagram: serie de {total} slides, "
            f"esta es la numero {num}.\n"
            f"Estilo visual: {estilo}. Tipografia: {tipografia}.\n"
            f"Paleta: fondo {c_fondo}, texto {c_texto}, acento {c_sec} (el acento resalta UNA palabra clave del "
            f"titulo y el numero de serie).\n"
            f"Composicion limpia, ordenada y con aire. Texto en ESPAÑOL, nitido y legible, EXACTAMENTE como se da."
            f"{ref_nota}")
        marcador = (f'\n- Arriba a la derecha, el numero "{num}/{total}" pequeno en {c_sec}, del mismo tamaño '
                    f"y estilo en todas las slides.")
        if role == "gancho":
            return (f"{cabecera}\n\n"
                    "PORTADA que para el scroll:\n"
                    f'- Titular GRANDE (el mayor peso visual), con una palabra clave en {c_sec}: "{title}"\n'
                    f'- Debajo, un subtitulo mas chico: "{body}"\n'
                    "- Una ilustracion protagonista, integrada en el estilo de la marca, que refuerza la idea."
                    f"{handle_portada}{marcador}\n")
        if role == "valor":
            return (f"{cabecera}\n\n"
                    "SLIDE DE VALOR:\n"
                    f'- Titulo arriba, con una palabra clave en {c_sec}: "{title}"\n'
                    f'- Debajo, el contenido como bullets legibles, tal cual:\n"{body}"\n'
                    "- Una ilustracion de apoyo sobre el tema de esta slide, a un lado o de fondo, en armonia con el texto.\n"
                    "- El pie de la slide va COMPLETAMENTE VACIO: sin @usuario, sin firma, sin texto de ningun tipo "
                    "(el @ aparece SOLO en la portada y en el cierre)."
                    f"{marcador}\n")
        # cierre / recompensa
        return (f"{cabecera}\n\n"
                "CIERRE (invitacion a actuar):\n"
                f'- Titulo arriba, con una palabra clave en {c_sec}: "{title}"\n'
                f'- El llamado va DENTRO de un recuadro/panel integrado al diseño, con la palabra clave en el mayor peso: "{body}"\n'
                "- El titulo y el llamado son el UNICO texto de la slide; una ilustracion calida los acompaña."
                f"{handle_cierre}{marcador}\n")

    # --- Presupuesto de tamano: nunca mandamos a Kie un prompt que sabemos que fallaria. ---
    prompt = render(estilo_full, tipografia_full)
    if len(prompt.encode("utf-8")) <= PROMPT_SAFETY_LIMIT:
        return prompt
    # Excede: recorta el estilo_visual (menor prioridad), luego la tipografia. Con referencias el estilo
    # lo cargan las imagenes adjuntas, asi que su TEXTO puede recortarse mucho sin perder el look.
    for est_max in (600, 400, 250, 150, 80, 40, 20):
        prompt = render(_recortar(estilo_full, est_max), tipografia_full)
        if len(prompt.encode("utf-8")) <= PROMPT_SAFETY_LIMIT:
            return prompt
    for tip_max in (120, 60, 30, 12):
        prompt = render(_recortar(estilo_full, 20), _recortar(tipografia_full, tip_max))
        if len(prompt.encode("utf-8")) <= PROMPT_SAFETY_LIMIT:
            return prompt
    # Ultimo recurso (caso patologico de estilo/tipografia gigantes): ambos al minimo.
    prompt = render(_recortar(estilo_full, 8), _recortar(tipografia_full, 8))
    if len(prompt.encode("utf-8")) <= PROMPT_SAFETY_LIMIT:
        return prompt
    ch, by = medir_prompt(prompt)
    raise PromptDemasiadoLargo(
        f"El texto de la slide {num} es demasiado largo para generarla de una sola vez "
        f"({ch:,} caracteres / {by:,} bytes; el maximo seguro son {PROMPT_SAFETY_LIMIT:,} bytes). "
        f"Acorta el copy de esta slide (o el estilo visual de tu marca) y vuelve a intentar.")


def create_task(api_key: str, prompt: str, image_input: Optional[List[str]] = None) -> Optional[str]:
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    input_params = {
        "prompt": prompt,
        "aspect_ratio": ASPECT_RATIO,
        "resolution": RESOLUTION,
        "output_format": FORMAT,
    }
    if image_input:  # imagenes de referencia (ej. la portada como molde de estilo)
        input_params["image_input"] = image_input
    payload = {"model": MODEL, "input": input_params}
    try:
        r = requests.post(KIE_CREATE_TASK, headers=headers, json=payload, timeout=30)
        r.raise_for_status()
        data = r.json()
        if data.get("code") == 200:
            task_id = (data.get("data") or {}).get("taskId")
            if task_id:
                return task_id
        print(f"   ❌ Kie AI no devolvio taskId: {data}")
    except Exception as e:
        print(f"   ❌ Error creando tarea: {e}")
        if hasattr(e, "response") and getattr(e, "response", None) is not None:
            print(f"      {e.response.text}")
    return None


def poll_task(api_key: str, task_id: str, label: str = "") -> Optional[str]:
    headers = {"Authorization": f"Bearer {api_key}"}
    for attempt in range(MAX_POLL_ATTEMPTS):
        try:
            r = requests.get(KIE_RECORD_INFO, headers=headers,
                             params={"taskId": task_id}, timeout=30)
            r.raise_for_status()
            data = r.json().get("data") or {}
            state = data.get("state", "")
            if state == "success":
                result = json.loads(data.get("resultJson", "{}"))
                urls = result.get("resultUrls", [])
                return urls[0] if urls else None
            if state == "fail":
                print(f"   ❌ {label} fallo: {data.get('failMsg', 'error desconocido')}")
                return None
            if attempt % 6 == 0:
                print(f"   {label} {state}... ({attempt * POLL_INTERVAL}s)")
            time.sleep(POLL_INTERVAL)
        except Exception as e:
            print(f"   ⚠️  {label} error en polling: {e}")
            time.sleep(POLL_INTERVAL)
    print(f"   ⏱️  {label} sigue en cola en Kie AI (se agotó la espera local). La imagen puede "
          f"terminar allá; vuelve a intentar esa slide con --regenerar.")
    return None


def download(url: str, path: Path) -> bool:
    try:
        r = requests.get(url, stream=True, timeout=60)
        r.raise_for_status()
        with open(path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"   ❌ Error descargando: {e}")
        return False


def editar_slide(api_key: str, slides_dir: Path, num: int, instruccion: str) -> bool:
    """Corrige UNA slide EDITANDOLA (no regenerando): sube la imagen actual + una instruccion chica y
    guarda el resultado encima. nano-banana-pro edita conservando el resto (texto en español, colores,
    tipografia, layout). Mas barato/rapido/fiable que regenerar desde cero (guia oficial de nano-banana:
    'si la imagen esta 80% bien, NUNCA la regeneres desde cero — refinala')."""
    path = slides_dir / f"slide-{num:02d}.png"
    if not path.exists():
        print(f"❌ No existe {path.name} para editar.")
        return False
    print(f"   ✏️  Editando slide {num}: {instruccion}")
    url = subir_referencia(api_key, path)
    if not url:
        print(f"   ❌ No pude subir la slide {num} para editar.")
        return False
    prompt = (f"Edita esta imagen de un carrusel de Instagram. Cambio pedido: {instruccion}. "
              "Deja TODO lo demas EXACTAMENTE igual: el mismo texto en español (sin re-escribirlo), los "
              "mismos colores, la misma tipografia, la misma composicion y el mismo numero de serie. "
              "No regeneres la escena; solo aplica ese cambio.")
    tid = create_task(api_key, prompt, image_input=[url])
    out_url = poll_task(api_key, tid, f"[editar slide {num}]") if tid else None
    if out_url and download(out_url, path):
        print(f"   ✅ Slide {num} editada -> {path.name}")
        return True
    print(f"   ❌ No se pudo editar la slide {num}.")
    return False


def main():
    ap = argparse.ArgumentParser(description="Genera un carrusel de Instagram con Kie AI.")
    ap.add_argument("bundle", help="Carpeta del carrusel (contiene carrusel.md)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Solo muestra el brief y los prompts, no genera imagenes (no gasta).")
    ap.add_argument("--regenerar", type=str, default=None,
                    help="Regenera solo estas slides, ej: '2,4'")
    ap.add_argument("--editar", type=int, default=None,
                    help="Corrige UNA slide EDITANDOLA (no regenera). Requiere --instruccion. Ej: --editar 4")
    ap.add_argument("--instruccion", type=str, default=None,
                    help='Que cambiar en la slide a editar. Ej: "quita el @usuario del footer"')
    args = ap.parse_args()

    bundle_path = Path(args.bundle).expanduser().resolve()
    bundle_path.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}\nFABRICA DE CARRUSELES\n{'='*60}")
    print(f"📦 Carpeta: {bundle_path}\n")

    # Modo EDICION: corrige una slide existente sin regenerar (no necesita marca ni carrusel.md).
    if args.editar is not None:
        if not args.instruccion:
            sys.exit('❌ --editar requiere --instruccion "que cambiar". Ej: --editar 4 --instruccion "quita el @usuario"')
        ok = editar_slide(get_api_key(), slides_dir_for(bundle_path), args.editar, args.instruccion)
        sys.exit(0 if ok else 1)

    marca = load_marca()
    print(f"🎨 Marca: {marca.get('negocio', '(sin definir)')} | {marca.get('instagram_usuario', '')}\n")

    slides = parse_carrusel(bundle_path)
    if not slides:
        sys.exit(1)

    total = len(slides)
    cover_num = 1 if any(s["number"] == 1 for s in slides) else slides[0]["number"]
    only = None
    if args.regenerar:
        try:
            only = {int(x.strip()) for x in args.regenerar.split(",") if x.strip()}
        except ValueError:
            print('❌ --regenerar espera números separados por coma, ej: "2,4"')
            sys.exit(1)
        validas = {s["number"] for s in slides}
        faltan = sorted(only - validas)
        if faltan:
            print(f"❌ Estas slides no existen en el carrusel: {faltan}. "
                  f"El carrusel tiene {total} slides (1 a {total}).")
            sys.exit(1)

    # Brief
    print(f"\n{'='*60}\nBRIEF\n{'='*60}")
    print(f"Total slides: {total} | Formato: 1080x1350 (4:5)\n")
    for s in slides:
        print(f"  Slide {s['number']} [{slide_role(s['number'], total)}]: {s['title']}")

    print(f"Densidad de contenido: {densidad_de(marca)}")

    # Referencias del usuario (config/referencias/): cuantas hay. En dry-run solo se cuentan; en la
    # generacion real se suben frescas a Kie (sus URLs expiran ~24h).
    n_refs_local = len(listar_referencias())
    molde_on = molde_activo(marca, n_refs_local > 0)
    print(f"Molde de portada: {'ON' if molde_on else 'OFF'} (modo {molde_de(marca)}"
          f"{f', {n_refs_local} referencia(s) del usuario' if n_refs_local else ''})")

    # Aviso: densidad 'completa' pero el copy viene corto (el copy se escribe SEGUN la densidad vigente).
    cortas = slides_copy_corto(slides, total, densidad_de(marca))
    if cortas:
        print(f"⚠️  Densidad COMPLETA pero el copy viene corto en la(s) slide(s) {cortas}: "
              f"'completa' pide 3-5 bullets por slide de valor. Reescribe el copy antes de generar.")

    # Aviso: sin @ de Instagram real (vacio o placeholder) -> las slides saldran SIN @ (jamas placeholder).
    if instagram_usuario_real(marca) is None:
        print("⚠️  No tienes tu @ de Instagram configurado — las slides saldrán sin tu @. "
              "Dímelo y lo agrego a tu marca.")

    def _params_prompt(is_cover: bool, molde_on: bool, n_refs_disponibles: int):
        """Devuelve (ancla, n_refs, sin_molde) para build_prompt segun molde e is_cover."""
        if molde_on:
            if is_cover:
                return (False, min(n_refs_disponibles, MAX_IMAGE_INPUT), False)
            return (True, min(n_refs_disponibles, MAX_IMAGE_INPUT - 1), False)
        return (False, min(n_refs_disponibles, MAX_IMAGE_INPUT), True)

    if args.dry_run:
        if n_refs_local:
            print(f"Referencias en config/referencias/: {n_refs_local} (se subirían a Kie al generar).")
        if not molde_on:
            print("Sin molde: las slides se generarían TODAS en paralelo desde el inicio.")
        # Tamano de cada prompt vs el limite de Kie. Asi el bug de "prompt demasiado largo" queda
        # atrapado en el dry-run (que no gasta) para siempre.
        print(f"\n{'='*60}\nTAMANO DE PROMPTS (limite Kie {KIE_PROMPT_LIMIT:,} · umbral seguro {PROMPT_SAFETY_LIMIT:,} bytes)\n{'='*60}")
        prompts = {}
        hay_error = False
        for s in slides:
            role = slide_role(s["number"], total)
            ancla, n_refs, sin_molde = _params_prompt(s["number"] == cover_num, molde_on, n_refs_local)
            try:
                p = build_prompt(s, role, marca, total, ancla=ancla, n_refs=n_refs, sin_molde=sin_molde)
                prompts[s["number"]] = (role, p)
                ch, by = medir_prompt(p)
                estado = "✓" if by <= PROMPT_SAFETY_LIMIT else "✗ SE PASA"
                print(f"  Slide {s['number']} ({role}): {ch:,} chars / {by:,} bytes / {KIE_PROMPT_LIMIT:,} {estado}")
            except PromptDemasiadoLargo as e:
                hay_error = True
                print(f"  Slide {s['number']} ({role}): ✗ {e}")
        print(f"\n(dry-run) Prompts completos que se enviarian:\n")
        for s in slides:
            if s["number"] in prompts:
                role, p = prompts[s["number"]]
                print(f"\n--- Slide {s['number']} ({role}) ---")
                print(p)
        if hay_error:
            print("\n⚠️  Una o más slides no caben en el presupuesto: acorta su copy antes de generar.")
        print("\n(dry-run) No se genero nada. Quita --dry-run para generar.")
        return

    api_key = get_api_key()
    slides_dir = slides_dir_for(bundle_path)
    slides_dir.mkdir(exist_ok=True)

    manifest_path = slides_dir / "manifest.json"
    start = time.time()
    generated = []

    # Subir las referencias del usuario a Kie (frescas; expiran ~24h). Nunca bloquea la generacion.
    ref_urls = subir_referencias(api_key) if n_refs_local else []

    def procesar(slide_obj, role, image_input, ancla, n_refs, sin_molde, permitir_fallback):
        """Genera UNA slide (crear tarea -> esperar -> opcional fallback sin molde -> descargar)."""
        n = slide_obj["number"]
        try:
            prompt = build_prompt(slide_obj, role, marca, total,
                                  ancla=ancla, n_refs=n_refs, sin_molde=sin_molde)
        except PromptDemasiadoLargo as e:
            print(f"   ❌ Slide {n}: {e}")
            return None
        tid = create_task(api_key, prompt, image_input=(image_input or None))
        url = poll_task(api_key, tid, f"[Slide {n}]") if tid else None
        if not url and permitir_fallback:
            # La URL de la portada-molde pudo expirar (URLs de Kie viven ~24h). Reintenta 1 vez SIN molde.
            print(f"   ⚠️  Slide {n} falló con el molde. La portada de referencia ya expiró "
                  f"(las URLs de Kie viven ~24h); genero sin molde…")
            imgs2 = ref_urls[:MAX_IMAGE_INPUT]
            try:
                prompt2 = build_prompt(slide_obj, role, marca, total,
                                       ancla=False, n_refs=len(imgs2), sin_molde=True)
            except PromptDemasiadoLargo as e:
                print(f"   ❌ Slide {n} (sin molde): {e}")
                return None
            tid2 = create_task(api_key, prompt2, image_input=(imgs2 or None))
            url = poll_task(api_key, tid2, f"[Slide {n} sin molde]") if tid2 else None
            if url:
                print(f"   ℹ️  Generé la slide {n} sin molde. Si quieres consistencia total, "
                      f"regenera también la slide 1 (--regenerar \"1\").")
        if url and download(url, slides_dir / f"slide-{n:02d}.png"):
            print(f"   ✅ Slide {n} -> slide-{n:02d}.png")
            return {"id": n, "role": role, "title": slide_obj["title"],
                    "file": f"slide-{n:02d}.png", "url": url}
        print(f"   ❌ Slide {n} sin resultado")
        return None

    if molde_on:
        # --- FLUJO CON MOLDE: la PORTADA primero (ancla de estilo), luego el resto en paralelo. ---
        cover_url = None
        regen_cover = (not only) or (cover_num in only)
        if regen_cover:
            print(f"\n{'='*60}\nFASE 1 — PORTADA (molde de estilo)\n{'='*60}\n")
            cs = next(s for s in slides if s["number"] == cover_num)
            cover_imgs = ensamblar_image_input(None, ref_urls)  # la portada usa solo referencias
            res = procesar(cs, slide_role(cover_num, total), cover_imgs,
                           ancla=False, n_refs=len(cover_imgs), sin_molde=False, permitir_fallback=False)
            if res:
                generated.append(res)
                cover_url = res["url"]
            else:
                print("   ⚠️  No se pudo generar la portada; las demas iran sin molde.")
        else:
            # regenerando solo slides internas: recuperar la URL de la portada del manifest
            if manifest_path.exists():
                try:
                    prev = json.loads(manifest_path.read_text(encoding="utf-8"))
                    cover_url = next((l.get("url") for l in manifest_slides(prev) if l.get("id") == cover_num), None)
                except Exception:
                    cover_url = None

        rest = [s for s in slides if s["number"] != cover_num and (not only or s["number"] in only)]
        if rest:
            usa_molde = bool(cover_url)
            slide_imgs = ensamblar_image_input(cover_url, ref_urls)
            n_refs_slide = len(slide_imgs) - (1 if usa_molde else 0)
            print(f"\n{'='*60}\nFASE 2 — {len(rest)} slides en paralelo"
                  f"{' (con molde de la portada)' if usa_molde else ' (sin molde)'}\n{'='*60}\n")
            with ThreadPoolExecutor(max_workers=len(rest)) as ex:
                futures = [ex.submit(procesar, s, slide_role(s["number"], total), slide_imgs,
                                     usa_molde, n_refs_slide, not usa_molde, usa_molde) for s in rest]
                for fut in as_completed(futures):
                    res = fut.result()
                    if res:
                        generated.append(res)
    else:
        # --- FLUJO SIN MOLDE: TODAS las slides en paralelo desde el inicio (bonus de velocidad). ---
        objetivo = [s for s in slides if (not only or s["number"] in only)]
        imgs = ensamblar_image_input(None, ref_urls)
        print(f"\n{'='*60}\n{len(objetivo)} slides en paralelo (sin molde"
              f"{', con referencias del usuario' if ref_urls else ''})\n{'='*60}\n")
        with ThreadPoolExecutor(max_workers=len(objetivo)) as ex:
            futures = [ex.submit(procesar, s, slide_role(s["number"], total), imgs,
                                 False, len(imgs), True, False) for s in objetivo]
            for fut in as_completed(futures):
                res = fut.result()
                if res:
                    generated.append(res)

    if not generated:
        print("\n❌ No se genero ninguna slide. Revisa tu llave y tus creditos de Kie AI.")
        sys.exit(1)

    # Merge con manifest previo (para no perder slides al regenerar solo algunas).
    # Lee la clave nueva "slides" o la vieja "laminas" (retrocompat).
    slides_map = {}
    if manifest_path.exists():
        try:
            for l in manifest_slides(json.loads(manifest_path.read_text(encoding="utf-8"))):
                slides_map[l["id"]] = l
        except Exception:
            pass
    for l in generated:
        slides_map[l["id"]] = l
    slides_all = [slides_map[k] for k in sorted(slides_map)]

    manifest = {
        "generado": datetime.now().isoformat(timespec="seconds"),
        "negocio": marca.get("negocio"),
        "instagram_usuario": marca.get("instagram_usuario"),
        "total": len(slides_all),
        "slides": slides_all,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    elapsed = int(time.time() - start)
    print(f"\n{'='*60}\nLISTO\n{'='*60}")
    print(f"Slides generadas ahora: {len(generated)}")
    print(f"Carpeta: {slides_dir}")
    print(f"Costo aprox: ~${len(generated) * 0.10:.2f} | Tiempo: {elapsed//60}m {elapsed%60}s")
    print(f"\nSiguiente paso: publicar con scripts/publicar.py\n")


if __name__ == "__main__":
    main()
