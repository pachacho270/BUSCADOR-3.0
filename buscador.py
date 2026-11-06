import os
import asyncio
import sqlite3
import time
import re
import unicodedata
import requests
from urllib.parse import quote

from telegram import Update
from telegram.request import HTTPXRequest
from telegram.error import NetworkError, RetryAfter
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes
)

from catalogos import buscar_catalogos
from telegram_integracion import buscar_telegram
from tmdb_api import buscar_tmdb, obtener_ficha
from orden_visionado import buscar_orden
from detector_subtitulos import detectar_idioma_subtitulos

TOKEN = os.environ.get("BOT_TOKEN", "")
ARCHIVE_API = "https://archive.org/advancedsearch.php"





def buscar_archive(titulo):
    def normalizar(texto):
        texto = unicodedata.normalize("NFKD", str(texto))
        texto = "".join(
            c for c in texto
            if not unicodedata.combining(c)
        )
        return " ".join(re.findall(r"[a-z0-9]+", texto.lower()))

    def titulo_coincide(resultado, buscado):
        resultado = normalizar(resultado)

        if resultado == buscado:
            return True

        patron = (
            r"^" + re.escape(buscado)
            + r" (?:18|19|20)\d{2}$"
        )
        return bool(re.fullmatch(patron, resultado))

    def obtener_duracion(meta, videos):
        posibles = [
            meta.get("runtime"),
            meta.get("length"),
        ]

        for video in videos:
            posibles.append(video.get("length"))

        for valor in posibles:
            if not valor:
                continue

            try:
                texto = str(valor).strip()

                if ":" in texto:
                    partes = [float(x) for x in texto.split(":")]
                    segundos = 0
                    for parte in partes:
                        segundos = segundos * 60 + parte
                    return segundos

                return float(texto)
            except (ValueError, TypeError):
                continue

        return None

    def leer_subtitulo(url):
        try:
            respuesta = requests.get(
                url,
                timeout=15,
                headers={"Range": "bytes=0-200000"}
            )
            respuesta.raise_for_status()
            contenido = respuesta.content[:200000]

            for codificacion in ("utf-8-sig", "cp1252"):
                try:
                    return contenido.decode(codificacion)
                except UnicodeDecodeError:
                    pass

            return contenido.decode("utf-8", errors="replace")
        except requests.RequestException as error:
            print("No se pudo leer subtítulo:", error)
            return None

    titulo_buscado = normalizar(titulo)

    if not titulo_buscado:
        return []

    params = {
        "q": f'title:({titulo}) AND mediatype:movies',
        "fl[]": ["identifier", "title", "year"],
        "rows": 100,
        "page": 1,
        "output": "json"
    }

    try:
        response = requests.get(
            ARCHIVE_API,
            params=params,
            timeout=20
        )
        response.raise_for_status()

        docs = response.json()["response"]["docs"]
        resultados = []
        vistos = set()

        extensiones_video = (
            ".mp4", ".mkv", ".avi", ".mov",
            ".mpeg", ".mpg", ".webm", ".ogv"
        )
        extensiones_sub = (".srt", ".vtt")

        for doc in docs:
            identifier = doc.get("identifier")
            titulo_resultado = doc.get("title", "")

            if not identifier or identifier in vistos:
                continue

            if not titulo_coincide(titulo_resultado, titulo_buscado):
                continue

            metadata_response = requests.get(
                f"https://archive.org/metadata/{identifier}",
                timeout=20
            )
            metadata_response.raise_for_status()

            metadata = metadata_response.json()
            meta = metadata.get("metadata", {})

            if meta.get("mediatype") != "movies":
                continue

            archivos = metadata.get("files", [])

            videos = [
                f for f in archivos
                if f.get("name", "").lower().endswith(extensiones_video)
                and f.get("source") != "metadata"
            ]

            if not videos:
                continue

            duracion = obtener_duracion(meta, videos)

            if duracion is not None and duracion < 20 * 60:
                continue

            vistos.add(identifier)

            if duracion is None:
                estado_duracion = (
                    "⏱️ Duración: no disponible; "
                    "no se puede confirmar que sea una película completa."
                )
            elif duracion >= 45 * 60:
                minutos = int(duracion // 60)
                estado_duracion = (
                    f"⏱️ Duración declarada: {minutos} minutos. "
                    "Candidato a película completa; no verificado."
                )
            else:
                minutos = int(duracion // 60)
                estado_duracion = (
                    f"⏱️ Duración declarada: {minutos} minutos. "
                    "Duración corta o intermedia; revisar."
                )

            subtitulos = [
                f for f in archivos
                if f.get("name", "").lower().endswith(extensiones_sub)
            ]

            estado_subtitulos = "💬 Subtítulos: no encontrados."

            for subtitulo in subtitulos[:5]:
                nombre = subtitulo.get("name", "")
                tamano = int(subtitulo.get("size", 0) or 0)

                if tamano <= 0 or tamano > 5 * 1024 * 1024:
                    continue

                url_sub = (
                    f"https://archive.org/download/"
                    f"{identifier}/{quote(nombre)}"
                )

                texto_sub = leer_subtitulo(url_sub)

                if not texto_sub:
                    continue

                idioma = detectar_idioma_subtitulos(texto_sub)

                if idioma == "español":
                    estado_subtitulos = (
                        f"💬 Subtítulos en español detectados "
                        f"por análisis de texto: {nombre}. "
                        "Detección automática orientativa."
                    )
                    break

                if idioma.startswith("No identificado") or idioma == "Idioma dudoso":
                    estado_subtitulos = (
                        f"💬 Subtítulo encontrado ({nombre}), "
                        "pero su idioma no se ha podido confirmar."
                    )
                else:
                    estado_subtitulos = (
                        f"💬 Subtítulos encontrados; idioma detectado: "
                        f"{idioma}."
                    )

            licencia = str(meta.get("licenseurl", "")).strip()

            if licencia:
                estado_licencia = (
                    "📜 Licencia declarada por el usuario: "
                    + licencia
                    + "\n⚠️ No se ha comprobado su validez."
                )
            else:
                estado_licencia = "📜 Licencia: no indicada."

            idiomas = meta.get("language", "")
            if isinstance(idiomas, list):
                idiomas = ", ".join(str(x) for x in idiomas)

            idiomas = str(idiomas).strip()

            if idiomas:
                estado_audio = (
                    f"🔊 Idioma declarado en la ficha: {idiomas}. "
                    "No demuestra por sí solo el audio disponible."
                )
            else:
                estado_audio = "🔊 Idioma de audio: no indicado."

            enlace = f"https://archive.org/details/{identifier}"

            resultados.append(
                f"🎬 {titulo_resultado}\n"
                f"📅 Año: {doc.get('year', 'Desconocido')}\n"
                f"{estado_duracion}\n"
                f"{estado_audio}\n"
                f"{estado_subtitulos}\n"
                f"{estado_licencia}\n"
                f"🔗 {enlace}\n"
                "ℹ️ Datos orientativos de la ficha y los archivos. "
                "No se ha verificado la reproducción ni los derechos."
            )

            if len(resultados) >= 10:
                break

        return resultados

    except (
        requests.RequestException,
        ValueError,
        KeyError,
        TypeError
    ) as error:
        print("Error en Internet Archive:", error)
        return None


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = (
        "🔎 BUSCADOR MULTIFUENTE 3.0\n\n"
        "/buscar título: busca películas y series.\n"
        "/torrent título: consulta las mismas fuentes.\n"
        "/serie nombre: consulta disponibilidad legal.\n"
        "/ayuda\n\n"
        "Consulta catálogos públicos.\n"
        "Los idiomas se muestran según la información "
        "declarada por las fuentes."
    )

    await responder(update, context, texto)


async def ayuda(update: Update, context: ContextTypes.DEFAULT_TYPE):
    texto = (
        "📚 AYUDA - BUSCADOR 3.0\n\n"
        "/buscar título: busca en los catálogos públicos.\n\n"
        "/torrent título: alias de búsqueda.\n\n"
        "/serie nombre: consulta disponibilidad legal "
        "en JustWatch España.\n\n"
        "Los resultados de catálogos no verifican "
        "la reproducción ni los archivos de subtítulos."
    )

    await responder(update, context, texto)



async def buscar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    titulo = " ".join(context.args).strip()

    if not titulo:
        await responder(
            update, context,
            "Escribe un título. Ejemplo: /buscar Nosferatu"
        )
        return

    await responder(
        update, context,
        f"🔍 Buscando: {titulo}\n"
        "Consultando catálogos públicos y Telegram..."
    )

    # Consultar ambas fuentes y recibir datos estructurados.
    resultados = await asyncio.gather(
        asyncio.to_thread(buscar_catalogos, titulo, True),
        buscar_telegram(titulo, estructurado=True),
        return_exceptions=True
    )

    resultados_catalogos, resultados_telegram = resultados

    # Si una fuente falla, la otra seguirá funcionando.
    if isinstance(resultados_catalogos, BaseException):
        print("[CATÁLOGOS] Error:", resultados_catalogos)
        resultados_catalogos = []

    if isinstance(resultados_telegram, BaseException):
        print("[TELEGRAM] Error:", resultados_telegram)
        resultados_telegram = []

    print(
        f"[BUSCADOR] Catálogos: {len(resultados_catalogos)} | "
        f"Telegram: {len(resultados_telegram)}"
    )

    # Resultados estructurados de catálogos.
    if resultados_catalogos:
        await responder(
            update, context,
            "📺 RESULTADOS DE CATÁLOGOS"
        )

        for resultado in resultados_catalogos[:5]:
            texto = resultado.get("ficha_texto") or resultado.get("titulo") or "Resultado sin título"
            await responder(update, context, texto)
    else:
        await responder(
            update, context,
            "📺 No se han encontrado resultados relevantes en los catálogos."
        )

    # Resultados estructurados de Telegram.
    if resultados_telegram:
        await responder(
            update, context,
            "📨 RESULTADOS DE TELEGRAM"
        )

        for resultado in resultados_telegram[:5]:
            texto = resultado.get("texto", "Publicación sin texto")
            enlace = resultado.get("enlace", "")
            estado = resultado.get("estado_idioma", "DESCONOCIDO")

            mensaje = f"{texto}\n🌐 Idioma: {estado}"

            if enlace:
                mensaje += f"\n🔗 {enlace}"

            await responder(update, context, mensaje)
    else:
        await responder(
            update, context,
            "📨 No se han encontrado publicaciones relevantes en Telegram."
        )


async def torrent(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await buscar(update, context)


async def serie(update: Update, context: ContextTypes.DEFAULT_TYPE):
    titulo = " ".join(context.args).strip()

    if not titulo:
        await responder(update, context,
            "Escribe una serie. Ejemplo: /serie Slow Horses"
        )
        return

    enlace = (
        "https://www.justwatch.com/es/buscar?q="
        + quote(titulo)
    )

    await responder(update, context,
        f"📺 Disponibilidad legal de {titulo}:\n{enlace}"
    )



async def orden(update: Update, context: ContextTypes.DEFAULT_TYPE):
    titulo = " ".join(context.args).strip()

    if not titulo:
        await responder(update, context,
            "Escribe un anime. Ejemplo: /orden Tokyo Ghoul"
        )
        return

    await responder(update, context,
        f"🔍 Consultando relaciones de {titulo} en AniList..."
    )

    resultado = await asyncio.to_thread(buscar_orden, titulo)
    await responder(update, context, resultado)






# BORRADO PERSISTENTE: una hora, guardado en SQLite.
TIEMPO_BORRADO = 3600
BASE_BORRADOS = "borrados.db"


def preparar_base_borrados():
    with sqlite3.connect(BASE_BORRADOS) as conexion:
        conexion.execute("""
            CREATE TABLE IF NOT EXISTS pendientes (
                chat_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                borrar_en REAL NOT NULL,
                PRIMARY KEY (chat_id, message_id)
            )
        """)


async def programar_borrado(chat_id, message_id):
    borrar_en = time.time() + TIEMPO_BORRADO

    with sqlite3.connect(BASE_BORRADOS) as conexion:
        cursor = conexion.execute(
            """
            INSERT OR IGNORE INTO pendientes
            (chat_id, message_id, borrar_en)
            VALUES (?, ?, ?)
            """,
            (chat_id, message_id, borrar_en)
        )

        if cursor.rowcount == 1:
            hora_borrado = time.strftime(
                "%d/%m/%Y %H:%M:%S",
                time.localtime(borrar_en)
            )
            estado = (
                f"[PROGRAMADO] Chat: {chat_id} | "
                f"Mensaje: {message_id} | "
                f"Borrado previsto: {hora_borrado}"
            )
        else:
            existente = conexion.execute(
                """
                SELECT borrar_en FROM pendientes
                WHERE chat_id = ? AND message_id = ?
                """,
                (chat_id, message_id)
            ).fetchone()

            if existente:
                hora_borrado = time.strftime(
                    "%d/%m/%Y %H:%M:%S",
                    time.localtime(existente[0])
                )
                estado = (
                    f"[YA PROGRAMADO] Chat: {chat_id} | "
                    f"Mensaje: {message_id} | "
                    f"Se mantiene el borrado previsto: {hora_borrado}"
                )
            else:
                estado = (
                    f"[AVISO] No se pudo confirmar la programación "
                    f"del mensaje {message_id} en el chat {chat_id}."
                )

    print(estado, flush=True)


async def procesar_borrados(app):
    print("[BORRADOS] Servicio de borrado iniciado.", flush=True)

    while True:
        ahora = time.time()

        with sqlite3.connect(BASE_BORRADOS) as conexion:
            pendientes = conexion.execute(
                """
                SELECT chat_id, message_id
                FROM pendientes
                WHERE borrar_en <= ?
                """,
                (ahora,)
            ).fetchall()

        for chat_id, message_id in pendientes:
            try:
                await app.bot.delete_message(
                    chat_id=chat_id,
                    message_id=message_id
                )

                hora = time.strftime(
                    "%d/%m/%Y %H:%M:%S",
                    time.localtime()
                )

                print(
                    f"[ELIMINADO] Chat: {chat_id} | "
                    f"Mensaje: {message_id} | Hora: {hora}",
                    flush=True
                )

                with sqlite3.connect(BASE_BORRADOS) as conexion:
                    conexion.execute(
                        """
                        DELETE FROM pendientes
                        WHERE chat_id = ? AND message_id = ?
                        """,
                        (chat_id, message_id)
                    )

            except Exception as error:
                nuevo_intento = time.time() + 300
                hora_reintento = time.strftime(
                    "%d/%m/%Y %H:%M:%S",
                    time.localtime(nuevo_intento)
                )

                print(
                    f"[ERROR] Chat: {chat_id} | "
                    f"Mensaje: {message_id} | "
                    f"Tipo: {type(error).__name__} | "
                    f"Detalle: {error!r} | "
                    f"Próximo intento: {hora_reintento}",
                    flush=True
                )

                # Mantener el reintento dentro de cinco minutos.
                with sqlite3.connect(BASE_BORRADOS) as conexion:
                    conexion.execute(
                        """
                        UPDATE pendientes
                        SET borrar_en = ?
                        WHERE chat_id = ? AND message_id = ?
                        """,
                        (nuevo_intento, chat_id, message_id)
                    )

        await asyncio.sleep(30)


async def iniciar_borrados(app):
    preparar_base_borrados()
    app.bot_data["tarea_borrados"] = asyncio.create_task(
        procesar_borrados(app)
    )
    print("[BORRADOS] Sistema persistente preparado.", flush=True)


async def detener_borrados(app):
    tarea = app.bot_data.get("tarea_borrados")
    if tarea:
        tarea.cancel()
        try:
            await tarea
        except asyncio.CancelledError:
            pass


async def responder(update, context, texto, **kwargs):
    mensaje = update.effective_message
    chat = update.effective_chat

    if not mensaje or not chat:
        return None

    # Mantener intacta la programación original de borrado.
    await programar_borrado(
        chat.id,
        mensaje.message_id
    )

    for intento in range(4):
        try:
            respuesta = await context.bot.send_message(
                chat_id=chat.id,
                text=texto,
                message_thread_id=mensaje.message_thread_id,
                reply_to_message_id=mensaje.message_id,
                **kwargs
            )

            await programar_borrado(
                chat.id,
                respuesta.message_id
            )

            return respuesta

        except RetryAfter as error:
            espera = float(error.retry_after) + 1
            print(
                f"[ENVÍO] Telegram limita los mensajes. "
                f"Reintentando en {espera:.1f} segundos."
            )

            if intento == 3:
                print("[ENVÍO] Se agotaron los intentos.")
                return None

            await asyncio.sleep(espera)

        except NetworkError as error:
            if intento == 3:
                print(
                    f"[ENVÍO] Fallo definitivo de red: {error}"
                )
                return None

            espera = 2 ** (intento + 1)
            print(
                f"[ENVÍO] Error temporal de red. "
                f"Intento {intento + 1}/4; "
                f"nuevo intento en {espera} segundos."
            )
            await asyncio.sleep(espera)

    return None


async def fijar_ayuda(update, context):
    usuario = update.effective_user
    chat = update.effective_chat
    mensaje = update.effective_message

    miembro = await context.bot.get_chat_member(
        chat.id,
        usuario.id
    )

    if miembro.status not in ("creator", "administrator"):
        await responder(
            update,
            context,
            "Solo los administradores pueden fijar las instrucciones."
        )
        return

    instrucciones = (
        "🔎 EL PERRO DE JHON WICK — INSTRUCCIONES\n\n"
        "/buscar título — Buscar películas y series.\n"
        "/torrent título — Consulta de catálogos.\n"
        "/serie nombre — Disponibilidad legal en JustWatch.\n"
        "/orden nombre — Guía de visionado y orden.\n"
        "/ayuda — Ver ayuda.\n\n"
        "📌 Este tema está reservado para el buscador.\n"
        "Las consultas y respuestas temporales se borran "
        "automáticamente después de una hora."
    )

    permanente = await context.bot.send_message(
        chat_id=chat.id,
        message_thread_id=mensaje.message_thread_id,
        text=instrucciones
    )

    await context.bot.pin_chat_message(
        chat_id=chat.id,
        message_id=permanente.message_id,
        disable_notification=True
    )

    await programar_borrado(
        chat.id,
        mensaje.message_id
    )


# CONTROL DE ACCESO: grupo Cositas, tema autorizado.
GRUPO_AUTORIZADO = -1004473280106
TEMA_AUTORIZADO = 1644

def proteger(func):
    async def funcion_protegida(update, context):
        mensaje = update.effective_message
        usuario = update.effective_user
        chat = update.effective_chat

        if not mensaje or not usuario or not chat:
            return

        if chat.id != GRUPO_AUTORIZADO:
            return

        if mensaje.message_thread_id != TEMA_AUTORIZADO:
            return

        try:
            miembro = await context.bot.get_chat_member(
                GRUPO_AUTORIZADO,
                usuario.id
            )
        except Exception as error:
            print("Error comprobando miembro:", error)
            return

        if miembro.status not in ("creator", "administrator", "member"):
            if not (miembro.status == "restricted" and miembro.is_member):
                return

        await func(update, context)

    return funcion_protegida

def main():
    if not TOKEN:
        raise RuntimeError(
            "Falta configurar BOT_TOKEN"
        )

    request = HTTPXRequest(
        connect_timeout=20,
        read_timeout=30,
        write_timeout=30,
        pool_timeout=10
    )

    get_updates_request = HTTPXRequest(
        connect_timeout=20,
        read_timeout=30,
        write_timeout=30,
        pool_timeout=10
    )

    app = (
        Application.builder()
        .token(TOKEN)
        .request(request)
        .get_updates_request(get_updates_request)
        .post_init(iniciar_borrados)
        .post_shutdown(detener_borrados)
        .build()
    )

    app.add_handler(CommandHandler("start", proteger(start)))
    app.add_handler(CommandHandler("ayuda", proteger(ayuda)))
    app.add_handler(CommandHandler("buscar", proteger(buscar)))
    app.add_handler(CommandHandler("torrent", proteger(torrent)))
    app.add_handler(CommandHandler("serie", proteger(serie)))
    app.add_handler(CommandHandler("orden", proteger(orden)))
    app.add_handler(CommandHandler("fijar_ayuda", proteger(fijar_ayuda)))

    print("BUSCADOR 3.0 INICIADO")

    app.run_polling()


if __name__ == "__main__":
    main()
