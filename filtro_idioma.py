import re
import unicodedata


def normalizar(valor):
    texto = str(valor or "").lower().strip()
    texto = unicodedata.normalize("NFKD", texto)
    return "".join(
        c for c in texto
        if not unicodedata.combining(c)
    )


def buscar_texto(valor):
    if isinstance(valor, dict):
        return " ".join(buscar_texto(v) for v in valor.values())
    if isinstance(valor, (list, tuple)):
        return " ".join(buscar_texto(v) for v in valor)
    return str(valor or "")


CAMPOS_AUDIO = [
    "audio", "audio_language", "audioLanguage",
    "audioLanguages", "audio_lang", "audioLang",
    "dubbing", "dub"
]

PATRONES_LATINO = [
    r"\blatino\b",
    r"\blatinoamericano\b",
    r"\bes-419\b",
    r"\bes-mx\b",
    r"\bes-ar\b",
    r"\bes-cl\b",
    r"\bes-co\b",
    r"\bes-pe\b",
    r"\bes-ve\b"
]


def audio_latino(meta):
    for campo in CAMPOS_AUDIO:
        texto = normalizar(buscar_texto(meta.get(campo)))
        if any(re.search(p, texto) for p in PATRONES_LATINO):
            return True
    return False


def audio_castellano(meta):
    patrones = [
        r"\bes-es\b",
        r"\bspa-es\b",
        r"\bcastellano\b",
        r"\bespanol de espana\b",
        r"\bspanish\s*\(\s*spain\s*\)",
        r"\bspanish\s+spain\b"
    ]

    for campo in CAMPOS_AUDIO:
        texto = normalizar(buscar_texto(meta.get(campo)))
        if any(re.search(p, texto) for p in patrones):
            return True

    return False


def subtitulos_espanol(subtitulos):
    if not isinstance(subtitulos, list):
        return False

    for subtitulo in subtitulos:
        if not isinstance(subtitulo, dict):
            continue

        datos = " ".join(
            str(subtitulo.get(campo, ""))
            for campo in [
                "lang", "language", "srclang",
                "label", "name", "title"
            ]
        )

        texto = normalizar(datos)

        # Nunca aceptar subtitulos identificados como latinos.
        if any(re.search(p, texto) for p in PATRONES_LATINO):
            continue

        patrones = [
            r"\bes\b",
            r"\bspa\b",
            r"\bspanish\b",
            r"\bespanol\b",
            r"\bcastellano\b"
        ]

        if any(re.search(p, texto) for p in patrones):
            return True

    return False


def evaluar_idioma(meta, subtitulos=None):
    meta = meta or {}

    # Descartar audio latino antes de cualquier otra comprobacion.
    if audio_latino(meta):
        return {
            "estado": "DESCARTAR",
            "motivo": "Audio latino no permitido"
        }

    if audio_castellano(meta):
        return {
            "estado": "ACEPTAR",
            "motivo": "Audio castellano de España declarado"
        }

    if subtitulos_espanol(subtitulos):
        return {
            "estado": "ACEPTAR",
            "motivo": "Subtítulos en español declarados"
        }

    return {
        "estado": "DESCONOCIDO",
        "motivo": "Idioma no declarado; comprobar audio y subtítulos manualmente"
    }
