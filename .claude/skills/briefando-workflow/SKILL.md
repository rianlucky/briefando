---
name: briefando-workflow
description: Workflow de desenvolvimento do Briefando — leitura de VISION.md/ROADMAP.md antes de codar, checklist de fim de sessão (roadmap, changelog, commit). Use no início de qualquer sessão de desenvolvimento neste projeto, antes de implementar ou alterar código, e ao encerrar a sessão.
---

# Briefando Workflow

## Objetivo

Garantir consistência durante o desenvolvimento do Briefando, mantendo a arquitetura, filosofia e documentação sempre alinhadas.

---

## Ao iniciar uma sessão de desenvolvimento

Antes de qualquer alteração no código, siga obrigatoriamente esta sequência.

### 1. Ler a documentação

Abrir e ler:

- [VISION.md](../../../VISION.md)
- [ROADMAP.md](../../../ROADMAP.md)

Objetivo:

- Relembrar a missão do projeto.
- Seguir os princípios arquiteturais.
- Identificar a próxima tarefa.
- Evitar desenvolver funcionalidades fora do roadmap.

Caso exista alguma dúvida sobre prioridades, utilizar o ROADMAP como fonte principal.

### 2. Planejamento

Antes de implementar qualquer alteração:

- identificar em qual fase do roadmap a tarefa pertence;
- verificar dependências;
- confirmar que a implementação está alinhada com a filosofia do projeto.

Evitar overengineering. Sempre preferir soluções simples e evolutivas.

### 3. Durante o desenvolvimento

Seguir os princípios definidos no VISION.md. Priorizar:

- simplicidade;
- baixo acoplamento;
- organização;
- componentes reutilizáveis;
- código legível;
- facilidade de manutenção.

Não criar funcionalidades fora do escopo da tarefa atual. Caso identifique melhorias futuras, registrar apenas como ideia para o ROADMAP ou Backlog — não implementar.

---

## Ao finalizar a sessão

Antes de encerrar o trabalho, executar esta checklist.

### Documentação

Verificar se alguma etapa foi concluída. Se sim:

- atualizar ROADMAP.md;
- marcar os itens concluídos;
- mover novas ideias para o backlog.

### Changelog

Atualizar CHANGELOG.md contendo:

- funcionalidades adicionadas;
- melhorias;
- correções;
- refatorações.

Utilizar linguagem objetiva.

### Git

Caso o usuário confirme que deseja registrar o progresso:

- revisar os arquivos modificados;
- sugerir uma mensagem de commit clara seguindo Conventional Commits.

Exemplos:

```
feat(queue): implement processing queue
fix(whisper): improve transcription retry
refactor(metadata): separate metadata generation module
docs(roadmap): update project progress
```

Após a confirmação do usuário:

- realizar commit;
- publicar no repositório remoto (push).

---

## IMPORTANTE

Nunca modificar automaticamente:

- VISION.md
- ROADMAP.md
- CHANGELOG.md

Sempre apresentar as alterações propostas primeiro e solicitar que o usuário revise antes da gravação.

O usuário deve manter controle sobre a documentação estratégica do projeto.

---

## Filosofia

O objetivo não é escrever a maior quantidade possível de código.

O objetivo é construir uma plataforma sustentável, organizada, escalável e fácil de manter.

Sempre que houver conflito entre velocidade e qualidade arquitetural, buscar um equilíbrio.

Preferir pequenas entregas frequentes em vez de grandes refatorações.

Cada sessão de desenvolvimento deve deixar o projeto um pouco melhor do que foi encontrado.
