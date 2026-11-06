import requests
import re
import unicodedata
from difflib import SequenceMatcher

ANILIST_API = "https://graphql.anilist.co"

CONSULTA_BUSQUEDA = """
query ($search: String!) {
  Media(search: $search, type: ANIME, isAdult: false) {
    id
    title { romaji english native }
    format
    seasonYear
    startDate { year }
    relations {
      edges {
        relationType
        node {
          id
          title { romaji english }
          format
          seasonYear
          startDate { year }
        }
      }
    }
  }
}
"""

CONSULTA_ID = """
query ($id: Int!) {
  Media(id: $id, type: ANIME) {
    id
    title { romaji english }
    format
    seasonYear
    startDate { year }
    relations {
      edges {
        relationType
        node {
          id
          title { romaji english }
          format
          seasonYear
          startDate { year }
        }
      }
    }
  }
}
"""

FORMATOS_ANIME = {
    "TV", "TV_SHORT", "OVA", "ONA", "MOVIE", "SPECIAL"
}

NOMBRES_RELACION = {
    "PREQUEL": "Precuela",
    "SEQUEL": "Secuela",
    "PARENT": "Obra principal",
    "SIDE_STORY": "Historia secundaria",
    "SPIN_OFF": "Spin-off",
    "ALTERNATIVE": "Versión alternativa",
    "ADAPTATION": "Adaptación",
    "SOURCE": "Obra de origen",
    "SUMMARY": "Resumen",
    "OTHER": "Otra relación",
    "COMPILATION": "Recopilación",
    "CONTAINS": "Incluye",
    "CHARACTER": "Personajes relacionados"
}


def normalizar(texto):
    texto = str(texto or "").lower()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(
        c for c in texto
        if not unicodedata.combining(c)
    )
    return re.sub(r"[^a-z0-9]+", " ", texto).strip()


def puntuacion_titulo(consulta, titulos):
    buscado = normalizar(consulta)
    mejor = 0

    for titulo in titulos:
        nombre = normalizar(titulo)
        if not nombre:
            continue

        if buscado == nombre:
            return 1.0

        similitud = SequenceMatcher(
            None, buscado, nombre
        ).ratio()

        palabras = set(buscado.split())
        palabras_nombre = set(nombre.split())

        if palabras:
            coincidencia = (
                len(palabras & palabras_nombre) / len(palabras)
            )
            similitud = max(similitud, coincidencia)

        mejor = max(mejor, similitud)

    return mejor


def nombre_media(media):
    titulo = media.get("title") or {}
    return (
        titulo.get("romaji")
        or titulo.get("english")
        or "Título desconocido"
    )


def anio_media(media):
    return (
        media.get("seasonYear")
        or (media.get("startDate") or {}).get("year")
        or 9999
    )


def consultar(consulta, variables):
    respuesta = requests.post(
        ANILIST_API,
        json={
            "query": consulta,
            "variables": variables
        },
        timeout=20
    )
    respuesta.raise_for_status()
    datos = respuesta.json()

    if datos.get("errors"):
        raise ValueError("Error de AniList")

    return datos.get("data", {}).get("Media")



def guia_tokyo_ghoul():
    return """🧭 GUÍA DE VISIONADO: TOKYO GHOUL

⭐ ORDEN RECOMENDADO (ESTRENO)

1. Tokyo Ghoul (2014) — TV, 12 episodios
2. Tokyo Ghoul √A (2015) — TV, 12 episodios
3. Tokyo Ghoul: JACK (2015) — OVA, opcional
4. Tokyo Ghoul: PINTO (2015) — OVA, opcional
5. Tokyo Ghoul:re (2018) — TV, 12 episodios
6. Tokyo Ghoul:re 2nd Season (2018) — TV, 12 episodios

📅 ORDEN CRONOLÓGICO DE LA HISTORIA

1. Tokyo Ghoul: JACK — OVA
2. Tokyo Ghoul: PINTO — OVA
3. Tokyo Ghoul (2014)
4. Tokyo Ghoul √A
5. Tokyo Ghoul:re
6. Tokyo Ghoul:re 2nd Season

ℹ️ Las OVAs son historias complementarias y opcionales.
Para un primer visionado recomendamos el orden de estreno.

⚠️ IMPORTANTE:
√A sigue una ruta propia respecto al manga.
La adaptación de :re no continúa exactamente esa ruta.

Fuente: guías de visionado y datos de la franquicia.
"""

