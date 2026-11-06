import os
import re
import unicodedata
import asyncio

from telethon import TelegramClient
from telethon.errors import FloodWaitError

from filtro_idioma import evaluar_idioma

SESION = "buscador_usuario"

# Evita que dos búsquedas utilicen simultáneamente la misma sesión.
_bloqueo = asyncio.Lock()


def puntuar(texto, titulo):
    def normalizar(valor):
        valor = unicodedata.normalize("NFKD", valor.lower())
        return "".join(
            c for c in valor
            if not unicodedata.combining(c)
        )

    texto = normalizar(texto)
    titulo = normalizar(titulo)

    palabras = re.findall(r"\w+", titulo)
    palabras = list(dict.fromkeys(palabras))

    puntos = 0

    if titulo and titulo in texto:
        puntos += 10

    for palabra in palabras:
        if len(palabra) > 2 and palabra in texto:
            puntos += 4

    # El año suma relevancia, pero no es obligatorio.
    for palabra in palabras:
        if re.fullmatch(r"19\d{2}|20\d{2}", palabra):
            if palabra in texto:
                puntos += 1

    if re.search(r"\b(t|temporada|season)\s*0*\d+", texto):
        puntos += 5

    if re.search(r"\b(e|ep|episodio|episode|capitulo)\s*0*\d+", texto):
        puntos += 5

    if re.search(r"\b\d{1,2}x\d{1,2}\b", texto):
        puntos += 6

    if any(x in texto for x in [
        "libro", "libreria", "novela", "autor",
        "edicion", "paginas"
    ]):
        puntos -= 8

    if any(x in texto for x in [
        "recomendacion", "que me aconsejais",
        "que serie veo", "me gusto mucho"
    ]):
        puntos -= 2

    return puntos


def evaluar_mensaje(texto):
    texto = texto or ""

    # Normalizar tildes para reconocer español, subtítulos, etc.
    normalizado = unicodedata.normalize("NFKD", texto.lower())
    normalizado = "".join(
        c for c in normalizado
        if not unicodedata.combining(c)
    )

    if re.search(
        r"\b(audio|doblaje|voces?)\s*(en\s*)?"
        r"(latino|latinoamericano)\b"
        r"|\bes-419\b|\bes-mx\b|\bes-ar\b",
        normalizado
    ):
        return {
            "estado": "DESCARTAR",
            "motivo": "Audio latino declarado"
        }

    audio = {}

    if re.search(
        r"\b(audio|doblaje|voces?)\s*(en\s*)?"
        r"(castellano|espanol de espana)\b"
        r"|\bcastellano de espana\b|\bes-es\b",
        normalizado
    ):
        audio["audio"] = "castellano"

    subtitulos = []

    if re.search(
        r"\b(subtitulos?|subs)\s*(en\s*)?"
        r"(espanol|castellano|spanish)\b"
        r"|\bspanish subtitles\b",
        normalizado
    ):
        subtitulos.append({"language": "espanol"})

    return evaluar_idioma(audio, subtitulos)


async def buscar_telegram(consulta, estructurado=False):
    api_id = os.getenv("TG_API_ID")
    api_hash = os.getenv("TG_API_HASH")

    if not api_id or not api_hash:
        print("[TELEGRAM] Faltan las variables de configuración.")
        return []

    resultados = []

    async with _bloqueo:
        client = TelegramClient(
            SESION,
            int(api_id),
            api_hash
        )

        try:
            await client.connect()

            if not await client.is_user_authorized():
                print("[TELEGRAM] La sesión no está autorizada.")
                return []

            espacios = 0
            total_mensajes = 0
            idioma_aceptado = 0
            idioma_desconocido = 0
            puntuacion_aceptada = 0

            async for dialogo in client.iter_dialogs():
                if not (dialogo.is_group or dialogo.is_channel):
                    continue

                espacios += 1

                try:
                    async for mensaje in client.iter_messages(
                        dialogo.entity,
                        search=consulta,
                        limit=20
                    ):
                        total_mensajes += 1
                        texto = mensaje.message or ""

                        if not texto.strip():
                            continue

                        idioma = evaluar_mensaje(texto)

                        if idioma["estado"] == "DESCARTAR":
                            continue
                        if idioma["estado"] == "ACEPTAR":
                            idioma_aceptado += 1
                        else:
                            idioma_desconocido += 1

                        puntos = puntuar(texto, consulta)

                        if puntos < 5:
                            continue
                        puntuacion_aceptada += 1

                        entidad = dialogo.entity
                        username = getattr(entidad, "username", None)

                        if username:
                            enlace = (
                                f"https://t.me/{username}/{mensaje.id}"
                            )
                        elif dialogo.is_channel:
                            enlace = (
                                f"https://t.me/c/{entidad.id}/{mensaje.id}"
                            )
                        else:
                            enlace = "Abrir el grupo en Telegram"

                        fecha = mensaje.date.strftime("%d/%m/%Y")

                        resultados.append({
                            "puntos": puntos,
                            "grupo": dialogo.name,
                            "fecha": mensaje.date,
                            "texto": texto,
                            "enlace": enlace,
                            "idioma": idioma["motivo"],
                            "estado_idioma": idioma["estado"]
                        })

                except FloodWaitError as error:
                    print(
                        "[TELEGRAM] Límite temporal:",
                        error.seconds,
                        "segundos."
                    )
                    break

                except Exception as error:
                    print(
                        f"[TELEGRAM] Error en un espacio: {error}"
                    )
                    continue

                await asyncio.sleep(0.15)

            resultados.sort(
                key=lambda x: (x["puntos"], x["fecha"]),
                reverse=True
            )

            print(
                f"[TELEGRAM] Espacios consultados: {espacios}. "
                f"Mensajes encontrados: {total_mensajes}. "
                f"Idioma confirmado: {idioma_aceptado}. "
                f"Idioma desconocido: {idioma_desconocido}. "
                f"Puntuación aceptada: {puntuacion_aceptada}. "
                f"Coincidencias: {len(resultados)}"
            )

            if estructurado:

                return resultados[:5]


            fichas = []

            for resultado in resultados[:5]:
                fichas.append(
                    "📨 RESULTADO DE TELEGRAM\n"
                    f"📂 Grupo: {resultado['grupo']}\n"
                    f"📅 Fecha: {resultado['fecha'].strftime('%d/%m/%Y')}\n"
                    f"⭐ Relevancia: {resultado['puntos']}\n"
                    f"🗣️ Estado del idioma: {resultado['estado_idioma']}\n"
                    f"📌 Información: {resultado['idioma']}\n"
                    f"💬 {resultado['texto'][:700]}\n"
                    f"🔗 {resultado['enlace']}\n"
                    "⚠️ El idioma se basa en lo declarado "
                    "en la publicación, no en una comprobación "
                    "del archivo multimedia."
                )

            return fichas

        except Exception as error:
            print(f"[TELEGRAM] Error general: {error}")
            return []

        finally:
            if client.is_connected():
                await client.disconnect()
