# Changelog

Todas as mudanças notáveis deste projeto serão documentadas neste arquivo.

Cada versão leva o nome de uma pedra/rocha/cristal, começando das mais comuns e
subindo de valor a cada fase do [ROADMAP](ROADMAP.md) concluída.

## [Não lançado]

## [0.5.3] - Esmeralda - 2026-08-04

### Adicionado
- Zoom sutil nos clipes: Ken Burns contínuo (100% → 108% ao longo do clipe) somado a um punch-in de corte seco (sem transição suave) nos picos de volume/energia da voz — detectado a partir do próprio áudio do clipe, sem custo de API nem dependência do Gemini. Só se aplica no foco em 1 pessoa; desativado no split-screen.

### Alterado
- Split-screen: cada metade agora recorta uma área proporcional ao tamanho do rosto detectado (em vez da altura inteira da fonte) — as pessoas ficam consistentemente mais "perto" no enquadramento, na mesma proporção, independente da distância real da câmera em cada vídeo.
- Split-screen: corrigida a atribuição de lado (topo/base) — antes reordenava por posição X a cada frame, o que podia trocar as pessoas de lado do nada quando elas se aproximavam ou a detecção saía ligeiramente instável. Agora cada rosto é atribuído ao lado mais próximo de onde estava no frame anterior, mantendo a identidade estável.
- Fonte das legendas trocada de Arial Black para Poppins ExtraBold (instalada localmente), com a borda do texto agora na cor da marca (`#030811`) em vez de preto.

### Corrigido
- **Bug crítico: a fila inteira parava de processar vídeos**, todos falhando com `OSError: [Errno 22] Invalid argument`. Causa raiz: `download.py` desativava mensagens do yt-dlp (`quiet: True`) mas não a barra de progresso interna dele (`noprogress`, flag separada) — rodando sem um console de verdade (via n8n Execute Command), a tentativa de escrever essa barra quebrava e derrubava o download inteiro, para qualquer vídeo. Corrigido com `"noprogress": True` (a barra de progresso do yt-dlp nunca foi usada mesmo — o progresso real já vem do nosso próprio hook).
- Dashboard: os 4 cards da Visão Geral (Hoje/Fila/Publicação/Consumo) agora ficam sempre com a mesma altura, preenchendo os mais curtos com linhas invisíveis até baterem com o mais alto — a tentativa anterior via CSS de flex/stretch não era confiável entre versões do Streamlit.
- Dashboard: gráfico "% do tempo por etapa" sem o eixo horizontal (atrapalhava mais do que ajudava) e com a legenda de volta (um `padding` anterior estava cortando ela); segmento "Download" (estreito demais pro número caber dentro) agora mostra o % por cima da barra em branco.
- Dashboard: eixo do gráfico Score × Views ajustado pra 70-100 (os dados reais ficam concentrados nessa faixa, o eixo 0-100 desperdiçava a maior parte do espaço).

## [0.5.2] - Esmeralda - 2026-08-03

### Adicionado
- `GEMINI_RETRY_DELAY_SECONDS` (novo, padrão 30s): delay entre tentativas especificamente da chamada ao Gemini, separado do delay genérico do pipeline. Erros "503 UNAVAILABLE" (modelo sobrecarregado do lado do Google) precisam de mais tempo entre tentativas que o delay genérico de 5s permitia, fazendo o retry esgotar o orçamento antes do pico de demanda passar.

## [0.5.1] - Esmeralda - 2026-08-03

### Adicionado
- `shortsgen queue run --once`: processa no máximo 1 item da fila e retorna na hora, mesmo com mais pendentes depois. Pensado pra agendadores como o n8n — sem essa flag, uma única chamada de `queue run` fica presa até drenar a fila inteira, e com vídeos longos (podcasts de 1h30-2h+) isso pode levar horas, travando o node "Execute Command" do n8n esperando o processo terminar. `queue run` sem a flag continua drenando tudo, pra uso manual no terminal.
- `GEMINI_TIMEOUT_SECONDS` (novo, padrão 300s): timeout configurável da chamada de highlights ao Gemini. O valor antigo fixo de 60s estourava com `504 DEADLINE_EXCEEDED` em vídeos longos, cuja transcrição inteira vira um prompt enorme.

## [0.5.0] - Esmeralda - 2026-08-03

