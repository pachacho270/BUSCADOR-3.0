import requests
import re
import unicodedata
from html.parser import HTMLParser
from urllib.parse import quote, urlparse

from filtro_idioma import (
    evaluar_idioma,
    audio_castellano,
    audio_latino,
    subtitulos_espanol
)

FUENTES = [
    {
        "nombre": "TorrentClaw",
        "url": "https://addon.torrentclaw.com/api/stremio/eyJsYW5nIjoiZXMiLCJxdWFsaXR5IjoiNzIwcCIsInNvcnQiOiJzZWVkZXJzIn0",
        "catalogos": [
            ("movie", "tc-search"),
            ("series", "tc-search")
        ]
    },
    {
        "nombre": "AnimeAV1",
        "url": "https://pigamer37.alwaysdata.net/onAirCatalogs=animeflv%2Canimeav1%2Chenaojara%2Ctioanime%2Canimejara%2Cjkanime&externalStreams=true",
        "catalogos": [
            ("AnimeAV1", "animeav1")
        ]
    },
    {
        "nombre": "Henaojara",
        "url": "https://pigamer37.alwaysdata.net/onAirCatalogs=animeflv%2Canimeav1%2Chenaojara%2Ctioanime%2Canimejara%2Cjkanime&externalStreams=true",
        "catalogos": [
            ("Henaojara", "henaojara")
        ]
    },
    {
        "nombre": "Latanime",
        "url": "https://pigamer37.alwaysdata.net/onAirCatalogs=animeflv%2Canimeav1%2Chenaojara%2Ctioanime%2Canimejara%2Cjkanime&externalStreams=true",
        "catalogos": [
            ("Latanime", "latanime")
        ]
    },
    {
        "nombre": "TioAnime",
        "url": "https://pigamer37.alwaysdata.net/onAirCatalogs=animeflv%2Canimeav1%2Chenaojara%2Ctioanime%2Canimejara%2Cjkanime&externalStreams=true",
        "catalogos": [
            ("TioAnime", "tioanime")
        ]
    }
]


class LectorHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.datos = []
        self.en_title = False

    def handle_starttag(self, tag, attrs):
        atributos = dict(attrs)

        if tag == "title":
            self.en_title = True

        if tag == "meta":
            nombre = atributos.get("name", "").lower()
            contenido = atributos.get("content", "")

            if nombre in ("description", "keywords"):
                self.datos.append(contenido)

    def handle_endtag(self, tag):
        if tag == "title":
            self.en_title = False

    def handle_data(self, data):
        if self.en_title:
            self.datos.append(data)


def normalizar(texto):
    texto = str(texto or "").lower()
    texto = unicodedata.normalize("NFKD", texto)

    return "".join(
        c for c in texto
        if not unicodedata.combining(c)
    )


def es_latino_por_titulo(titulo):
    texto = normalizar(titulo)

    indicadores = [
        "latino",
        "latinoamericano",
        "espanol latino"
    ]

    return any(x in texto for x in indicadores)



TITULOS_ALTERNATIVOS = {
    "attack on titan": ["Shingeki no Kyojin"],
    "shingeki no kyojin": ["Attack on Titan"],

    "your lie in april": ["Shigatsu wa Kimi no Uso"],
    "shigatsu wa kimi no uso": ["Your Lie in April"],

    "erased": ["Boku dake ga Inai Machi"],
    "boku dake ga inai machi": ["Erased"],

    "tokyo ghoul": ["Tokyo Kushu"],
    "tokyo kushu": ["Tokyo Ghoul"],
}


def obtener_busquedas(titulo):
    normalizado = normalizar(titulo)
    alternativas = TITULOS_ALTERNATIVOS.get(normalizado, [])
    return [titulo] + alternativas


def coincide_titulo(nombre, consulta):
    palabras_vacias = {
        "to", "the", "a", "an", "of", "and",
        "de", "la", "el", "los", "las", "y"
    }

    palabras_consulta = {
        x for x in re.findall(r"[a-z0-9]+", normalizar(consulta))
        if x not in palabras_vacias
    }

    palabras_nombre = {
        x for x in re.findall(r"[a-z0-9]+", normalizar(nombre))
    }

    if not palabras_consulta:
        return False

    coincidencias = palabras_consulta.intersection(palabras_nombre)

    # Para búsquedas de una sola palabra, exigir coincidencia exacta.
    if len(palabras_consulta) == 1:
        return bool(coincidencias)

    # Para títulos compuestos, exigir al menos un 75 % de coincidencia.
    return len(coincidencias) / len(palabras_consulta) >= 0.75


