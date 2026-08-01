class PipelineCancelled(Exception):
    """Levantada quando um cancelamento pedido pelo usuario (TUI) e aplicado
    num ponto de checagem do pipeline (download, ffmpeg, reframe, entre clipes).

    Modulo separado (sem depender de pipeline_runner/pipeline) pra evitar
    import circular: tanto a orquestracao quanto as etapas do pipeline
    precisam levantar/checar essa excecao.
    """
