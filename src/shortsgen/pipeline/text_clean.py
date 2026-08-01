import re

# Vicios de linguagem/interjeicoes de preenchimento comuns em PT-BR e EN.
# Deliberadamente NAO inclui palavras ambiguas (ex: "um" em portugues e artigo,
# nao filler) para nao corromper o sentido do texto.
_FILLERS = [
    "né", "ne", "tipo", "sabe", "ahn", "hã", "hein", "uhum", "uhn",
    "hum", "hmm", "éh", "eh", "aham", "tá", "ta",
    "uh", "uhh", "umm", "hmm",
]

_FILLER_PATTERN = re.compile(
    r"(?<!\w)(" + "|".join(re.escape(f) for f in sorted(_FILLERS, key=len, reverse=True)) + r")(?!\w)[,.]?\s*",
    re.IGNORECASE,
)

# Colapsa palavras repetidas em sequencia (gagueira/hesitacao): "eu eu eu acho" -> "eu acho"
_REPEAT_WORD_PATTERN = re.compile(r"\b(\w+)(\s+\1\b){1,}", re.IGNORECASE)

_MULTI_SPACE = re.compile(r"\s{2,}")


def clean_for_prompt(text: str) -> str:
    """Remove vicios de linguagem e repeticoes para encolher o texto mandado pro Gemini.

    Usado apenas na hora de montar o prompt de deteccao de highlights -- a
    transcricao original (com word-level timestamps) usada pra cortar e legendar
    os clipes NAO passa por aqui e permanece intacta.
    """
    cleaned = _REPEAT_WORD_PATTERN.sub(r"\1", text)
    cleaned = _FILLER_PATTERN.sub("", cleaned)
    cleaned = _MULTI_SPACE.sub(" ", cleaned).strip()
    return cleaned
