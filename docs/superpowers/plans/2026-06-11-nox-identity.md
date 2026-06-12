# Unificação de Identidade do Nox — Plano de Implementação

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Alinhar todo o código a uma identidade canônica única — Nox, voz "dark gentleman noir" definida só em `core/prompt.txt`, espelhando o idioma do usuário — removendo o legado "sir"/Jarvis/Iron Man/MARK/FatihMakes.

**Architecture:** UMA fonte de persona: só `core/prompt.txt`. Todo sub-LLM vira trabalhador neutro (não se declara persona, não ordena "sir"). Como `speak()` injeta texto no Gemini Live que re-voca na persona+idioma, frases de status só precisam ser neutras — sem módulo de voz novo.

**Tech Stack:** Python 3.11/3.12, google-genai (Gemini Live), OpenRouter/Moonshot. Sem harness de teste → verificação por `grep` + run manual.

**Spec:** `docs/superpowers/specs/2026-06-11-nox-identity-design.md`

## Nota de ambiente (IMPORTANTE)
O hook do plugin Mercado Pago (`validate_mp_credentials.py`) está quebrado e bloqueia as ferramentas nativas **Read/Write/Edit/Bash** nesta sessão (caminho com espaço em "Atual Master"). Contorno:
- Edições → Desktop Commander `edit_block` (`old_string`/`new_string`, `expected_replacements`).
- Leituras/grep → tools `Grep`/`Glob` (funcionam) ou Desktop Commander `read_file`.
- Git → tool **PowerShell** (não passa pelo hook). Commits só se o usuário autorizar.

## File Structure
Nenhum arquivo novo. Edição cirúrgica de:
- Sub-LLMs (Tier 1): `agent/executor.py`, `actions/screen_processor.py`, `actions/youtube_video.py`, `or_client.py`, `main.py`.
- Strings "sir" (Tier 2): `agent/executor.py`, `agent/error_handler.py`, `main.py`, `actions/{open_app,send_message,web_search,weather_report,flight_finder,code_helper,dev_agent,youtube_video}.py`.
- Cosmético (Tier 3): `ui.py`, `actions/screen_processor.py`, `readme.md`.
- **NÃO tocar:** `actions/reminder.py` (prefixos "MARK*" são nomes de task do Scheduler).

---

## Task 1: Tier 1 — Neutralizar os sub-LLMs que redefinem a persona

**Files:**
- Modify: `actions/screen_processor.py` (SYSTEM_PROMPT, ~L42-51)
- Modify: `actions/youtube_video.py` (system do resumo, ~L163-169)
- Modify: `or_client.py` (default `system` do `chat()`, ~L253-256)
- Modify: `main.py` (fallback `_load_system_prompt`, ~L82-86)
- Modify: `agent/executor.py` (`_summarize`, ~L382-392)

- [ ] **Step 1: `screen_processor.py` — prompt de visão neutro**

`edit_block` old_string:
```python
SYSTEM_PROMPT = (
    "You are NOX from Iron Man movies. "
    "Analyze images with technical precision and intelligence. "
    "Help the user in a way they can understand — don't be overly complex. "
    "Be concise, smart, and helpful like Tony Stark's AI assistant. "
    "Respond in maximum 2 short sentences. Speed is priority. "
    "Address the user as 'sir' for a tone of respect. "
    "Ask if the user needs any further help with their problem."
)
```
new_string:
```python
SYSTEM_PROMPT = (
    "Analyze images with technical precision and intelligence. "
    "Help the user in a way they can understand — don't be overly complex. "
    "Be concise and smart. "
    "Respond in maximum 2 short sentences. Speed is priority. "
    "Respond in the same language as the user's question."
)
```

- [ ] **Step 2: `youtube_video.py` — resumo de vídeo neutro**

`edit_block` old_string:
```python
            "You are NOX, an AI assistant. "
            "Summarize YouTube video transcripts clearly and concisely. "
            "Structure: 1-sentence overview, then 3-5 key points. "
            "Be direct. Address the user as 'sir'. "
            "Match the language of the transcript."
```
new_string:
```python
            "Summarize YouTube video transcripts clearly and concisely. "
            "Structure: 1-sentence overview, then 3-5 key points. "
            "Be direct. "
            "Match the language of the transcript."
```

- [ ] **Step 3: `or_client.py` — remover auto-referência "inspired by NOX"**

