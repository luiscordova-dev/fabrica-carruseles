#!/usr/bin/env python3
"""
publicar.py - Publica un carrusel de imagenes en Instagram usando Upload-Post.

Sube las slides (PNG) de una carpeta como UN carrusel de Instagram, con caption.
La API de Upload-Post arma el carrusel automaticamente al mandar varias fotos.

Uso:
    python3 publicar.py <ruta-carpeta-bundle> --caption "Tu texto"
    python3 publicar.py <ruta-carpeta-bundle> --caption-file caption.txt
    python3 publicar.py <ruta-carpeta-bundle> --caption "..." --dry-run
    python3 publicar.py <ruta-carpeta-bundle> --caption "..." --plataformas instagram,tiktok

Por defecto publica solo en instagram. Con --plataformas eliges otras redes que
tengas conectadas en Upload-Post (o pon "plataformas": [...] en config/marca.json).

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
from typing import List

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:
    pass

# `requests` solo hace falta para SUBIR de verdad. El --dry-run (que walkthroughs/02 manda correr
# como verificacion) no toca la red, asi que el import es suave: sin la libreria el ensayo sigue
# corriendo y solo al publicar sale un mensaje claro, no un stack trace.
try:
    import requests
except ImportError:                                              # pragma: no cover
    requests = None

SKILL_ROOT = Path(__file__).resolve().parent.parent
MARCA_FILE = SKILL_ROOT / "config" / "marca.json"

UPLOAD_POST_URL = "https://api.upload-post.com/api/upload_photos"
MAX_FOTOS = 10  # limite de Instagram por carrusel

# Plataformas que Upload-Post acepta para FOTOS/carruseles en el campo platform[]
# (lista oficial del endpoint /api/upload_photos, docs.upload-post.com).
PLATAFORMAS_SOPORTADAS = [
    "instagram", "tiktok", "linkedin", "facebook", "x",
    "threads", "pinterest", "bluesky", "reddit", "discord", "telegram",
]
# Estas redes exigen parametros extra para fotos que esta skill AUN no manda,
# asi que publicar ahi puede fallar (limitacion documentada, no implementada):
#   facebook  -> facebook_page_id
#   pinterest -> pinterest_board_id
#   reddit    -> subreddit
PLATAFORMAS_REQUIEREN_EXTRA = {
    "facebook": "facebook_page_id",
    "pinterest": "pinterest_board_id",
    "reddit": "subreddit",
}
# Redes 100% listas con solo fotos + caption (sin parametros extra).
PLATAFORMAS_LISTAS = [p for p in PLATAFORMAS_SOPORTADAS if p not in PLATAFORMAS_REQUIEREN_EXTRA]


def parse_plataformas(raw: str) -> List[str]:
    """Normaliza '--plataformas' (lista por coma) y valida contra la lista oficial de fotos."""
    plats = []
    for p in (raw or "").split(","):
        p = p.strip().lower()
        if p and p not in plats:  # sin vacios ni duplicados, conserva el orden
            plats.append(p)
    if not plats:
        plats = ["instagram"]
    invalidas = [p for p in plats if p not in PLATAFORMAS_SOPORTADAS]
    if invalidas:
        print(f"❌ Plataforma(s) no soportada(s) para fotos: {', '.join(invalidas)}.")
        print(f"   Válidas (Upload-Post, fotos): {', '.join(PLATAFORMAS_SOPORTADAS)}.")
        sys.exit(1)
    return plats


def load_marca() -> dict:
    if MARCA_FILE.exists():
        with open(MARCA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def find_slides(bundle_path: Path) -> List[Path]:
    """Busca las slides PNG ordenadas (slides/slide-01.png, ...).
    Retrocompat: si el output es viejo (laminas/lamina-01.png), tambien lo encuentra sin fallar."""
    slides_dir = bundle_path / "slides"
    legacy_dir = bundle_path / "laminas"
    if slides_dir.exists():
        search_dir = slides_dir
    elif legacy_dir.exists():
        search_dir = legacy_dir
    else:
        search_dir = bundle_path
    fotos = sorted(search_dir.glob("slide-*.png"))
    if not fotos:  # retrocompat: outputs generados antes del cambio de nombre
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



def abrir_carpeta(path: Path) -> bool:
    """Abre la carpeta en el explorador de archivos (Finder en Mac, Explorer en Windows,
    xdg-open en Linux) para que la persona vea su carrusel al instante. Nunca revienta:
    abrir es un extra y no debe tumbar la publicacion. Devuelve True si lanzo el comando."""
    import subprocess
    try:
        if sys.platform == "darwin":          # Mac
            subprocess.run(["open", str(path)], check=False)
        elif os.name == "nt":                 # Windows
            os.startfile(str(path))           # noqa: PLE1101 (solo existe en Windows)
        else:                                  # Linux u otros
            subprocess.run(["xdg-open", str(path)], check=False)
        return True
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser(description="Publica un carrusel en Instagram (Upload-Post).")
    ap.add_argument("bundle", help="Carpeta del carrusel (con slides/)")
    ap.add_argument("--caption", type=str, default=None, help="Texto del pie de foto (caption)")
    ap.add_argument("--caption-file", type=str, default=None, help="Archivo con el caption")
    ap.add_argument("--user", type=str, default=None,
                    help="Perfil de Upload-Post (si no, se toma de marca.json)")
    ap.add_argument("--palabra", type=str, default=None,
                    help="Palabra del CTA de ESTE carrusel (para verificar que el caption la incluya).")
    ap.add_argument("--plataformas", type=str, default=None,
                    help="Redes donde publicar, separadas por coma (default: marca.json o 'instagram'). "
                         "Opciones: " + ", ".join(PLATAFORMAS_SOPORTADAS))
    ap.add_argument("--dry-run", action="store_true",
                    help="Arma y muestra el request sin publicar (no postea nada).")
    args = ap.parse_args()

    bundle_path = Path(args.bundle).expanduser().resolve()
    marca = load_marca()

    fotos = find_slides(bundle_path)
    if not fotos:
        print(f"❌ No encontre slides PNG en {bundle_path}. Genera el carrusel primero.")
        sys.exit(1)
    if len(fotos) > MAX_FOTOS:
        print(f"⚠️  Tienes {len(fotos)} slides; Instagram acepta {MAX_FOTOS} por carrusel. "
              f"Se subiran las primeras {MAX_FOTOS}.")
        fotos = fotos[:MAX_FOTOS]

    caption = build_caption(args)
    user = args.user or marca.get("upload_post_user")

    # Plataformas: CLI (--plataformas) manda; si no, lo de marca.json; si no, instagram.
    if args.plataformas is not None:
        plataformas = parse_plataformas(args.plataformas)
    else:
        m_plats = marca.get("plataformas")
        if isinstance(m_plats, list) and m_plats:
            plataformas = parse_plataformas(",".join(str(x) for x in m_plats))
        else:
            plataformas = ["instagram"]

    print(f"\n{'='*60}\nPUBLICAR CARRUSEL EN INSTAGRAM\n{'='*60}")
    print(f"📦 Carpeta: {bundle_path}")
    print(f"🖼️  Slides ({len(fotos)}):")
    for f in fotos:
        print(f"     - {f.name}")
    print(f"👤 Perfil (user): {user or '(NO configurado)'}")
    print(f"🌐 Plataformas: {', '.join(plataformas)}")
    # Aviso: redes que piden parametros extra que esta skill todavia no configura.
    faltan_extra = [p for p in plataformas if p in PLATAFORMAS_REQUIEREN_EXTRA]
    for p in faltan_extra:
        print(f"⚠️  '{p}' necesita el parámetro extra '{PLATAFORMAS_REQUIEREN_EXTRA[p]}' para fotos, "
              f"que esta skill aún no envía; esa red puede fallar.")
    if faltan_extra:
        print(f"   Redes 100% listas con solo fotos + caption: {', '.join(PLATAFORMAS_LISTAS)}.")
    print(f"📝 Caption:\n{caption}\n")

    # Campos multipart tal como los espera Upload-Post.
    # 'platform[]' se repite una vez por cada red seleccionada.
    data_fields = [("user", user or "TU_PERFIL")]
    data_fields += [("platform[]", p) for p in plataformas]
    data_fields += [
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
        print("\nArchivos (se repite 'photos[]' por cada slide):")
        for f in fotos:
            print(f"   photos[] = @{f}  (image/png)")
        # Validaciones utiles
        print("\nChequeos:")
        print(f"   [{'ok' if user else 'FALTA'}] perfil 'user' configurado")
        print(f"   [{'ok' if 1 <= len(fotos) <= MAX_FOTOS else 'FALTA'}] entre 1 y {MAX_FOTOS} slides ({len(fotos)})")
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

    if requests is None:
        print("❌ Falta una libreria para conectarse a internet.")
        print("   Instalala con el Python de la skill:")
        print('   Mac/Linux : "$HOME/.claude/skills/carrusel/venv/bin/pip" install requests')
        print('   Windows   : "$HOME\\.claude\\skills\\carrusel\\venv\\Scripts\\pip.exe" install requests')
        sys.exit(1)

    headers = {"Authorization": f"Apikey {api_key}"}
    files = [("photos[]", (f.name, open(f, "rb"), "image/png")) for f in fotos]
    try:
        print(f"⏳ Publicando {len(files)} slides...")
        resp = requests.post(UPLOAD_POST_URL, headers=headers, data=data_fields,
                             files=files, timeout=180)
        print(f"HTTP {resp.status_code}")
        try:
            print(json.dumps(resp.json(), indent=2, ensure_ascii=False))
        except Exception:
            print(resp.text)
        resp.raise_for_status()
        print("\n✅ Enviado a Upload-Post. Revisa tu Instagram en unos segundos.")
        print(f"📁 Tu carrusel esta en: {bundle_path}")
        if abrir_carpeta(bundle_path):
            print("🔎 Abri la carpeta para que lo veas.")
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