Fase 5 (Plataforma) iniciada — Dashboard Web completo, mais descoberta automática de vídeos, correções de confiabilidade e uma auditoria de BI/UX.

### Adicionado
- **Dashboard Web** (`shortsgen dashboard`, Streamlit): painel visual completo com 8 páginas — Visão Geral (atividade em tempo real, seletor de período Hoje/7 dias/Mês, tempo médio por etapa, funil de conversão Enfileirado→Processado→Aprovado→Publicado, consumo de tokens Gemini e tempo de máquina), Clipes (preview de vídeo, busca por título, aprovação manual), Fila, Analytics (melhores títulos, score×views com linha de tendência e correlação, taxa de engajamento, views por dias-desde-publicação, alerta de limitação de CTR), Fontes, Revisão Manual (fluxo um-a-um) e Histórico (execuções + log filtrado). Estilizado com a paleta da marca (dourado `#FDBB11` / navy `#030811`) e gráficos em Altair/Vega-Lite.
- Rastreamento real de consumo de tokens do Gemini: `runs.gemini_input_tokens`/`gemini_output_tokens` gravam o uso reportado pela própria API (`response.usage_metadata`) a cada chamada de highlights — dá visibilidade de consumo sem precisar estimar nada.
- Descoberta automática de vídeos novos: tabela `sources` guarda canais/playlists do YouTube monitorados via RSS (atraso mínimo e duração mínima configuráveis por fonte). `shortsgen sources add/list/remove` gerencia as fontes. `queue add-if-new` adiciona um vídeo à fila só se nunca tiver sido visto antes (em qualquer status), evitando reprocessar o mesmo vídeo repetidamente conforme o feed RSS é revarrido periodicamente. Fluxo completo no n8n: Schedule Trigger → `sources list` → RSS Feed Read por fonte → filtro de atraso → checagem de duração (YouTube Data API) → `queue add-if-new`.

### Alterado
- TUI vira um painel de monitoramento puro: removido o disparo manual de vídeo (campo de URL/botões Gerar/Cancelar), já que a descoberta automática + fila cobrem esse caso agora. Novo painel "Atividade atual" mostra em tempo real a etapa, o tempo decorrido e uma barra de progresso estimada (tempo decorrido da etapa / média histórica dessa etapa) de qualquer execução em andamento, lendo direto do banco — funciona pra jobs disparados de qualquer lugar (n8n, `queue run` via CLI), não só pela própria TUI. Novo painel "Execuções recentes" com o histórico das últimas rodadas.

### Corrigido
- **Duas execuções de `queue run` simultâneas processavam o mesmo vídeo em paralelo, competindo por CPU e deixando tudo mais lento** (achado ao investigar uma execução real travada a 100% de CPU): `recover_orphans()` assumia que só existe um worker por vez e, ao rodar numa segunda `queue run` disparada pelo n8n antes da primeira terminar, devolvia pra fila um item que a primeira ainda estava processando de verdade — reiniciando o mesmo vídeo do zero em paralelo. Corrigido com um lock exclusivo de sistema operacional em `run_queue()`: uma segunda execução concorrente agora sai na hora sem mexer em nada, em vez de duplicar trabalho.
- URL enfileirada com `&list=...&index=...` baixava a playlist inteira em vez de só o vídeo (yt-dlp trata isso como playlist por padrão) — `noplaylist: True` adicionado às opções de download.
- Bloqueio do YouTube ("Sign in to confirm you're not a bot") que travava a fila inteira ao processar muitos vídeos em sequência: yt-dlp agora autentica com cookies exportados do navegador (`YTDLP_COOKIES_FILE`) e usa Node.js como runtime JS pra resolver o desafio anti-throttling do YouTube (pacote `yt-dlp-ejs`), sem os quais quase nenhum formato de vídeo fica disponível. Sem isso, downloads em lote (ex.: descoberta automática processando dezenas de vídeos) paravam de funcionar completamente.

### Performance
- Comandos leves da CLI (`queue add`, `sources list`, `clips ...`, etc.) não carregam mais as bibliotecas pesadas do pipeline (mediapipe, faster-whisper, google-genai) à toa — só `generate` e `queue run` (que realmente rodam o pipeline) pagam esse custo agora. Reduz de ~4s pra ~1.3s por chamada, importante para automações que chamam a CLI em lote (ex.: descoberta de vídeos processando dezenas de itens em sequência).
- Corrigido N+1 query no Analytics: histórico de views dos top-5 clipes vinha de 5 consultas separadas ao banco; agora é 1 consulta só (`get_clip_analytics_history_bulk`).