def consultar_catalogo(base, tipo, catalogo, titulo):
    url = (
        f"{base}/catalog/"
        f"{quote(tipo, safe='')}/"
        f"{quote(catalogo, safe='')}/search="
        f"{quote(titulo, safe='')}.json"
    )

    respuesta = requests.get(url, timeout=20)
    respuesta.raise_for_status()

    datos = respuesta.json()
    return datos.get("metas", [])


def consultar_metadatos(base, tipo, identificador):
    url = (
        f"{base}/meta/"
        f"{quote(tipo, safe='')}/"
        f"{quote(str(identificador), safe=':')}.json"
    )

    respuesta = requests.get(url, timeout=20)
    respuesta.raise_for_status()

    datos = respuesta.json()
    return datos.get("meta") or {}


def detectar_subtitulos_web(url, titulo_esperado=None):
    if not url:
        return False

    try:
        datos_url = urlparse(url)

        if datos_url.scheme != "https":
            return False

        if datos_url.hostname not in (
            "animeav1.com",
            "www.animeav1.com"
        ):
            return False

        respuesta = requests.get(
            url,
            timeout=20,
            headers={
                "User-Agent": "Mozilla/5.0 BUSCADOR3.0"
            },
            allow_redirects=False
        )

        if respuesta.status_code != 200:
            return False

        lector = LectorHTML()
        lector.feed(
            respuesta.content.decode(
                "utf-8",
                errors="replace"
            )
        )

        texto = normalizar(" ".join(lector.datos))

        if titulo_esperado:
            texto_compacto = re.sub(
                r"[^a-z0-9]", "", texto
            )

            titulo_compacto = re.sub(
                r"[^a-z0-9]",
                "",
                normalizar(titulo_esperado)
            )

            if (
                not titulo_compacto
                or titulo_compacto not in texto_compacto
            ):
                return False

        patrones = [
            r"sub\s*espanol",
            r"subtitulos?\s+en\s+espanol",
            r"subtitulado\s+al\s+espanol",
            r"sub\s+spanish",
            r"spanish\s+subtitles"
        ]

        return any(
            re.search(patron, texto)
            for patron in patrones
        )

    except Exception:
        return False


def obtener_tipo(meta, elemento, tipo_catalogo, fuente):
    tipo = str(
        meta.get("type")
        or elemento.get("type")
        or tipo_catalogo
    ).lower()

    if "movie" in tipo:
        return "Película"

    if "anime" in tipo or fuente == "AnimeAV1":
        return "Anime / serie"

    if "series" in tipo:
        return "Serie"

    return "Contenido"


def obtener_enlace(meta, elemento):
    url = meta.get("website") or elemento.get("website")

    if not url:
        return None

    try:
        datos = urlparse(url)

        if datos.scheme == "https" and datos.hostname:
            return url

    except Exception:
        pass

    return None



def clasificar_contenido(nombre, tipo_contenido, tipo_catalogo, exacto):
    texto = normalizar(nombre)
    tipo = normalizar(tipo_contenido)
    catalogo = normalizar(tipo_catalogo)

    es_pelicula = (
        "movie" in catalogo
        or "pelicula" in tipo
        or bool(re.search(r"\b(movie|film|gekijouban)\b", texto))
    )

    if exacto:
        if es_pelicula:
            return "Película principal", 0
        return "Serie principal", 0

    if re.search(r"\b(ova|oad|special|especial)\b", texto):
        return "OVA / especial", 3

    if re.search(r"\b(movie|film|gekijouban)\b", texto):
        return "Película relacionada", 2

    if (
        re.search(r"\b(season|temporada|part|2nd|3rd|4th|cour)\b", texto)
        or "final season" in texto
        or "kanketsu-hen" in texto
        or ":re" in texto
    ):
        return "Temporada / continuación", 1

    if re.search(r"\b(jack|pinto)\b", texto):
        return "OVA / especial", 3

    return "Contenido relacionado", 4