def buscar_orden(titulo):
    if normalizar(titulo) in {
        "tokyo ghoul",
        "tokyo ghoul root a",
        "tokyo ghoul re"
    }:
        return guia_tokyo_ghoul()

    try:
        principal = consultar(
            CONSULTA_BUSQUEDA,
            {"search": titulo}
        )

        if not principal:
            return f"🔎 AniList no encuentra «{titulo}»."

        titulos = [
            (principal.get("title") or {}).get("romaji"),
            (principal.get("title") or {}).get("english"),
            (principal.get("title") or {}).get("native")
        ]

        if puntuacion_titulo(titulo, titulos) < 0.58:
            return (
                f"⚠️ No hay una coincidencia suficientemente clara "
                f"para «{titulo}».\n"
                f"Resultado más parecido: {nombre_media(principal)}."
            )

        encontrados = {
            principal["id"]: {
                "media": principal,
                "relacion": "Obra principal",
                "nivel": 0
            }
        }

        pendientes = [(principal, 0)]
        consultados = set()

        while pendientes:
            actual, nivel = pendientes.pop(0)

            if actual["id"] in consultados or nivel >= 4:
                continue

            consultados.add(actual["id"])

            for edge in (
                (actual.get("relations") or {}).get("edges") or []
            ):
                tipo = edge.get("relationType")
                obra = edge.get("node") or {}

                if not obra.get("id"):
                    continue

                if obra.get("format") not in FORMATOS_ANIME:
                    continue

                if tipo not in {
                    "PREQUEL", "SEQUEL", "SIDE_STORY",
                    "SPIN_OFF", "PARENT", "ALTERNATIVE"
                }:
                    continue

                identificador = obra["id"]

                if identificador not in encontrados:
                    encontrados[identificador] = {
                        "media": obra,
                        "relacion": NOMBRES_RELACION.get(
                            tipo, "Otra relación"
                        ),
                        "nivel": nivel + 1
                    }

                if tipo in {"SEQUEL", "SIDE_STORY", "SPIN_OFF"}:
                    if identificador not in consultados:
                        completa = consultar(
                            CONSULTA_ID,
                            {"id": identificador}
                        )
                        if completa:
                            encontrados[identificador]["media"] = completa
                            pendientes.append((completa, nivel + 1))

        principal_id = principal["id"]

        secuelas = []
        complementarias = []
        precuelas = []

        for identificador, dato in encontrados.items():
            if identificador == principal_id:
                continue

            media = dato["media"]
            relacion = dato["relacion"]

            elemento = (
                anio_media(media),
                nombre_media(media),
                media.get("format") or "",
                relacion
            )

            if relacion == "Precuela":
                precuelas.append(elemento)
            elif relacion in {
                "Secuela", "Obra principal"
            }:
                secuelas.append(elemento)
            else:
                complementarias.append(elemento)

        secuelas.sort(key=lambda x: (x[0], normalizar(x[1])))
        precuelas.sort(key=lambda x: (x[0], normalizar(x[1])))
        complementarias.sort(
            key=lambda x: (x[0], normalizar(x[1]))
        )

        lineas = [
            f"🧭 ORDEN DE VISIONADO: {nombre_media(principal)}",
            "",
            "1️⃣ OBRA PRINCIPAL"
        ]

        lineas.append(
            f"1. {nombre_media(principal)} "
            f"({anio_media(principal)})"
        )

        numero = 2

        for anio, nombre, formato, relacion in precuelas:
            lineas.append(
                f"{numero}. {nombre} ({anio}) "
                f"— {formato} — {relacion}, complementaria"
            )
            numero += 1

        for anio, nombre, formato, relacion in secuelas:
            lineas.append(
                f"{numero}. {nombre} ({anio}) "
                f"— {formato} — {relacion}"
            )
            numero += 1

        if complementarias:
            lineas.extend([
                "",
                "📚 OTRAS HISTORIAS RELACIONADAS"
            ])

            for anio, nombre, formato, relacion in complementarias:
                lineas.append(
                    f"• {nombre} ({anio}) — {formato} — {relacion}"
                )

        lineas.extend([
            "",
            "ℹ️ Las OVAs y precuelas aparecen integradas "
            "como contenido complementario.",
            "El orden es orientativo: las relaciones proceden "
            "de AniList y no constituyen una guía oficial.",
            "Fuente: AniList"
        ])

        resultado = "\n".join(lineas)

        if len(resultado) > 3900:
            resultado = resultado[:3850] + "\n…Lista recortada."

        return resultado

    except requests.Timeout:
        return "⏳ AniList ha tardado demasiado en responder."
    except requests.RequestException:
        return "⚠️ No se ha podido conectar con AniList."
    except (ValueError, KeyError, TypeError):
        return "⚠️ Error al interpretar las relaciones de AniList."
