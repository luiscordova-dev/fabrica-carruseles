#!/usr/bin/env bash
# Instalador de la Fábrica de Carruseles (Mac / Linux).
# Copia la skill a ~/.claude/skills/carrusel/, prepara su entorno de Python,
# y (al actualizar) conserva tus llaves, tu marca y tus carruseles.
set -e

SKILL_NAME="carrusel"
REPO_URL="https://github.com/luiscordova-dev/fabrica-carruseles.git"
TARGET="$HOME/.claude/skills/$SKILL_NAME"
BACKUP=""

echo ""
echo "  🎠  Instalando Fábrica de Carruseles..."
echo ""

# 1) Verificar que Claude Code está instalado (~/.claude debe existir)
if [ ! -d "$HOME/.claude" ]; then
  echo "  ✗ No encuentro la carpeta ~/.claude."
  echo "    ¿Tienes Claude Code instalado? Instálalo primero: https://claude.com/claude-code"
  exit 1
fi

# 2) Verificar git
if ! command -v git >/dev/null 2>&1; then
  echo "  ✗ Necesitas git instalado."
  exit 1
fi

mkdir -p "$HOME/.claude/skills"

# 3) Si ya existe, preguntar si actualizar (leyendo del teclado) y respaldar SIN borrar todavía
if [ -d "$TARGET" ]; then
  printf "  Ya tienes la skill instalada. ¿Actualizar a la última versión? (s/n): "
  if [ -r /dev/tty ]; then read -r RESP < /dev/tty; else read -r RESP; fi
  case "$RESP" in
    [Ss]*) ;;
    *) echo "  Ok, no toco nada."; exit 0 ;;
  esac
  BACKUP="$(mktemp -d)"
  [ -f "$TARGET/.env" ] && cp "$TARGET/.env" "$BACKUP/.env"
  [ -f "$TARGET/config/marca.json" ] && cp "$TARGET/config/marca.json" "$BACKUP/marca.json"
  [ -d "$TARGET/outputs" ] && cp -R "$TARGET/outputs" "$BACKUP/outputs"
fi

# 4) Clonar a un TEMPORAL primero. Solo si la descarga sale bien reemplazamos la instalación.
TMP_DIR="$(mktemp -d)"
if ! git clone --depth 1 --quiet "$REPO_URL" "$TMP_DIR/carrusel"; then
  echo "  ✗ No pude descargar la skill (¿sin internet, o el repo aún no es público?)."
  echo "    No toqué tu instalación."
  rm -rf "$TMP_DIR" "$BACKUP"
  exit 1
fi
rm -rf "$TMP_DIR/carrusel/.git"
rm -rf "$TARGET"                    # ahora sí: la descarga fue exitosa
mv "$TMP_DIR/carrusel" "$TARGET"
rm -rf "$TMP_DIR"

# 5) Restaurar datos del usuario (si veníamos de una actualización)
if [ -n "$BACKUP" ]; then
  [ -f "$BACKUP/.env" ] && cp "$BACKUP/.env" "$TARGET/.env"
  [ -f "$BACKUP/marca.json" ] && cp "$BACKUP/marca.json" "$TARGET/config/marca.json"
  [ -d "$BACKUP/outputs" ] && cp -R "$BACKUP/outputs/." "$TARGET/outputs/" 2>/dev/null || true
  rm -rf "$BACKUP"
  echo "  ↩️  Conservé tus llaves, tu marca y tus carruseles."
fi

# 6) Preparar entorno de Python (venv aislado, funciona en Macs "externally-managed")
echo "  📦 Preparando entorno de Python..."
if python3 -m venv "$TARGET/venv" 2>/dev/null; then
  "$TARGET/venv/bin/pip" install --quiet --upgrade pip >/dev/null 2>&1 || true
  if "$TARGET/venv/bin/pip" install --quiet -r "$TARGET/requirements.txt"; then
    echo "  ✅ Entorno listo."
  else
    echo "  ⚠️  No pude instalar dependencias. Corre luego:"
    echo "     \"$TARGET/venv/bin/pip\" install -r \"$TARGET/requirements.txt\""
  fi
else
  echo "  ⚠️  No pude crear el entorno de Python. Necesitas Python 3 instalado."
fi

echo ""
echo "  ✅ ¡Listo! La skill quedó en: $TARGET"
echo ""
echo "  Abre Claude Code y escribe:  /carrusel"
echo "  (o simplemente pídele: \"hazme un carrusel sobre ...\")"
echo ""
