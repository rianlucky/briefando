# Changelog

Todas as mudanças notáveis deste projeto serão documentadas neste arquivo.

Cada versão leva o nome de uma pedra/rocha/cristal, começando das mais comuns e
subindo de valor a cada fase do [ROADMAP](ROADMAP.md) concluída.

## [Não lançado]

### Adicionado
- Histórico de execuções em SQLite (`data/shortsgen.db`): estados do pipeline (`running`/`success`/`error`), mensagem de erro e tempo por etapa (download, transcrição, highlights, render).
- Comando `shortsgen stats`: shorts gerados hoje, execuções com erro hoje e tempo médio por etapa.

## [0.1.0] - Quartzo - 2026-08-01

Primeira versão versionada do projeto — MVP funcional + Fase 1 (Fundação) do roadmap.

### Adicionado
- Skill `briefando-workflow` para padronizar o fluxo de desenvolvimento (leitura de VISION/ROADMAP no início da sessão, checklist de encerramento).
- Comando `shortsgen doctor`: health check que verifica ffmpeg no PATH, `GEMINI_API_KEY` configurada e diretórios de trabalho graváveis, sem rodar o pipeline.
- Logging estruturado em `logs/shortsgen.log` (início/fim de cada etapa e traceback completo em caso de falha), complementando a saída interativa do `rich.Console`.
- Timeouts em todas as chamadas externas: Gemini (60s), yt-dlp (socket_timeout 30s), ffmpeg (300s).
- Variáveis `WHISPER_COMPUTE_TYPE`, `CLIP_MIN_SECONDS`, `CLIP_MAX_SECONDS`, `WORK_DIR`, `OUTPUT_DIR` documentadas em `.env.example`.

### Alterado
- **Breaking:** rodar o gerador agora exige o subcomando explícito `generate` (`shortsgen generate "<source>"` em vez de `shortsgen "<source>"`), necessário para acomodar o novo comando `doctor`.

### Corrigido
- Validação antecipada de `GEMINI_API_KEY`: o pipeline agora falha imediatamente com mensagem clara em vez de quebrar depois de baixar e transcrever o vídeo.
- Falhas no pipeline não apagam mais os arquivos temporários da execução (`temp/<run_id>/`) — preservados para inspeção/depuração em vez de forçar reprocessar tudo do zero.

### Removido
- Código morto: `Transcript.as_timestamped_text`, método não utilizado em nenhum lugar do código.

### Documentação
- Auditoria técnica completa da arquitetura: estrutura, configuração, prompts, pipeline, tratamento de erros, persistência, logs, performance, escalabilidade, código morto, segurança.
- ROADMAP.md atualizado com os achados da auditoria e o progresso da Fase 1 (Auditoria, Configuração, Robustez) — decisão registrada de adiar "configuração por canal" e "configuração de idiomas" para a Fase 5, evitando abstração prematura com um único canal/idioma em uso.
- README.md atualizado com o comando `doctor` e o comportamento de preservação de arquivos temporários em caso de erro.
