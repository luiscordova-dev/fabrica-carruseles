# Llave de Kie AI (crea las imágenes)

Kie AI es el servicio que dibuja cada slide del carrusel (usa el modelo nano-banana-pro).
Cuesta muy poco: alrededor de **$0.10 USD por imagen** (un carrusel de 6 slides ≈ $0.60).

**La recarga mínima son $5 USD = 1,000 créditos.** A ~$0.10 por slide, con esos $5 haces **~50 slides ≈
8 carruseles completos** de 6. Es normal que pida un mínimo; con $5 tienes para rato.

## Guíalo así (paso a paso)

> Vamos por la llave que crea las imágenes. Es como una contraseña que le da permiso
> a tu Fábrica de Carruseles para generar imágenes.
>
> 1. Entra a **https://kie.ai** y crea tu cuenta (o inicia sesión).
> 2. Vas a necesitar cargar un poco de saldo para generar imágenes. Con **$5 USD** te
>    alcanza para muchísimos carruseles. Si tu tarjeta local no pasa, prueba con otra
>    (a veces las tarjetas digitales tipo Nu o Mercado Pago funcionan mejor).
> 3. Busca en el menú la sección de **API Keys** (o "API").
> 4. Crea una llave nueva ("Create API Key").
> 5. Cópiala completa (es una cadena larga de letras y números).
> 6. Pégamela aquí en el chat.

> 💡 **Si te pierdes** en cualquier paso (no ves el menú, no encuentras el botón), **toma una
> captura de pantalla y pásamela** — la miro y te digo exactamente dónde picar.

## Cuando el usuario pegue la llave
- **NO la imprimas de vuelta** en el chat.
- Guárdala en el archivo `.env` de la skill, en la línea `KIE_API_KEY=` (crea el `.env`
  a partir de `.env.example` si no existe).
- Confirma sin mostrar el valor: "Listo, tu llave de Kie AI quedó guardada. ✅"

## Verificación
No hace falta una prueba aparte: el **primer carrusel** confirma que la llave sirve. Cuando ya exista
un `carrusel.md`, su `--dry-run` no gasta y valida el formato; y la generación real confirma la llave.

## Nota
El nombre de la variable es `KIE_API_KEY`. El script también acepta `KIE_AI_API_KEY`
por compatibilidad, pero usa `KIE_API_KEY`.
