# Spec — Unificação de Identidade do Nox

**Data:** 2026-06-11
**Status:** Aprovado o direcionamento; aguardando revisão da spec.

## Contexto / Problema
O Nox é um fork re-skinado do projeto "MARK XXXIX-OR" (FatihMakes). A camada
nova (persona noir em `core/prompt.txt`, memória/CRM imobiliário) foi sobreposta
à base antiga sem limpar o branding original. Resultado: **três identidades
conflitantes** no código — persona noir (PT) vs. mordomo "Jarvis/sir" (inglês,
cravado) vs. nome "MARK/FatihMakes". O conflito mais grave é que **6 sub-LLMs
redefinem a persona errada** e o resumo de tarefas **ordena** o modelo a dizer
"sir", atropelando a persona noir.

## Identidade Canônica (fonte da verdade)
- **Nomes (hierarquia):** **Genesis** = nome OFICIAL do projeto (repo, produto,
  título do README, LICENSE). **Nox** = nome da PERSONA do assistente (como ele
  se chama, a voz noir do `prompt.txt`, o log, os sub-LLMs). README/UI = Genesis
  rodando o assistente Nox; persona/voz = Nox.
- **Quem é:** Nox — assistente pessoal **geral e amplo** (capacidade estilo
  Jarvis: controla SO, arquivos, web, jogos, código). Imobiliário/CRM e
  cyber/dev são **capacidades**, não a definição.
- **Voz/persona:** *dark gentleman noir* — intelecto arrogante, ironia seca,
  humor negro, respostas densas e curtas. Definida UMA vez em `core/prompt.txt`.
- **Criador:** mitternacht / Eliézer Barbosa (mantido, faz parte da persona).
- **Idioma:** **espelha o usuário** — responde no idioma em que falaram. Zero
  texto de persona cravado em inglês. Parâmetros de ferramenta seguem em inglês.
- **Legado a remover:** "MARK XXXIX", "FatihMakes", "Jarvis", "Iron Man", e todo
  `"sir"` hardcoded.

## Princípio de arquitetura: UMA fonte de persona
Hoje a persona vive em dois lugares que brigam: `prompt.txt` (que o Gemini Live
obedece) **e** strings/prompts em Python. A regra nova:

> **Só `core/prompt.txt` define a persona.** Todo sub-LLM (visão, youtube,
> resumo de tarefa, reflexão, etc.) é um **trabalhador neutro**: faz a tarefa,
> sem se declarar "NOX/Jarvis/Iron Man" e sem mandar dizer "sir".

Isso aproveita um detalhe do mecanismo: `speak()` injeta texto no Gemini Live
(`send_client_content(... turn_complete=True)`), que **re-voca** na persona e no
idioma da conversa. Logo, frases de status não precisam carregar persona — basta
serem neutras. Não é necessário um "módulo de voz" novo (YAGNI); a regra acima
já elimina a causa-raiz.

## Escopo real (maior do que parecia)
Varredura `grep "sir|Jarvis|MARK|Iron Man"` → ~50 ocorrências em ~10 arquivos.
Organizado por impacto:

### Tier 1 — Sub-LLMs que redefinem a persona (MAIOR impacto)
Corrigir os system prompts para serem neutros (ou herdarem a persona):
- `agent/executor.py:392` — `_summarize`: remove *"Address the user as 'sir'"*;
  gerar resumo **na persona + no idioma do objetivo** (já chama o Gemini).
- `actions/screen_processor.py:44,49` — *"You are NOX from Iron Man... address
  as sir"* → prompt de visão neutro.
- `actions/youtube_video.py:164,167` — idem (resumo de vídeo neutro).
- `or_client.py:255` — *"...inspired by NOX"* (auto-referência quebrada) →
  system genérico neutro.
- `main.py:84` — fallback de system prompt em inglês → fallback neutro/coerente
  (só usado se `prompt.txt` não carregar).

### Tier 2 — `"sir"` cravado em strings de retorno/fala (mecânico)
Remover "sir" e deixar frases curtas/neutras (o Gemini re-voca). Arquivos:
`main.py` (Goodbye), `agent/executor.py`, `agent/error_handler.py`,
`actions/code_helper.py`, `actions/dev_agent.py`, `actions/flight_finder.py`,
`actions/weather_report.py`, `actions/open_app.py`, `actions/send_message.py`,
`actions/web_search.py`, `actions/youtube_video.py`.

### Tier 3 — Branding cosmético (baixo risco, por último)
- `ui.py:1875` — "FatihMakes Industries · NOX · CLASSIFIED" → marca do Nox.
- `actions/screen_processor.py:256` — `write_log("Jarvis: ...")` → `"Nox: "`.
- `readme.md` — re-frontar como Nox (capacidades + persona), **mantendo** o
  crédito ao upstream MARK XXXIX-OR / FatihMakes, pois a licença CC BY-NC exige
  atribuição. Não remover a atribuição original.
- `actions/reminder.py` — prefixos "MARKReminder"/"MARK Reminder" no Task
  Scheduler: **manter** (são nomes internos de task; renomear quebra agendamentos
  já existentes). Anotado como decisão consciente.

## Fora de escopo (outros achados da análise)
IterationBudget decorativo, `cmd_control` fantasma, modelos OpenRouter, sandbox,
segredos no `.gitignore`. Ficam para specs próprias.

## Critérios de sucesso
1. `grep -ri "sir\|jarvis\|iron man\|fatihmakes" actions/ agent/ core/ main.py`
   não retorna nada de persona (exceto nomes de task em `reminder.py`).
2. Nenhum sub-LLM se declara "NOX/Jarvis/Iron Man" nem ordena "sir".
3. `core/prompt.txt` é o único lugar com definição de persona.
4. Falar com o Nox em PT → resposta noir em PT; em EN → resposta noir em EN.
5. Resumo de `agent_task` sai na persona e no idioma do pedido, sem "sir".

## Verificação
- Estático: o grep do critério 1.
- Dinâmico: `python main.py` com chave Gemini; testar (a) comando simples em PT,
  (b) o mesmo em inglês, (c) uma `agent_task` longa que dispare replan, ouvindo o
  resumo final. Conferir tom noir + idioma espelhado, sem "sir".
