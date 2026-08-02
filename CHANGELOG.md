# Changelog

Todas as mudanças notáveis deste projeto serão documentadas neste arquivo.

Cada versão leva o nome de uma pedra/rocha/cristal, começando das mais comuns e
subindo de valor a cada fase do [ROADMAP](ROADMAP.md) concluída.

## [Não lançado]

## [0.3.0] - Ametista - 2026-08-02

Fase 3 (Automação) do roadmap concluída.

### Adicionado
- Fila de processamento (`shortsgen queue add/list/run/retry`): tabela `queue` em SQLite com deduplicação por chave normalizada (ID do vídeo pra URLs do YouTube, caminho absoluto resolvido pra arquivos locais) via índice único parcial (só considera itens pendentes/rodando, não bloqueia reprocessar depois). Itens travados em `running` por uma execução anterior interrompida são recuperados automaticamente na próxima chamada de `queue run`. Retry automático configurável via `QUEUE_MAX_RETRIES` (padrão 3 tentativas no total); esgotado o limite, o item vira erro terminal e pode ser reenfileirado manualmente com `queue retry <id>`.
- Rastreamento de publicação (`shortsgen clips list/next-pending/mark-published`): tabela `clips` em SQLite registra cada clipe gerado (`run_id`, caminho, título) e seu status de publicação. `clips next-pending` imprime o próximo clipe não publicado em JSON puro, pensado pra automação externa (ex.: n8n via node Execute Command) buscar o que falta subir e marcar como publicado depois do upload, sem precisar de node de banco de dados dedicado.
- Fluxo de publicação ponta a ponta via n8n: Schedule Trigger (3 horários/dia) → `queue run` → `clips next-pending` → upload no YouTube → `clips mark-published`. Testado com vídeo real, upload confirmado. `output_dir` servido via `python -m http.server` local pro node HTTP Request do n8n ler o binário (workaround pra uma incompatibilidade do node nativo `Read/Write Files from Disk` nesta máquina).
- Metadata automática de publicação: o mesmo pedido ao Gemini que gera os highlights agora também gera descrição, tags, hashtags e categoria (mapeada para o ID oficial do YouTube a partir de uma lista fixa de 10 categorias). `clips next-pending` já devolve tudo pronto pro upload (descrição com hashtags anexadas, tags como lista, `category_id`).
- Painéis de Fila e Publicação na TUI: contagens (pendente/rodando/concluído/erro da fila; aguardando publicar/publicados) atualizando a cada 5s, mesmo padrão dos painéis existentes.
- `shortsgen tui` agora sobe automaticamente o n8n e o servidor de arquivos de `output/` (cada um numa janela própria, com as variáveis de ambiente certas) se ainda não estiverem rodando — não duplica se já estiverem de pé.
- O botão "Gerar" da TUI agora também passa pela fila (`queue add` + acompanhamento do mesmo item), não só o `queue run` externo — o painel de Fila reflete qualquer execução, venha de onde vier. Cancelamento pela TUI devolve o item pra `pending` sem contar como erro de retry.
- `shortsgen clips cleanup`: apaga do disco os clipes publicados há mais de `CLIP_RETENTION_DAYS` dias (padrão 10, configurável via `.env`), marcando `deleted_at` no banco pra não tentar de novo.
- `shortsgen clips archive <id>`: move o arquivo do clipe pra `output/postado/` e atualiza o caminho no banco na mesma operação, mantendo o `clips cleanup` consistente mesmo depois do arquivo ser movido.
- `clips next-pending` agora escolhe aleatoriamente entre os clipes pendentes (não mais o mais antigo primeiro) — evita publicar sempre na mesma ordem/sequência dos vídeos processados.
- Retry automático de transcrição (Whisper) e highlights (Gemini) dentro do próprio pipeline (`PIPELINE_RETRY_ATTEMPTS`, padrão 3, com `PIPELINE_RETRY_DELAY_SECONDS` entre tentativas) — falhas transitórias de rede/API não derrubam a execução inteira nem forçam reprocessar desde o download. `clips mark-published` agora aceita `--video-id` pra guardar o ID do vídeo no YouTube (auditoria). Retry do upload e idempotência do fluxo n8n resolvidos via "Retry On Fail" nos nodes (configuração, não código).

### Corrigido
- SDK do Gemini corrompia (perda irreversível, não só exibição) títulos de highlight com acentos quando o Python rodava sem modo UTF-8 no Windows (`locale.getpreferredencoding()` caindo pro codepage cp1252 do sistema). Causa raiz confirmada isolando a chamada ao Gemini com/sem `PYTHONUTF8=1`. Novo check em `shortsgen doctor` (`Modo UTF-8 do Python`) detecta o ambiente errado antes de gerar clipes.

