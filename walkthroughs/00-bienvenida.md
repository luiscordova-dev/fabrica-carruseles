# Bienvenida — antes de empezar

Léele esto al usuario con calma. El objetivo de este paso es confirmar que tiene lo mínimo
para que todo lo demás fluya, y que sepa qué va a pasar.

## Qué le vas a decir (adáptalo, no lo leas robótico)

> ¡Hola! Vamos a dejar lista tu Fábrica de Carruseles. En unos minutos vas a poder pedirme
> un carrusel para Instagram y yo te lo genero con tu marca y, si quieres, lo publico por ti.
>
> Solo necesitamos tres cosas:
> 1. Configurar tu marca (te voy a hacer unas preguntas rápidas).
> 2. Una llave de Kie AI (es lo que crea las imágenes).
> 3. Una llave de Upload Post (es lo que publica en Instagram por ti).
>
> Yo te guío en cada una. Empecemos.

## Verificaciones técnicas (hazlas tú, en silencio, y reporta el resultado)

1. **Python 3** — corre `python3 --version`. Si no está, guía a instalarlo (en Mac normalmente ya viene; en Windows, desde python.org marcando "Add to PATH").
2. **Dependencias** — el instalador ya deja un entorno de Python (`venv/`) dentro de la skill con todo instalado, y los scripts se corren con ese Python (ver Paso 0 del `SKILL.md`). Si no existe `venv/`, créalo como indica ese Paso 0.
3. Confirma que existe `config/marca.json`. Si no, lo vas a crear en el onboarding (siguiente paso).

## Reglas para ti (el asistente)
- Una cosa a la vez. No abrumes con listas técnicas.
- Si algo falla, tradúcelo a lenguaje simple y ofrece la solución, no el error crudo.
- Celebra cuando algo queda listo. Esto debe sentirse fácil.
