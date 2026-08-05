# 🚀 Briefando Roadmap

>Status: Fase 5 (Plataforma) em andamento ✅ (Dashboard Web concluído) — próximo: Multi-canais, Deploy, Publicadores

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

# 🛠️ FASE 2 — Operação ✅ (concluída 2026-08-01)

## Interface

- [x] TUI (`shortsgen tui`, Textual — painel interativo, 2026-08-01)
- [x] Barra de progresso (progresso ao vivo por clipe dentro do painel, 2026-08-01)
- [x] Pipeline em tempo real (painel dispara e acompanha o `run_pipeline` numa worker thread, 2026-08-01)
- [x] Status dos serviços (checks de `doctor` reaproveitados no painel, atualizando a cada 5s, 2026-08-01)
- [x] Estatísticas do dia (painel de stats reaproveitando `get_daily_stats`, atualizando a cada 5s, 2026-08-01)

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

# ⚙️ FASE 3 — Automação ✅ (concluída 2026-08-02)

## Fila

- [x] Queue
- [x] Evitar duplicações
- [x] Retomar processamento

## Publicação

- [x] Scheduler
- [x] Máximo de 3 Shorts/dia
- [x] Horários configuráveis

(implementado via n8n, 2026-08-01: Schedule Trigger com 3 regras de cron, cada uma publicando 1 clipe — o limite diário nasce do próprio agendamento, sem lógica de contagem em código)

## Metadata

- [x] Título
- [x] Descrição
- [x] Tags
- [x] Hashtags
- [x] Categoria

## Confiabilidade

- [x] Retry Whisper
- [x] Retry Gemini
- [x] Retry Upload
- [x] Idempotência

---

# 🧠 FASE 4 — Inteligência ✅ (majoritariamente concluída 2026-08-02, IA em revisão)

## Score

- [x] Quality Score
- [x] Score mínimo para publicar
- [x] Revisão manual

## Analytics

- [x] Histórico de views
- [ ] Histórico de CTR (bloqueado: métrica de impressões/CTR de Shorts não é exposta pela API pública do YouTube, só aparece no YouTube Studio manualmente — sem solução automatizada disponível, decisão 2026-08-02)
- [x] Histórico de retenção
- [x] Banco de títulos

## IA

- [ ] Aprender melhores títulos (implementado 2026-08-02, em revisão — marcar concluído após acompanhar resultados reais com mais videos)
- [ ] Aprender melhores ganchos (implementado 2026-08-02, em revisão — marcar concluído após acompanhar resultados reais com mais videos)
- [ ] Melhorar prompts automaticamente (implementado 2026-08-02, em revisão — marcar concluído após acompanhar resultados reais com mais videos)

---

# 🌎 FASE 5 — Plataforma

## Dashboard

- [x] Dashboard Web (Streamlit, 2026-08-03)
- [x] Histórico (2026-08-03)
- [x] Logs (2026-08-03)
- [x] Estatísticas (2026-08-03)

## Multi

- [ ] Multi canais
- [ ] Multi idiomas
- [ ] Multi usuários

## Deploy

- [ ] Docker
- [ ] VPS
- [ ] Backup

## Publicadores

- [x] YouTube (via n8n, scheduler + upload já em produção)
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