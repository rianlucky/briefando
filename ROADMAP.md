# 🚀 Briefando Roadmap

>Status: MVP Funcional ✅

---

# 🚀 FASE 1 — Fundação

## Auditoria

- [x] Auditoria arquitetural completa (2026-08-01 — ver relatório da sessão)
- [x] Ajustar pontos encontrados:
  - [x] Não apagar `run_dir`/temp quando o pipeline falha (2026-08-01)
  - [x] Validar `GEMINI_API_KEY` cedo, antes de baixar/transcrever (2026-08-01)
  - [x] Timeout nas chamadas de `subprocess` (ffmpeg) (2026-08-01)
- [x] Remover código morto (`Transcript.as_timestamped_text` removido, 2026-08-01)
- [x] Padronizar estrutura de pastas (já adequada — confirmado na auditoria)
- [x] Padronizar nomenclatura (já adequada — confirmado na auditoria)

## Configuração

- [x] Criar arquivo .env (já existe localmente)
- [x] Config centralizada (já existe via `config.py`/pydantic-settings)
- [ ] Configuração por canal (adiado de propósito: só existe 1 canal hoje, não há caso real pra validar o design ainda — decisão em 2026-08-01, revisitar na Fase 5)
- [x] Configuração dos modelos (`gemini_model`, `whisper_model_size`, `whisper_device`, `whisper_compute_type` via .env)
- [ ] Configuração de idiomas (adiado de propósito: só existe 1 idioma de saída hoje, evitar abstração prematura — decisão em 2026-08-01, revisitar na Fase 5)
- [x] Configuração de diretórios (`work_dir`, `output_dir` agora documentados em `.env.example`)
- [x] Completar `.env.example` (`WHISPER_COMPUTE_TYPE`, `CLIP_MIN_SECONDS`, `CLIP_MAX_SECONDS`, `WORK_DIR`, `OUTPUT_DIR`, 2026-08-01)

## Robustez

- [x] Health Check (comando `shortsgen doctor`: ffmpeg, GEMINI_API_KEY, diretórios graváveis, 2026-08-01)
- [x] Logger único (`logging` em arquivo `logs/shortsgen.log`, complementando o `rich.Console` interativo, 2026-08-01)
- [x] Tratamento de exceções (cli.py preserva `run_dir` e reporta erro claro em vez de falhar silenciosamente, 2026-08-01)
- [x] Timeout das APIs (Gemini 60s, yt-dlp socket_timeout 30s, ffmpeg subprocess 300s, 2026-08-01)

---

# 🛠️ FASE 2 — Operação

## Interface

- [ ] TUI
- [ ] Barra de progresso
- [ ] Pipeline em tempo real
- [ ] Status dos serviços
- [ ] Estatísticas do dia

## Pipeline

- [x] Estados do pipeline (`runs.status`: running/success/error, 2026-08-01)
- [x] Histórico SQLite (`data/shortsgen.db`, tabelas `runs`/`run_stages`, 2026-08-01)
- [x] Histórico de erros (`runs.error_message`, 2026-08-01)
- [x] Tempo por etapa (granularidade grosseira: download/transcrição/highlights/render, 2026-08-01)

## Monitoramento

- [x] Tempo médio (comando `shortsgen stats`, 2026-08-01)
- [x] Shorts criados hoje (comando `shortsgen stats`, 2026-08-01)
- [ ] Shorts publicados (depende da etapa de publicação, ainda não implementada)
- [x] Shorts com erro (comando `shortsgen stats`, 2026-08-01)

---

# ⚙️ FASE 3 — Automação

## Fila

- [ ] Queue
- [ ] Evitar duplicações
- [ ] Retomar processamento

## Publicação

- [ ] Scheduler
- [ ] Máximo de 3 Shorts/dia
- [ ] Horários configuráveis

## Metadata

- [ ] Título
- [ ] Descrição
- [ ] Tags
- [ ] Hashtags
- [ ] Categoria

## Confiabilidade

- [ ] Retry Whisper
- [ ] Retry Gemini
- [ ] Retry Upload
- [ ] Idempotência

---

# 🧠 FASE 4 — Inteligência

## Score

- [ ] Quality Score
- [ ] Score mínimo para publicar
- [ ] Revisão manual

## Analytics

- [ ] Histórico de views
- [ ] Histórico de CTR
- [ ] Histórico de retenção
- [ ] Banco de títulos

## IA

- [ ] Aprender melhores títulos
- [ ] Aprender melhores ganchos
- [ ] Melhorar prompts automaticamente

---

# 🌎 FASE 5 — Plataforma

## Dashboard

- [ ] Dashboard Web
- [ ] Histórico
- [ ] Logs
- [ ] Estatísticas

## Multi

- [ ] Multi canais
- [ ] Multi idiomas
- [ ] Multi usuários

## Deploy

- [ ] Docker
- [ ] VPS
- [ ] Backup

## Publicadores

- [ ] YouTube
- [ ] TikTok
- [ ] Instagram
- [ ] Kwai

---

# 💡 Backlog (Ignorar por enquanto)

- [ ] Música de fundo
- [ ] Thumbnail automática
- [ ] Corte inteligente
- [ ] Banco de prompts
- [ ] API pública
- [ ] Painel financeiro
- [ ] Custos por Shorts
- [ ] Dashboard IA

---

# 🐞 Bugs conhecidos

- [ ]

---

# 📝 Ideias

- [ ]