#!/usr/bin/env python3
"""
publicar.py - Publica un carrusel de imagenes en Instagram usando Upload-Post.

Sube las laminas (PNG) de una carpeta como UN carrusel de Instagram, con caption.
La API de Upload-Post arma el carrusel automaticamente al mandar varias fotos.

Uso:
    python3 publicar.py <ruta-carpeta-bundle> --caption "Tu texto"
    python3 publicar.py <ruta-carpeta-bundle> --caption-file caption.txt
    python3 publicar.py <ruta-carpeta-bundle> --caption "..." --dry-run

--dry-run arma el request EXACTO (endpoint, headers, campos, archivos) y lo
muestra SIN publicar nada. Sirve para verificar antes de postear en vivo.

Requiere (para publicar de verdad, no en dry-run):
    - UPLOAD_POST_API_KEY en el entorno o en el .env de la skill.
    - El "user" (perfil) conectado en el dashboard de Upload-Post
      (se guarda en config/marca.json como "upload_post_user", o se pasa con --user).
      Sigue el walkthrough 02-upload-post.md.

Referencia API: https://docs.upload-post.com  (endpoint POST /api/upload_photos)
"""

import os
import sys
import json
import argparse
from pathlib import Path
from typing import List, Optional

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

import requests

SKILL_ROOT = Path(__file__).resolve().parent.parent
MARCA_FILE = SKILL_ROOT / "config" / "marca.json"

UPLOAD_POST_URL = "https://api.upload-post.com/api/upload_photos"
MAX_FOTOS = 10  # limite de Instagram por carrusel


