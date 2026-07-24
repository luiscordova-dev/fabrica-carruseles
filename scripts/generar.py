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

# --- API Kie AI (nano-banana-pro) ---
KIE_API_BASE = "https://api.kie.ai/api/v1/jobs"
KIE_CREATE_TASK = f"{KIE_API_BASE}/createTask"
KIE_RECORD_INFO = f"{KIE_API_BASE}/recordInfo"
MODEL = "nano-banana-pro"
ASPECT_RATIO = "4:5"   # Instagram carrusel (vertical). El encuadre va SOLO por este parametro,
RESOLUTION = "1K"      # nunca en el prompt. 1K (~1024px) basta para IG y es mas rapido/barato que 2K/4K.
FORMAT = "png"
MAX_POLL_ATTEMPTS = 120   # ~10 min por slide: Kie AI a veces encola y tarda varios minutos
POLL_INTERVAL = 5


def get_api_key() -> str:
    key = os.environ.get("KIE_API_KEY") or os.environ.get("KIE_AI_API_KEY")
    if not key:
        print("❌ Falta la llave de Kie AI. Ponla en el .env de la skill como KIE_API_KEY=...")
        print("   (Sigue el walkthrough 01-kie-ai.md si aun no la tienes.)")
        sys.exit(1)
    return key