## [0.2.0] - Ágata - 2026-08-01

Fase 2 (Operação) do roadmap concluída.

### Corrigido
- Split-screen do reenquadramento (`reframe.py`) quase nunca ativava em vídeos reais de 2 pessoas. Causa raiz medida em footage real (podcast 1920x1080): `_MIN_FACE_AREA_RATIO` (1%) descartava os dois rostos na maioria dos frames, porque em enquadramento de 2 pessoas dividindo o frame os rostos reais ficam entre ~0.7%-1.4% da área — bem em cima do corte antigo. Ajustado pra 0.6% (medido: falsos-positivos de fundo ficam em ~0.4-0.5%, dá margem segura). Resultado no teste real: 0% → ~61% do tempo em split-screen, sem falso-positivo em vídeo de 1 pessoa (regressão testada).
- `_debounce_mode` exigia detecção **contínua e sem falhas** por 1.2s pra confirmar troca de modo — qualquer soluço isolado de detecção reiniciava a contagem do zero. Trocado por voto de maioria numa janela deslizante (65% das amostras) — tolera falhas pontuais de detecção sem reiniciar a janela inteira.

### Adicionado
- Histórico de execuções em SQLite (`data/shortsgen.db`): estados do pipeline (`running`/`success`/`error`), mensagem de erro e tempo por etapa (download, transcrição, highlights, render).
- Comando `shortsgen stats`: shorts gerados hoje, execuções com erro hoje e tempo médio por etapa.
- Comando `shortsgen tui`: painel interativo em Textual — status dos serviços e estatísticas do dia atualizando sozinhos a cada 5s, com um campo para colar uma URL/arquivo e rodar o pipeline dali mesmo, acompanhando o progresso ao vivo (etapa atual, barra de progresso por clipe e log da execução).
- `pipeline_runner.py`: orquestração do pipeline extraída do `cli.py` para um `ProgressReporter` reutilizável — CLI (`rich`) e TUI (`textual`) compartilham a mesma lógica, cada um só troca como o progresso é exibido.
- `health.py` e `get_daily_stats` (em `history.py`): checks do `doctor` e cálculo de estatísticas viraram funções compartilhadas, reaproveitadas tanto pela CLI quanto pelo TUI.
- Progresso real de download no painel: hooks nativos do yt-dlp (bytes baixados/total) refletidos na barra de progresso.
- Estimativa de progresso da transcrição: como o faster-whisper não reporta progresso incremental, a barra estima o percentual a partir do tempo decorrido e de um fator (`tempo de transcrição / duração do vídeo`) calculado com a média do próprio histórico (`get_transcription_factor`) — melhora sozinho conforme mais vídeos rodam. Nova coluna `runs.source_duration_seconds` (com migração automática pra bancos já existentes) guarda a duração de cada vídeo processado.
- Timestamp (`dd/mm/aaaa hh:mm:ss`) em cada linha do log de atividades do painel.
- Botão **Cancelar** no painel: interrompe download, highlights e render (ffmpeg/reframe mortos na hora via `cancel_event`) de forma limpa. A transcrição (Whisper) não tem ponto de interrupção no meio — o cancelamento nesse caso só é aplicado assim que a transcrição atual terminar. Novo estado `cancelled` no histórico (distinto de `error`).

### Corrigido
- `work_dir`/`output_dir`/`log_dir`/`db_path`/`.env` agora são resolvidos sempre em relação à raiz do projeto (onde está o `pyproject.toml`), não mais em relação ao diretório de onde o comando foi chamado. Antes, rodar o CLI/TUI de dentro de `output/` (por exemplo) recriava silenciosamente `temp/`, `output/`, `logs/` e `data/` aninhados ali dentro.
- Reporter do TUI agora falha de forma silenciosa (só loga) se o painel já tiver sido fechado enquanto uma execução ainda rodava em background — antes, essa falha de UI podia sobrescrever o resultado real da execução no histórico.

### Performance
- `WHISPER_CPU_THREADS=4` (novo, configurável): benchmark real mostrou 4 threads explícitos ~9% mais rápido que o padrão implícito da lib e que usar os 8 threads lógicos (SMT) da CPU — matriz/CPU-bound não ganha com hyperthreading, só sofre contenção. Ajustar pro número de núcleos físicos da CPU, não threads lógicos.

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