def load_marca() -> dict:
    if MARCA_FILE.exists():
        with open(MARCA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def find_laminas(bundle_path: Path) -> List[Path]:
    """Busca las laminas PNG ordenadas (laminas/lamina-01.png, ...)."""
    laminas_dir = bundle_path / "laminas"
    search_dir = laminas_dir if laminas_dir.exists() else bundle_path
    fotos = sorted(search_dir.glob("lamina-*.png"))
    if not fotos:
        fotos = sorted(search_dir.glob("*.png"))
    return fotos


def build_caption(args) -> str:
    if args.caption_file:
        return Path(args.caption_file).read_text(encoding="utf-8").strip()
    if args.caption:
        return args.caption
    print('❌ Falta el pie de foto. Pásalo con --caption "..." o --caption-file caption.txt')
    sys.exit(1)


def main():
    ap = argparse.ArgumentParser(description="Publica un carrusel en Instagram (Upload-Post).")
    ap.add_argument("bundle", help="Carpeta del carrusel (con laminas/)")
    ap.add_argument("--caption", type=str, default=None, help="Texto del pie de foto (caption)")
    ap.add_argument("--caption-file", type=str, default=None, help="Archivo con el caption")
    ap.add_argument("--user", type=str, default=None,
                    help="Perfil de Upload-Post (si no, se toma de marca.json)")
    ap.add_argument("--palabra", type=str, default=None,
                    help="Palabra del CTA de ESTE carrusel (para verificar que el caption la incluya).")
    ap.add_argument("--dry-run", action="store_true",
                    help="Arma y muestra el request sin publicar (no postea nada).")
    args = ap.parse_args()

    bundle_path = Path(args.bundle).expanduser().resolve()
    marca = load_marca()

    fotos = find_laminas(bundle_path)
    if not fotos:
        print(f"❌ No encontre laminas PNG en {bundle_path}. Genera el carrusel primero.")
        sys.exit(1)
    if len(fotos) > MAX_FOTOS:
        print(f"⚠️  Tienes {len(fotos)} laminas; Instagram acepta {MAX_FOTOS} por carrusel. "
              f"Se subiran las primeras {MAX_FOTOS}.")
        fotos = fotos[:MAX_FOTOS]

    caption = build_caption(args)
    user = args.user or marca.get("upload_post_user")

    print(f"\n{'='*60}\nPUBLICAR CARRUSEL EN INSTAGRAM\n{'='*60}")
    print(f"📦 Carpeta: {bundle_path}")
    print(f"🖼️  Laminas ({len(fotos)}):")
    for f in fotos:
        print(f"     - {f.name}")
    print(f"👤 Perfil (user): {user or '(NO configurado)'}")
    print(f"📝 Caption:\n{caption}\n")

    # Campos multipart tal como los espera Upload-Post.
    data_fields = [
        ("user", user or "TU_PERFIL"),
        ("platform[]", "instagram"),
        ("title", caption),          # en Upload-Post el caption de fotos va en 'title'
        ("media_type", "IMAGE"),
    ]

    if args.dry_run:
        print(f"{'='*60}\n(DRY-RUN) Request que se enviaria\n{'='*60}")
        print(f"POST {UPLOAD_POST_URL}")
        print(f"Header: Authorization: Apikey <UPLOAD_POST_API_KEY>")
        print(f"Content-Type: multipart/form-data\n")
        print("Campos de texto:")
        for k, v in data_fields:
            shown = v if len(str(v)) < 80 else str(v)[:77] + "..."
            print(f"   {k} = {shown}")
        print("\nArchivos (se repite 'photos[]' por cada lamina):")
        for f in fotos:
            print(f"   photos[] = @{f}  (image/png)")
        # Validaciones utiles
        print("\nChequeos:")
        print(f"   [{'ok' if user else 'FALTA'}] perfil 'user' configurado")
        print(f"   [{'ok' if 1 <= len(fotos) <= MAX_FOTOS else 'FALTA'}] entre 1 y {MAX_FOTOS} laminas ({len(fotos)})")
        print(f"   [{'ok' if caption.strip() else 'FALTA'}] caption no vacio")
        palabra = (args.palabra or "").strip()
        if palabra:
            ok = palabra.lower() in caption.lower()
            print(f"   [{'ok' if ok else 'OJO'}] el caption incluye la palabra para comentar ({palabra})")
        key_present = bool(os.environ.get("UPLOAD_POST_API_KEY"))
        print(f"   [{'ok' if key_present else 'FALTA'}] UPLOAD_POST_API_KEY en el entorno")
        print("\n(dry-run) No se publico nada. Quita --dry-run para publicar de verdad.\n")
        return

    # --- Publicacion real ---
    api_key = os.environ.get("UPLOAD_POST_API_KEY")
    if not api_key:
        print("❌ Falta UPLOAD_POST_API_KEY en el .env de la skill.")
        print("   Sigue el walkthrough 02-upload-post.md para sacarla y conectar tu Instagram.")
        sys.exit(1)
    if not user:
        print("❌ Falta el perfil (user) de Upload-Post.")
        print("   Ponlo en config/marca.json como 'upload_post_user' o pasalo con --user.")
        sys.exit(1)

    headers = {"Authorization": f"Apikey {api_key}"}
    files = [("photos[]", (f.name, open(f, "rb"), "image/png")) for f in fotos]
    try:
        print(f"⏳ Publicando {len(files)} láminas...")
        resp = requests.post(UPLOAD_POST_URL, headers=headers, data=data_fields,
                             files=files, timeout=180)
        print(f"HTTP {resp.status_code}")
        try:
            print(json.dumps(resp.json(), indent=2, ensure_ascii=False))
        except Exception:
            print(resp.text)
        resp.raise_for_status()
        print("\n✅ Enviado a Upload-Post. Revisa tu Instagram en unos segundos.")
    except Exception as e:
        print(f"\n❌ Error publicando: {e}")
        print("   Causas comunes: IG no es Business/Creator ligada a pagina de Facebook,")
        print("   perfil no conectado en el dashboard, o llave incorrecta.")
        sys.exit(1)
    finally:
        for _, (_, fh, _) in files:
            try:
                fh.close()
            except Exception:
                pass


if __name__ == "__main__":
    main()