`edit_block` old_string:
```python
            "You are a component of NOX, an AI assistant inspired by NOX. "
            "Be concise, helpful, and precise."
```
new_string:
```python
            "You are an internal worker module for an assistant. "
            "Be concise, helpful, and precise."
```

- [ ] **Step 4: `main.py` — fallback de system prompt coerente + idioma**

`edit_block` old_string:
```python
            "You are NOX. Dark gentleman, Dev FirstIA, cyber security expert. "
            "Be concise, direct, and always use the provided tools to complete tasks. "
            "Never simulate or guess results — always call the appropriate tool."
```
new_string:
```python
            "You are Nox, a dark gentleman noir personal assistant. "
            "Be concise and direct, and always use the provided tools to complete tasks. "
            "Never simulate or guess results — always call the appropriate tool. "
            "Respond in the same language the user speaks."
```

- [ ] **Step 5: `agent/executor.py` `_summarize` — sem "sir", na língua do objetivo**

`edit_block` old_string:
```python
        fallback = f"All done, sir. Completed {len(completed_steps)} steps for: {goal[:60]}."
```
new_string:
```python
        fallback = f"Done. Completed {len(completed_steps)} steps for: {goal[:60]}."
```

`edit_block` old_string:
```python
                "Write a single natural sentence summarizing what was accomplished. "
                "Address the user as 'sir'. Be direct and positive."
```
new_string:
```python
                "Write a single natural sentence summarizing what was accomplished. "
                "Write it in the same language as the user goal above. "
                "Be direct and concise. Do not use any form of address such as 'sir'."
```

- [ ] **Step 6: Verificar Tier 1**

Grep (tool Grep, glob `*.py`): padrão `Iron Man|inspired by NOX|Address the user as 'sir'`
Esperado: **0 ocorrências**.

- [ ] **Step 7: Commit** (só se autorizado — git via PowerShell)

```powershell
git add actions/screen_processor.py actions/youtube_video.py or_client.py main.py agent/executor.py
git commit -m "refactor(identity): neutralize sub-LLM persona prompts (Tier 1)"
```

---

## Task 2: Tier 2 — Remover "sir" da camada de agente + main.py

**Files:**
- Modify: `agent/executor.py` (L33, 274, 284, 333, 342, 372, 376)
- Modify: `agent/error_handler.py` (L90, 128, 140)
- Modify: `main.py` (L836)

Regra: remover ", sir"/" sir" mantendo a frase. Cada um é um `edit_block`.

- [ ] **Step 1: `agent/executor.py`** — 7 substituições

| old_string | new_string |
|---|---|
| `speak("Writing custom code for this task, sir.")` | `speak("Writing custom code for this task.")` |
| `msg = "I couldn't create a valid plan for this task, sir."` | `msg = "I couldn't create a valid plan for this task."` |
| `if speak: speak("Task cancelled, sir.")` | `if speak: speak("Task cancelled.")` |
| `msg = f"Task aborted, sir. {recovery.get('reason', '')}"` | `msg = f"Task aborted. {recovery.get('reason', '')}"` |
| `if speak: speak("Trying an alternative approach, sir.")` | `if speak: speak("Trying an alternative approach.")` |
| `msg = f"Task failed after {replan_attempts} replan attempts, sir."` | `msg = f"Task failed after {replan_attempts} replan attempts."` |
| `if speak: speak("Adjusting my approach, sir.")` | `if speak: speak("Adjusting my approach.")` |

- [ ] **Step 2: `agent/error_handler.py`** — 3 substituições

| old_string | new_string |
|---|---|
| `"Trying a different approach, sir."` | `"Trying a different approach."` |
| `"This step is critical — finding alternative approach, sir."` | `"This step is critical — finding alternative approach."` |
| `"Encountered an issue, adjusting approach, sir."` | `"Encountered an issue, adjusting approach."` |

- [ ] **Step 3: `main.py`** — 1 substituição

old_string: `self.speak("Goodbye, sir.")` → new_string: `self.speak("Goodbye.")`

- [ ] **Step 4: Verificar** — Grep `sir` em `agent/executor.py`, `agent/error_handler.py`, `main.py` → **0**.

- [ ] **Step 5: Commit** (se autorizado)
```powershell
git add agent/executor.py agent/error_handler.py main.py
git commit -m "refactor(identity): drop hardcoded 'sir' in agent layer (Tier 2)"
```

