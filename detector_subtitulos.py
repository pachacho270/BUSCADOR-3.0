import re
import unicodedata
from collections import Counter


def normalizar(texto):
    texto = unicodedata.normalize("NFKD", texto.lower())
    return "".join(
        c for c in texto
        if not unicodedata.combining(c)
    )


def limpiar_subtitulos(texto):
    texto = re.sub(r"<[^>]+>", " ", texto)
    texto = re.sub(r"\{[^}]*\}", " ", texto)
    texto = re.sub(r"^\s*\d+\s*$", " ", texto, flags=re.MULTILINE)
    texto = re.sub(
        r"\d{2}:\d{2}:\d{2}[,.]\d+\s*-->\s*.*",
        " ",
        texto
    )
    texto = re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", texto)
    return texto


def detectar_idioma_subtitulos(texto):
    texto = normalizar(limpiar_subtitulos(texto))
    palabras = re.findall(r"[a-z]+", texto)

    if len(palabras) < 80:
        return "No identificado: muestra insuficiente"

    vocabularios = {
        "español": {
            "que", "como", "pero", "porque", "para",
            "usted", "ustedes", "nosotros", "tiene",
            "tengo", "esta", "estoy", "mucho", "nada",
            "cuando", "donde", "tambien", "hombre",
            "mujer", "ahora", "quiero", "puede",
            "desde", "hasta", "aqui", "alli", "bien",
            "verdad", "todo", "todos", "ella", "ellos",
            "hacer", "ser", "estar", "tener", "dijo",
            " señor", "señor", "gracias", "casa"
        },
        "portugués": {
            "nao", "voce", "voces", "uma", "muito",
            "tambem", "entao", "estao", "porque",
            "para", "com", "como", "sao", "mais",
            "pode", "senhor", "senhora", "estou",
            "aqui", "agora", "obrigado", "obrigada"
        },
        "inglés": {
            "the", "and", "you", "that", "this",
            "with", "have", "what", "when", "where",
            "your", "there", "they", "would", "could",
            "from", "about", "because", "hello",
            "was", "were", "then", "them", "know",
            "like", "want", "here", "there", "have"
        },
        "francés": {
            "bonjour", "avec", "vous", "nous",
            "mais", "pour", "dans", "cette",
            "comme", "merci", "tout", "une",
            "pas", "est", "sont", "avoir", "être"
        },
        "alemán": {
            "und", "nicht", "ich", "ein", "eine",
            "der", "die", "das", "mit", "ist",
            "haben", "sind", "aber", "auch", "nicht"
        }
    }

    conteos = Counter()

    for idioma, vocabulario in vocabularios.items():
        conteos[idioma] = sum(
            1 for palabra in palabras
            if palabra in vocabulario
        )

    ordenados = conteos.most_common()

    if not ordenados or ordenados[0][1] < 8:
        return "No identificado"

    mejor, puntos = ordenados[0]
    segundo = ordenados[1][1]

    if puntos - segundo < 3:
        return "Idioma dudoso"

    return mejor


if __name__ == "__main__":
    print("Detector de subtítulos preparado.")
