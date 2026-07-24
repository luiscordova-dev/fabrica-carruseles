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
Las imagenes se guardan en <ruta-carpeta-bundle>/laminas/lamina-01.png, etc.

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
        }
    with open(MARCA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


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
    num = slide["number"]

    ref = ""
    if ancla:
        ref = ("REFERENCIA DE ESTILO: la imagen adjunta es la PORTADA de este mismo carrusel. Copia EXACTAMENTE su\n"
               "sistema visual (paleta, tipografia, tratamiento grafico, texturas y estilo de composicion) para que\n"
               "TODAS las slides se vean como una serie coherente. NO copies su texto ni su contenido — solo el estilo.\n\n")
    flecha = ('- En el borde derecho, una flecha "→" pequeña y discreta que invite a deslizar a la siguiente slide.\n'
              if num < total else "")

    base = f"""{ref}Diseño de una slide vertical para carrusel de Instagram (formato vertical, mas alto que ancho).

IDENTIDAD DE MARCA (respetala estrictamente):
- Estilo visual: {estilo}
- Paleta: primario {c_prim}, acento {c_sec}, fondo {c_fondo}, texto {c_texto}.
- Tipografia: {tipografia.rstrip('.')}. El texto debe leerse PERFECTAMENTE, bien escrito, sin faltas de ortografia, GRANDE y con alto contraste.
- Texto CORTO y grande: mejor pocas palabras enormes que un parrafo. Composicion limpia, con aire, moderna.
- IDIOMA (CRITICO): escribe el texto EXACTAMENTE como se te da, palabra por palabra, EN ESPAÑOL.
  NO lo traduzcas al ingles ni a otro idioma, NO lo parafrasees, NO cambies ni agregues palabras.
- No escribas dentro de la imagen ninguna medida, dimension, proporcion, unidad ni etiqueta tecnica,
  ni nombres internos de seccion; unicamente el mensaje real de la slide.
- ELEMENTO DE SERIE: un indicador pequeño y discreto "{num}/{total}" en una esquina inferior, en el color del texto, SIEMPRE en la misma posicion.
{flecha}- SIN marcas de agua, SIN logos ajenos, SIN rostros de personas reales.

"""

    title = slide["title"]
    body = slide["content"]

    if role == "gancho":
        return base + f"""ESTA ES LA PORTADA (SLIDE 1) — tiene que PARAR EL SCROLL.

Titulo grande y contundente (es un gancho de dolor o de promesa, con un numero si lo hay):
"{title}"

Texto de apoyo:
"{body}"

REQUISITOS:
- El titulo es el protagonista visual: el mayor peso tipografico del estilo de la marca, muy grande.
- Un elemento grafico simple y potente que refuerce la idea, en el estilo visual de la marca, con el color acento {c_sec}.
- Fondo {c_fondo}. Maximo impacto y contraste. Que de curiosidad por deslizar.
"""

    if role == "valor":
        return base + f"""SLIDE INTERMEDIA (contenido util).

Titulo de la slide:
"{title}"

Contenido (respeta los bullets/pasos tal cual, texto legible):
"{body}"

REQUISITOS:
- Jerarquia clara: titulo arriba, contenido en bullets o pasos, muy escaneable.
- Un grafico conceptual simple que acompañe la idea (no que decore de mas).
- Fondo limpio {c_fondo}, acentos en {c_sec}. Consistente con la portada.
"""

    # cierre
    return base + f"""ULTIMA SLIDE (cierre e invitacion a actuar).

Mensaje de cierre (escribelo TAL CUAL, natural y cercano):
"{body}"

REQUISITOS:
- Debe sentirse como una invitacion entre personas, no como un anuncio.
- Incluye de forma clara y destacada el usuario: "{handle}".
- COHERENCIA DE MARCA (critico): usa EXACTAMENTE la misma paleta del resto del carrusel.
  El color acento protagonista es {c_sec}.
  Puede ser un bloque grande de {c_sec} o el fondo {c_fondo} con {c_sec} de acento fuerte.
- Refuerza la accion con un elemento visual (una flecha hacia el usuario o un boton) sin saturar.
- Al ser la ULTIMA slide, NO incluyas la flecha de "deslizar →" en la esquina (ya no hay siguiente).
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

    if args.dry_run:
        print(f"\n(dry-run) Prompts que se enviarian:\n")
        for s in slides:
            role = slide_role(s["number"], total)
            print(f"\n--- Slide {s['number']} ({role}) ---")
            print(build_prompt(s, role, marca, total, ancla=(role != "gancho"))[:600] + "...")
        print("\n(dry-run) No se genero nada. Quita --dry-run para generar.")
        return

    api_key = get_api_key()
    laminas_dir = bundle_path / "laminas"
    laminas_dir.mkdir(exist_ok=True)

    manifest_path = laminas_dir / "manifest.json"
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
        if cover_url and download(cover_url, laminas_dir / f"lamina-{cover_num:02d}.png"):
            print(f"   ✅ Portada -> lamina-{cover_num:02d}.png")
            generated.append({"id": cover_num, "role": "gancho", "title": cs["title"],
                              "file": f"lamina-{cover_num:02d}.png", "url": cover_url})
        else:
            print("   ⚠️  No se pudo generar la portada; las demas iran sin molde.")
            cover_url = None
    else:
        # regenerando solo slides internas: recuperar la URL de la portada del manifest
        if manifest_path.exists():
            try:
                prev = json.loads(manifest_path.read_text(encoding="utf-8"))
                cover_url = next((l.get("url") for l in prev.get("laminas", []) if l.get("id") == cover_num), None)
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
                if download(url, laminas_dir / f"lamina-{n:02d}.png"):
                    print(f"   ✅ Slide {n} -> lamina-{n:02d}.png")
                    info = pending[n]
                    generated.append({"id": n, "role": info["role"], "title": info["slide"]["title"],
                                      "file": f"lamina-{n:02d}.png", "url": url})

    if not generated:
        print("\n❌ No se genero ninguna slide. Revisa tu llave y tus creditos de Kie AI.")
        sys.exit(1)

    # Merge con manifest previo (para no perder slides al regenerar solo algunas)
    laminas_map = {}
    if manifest_path.exists():
        try:
            for l in json.loads(manifest_path.read_text(encoding="utf-8")).get("laminas", []):
                laminas_map[l["id"]] = l
        except Exception:
            pass
    for l in generated:
        laminas_map[l["id"]] = l
    laminas_all = [laminas_map[k] for k in sorted(laminas_map)]

    manifest = {
        "generado": datetime.now().isoformat(timespec="seconds"),
        "negocio": marca.get("negocio"),
        "instagram_usuario": marca.get("instagram_usuario"),
        "total": len(laminas_all),
        "laminas": laminas_all,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    elapsed = int(time.time() - start)
    print(f"\n{'='*60}\nLISTO\n{'='*60}")
    print(f"Slides generadas ahora: {len(generated)}")
    print(f"Carpeta: {laminas_dir}")
    print(f"Costo aprox: ~${len(generated) * 0.10:.2f} | Tiempo: {elapsed//60}m {elapsed%60}s")
    print(f"\nSiguiente paso: publicar con scripts/publicar.py\n")


if __name__ == "__main__":
    main()