---

## Task 3: Tier 2 — actions grupo A (mensagens curtas)

**Files:** `actions/open_app.py` (L176,194,199,202,208), `actions/send_message.py` (L191,193), `actions/web_search.py` (L123,153), `actions/weather_report.py` (L42)

- [ ] **Step 1: `actions/open_app.py`**

| old_string | new_string | obs |
|---|---|---|
| `return "Please specify which application to open, sir."` | `return "Please specify which application to open."` | |
| `return f"Opened {app_name} successfully, sir."` | `return f"Opened {app_name} successfully."` | **expected_replacements=2** (L194 e L199 idênticas) |
| `f"I tried to open {app_name}, sir, but couldn't confirm it launched. "` | `f"I tried to open {app_name}, but couldn't confirm it launched. "` | |
| `return f"Failed to open {app_name}, sir: {e}"` | `return f"Failed to open {app_name}: {e}"` | |

- [ ] **Step 2: `actions/send_message.py`**

| old_string | new_string |
|---|---|
| `return "Please specify who to send the message to, sir."` | `return "Please specify who to send the message to."` |
| `return "Please specify what message to send, sir."` | `return "Please specify what message to send."` |

- [ ] **Step 3: `actions/web_search.py`**

| old_string | new_string |
|---|---|
| `return "Please provide a search query, sir."` | `return "Please provide a search query."` |
| `return f"Search failed, sir: {e2}"` | `return f"Search failed: {e2}"` |

- [ ] **Step 4: `actions/weather_report.py`**

old_string: `msg = f"Showing the weather for {city}, {time}, sir."`
new_string: `msg = f"Showing the weather for {city}, {time}."`

- [ ] **Step 5: Verificar** — Grep `sir` nos 4 arquivos → **0**.

- [ ] **Step 6: Commit** (se autorizado)
```powershell
git add actions/open_app.py actions/send_message.py actions/web_search.py actions/weather_report.py
git commit -m "refactor(identity): drop 'sir' in actions group A (Tier 2)"
```

---

## Task 4: Tier 2 — actions grupo B (flight_finder, code_helper, dev_agent)

**Files:** `actions/flight_finder.py`, `actions/code_helper.py`, `actions/dev_agent.py`

- [ ] **Step 1: `actions/flight_finder.py`** (8 edições)

| old_string | new_string |
|---|---|
| `f"on {date}, sir. The page may not have loaded correctly."` | `f"on {date}. The page may not have loaded correctly."` |
| `f"Here are the top flights from {origin} to {destination} on {date}, sir."` | `f"Here are the top flights from {origin} to {destination} on {date}."` |
| `return "Please provide both origin and destination, sir."` | `return "Please provide both origin and destination."` |
| `return "Please provide a departure date, sir."` | `return "Please provide a departure date."` |
| `speak(f"Searching flights from {origin} to {destination} on {date}, sir.")` | `speak(f"Searching flights from {origin} to {destination} on {date}.")` |
| `return "Could not retrieve flight data, sir. The page may not have loaded."` | `return "Could not retrieve flight data. The page may not have loaded."` |
| `speak("Analysing the results now, sir.")` | `speak("Analysing the results now.")` |
| `return f"Flight search failed, sir: {e}"` | `return f"Flight search failed: {e}"` |

- [ ] **Step 2: `actions/code_helper.py`** (10 edições)

| old_string | new_string |
|---|---|
| `return "Please describe what you want me to build, sir."` | `return "Please describe what you want me to build."` |
| `f"Build complete, sir. "` | `f"Build complete. "` |
| `f"I was unable to build a working version after {MAX_BUILD_ATTEMPTS} attempts, sir. "` | `f"I was unable to build a working version after {MAX_BUILD_ATTEMPTS} attempts. "` |
| `return "Please describe what you want me to write, sir."` | `return "Please describe what you want me to write."` |
| `return "Please provide a file path to edit, sir."` | `return "Please provide a file path to edit."` |
| `return "Please describe what change to make, sir."` | `return "Please describe what change to make."` |
| `return "Please provide code or a file path to explain, sir."` | `return "Please provide code or a file path to explain."` |
| `return "Please provide a file path to run, sir."` | `return "Please provide a file path to run."` |
| `return "Please provide code or a file path to optimize, sir."` | `return "Please provide code or a file path to optimize."` |
| `return "Could not take screenshot, sir. Please make sure PyAutoGUI is installed."` | `return "Could not take screenshot. Please make sure PyAutoGUI is installed."` |