def load_marca() -> Dict:
    """Carga la marca del usuario. Si no existe, usa valores neutros para no romper."""
    if not MARCA_FILE.exists():
        print(f"⚠️  No encontre {MARCA_FILE}. Usando valores por defecto.")
        print("   Corre el onboarding de la skill para configurar tu marca.")
        return {
            "negocio": "un negocio",
            "tono": "claro y directo",
            "colores": {"primario": "#111111", "secundario": "#6F00FF",
                        "fondo": "#FFFFFF", "texto": "#111111"},
            "tipografia": "sans-serif bold, limpia y moderna",
            "estilo_visual": "ilustracion flat minimalista, alto contraste, formas geometricas simples, sin texturas de acuarela",
            "instagram_usuario": "@tu_usuario",
            "densidad": "media",
        }
    with open(MARCA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


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


TRATAMIENTOS_VISUALES = {"escena-fotografica", "ilustracion"}


def tratamiento_visual_de(marca: Dict) -> str:
    """Como se resuelve el elemento visual: 'escena-fotografica' (producto/objeto real en escena con
    luz y sombras) o 'ilustracion' (dibujo/vector fundido con el diseño). Es un atributo de la ESTETICA
    del usuario. Si el campo no viene, se infiere del estilo_visual; ante empate, 'ilustracion'
    (coincide con el estilo por defecto de la skill)."""
    t = str(marca.get("tratamiento_visual", "")).strip().lower()
    if t in TRATAMIENTOS_VISUALES:
        return t
    estilo = str(marca.get("estilo_visual", "")).lower()
    foto_signals = ["foto", "fotograf", "luz natural", "escena", "producto en primer plano",
                    "editorial", "stock", "primer plano"]
    ilus_signals = ["ilustracion", "ilustración", "flat", "vector", "dibujo", "3d", "render",
                    "acuarela", "grafico", "gráfico", "isometric"]
    foto = sum(1 for s in foto_signals if s in estilo)
    ilus = sum(1 for s in ilus_signals if s in estilo)
    return "escena-fotografica" if foto > ilus else "ilustracion"


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


ELEMENTOS_SERIE_VALIDOS = {"numero", "badge", "barra"}


def elemento_serie_de(marca: Dict) -> str:
    """Convencion de serie elegida por el usuario (modelada de sus referencias).
    Default 'numero' (n/total discreto abajo-derecha) si falta o es invalida.
    UNA sola convencion por carrusel, con posicion fija e identica en todas las slides."""
    e = str(marca.get("elemento_serie", "numero")).strip().lower()
    return e if e in ELEMENTOS_SERIE_VALIDOS else "numero"


def numero_serie_instr(num: int, total: int, elemento: str = "numero") -> str:
    """Instruccion del UNICO elemento de serie del carrusel. El texto es IDENTICO en todas las
    slides (solo cambia el valor n/total) para minimizar la variacion entre imagenes: misma
    posicion, mismo tamano, mismo tratamiento en toda la serie. El DEFAULT es el numero discreto
    abajo-derecha; 'badge' y 'barra' son convenciones alternativas que el usuario puede elegir/modelar
    de sus referencias (una sola por carrusel, siempre en la misma posicion)."""
    if elemento == "badge":
        return (f'ELEMENTO DE SERIE: coloca el numero "{num}/{total}" dentro de una pastilla/badge pequena en la '
                f'ESQUINA SUPERIOR DERECHA, con el MISMO estilo de pastilla, tipografia y color en toda la serie, '
                f'en identica posicion y tamano en cada slide.')
    if elemento == "barra":
        return (f'ELEMENTO DE SERIE: en el FOOTER, una barra de progreso horizontal con el numero "{num}/{total}" '
                f'al lado, con el MISMO estilo, grosor, tipografia y color en toda la serie, en identica posicion '
                f'en cada slide (la barra refleja el avance {num} de {total}).')
    return (f'ELEMENTO DE SERIE: coloca el numero "{num}/{total}" en la ESQUINA INFERIOR DERECHA, '
            f'pequeno y discreto, con la MISMA tipografia y el MISMO color del texto en toda la serie, '
            f'en identica posicion y tamano en cada slide.')


def extras_prohibidos(elemento_serie: str) -> str:
    """Prohibe los recursos que NO son parte de la anatomia default (mas elementos = mas deriva de
    posicion y mas typos). Solo entran cuando el usuario los trae en sus referencias; la skill nunca
    los agrega sola. Se omite de la lista el que sea la convencion de serie elegida, para no contradecirla."""
    extras = ["numeros fantasma", "barras de progreso", "badges o pastillas",
              "tarjetas comparativas", "stickers o washi tape", "footer de swipe"]
    if elemento_serie == "badge":
        extras.remove("badges o pastillas")
    elif elemento_serie == "barra":
        extras.remove("barras de progreso")
    return ("NO agregues por tu cuenta " + ", ".join(extras) +
            ": no son parte de la anatomia default (solo entran si el usuario los trae en sus referencias).")


def contar_bullets(body: str) -> int:
    """Cuenta las lineas no vacias del cuerpo = cuantos bullets/ideas trae la slide."""
    return len([ln for ln in (body or "").splitlines() if ln.strip()])


def tratamiento_visual_instr(tratamiento: str) -> str:
    """Instruccion de COMO se integra el elemento visual. Redactada en positivo (lo que SI debe pasar)
    + veto explicito, porque los modelos obedecen mejor lo generativo que la sola prohibicion.
    El visual SIEMPRE vive dentro de la composicion, jamas como bloque recortado tipo diapositiva."""
    if tratamiento == "escena-fotografica":
        positivo = ("el producto/objeto vive DENTRO de una escena fotografica real: sobre una superficie o plato, "
                    "con luz natural y sombras suaves que lo anclan al mismo fondo de la slide, encuadre editorial. "
                    "El texto se acomoda sobre las zonas limpias de esa misma foto")
    else:
        positivo = ("la ilustracion/grafico esta FUNDIDA con el diseño: comparte fondo, paleta y trazo con el resto de "
                    "la slide, sin recuadro propio, integrada como parte de la composicion")
    return ("TRATAMIENTO DEL VISUAL (critico): " + positivo + ". El elemento visual va integrado, sin marcos ni bordes "
            "duros. PROHIBIDO: fotos recortadas dentro de un rectangulo o bloque, collage de foto pegada, y el layout "
            "'columna de texto a un lado + bloque de imagen al otro' tipo diapositiva de PowerPoint. Nada de ese aspecto.")


def anatomia_valor(densidad: str) -> str:
    """Cuantos bullets lleva el cuerpo (opcion a) de una slide de valor, segun la densidad elegida.
    La densidad regula CUANTA info por slide; la estetica la pone la marca, no esta funcion.
    El presupuesto total (~30 palabras, max 5 elementos) manda sobre la densidad."""
    if densidad == "aireada":
        return ("- Densidad AIREADA: 1-2 bullets muy cortos (o el visual protagonista con 0-1 bullet). "
                "Mucho aire, una sola idea respirando.")
    if densidad == "completa":
        return ("- Densidad COMPLETA: hasta 3 bullets cortos con marcador de punto (keywords en negrita). "
                "Se ve llena y ordenada, siempre dentro del presupuesto de texto.")
    return ("- Densidad MEDIA: 2-3 bullets cortos con marcador de punto (keywords en negrita). "
            "Equilibrio entre informacion y aire, siempre escaneable.")


def build_prompt(slide: Dict, role: str, marca: Dict, total: int, ancla: bool = False) -> str:
    """Construye el prompt de imagen para una slide.
    total = numero de slides; ancla = True cuando se adjunta la portada como referencia de estilo."""
    colores = marca.get("colores", {})
    c_prim = colores.get("primario", "#111111")
    c_sec = colores.get("secundario", "#6F00FF")
    c_fondo = colores.get("fondo", "#FFFFFF")
    c_texto = colores.get("texto", "#111111")
    tipografia = marca.get("tipografia", "sans-serif bold, limpia y moderna")
    estilo = marca.get("estilo_visual", "ilustracion flat minimalista, alto contraste")
    handle = marca.get("instagram_usuario", "@tu_usuario")
    densidad = densidad_de(marca)
    elemento_serie = elemento_serie_de(marca)
    tratamiento = tratamiento_visual_de(marca)
    num = slide["number"]

    ref = ""
    if ancla:
        ref = ("REFERENCIA DE ESTILO: la imagen adjunta es la PORTADA de este mismo carrusel. Copia EXACTAMENTE su\n"
               "sistema visual (paleta, tipografia, tratamiento grafico, texturas y estilo de composicion) para que\n"
               "TODAS las slides se vean como una serie coherente. NO copies su texto ni su contenido — solo el estilo.\n\n")

    # Bloque de COMPOSICION comun a toda la serie. La composicion (jerarquia, densidad con orden,
    # footer integrado, elemento que guia el ojo) la define el sistema. La ESTETICA — incluida la
    # temperatura calida/fria — viene SOLO del estilo_visual de la marca: aqui no se impone ninguna.
    base = f"""{ref}Diseño de una slide vertical para carrusel de Instagram (formato vertical, mas alto que ancho).

IDENTIDAD DE MARCA (respetala estrictamente):
- Estilo visual: {estilo}
- Paleta: primario {c_prim}, acento {c_sec}, fondo {c_fondo}, texto {c_texto}.
- Tipografia: {tipografia.rstrip('.')}. El texto debe leerse PERFECTAMENTE, bien escrito, sin faltas de ortografia, y con alto contraste.
- IDIOMA (CRITICO): escribe el texto EXACTAMENTE como se te da, palabra por palabra, EN ESPAÑOL.
  NO lo traduzcas al ingles ni a otro idioma, NO lo parafrasees, NO cambies ni agregues palabras.
- No escribas dentro de la imagen ninguna medida, dimension, proporcion, unidad ni etiqueta tecnica,
  ni nombres internos de seccion; unicamente el mensaje real de la slide.
- SIN marcas de agua, SIN logos ajenos, SIN rostros de personas reales.

ANATOMIA FIJA DE LA SERIE (maximo 5 elementos por slide, ~30 palabras en total — equilibrio, no espectaculo):
- Jerarquia tipografica clara, con tamanos MUY distintos entre niveles (eyebrow > titulo > subtitulo > cuerpo).
- EYEBROW (opcional): una etiqueta corta de 1-3 palabras arriba (ej. "PASO 2", "EL ERROR #1") que da contexto antes del titulo. Usala solo si aporta.
- Densidad CON orden: elementos alineados a una reticula, con aire; nunca texto flotando en el vacio ni amontonado. Se ve llena y ordenada, sin saturar.
- Presupuesto de texto ESTRICTO: titulo <=8 palabras, subtitulo <=10 palabras, bullets <=7 palabras. Cero parrafos. Mas texto y mas elementos = mas deriva de posicion y mas errores al renderizar.
- {extras_prohibidos(elemento_serie)}
- {tratamiento_visual_instr(tratamiento)}
- Footer integrado como parte del diseño, no elementos sueltos flotando.
- {numero_serie_instr(num, total, elemento_serie)}

"""

    title = slide["title"]
    body = slide["content"]

    if role == "gancho":
        return base + f"""ESTA ES LA PORTADA (SLIDE 1) — tiene que PARAR EL SCROLL.

Gancho grande y contundente (dolor o promesa, con un numero si lo hay):
"{title}"

Subtitulo de apoyo:
"{body}"

REQUISITOS:
- Anatomia de portada: gancho GRANDE (protagonista visual, el mayor peso tipografico) + subtitulo + un elemento protagonista.
- Resalta UNA palabra clave del gancho con el color de acento {c_sec} (coloreada o subrayada), con la MISMA convencion en toda la serie.
- El elemento protagonista refuerza la idea, en el estilo visual de la marca, con el color acento {c_sec}.
- Fondo {c_fondo}. Maximo impacto y contraste. Que invite a seguir viendo el carrusel.
"""

    if role == "valor":
        n_bullets = contar_bullets(body)
        if n_bullets >= 2:
            cuerpo = (f"  - CUERPO = BULLETS (esta slide trae {n_bullets} ideas): el texto manda. El visual es SECUNDARIO: "
                      "pequeño y de apoyo, integrado en una esquina o como textura/ambiente del fondo, NUNCA un visual "
                      "protagonista a media pantalla que compita con los bullets.\n"
                      f"{anatomia_valor(densidad)}\n"
                      "  - SUBTITULO: no repitas el contenido de ningun bullet. Si el texto ya queda cubierto por los bullets, "
                      "OMITE el subtitulo y ve directo del titulo a los bullets.")
        else:
            cuerpo = ("  - CUERPO = VISUAL PROTAGONISTA (esta slide trae 0-1 idea de texto): el elemento visual es el heroe, "
                      "integrado en la escena. A lo sumo 1 linea de apoyo; nada de listas de bullets.")
        return base + f"""SLIDE INTERMEDIA (contenido util) — anatomia de slide de valor.

Titulo de la slide:
"{title}"

Contenido (respeta los bullets/pasos tal cual, texto legible):
"{body}"

REQUISITOS:
- Anatomia: (eyebrow opcional) + titulo + [subtitulo solo si aporta] + CUERPO + serie. Jerarquia clara de arriba a abajo.
- Resalta UNA palabra clave del titulo con el color de acento {c_sec} (coloreada o subrayada), con la MISMA convencion en toda la serie.
- El CUERPO es UNA sola decision, JAMAS bullets Y visual protagonista compitiendo:
{cuerpo}
- Fondo limpio {c_fondo}, acentos en {c_sec}. Consistente con la portada.
"""

    # cierre
    return base + f"""ULTIMA SLIDE (cierre e invitacion a actuar) — anatomia de cierre: CTA + @usuario.

Mensaje de cierre (escribelo TAL CUAL, natural y cercano):
"{body}"

REQUISITOS:
- Debe sentirse como una invitacion entre personas, no como un anuncio.
- Incluye de forma clara y destacada el usuario: "{handle}", integrado en el footer del diseño.
- COHERENCIA DE MARCA (critico): usa EXACTAMENTE la misma paleta del resto del carrusel.
  El color acento protagonista es {c_sec}.
  Puede ser un bloque grande de {c_sec} o el fondo {c_fondo} con {c_sec} de acento fuerte.
- Un CTA claro y destacado (el llamado a la accion del mensaje), sin saturar.
"""


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


def main():
    ap = argparse.ArgumentParser(description="Genera un carrusel de Instagram con Kie AI.")
    ap.add_argument("bundle", help="Carpeta del carrusel (contiene carrusel.md)")
    ap.add_argument("--dry-run", action="store_true",
                    help="Solo muestra el brief y los prompts, no genera imagenes (no gasta).")
    ap.add_argument("--regenerar", type=str, default=None,
                    help="Regenera solo estas slides, ej: '2,4'")
    args = ap.parse_args()

    bundle_path = Path(args.bundle).expanduser().resolve()
    bundle_path.mkdir(parents=True, exist_ok=True)

    print(f"\n{'='*60}\nFABRICA DE CARRUSELES\n{'='*60}")
    print(f"📦 Carpeta: {bundle_path}\n")

    marca = load_marca()
    print(f"🎨 Marca: {marca.get('negocio', '(sin definir)')} | {marca.get('instagram_usuario', '')}\n")

    slides = parse_carrusel(bundle_path)
    if not slides:
        sys.exit(1)

    total = len(slides)
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

    if args.dry_run:
        print(f"\n(dry-run) Prompts completos que se enviarian:\n")
        for s in slides:
            role = slide_role(s["number"], total)
            print(f"\n--- Slide {s['number']} ({role}) ---")
            print(build_prompt(s, role, marca, total, ancla=(role != "gancho")))
        print("\n(dry-run) No se genero nada. Quita --dry-run para generar.")
        return

    api_key = get_api_key()
    slides_dir = slides_dir_for(bundle_path)
    slides_dir.mkdir(exist_ok=True)

    manifest_path = slides_dir / "manifest.json"
    start = time.time()
    generated = []
    cover_num = 1 if any(s["number"] == 1 for s in slides) else slides[0]["number"]

    # --- FASE 1: la PORTADA primero. Sera el molde de estilo de las demas slides. ---
    cover_url = None
    regen_cover = (not only) or (cover_num in only)
    if regen_cover:
        print(f"\n{'='*60}\nFASE 1 — PORTADA (molde de estilo)\n{'='*60}\n")
        cs = next(s for s in slides if s["number"] == cover_num)
        tid = create_task(api_key, build_prompt(cs, slide_role(cover_num, total), marca, total))
        cover_url = poll_task(api_key, tid, "[Portada]") if tid else None
        if cover_url and download(cover_url, slides_dir / f"slide-{cover_num:02d}.png"):
            print(f"   ✅ Portada -> slide-{cover_num:02d}.png")
            generated.append({"id": cover_num, "role": "gancho", "title": cs["title"],
                              "file": f"slide-{cover_num:02d}.png", "url": cover_url})
        else:
            print("   ⚠️  No se pudo generar la portada; las demas iran sin molde.")
            cover_url = None
    else:
        # regenerando solo slides internas: recuperar la URL de la portada del manifest
        if manifest_path.exists():
            try:
                prev = json.loads(manifest_path.read_text(encoding="utf-8"))
                cover_url = next((l.get("url") for l in manifest_slides(prev) if l.get("id") == cover_num), None)
            except Exception:
                cover_url = None

    # --- FASE 2: las demas slides en paralelo, usando la portada como referencia de estilo. ---
    rest = [s for s in slides if s["number"] != cover_num and (not only or s["number"] in only)]
    pending = {}
    for s in rest:
        n = s["number"]
        role = slide_role(n, total)
        tid = create_task(api_key, build_prompt(s, role, marca, total, ancla=bool(cover_url)),
                          image_input=[cover_url] if cover_url else None)
        if tid:
            pending[n] = {"task_id": tid, "slide": s, "role": role}
            print(f"   ✅ Slide {n} enviada ({tid[:12]}...)")
        else:
            print(f"   ❌ Slide {n} no se pudo enviar")

    if pending:
        print(f"\n{'='*60}\nFASE 2 — {len(pending)} slides en paralelo{' (con molde de la portada)' if cover_url else ''}\n{'='*60}\n")
        with ThreadPoolExecutor(max_workers=len(pending)) as ex:
            futures = {ex.submit(poll_task, api_key, info["task_id"], f"[Slide {n}]"): n
                       for n, info in pending.items()}
            for fut in as_completed(futures):
                n = futures[fut]
                url = fut.result()
                if not url:
                    print(f"   ❌ Slide {n} sin resultado")
                    continue
                if download(url, slides_dir / f"slide-{n:02d}.png"):
                    print(f"   ✅ Slide {n} -> slide-{n:02d}.png")
                    info = pending[n]
                    generated.append({"id": n, "role": info["role"], "title": info["slide"]["title"],
                                      "file": f"slide-{n:02d}.png", "url": url})

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