### Auditoria de BI/UX
Revisão crítica do dashboard (especialista UI/UX + BI + dados de negócio), aplicada item a item:
- Tendência ▲/▼ vs período anterior nos números do dia, com seletor de período (Hoje / Últimos 7 dias / Este mês).
- Linha de tendência (regressão) e correlação de Pearson no gráfico Score do Gemini × Views reais.
- Gráfico de views recortado por dias-desde-publicação (coorte) em vez de data de calendário, pra comparar clipes publicados em datas diferentes de forma justa.
- Taxa de engajamento (likes + comentários / views) — mais diagnóstico de qualidade real do conteúdo do que views cru.
- Funil de conversão Enfileirado → Processado → Aprovado → Publicado, com % de conversão por etapa.
- Aviso explícito de que CTR/impressões não aparecem por limitação da própria API do YouTube (antes só omitia silenciosamente).
- Vocabulário visual de card unificado entre todas as páginas (antes misturava HTML customizado com `st.metric` nativo); paleta categórica compartilhada num só módulo (`dashboard/components.py`).
- Badges coloridos de status (🟢🟡🔵🔴) em Clipes, Fila e Histórico, em vez de texto plano.
- Links externos da sidebar com ícone.
- % escrito dentro de cada segmento do gráfico de tempo por etapa, além da legenda.
- "Pular" na Revisão Manual agora persiste no banco (`clips.review_skipped_at`) e navega por ID do clipe em vez de posição na lista — sobrevive a reload e não quebra mais se um clipe novo chegar no meio da revisão.
- Nova página "Configurações" (somente leitura) mostrando os parâmetros operacionais atuais (`.env`), antes invisíveis fora do arquivo.
- Alerta em destaque na Visão Geral quando a fila acumula 5+ itens com erro.
- Busca por título na página de Clipes, além do filtro por status.

## [0.4.0] - Topázio - 2026-08-02

Fase 4 (Inteligência) do roadmap majoritariamente concluída — IA em revisão com dados reais.

### Adicionado
- IA (em revisão): antes de pedir os highlights, o Gemini recebe como referência os títulos que mais performaram no canal (via `get_top_performing_titles`), pra aprender com o que já funcionou de verdade em vez de depender só de um prompt estático. Só entra no prompt com histórico mínimo (`MIN_HISTORY_FOR_LEARNING`, padrão 3 clipes com métricas) pra não induzir a partir de poucas amostras.
- Fluxo de Analytics ponta a ponta via n8n: Schedule Trigger diário → `clips for-analytics` → YouTube Data API (views/likes/comments) + Analytics API (tempo assistido/retenção) → `clips record-analytics`. Testado com 9 vídeos reais. CTR/impressões não são expostos pela API pública do YouTube — descartado do fluxo automatizado. `shortsgen clips set-video-id` adicionado pra backfill de clipes publicados antes do rastreamento de ID existir.
- Analytics: nova tabela `clip_analytics` guarda uma série temporal de métricas por clipe (views, likes, comments, impressões, CTR, duração média assistida, retenção). `shortsgen clips for-analytics` lista os clipes publicados com ID do YouTube conhecido; `clips record-analytics <id>` registra uma leitura; `clips analytics <id>` mostra o histórico.
- Quality Score: o mesmo pedido ao Gemini que gera os highlights agora também gera uma nota de 0-100 do potencial viral de cada clipe. Um mínimo configurável (`MIN_QUALITY_SCORE`, padrão 60) decide o que entra automático no fluxo de publicação (`clips next-pending`); o que fica abaixo espera revisão manual (`shortsgen clips review` lista os pendentes — inclusive clipes antigos sem nota, gerados antes dessa funcionalidade existir — e `clips approve <id>` libera um clipe específico pro fluxo normal).

### Alterado
- Posição da legenda agora acompanha o enquadramento do instante: linha de divisão do split-screen, ou ~10% mais alta que antes no foco em 1 pessoa (evitava ficar coberta pela descrição/UI nativa do Shorts/TikTok/Reels). Palavra ativa (efeito karaoke) agora também aumenta de tamanho (~130%), além de ficar amarela — mais dinâmico.

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
