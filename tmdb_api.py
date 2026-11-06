import os
import requests

BASE = "https://api.themoviedb.org/3"
IDIOMA = "es-ES"
PAIS = "ES"


def tmdb_get(ruta, parametros=None):
    token = os.getenv("TMDB_READ_TOKEN")

    if not token:
        raise RuntimeError("Falta configurar TMDB_READ_TOKEN")

    headers = {
        "Authorization": f"Bearer {token}",
        "accept": "application/json"
    }

    params = dict(parametros or {})
    params["language"] = IDIOMA

    respuesta = requests.get(
        BASE + ruta,
        headers=headers,
        params=params,
        timeout=20
    )

    respuesta.raise_for_status()
    return respuesta.json()


def buscar_tmdb(titulo, limite=10):
    datos = tmdb_get(
        "/search/multi",
        {"query": titulo}
    )

    resultados = []

    for obra in datos.get("results", []):
        tipo = obra.get("media_type")

        if tipo not in ("movie", "tv"):
            continue

        resultados.append({
            "id": obra.get("id"),
            "tipo": tipo,
            "titulo": obra.get("title") or obra.get("name"),
            "titulo_original": (
                obra.get("original_title")
                or obra.get("original_name")
            ),
            "anio": (
                obra.get("release_date")
                or obra.get("first_air_date")
                or ""
            )[:4],
            "sinopsis": obra.get("overview", ""),
            "poster": obra.get("poster_path"),
            "popularidad": obra.get("popularity")
        })

    return resultados[:limite]


def obtener_proveedores(tipo, identificador):
    if tipo not in ("movie", "tv"):
        return {}

    datos = tmdb_get(
        f"/{tipo}/{identificador}/watch/providers"
    )

    espana = datos.get("results", {}).get(PAIS, {})

    categorias = {}

    for clave in ("flatrate", "free", "ads", "rent", "buy"):
        categorias[clave] = [
            {
                "nombre": p.get("provider_name"),
                "id": p.get("provider_id"),
                "logo": p.get("logo_path")
            }
            for p in espana.get(clave, [])
        ]

    categorias["enlace"] = espana.get("link")
    return categorias


def obtener_ficha(tipo, identificador):
    if tipo not in ("movie", "tv"):
        raise ValueError("Tipo de contenido no válido")

    datos = tmdb_get(
        f"/{tipo}/{identificador}",
        {"append_to_response": "credits"}
    )

    creditos = datos.get("credits", {})
    reparto = []

    for persona in creditos.get("cast", [])[:10]:
        reparto.append({
            "nombre": persona.get("name"),
            "personaje": persona.get("character")
        })

    ficha = {
        "id": identificador,
        "tipo": tipo,
        "titulo": datos.get("title") or datos.get("name"),
        "titulo_original": (
            datos.get("original_title")
            or datos.get("original_name")
        ),
        "sinopsis": datos.get("overview", ""),
        "anio": (
            datos.get("release_date")
            or datos.get("first_air_date")
            or ""
        )[:4],
        "generos": [
            g.get("name") for g in datos.get("genres", [])
        ],
        "duracion": datos.get("runtime"),
        "duracion_episodio": (
            datos.get("episode_run_time", [])
        ),
        "temporadas": datos.get("number_of_seasons"),
        "episodios": datos.get("number_of_episodes"),
        "reparto": reparto,
        "poster": datos.get("poster_path"),
        "proveedores": obtener_proveedores(
            tipo, identificador
        )
    }

    return ficha


def obtener_temporada(identificador, numero):
    return tmdb_get(
        f"/tv/{identificador}/season/{numero}"
    )