- [ ] **Step 3: `actions/dev_agent.py`** (5 edições)

| old_string | new_string |
|---|---|
| `msg = "Rate limit reached, sir. Please try again in a moment."` | `msg = "Rate limit reached. Please try again in a moment."` |
| `msg = "I could not write any project files, sir."` | `msg = "I could not write any project files."` |
| `f"Project '{proj_name}' is working, sir. "` | `f"Project '{proj_name}' is working. "` |
| `f"I couldn't fully fix '{proj_name}' after {MAX_FIX_ATTEMPTS} attempts, sir. "` | `f"I couldn't fully fix '{proj_name}' after {MAX_FIX_ATTEMPTS} attempts. "` |
| `return "Please describe the project you want me to build, sir."` | `return "Please describe the project you want me to build."` |

- [ ] **Step 4: Verificar** — Grep `sir` nos 3 arquivos → **0**.

- [ ] **Step 5: Commit** (se autorizado)
```powershell
git add actions/flight_finder.py actions/code_helper.py actions/dev_agent.py
git commit -m "refactor(identity): drop 'sir' in actions group B (Tier 2)"
```

---

## Task 5: Tier 2 — actions/youtube_video.py (restante)

**Files:** `actions/youtube_video.py` (L266,296,298,302,307,311,319,336,340,347,357,370,378)

- [ ] **Step 1: 13 edições**

| old_string | new_string |
|---|---|
| `return "Please tell me what you'd like to watch, sir."` | `return "Please tell me what you'd like to watch."` |
| `return "No URL provided, sir. Summary cancelled."` | `return "No URL provided. Summary cancelled."` |
| `return "That doesn't appear to be a valid YouTube URL, sir."` | `return "That doesn't appear to be a valid YouTube URL."` |
| `return "Could not extract video ID from that URL, sir."` | `return "Could not extract video ID from that URL."` |
| `speak("Fetching the transcript now, sir. One moment.")` | `speak("Fetching the transcript now. One moment.")` |
| `return "I couldn't retrieve a transcript for that video, sir."` | `return "I couldn't retrieve a transcript for that video."` |
| `return f"Summary generation failed, sir: {e}"` | `return f"Summary generation failed: {e}"` |
| `return "Please provide a valid YouTube URL, sir."` | `return "Please provide a valid YouTube URL."` |
| `return "Could not extract video ID, sir."` | `return "Could not extract video ID."` |
| `return "Could not retrieve video information, sir."` | `return "Could not retrieve video information."` |
| `speak(f"Here's the video info, sir. {result.replace(chr(10), '. ')}")` | `speak(f"Here's the video info. {result.replace(chr(10), '. ')}")` |
| `return f"Could not fetch trending videos for region {region}, sir."` | `return f"Could not fetch trending videos for region {region}."` |
| `spoken = "Here are the top trending videos, sir. " + ". ".join(` | `spoken = "Here are the top trending videos. " + ". ".join(` |

- [ ] **Step 2: Verificar** — Grep `sir` em `actions/youtube_video.py` → **0**.

- [ ] **Step 3: Commit** (se autorizado)
```powershell
git add actions/youtube_video.py
git commit -m "refactor(identity): drop 'sir' in youtube_video (Tier 2)"
```

---

## Task 6: Tier 3 — Branding cosmético

**Files:** `ui.py` (L1875), `actions/screen_processor.py` (L256), `readme.md`

- [ ] **Step 1: `ui.py` — label**

old_string: `lay.addWidget(_fl("FatihMakes Industries  ·  NOX  ·  CLASSIFIED"))`
new_string: `lay.addWidget(_fl("GENESIS  ·  NOX  ·  CLASSIFIED"))`
(Genesis = projeto; Nox = assistente.)

- [ ] **Step 2: `actions/screen_processor.py` — log "Jarvis:" → "Nox:"**

old_string: `self._player.write_log(f"Jarvis: {full}")`
new_string: `self._player.write_log(f"Nox: {full}")`

- [ ] **Step 3: `readme.md` — re-frontar como Nox, mantendo atribuição CC BY-NC**