def buscar_catalogos(titulo, estructurado=False):
    aceptados = []
    vistos = set()

    busquedas = obtener_busquedas(titulo)

    for fuente in FUENTES:
        base = fuente["url"]

        for tipo_catalogo, catalogo in fuente["catalogos"]:
            for busqueda in busquedas:
                try:
                    elementos = consultar_catalogo(
                        base,
                        tipo_catalogo,
                        catalogo,
                        busqueda
                    )

                    for elemento in elementos[:10]:
                        nombre = elemento.get("name", "Sin título")
                        identificador = elemento.get("id")

                        if not identificador:
                            continue

                        if es_latino_por_titulo(nombre):
                            continue

                        tipo_meta = elemento.get("type")
                        if not tipo_meta:
                            tipo_meta = (
                                "movie"
                                if tipo_catalogo.lower() == "movie"
                                else "series"
                            )

                        try:
                            meta = consultar_metadatos(
                                base,
                                tipo_meta,
                                identificador
                            )
                        except Exception:
                            meta = {}

                        if not meta:
                            meta = elemento

                        nombre_final = meta.get("name", nombre)

                        if not coincide_titulo(nombre_final, busqueda):
                            continue

                        clave = (fuente["nombre"], identificador)

                        if clave in vistos:
                            continue

                        vistos.add(clave)

                        exacto = (
                            normalizar(nombre_final)
                            == normalizar(busqueda)
                        )

                        coincidencia = (
                            "Título coincidente"
                            if exacto
                            else "Título relacionado"
                        )

                        subtitulos = meta.get("subtitles", [])
                        resultado_idioma = evaluar_idioma(
                            meta,
                            subtitulos
                        )

                        if resultado_idioma["estado"] == "DESCARTAR":
                            continue

                        motivo = resultado_idioma["motivo"]
                        if resultado_idioma["estado"] == "DESCONOCIDO":
                            verificacion = "Idioma desconocido: comprobar manualmente audio y subtítulos"
                        else:
                            verificacion = "Idioma declarado en los metadatos"

                        if not motivo:
                            continue

                        anio = (
                            meta.get("year")
                            or meta.get("releaseInfo")
                            or elemento.get("year")
                            or elemento.get("releaseInfo")
                            or "Desconocido"
                        )

                        tipo_contenido = obtener_tipo(
                            meta,
                            elemento,
                            tipo_catalogo,
                            fuente["nombre"]
                        )

                        enlace = obtener_enlace(meta, elemento)

                        categoria, prioridad = clasificar_contenido(
                            nombre_final,
                            tipo_contenido,
                            tipo_catalogo,
                            exacto
                        )

                        ficha = (
                            f"🎬 {nombre_final}\n"
                            f"📁 Tipo: {tipo_contenido}\n"
                            f"📂 Categoría: {categoria}\n"
                            f"📌 Coincidencia: {coincidencia}\n"
                            f"📅 Año: {anio}\n"
                            f"🌐 Fuente: {fuente['nombre']}\n"
                            f"🗣️ Idioma: {motivo}\n"
                            f"ℹ️ {verificacion}\n"
                            f"⚠️ No se ha verificado el archivo "
                            f"de audio o subtítulos."
                        )

                        if enlace:
                            ficha += f"\n🔗 Ficha: {enlace}"

                        anio_numero = int(__import__("re").search(
                            r"\d{4}", str(anio)
                        ).group()) if __import__("re").search(
                            r"\d{4}", str(anio)
                        ) else 9999

                        nombre_orden = normalizar(nombre_final)

                        if "2nd season" in nombre_orden:
                            orden_temporada = 2
                        elif "3rd season" in nombre_orden:
                            orden_temporada = 3
                        elif "4th season" in nombre_orden:
                            orden_temporada = 4
                        else:
                            orden_temporada = 1

                        datos_resultado = {
                            "id_origen": identificador,
                            "tipo_origen": tipo_meta,
                            "titulo": nombre_final,
                            "tipo": tipo_contenido,
                            "categoria": categoria,
                            "anio": str(anio),
                            "fuente": fuente["nombre"],
                            "url_fuente": base,
                            "catalogo": catalogo,
                            "tipo_catalogo": tipo_catalogo,
                            "enlace": enlace,
                            "coincidencia": coincidencia,
                            "estado_idioma": resultado_idioma["estado"],
                            "motivo_idioma": motivo,
                            "verificacion_idioma": verificacion,
                            "prioridad": prioridad,
                            "ficha_texto": ficha
                        }

                        aceptados.append((
                            prioridad,
                            anio_numero,
                            orden_temporada,
                            ficha,
                            datos_resultado
                        ))

                except Exception as error:
                    print(
                        "Error en",
                        fuente["nombre"],
                        ":",
                        error
                    )
                    continue

    aceptados.sort(
        key=lambda resultado: (
            resultado[0],
            resultado[1],
            resultado[2]
        )
    )
    if estructurado:
        return [
            datos
            for prioridad, anio, orden_temporada, ficha, datos in aceptados
        ]

    return [
        ficha
        for prioridad, anio, orden_temporada, ficha, datos in aceptados
    ]
