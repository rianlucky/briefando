# shortsgen

Gerador automatico de shorts/clipes verticais a partir de videos longos (YouTube ou arquivo local), estilo Opus Clip:

1. Baixa o video (yt-dlp) ou usa um arquivo local
2. Transcreve com timestamps por palavra (faster-whisper, local)
3. Pergunta ao Gemini quais trechos tem mais potencial de viralizar
4. Corta cada trecho, reenquadra pra 9:16 seguindo o rosto de quem fala (mediapipe/opencv)
5. Queima legenda sincronizada
6. Salva os clipes finais em `output/`

## Setup

```sh
uv sync
cp .env.example .env
# edite .env e coloque sua GEMINI_API_KEY
```

## Uso

```sh
uv run python -m shortsgen.cli generate "https://www.youtube.com/watch?v=XXXXXXXX"
uv run python -m shortsgen.cli generate "C:\videos\podcast.mp4" --max-clips 3
```

Antes de rodar pela primeira vez (ou se algo der errado), confira se as dependencias e configuracoes estao OK:

```sh
uv run python -m shortsgen.cli doctor
```

Logs de cada execucao (incluindo tracebacks de erro) ficam em `logs/shortsgen.log`. Em caso de falha, os arquivos temporarios da execucao (`temp/<run_id>/`) sao preservados em vez de apagados, pra nao perder o download/transcricao ja feitos.

Todo run fica registrado em `data/shortsgen.db` (SQLite): estado (rodando/sucesso/erro), tempo gasto em cada etapa e mensagem de erro quando falha. Pra ver um resumo:

```sh
uv run python -m shortsgen.cli stats
```

> Nesta maquina, o antivirus bloqueia o executavel `shortsgen.exe` que o uv gera
> (launcher generico nao assinado). Por isso rodamos via `python -m shortsgen.cli`
> em vez de `uv run shortsgen`. Se isso nao acontecer na sua maquina, `uv run shortsgen`
> tambem funciona normalmente.

## Requisitos de sistema

- Python 3.12 ou 3.13
- ffmpeg no PATH
- uv (`python-preference = "only-system"` esta fixado no pyproject.toml porque o
  Python que o proprio uv baixaria e bloqueado pelo antivirus nesta maquina)