`write_file` (rewrite) com este conteúdo:
```markdown
# 🌑 Genesis

**Genesis** é a plataforma; **Nox** é o assistente que ela executa — uma IA de
voz em tempo real que ouve, vê, entende e controla o computador. Persona "dark
gentleman noir"; fala no idioma do usuário. Execução local.

## Capacidades
- 🎙️ Voz em tempo real (Gemini Live, áudio nativo)
- 🖥️ Controle do sistema: apps, arquivos, terminal, configurações
- 🧩 Tarefas autônomas multi-etapas (planner + executor)
- 👁️ Visão de tela e webcam
- 🧠 Memória persistente (longo prazo + procedural)
- 🏠 Módulo imobiliário/CRM e utilidades (web, YouTube, clima, voos, jogos)

## Quick Start
```bash
pip install -r requirements.txt
playwright install
python main.py
```
Requer chave Gemini (e, opcional, OpenRouter). Plataforma de referência: Windows 10/11, Python 3.11/3.12.

## Créditos / Upstream
Construído sobre o projeto open-source **MARK XXXIX-OR**, por **FatihMakes**
(YouTube: @FatihMakes), licenciado **CC BY-NC 4.0**. Este fork mantém a mesma
licença e atribuição. Uso pessoal e não-comercial.
```

- [ ] **Step 4: Commit** (se autorizado)
```powershell
git add ui.py actions/screen_processor.py readme.md
git commit -m "refactor(identity): rebrand UI/readme to Nox, keep upstream credit (Tier 3)"
```

---

## Task 7: Verificação final (estática + dinâmica)

- [ ] **Step 1: Grep de persona zerado**

Tool Grep, `path` = repo, pattern (case-insensitive):
`\bsir\b|jarvis|iron man|fatihmakes|inspired by NOX`
Conferir resultados: as ÚNICAS ocorrências aceitáveis de "MARK" são nomes de task em `actions/reminder.py`. Para "sir/jarvis/iron man/fatihmakes/inspired by NOX" o esperado é **0** em `actions/`, `agent/`, `core/`, `main.py`, `or_client.py`, `ui.py`.

- [ ] **Step 2: `prompt.txt` é a única definição de persona**

Confirmar (leitura) que nenhum sub-LLM em `actions/`/`agent/`/`or_client.py` se declara "NOX/Jarvis/Iron Man" nem ordena forma de tratamento. A persona vive só em `core/prompt.txt`.

- [ ] **Step 3: Teste dinâmico (requer chave Gemini)**

Rodar `python main.py` e validar:
1. Comando simples em **PT** (ex.: "que horas são?") → resposta noir em PT, sem "sir".
2. O mesmo em **inglês** → resposta noir em EN (idioma espelhado).
3. Uma `agent_task` longa que dispare replan (ex.: "pesquise X e salve num arquivo") → ouvir o resumo final: deve sair na persona + idioma do pedido, sem "sir".

- [ ] **Step 4: Commit final / fechar branch** (se autorizado)

---

## Self-Review (autor)

**1. Cobertura da spec:**
- Identidade canônica → Tasks 1,6 (persona-source) ✓
- UMA fonte de persona → Task 1 (neutraliza sub-LLMs) + critério Task 7.2 ✓
- Espelhar idioma → Task 1 (screen_processor, main fallback, _summarize) ✓
- Tier 1 (6 sub-LLMs) → Task 1 (5 arquivos; nota: youtube tinha 1 system, screen 1, executor 1, or_client 1, main 1 = 5 prompts; o 6º "sub-LLM" da spec era contagem aproximada) ✓
- Tier 2 (~50 "sir") → Tasks 2-5 ✓
- Tier 3 → Task 6 ✓
- reminder.py mantido → documentado (File Structure + Task 7.1) ✓
- Critérios de sucesso → Task 7 ✓

**2. Placeholders:** nenhum "TBD/TODO"; todas as edições têm old/new exatos.

**3. Consistência de tipos/nomes:** edições são strings literais; sem novas funções/assinaturas. `expected_replacements=2` sinalizado onde há duplicata (open_app "Opened ... successfully").

**Ajuste pós-review:** a spec falava em "6 sub-LLMs"; a contagem precisa é **5 prompts** (screen_processor, youtube_video, or_client, main fallback, executor `_summarize`). Sem lacuna — apenas precisão.
