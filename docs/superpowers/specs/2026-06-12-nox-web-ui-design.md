# Nox Web UI — Design Spec

**Data:** 2026-06-12
**Status:** Aprovado pelo usuário (brainstorm concluído)
**Substitui:** interface PyQt6 atual (`ui.py`), que permanece como fallback até o M5

## 1. Objetivo

Substituir a interface desktop PyQt6 do Nox por uma interface web (React) com animações de alto nível, rodando:

- **Desktop:** janela nativa fina (pywebview/WebView2) apontando para um servidor local.
- **Mobile:** o navegador do celular acessa o mesmo servidor pela rede Wi-Fi local (pareamento por QR code + token).

O protagonista visual é um **cérebro de redes neurais vivo** conectado a um **chip de IA** por filamentos de energia, com três estágios reativos sincronizados ao backend: **parado**, **pensando** e **falando** (este último pulsando com a amplitude real da voz TTS).

Referências visuais validadas no brainstorm (servidor visual, sessão `1542-1781294751`):

- `layout-hierarchy.html` — layout **C — Adaptativo** escolhido.
- `neural-brain-chip.html` — demo interativo v2 do cérebro+chip **aprovado** ("Otimoooo gostei muito").
- Imagem de referência do usuário: cérebro holográfico azul com núcleo sináptico laranja sobre chip.

## 2. Decisões de brainstorm (fechadas)

| Decisão | Escolha |
| --- | --- |
| Escopo funcional | Repensar do zero (não é port 1:1) |
| Hierarquia de layout | C — Adaptativo: cérebro domina ocioso; em conversa encolhe para ~45% e o chat divide o palco. O cérebro **nunca** vira ícone |
| Direção visual | Holograma neural: fundo escuro profundo (#020611), rede ciano/azul (#22d3ee/#38bdf8), núcleo e acentos laranja (#ff8c42/#ff6b00) — herda a identidade atual do Nox |
| Plataformas | Desktop **e** mobile já nesta fase |
| Casca desktop | **pywebview** (WebView2) — não PyQt6-WebEngine, não Electron |
| Ponte | FastAPI + WebSocket no processo Python do Nox |
| Áudio desktop | Permanece em Python (sounddevice), inalterado |
| Áudio mobile | Mic do celular via navegador → WS binário → backend; TTS de volta ao celular. Uma fonte ativa por vez (PC ⇄ celular) |

## 3. Arquitetura

```text
c:\nox\
├── server/                  # NOVO — ponte FastAPI
│   ├── app.py               # FastAPI: rotas REST, static files (webui/dist), startup
│   ├── ws.py                # WebSocket: hub de conexões, broadcast de eventos
│   ├── web_ui.py            # classe WebUI — adapter com a MESMA interface da NoxUI
│   ├── audio_router.py      # alternância de fonte/destino de áudio PC⇄celular
│   └── auth.py              # token de acesso, geração de QR
├── webui/                   # NOVO — frontend React
│   ├── src/
│   │   ├── stage/           # Brain.tsx (R3F), Chip.tsx, Stage.tsx (morph ocioso⇄conversa)
│   │   ├── chat/            # ChatPanel, Bubble, ToolChip, Composer (input)
│   │   ├── dock/            # MetricsDock (sparklines CPU/RAM/NET/GPU, quotas API)
│   │   ├── settings/        # Setup de API keys (substitui SetupOverlay), acesso mobile + QR
│   │   ├── lib/             # ws.ts (reconexão), audio.ts (worklets mobile), store.ts (zustand)
│   │   └── App.tsx
│   └── dist/                # build servido pelo FastAPI — COMMITADO no repo (usuário final não roda Node)
├── desktop.py               # NOVO — casca pywebview (~30 linhas)
├── main.py                  # ALTERADO — instancia WebUI em vez de NoxUI (flag --legacy-ui mantém a antiga)
└── ui.py                    # INTACTO — fallback legacy até M5
```

**Stack frontend:** React 18 + TypeScript + Vite + Tailwind CSS + Framer Motion (morphs de layout/UI) + React Three Fiber + drei (cérebro 3D) + zustand. Node é dependência **só de desenvolvimento**; usuário final recebe `webui/dist` pronto.

**Servidor:** porta padrão `8765` (configurável em `config/api_keys.json`, chave `web_port`). Bind padrão `127.0.0.1`; muda para `0.0.0.0` somente com "acesso mobile" ativado nas configurações.

## 4. Contrato UI ↔ backend

### 4.1 Adapter `WebUI` (server/web_ui.py)

Duck-type da interface que `NoxCore` (main.py) já consome — main.py muda no mínimo:

| Membro | Comportamento novo |
| --- | --- |
| `on_text_command` (callable, set pelo NoxCore) | invocado quando chega evento WS `message` |
| `set_state(state)` | broadcast WS `{"t":"state","state":"LISTENING\|THINKING\|SPEAKING\|MUTED"}` |
| `write_log(text)` | parse do prefixo (`You:`/`Nox:`/`File:`/`[Err`/resto) → WS `{"t":"chat","role":"user\|nox\|file\|err\|sys","text":...}` |
| `muted` (get/set) | estado interno; set → broadcast `{"t":"mute","muted":bool}`; client envia `mute` para alternar |
| `current_file` (get) | caminho do último upload via REST |
| `wait_for_api_key()` | bloqueia até config válida existir (a UI React mostra a tela de setup e faz POST) |
| `start_speaking()/stop_speaking()/speak(text)` | mesmos atalhos da NoxUI atual |
| **novo, opcional** `on_audio_level(level: float)` | broadcast `{"t":"viz","level":0..1}` (≤30/s, com coalescência) — no-op na UI legacy |
| **novo, opcional** `tool_event(name, status, ms)` | broadcast `{"t":"tool","name":...,"status":"start\|ok\|fail","ms":int}` — chamado em `_execute_tool` (M3) |

Princípio: M1 funciona **sem nenhuma mudança semântica** no backend (só troca de classe). Hooks novos são opcionais e protegidos com `getattr`.

### 4.2 Protocolo WebSocket (`/ws?token=...`)

**Servidor → cliente (JSON):** `state`, `chat`, `mute`, `viz`, `tool`, `metrics` (1/s: cpu, mem, net up/down, gpu, temp, uptime, quotas), `audio_source`, `hello` (estado completo ao conectar).
**Cliente → servidor (JSON):** `message {text}`, `mute {muted}`, `audio_source {source:"pc"|"phone"}`, `dev_tools {enabled}`.
**Binário:** frames PCM — celular→servidor mic 16 kHz int16 mono; servidor→celular TTS 24 kHz int16 mono (somente para o cliente que detém a fonte "phone").

**REST:** `POST /api/message` (alternativa ao WS), `POST /api/upload` (multipart → salva em `home/uploads/`, seta `current_file`, dispara `on_text_command("[FILE_UPLOADED] ...")` como hoje), `GET/POST /api/config` (setup de keys; nunca devolve segredos completos), `GET /api/qr` (PNG do QR de pareamento, só quando mobile ativado).

### 4.3 Sincronização de voz (o diferencial)

- `NoxCore._play_audio` (TTS 24 kHz): calcula RMS por chunk → `ui.on_audio_level(rms_norm)` → cérebro pulsa com a voz real.
- `NoxCore._listen_audio` (mic 16 kHz): RMS quando em LISTENING → cérebro reage sutilmente à voz do usuário.
- Frontend interpola níveis entre frames (spring) para 60fps visuais com ≤30 eventos/s.

## 5. O palco (Stage)

- **Cérebro:** React Three Fiber — nuvem de ~2.000 pontos amostrados em malha de cérebro anatômica (asset GLB low-poly de licença livre/CC0; fallback: forma procedural por união de elipsoides, como no demo v2), arestas por vizinhança, shader com glow/bloom (postprocessing), núcleo laranja, pulsos sinápticos viajando pelas arestas, chip isométrico abaixo conectado por raios (shader/linhas animadas) — replicando o demo v2 aprovado em 3D real.
- **Estágios:** `idle` (respiração lenta), `thinking` (morph de forma + cascata de pulsos + chip intenso), `speaking` (ondas + pulso síncrono ao `viz`). Mapeiam os estados do backend: LISTENING→idle reativo ao mic, THINKING→thinking, SPEAKING→speaking, MUTED→idle escurecido com selo de mudo.
- **Morph de layout (Framer Motion shared layout):** ocioso = cérebro grande central + saudação + composer flutuante; em conversa = cérebro sobe para ~45% da altura (sempre animado) e o ChatPanel entra por baixo em painéis de vidro. Transição contínua, sem cortes.
- **Performance:** alvo 60fps desktop / 30fps mobile; densidade de pontos reduz por breakpoint e por `devicePixelRatio`; `prefers-reduced-motion` troca animações por transições discretas.

## 6. Componentes

- **Chat:** bolhas user/Nox com streaming de texto, mensagens `sys` discretas, `err` em vermelho; **ToolChips** inline ("file_controller ✓ 0,4s") a partir dos eventos `tool` (M3; antes disso, linhas `sys`).
- **Composer:** input + botão enviar (Enter envia), estado desabilitado quando WS caído.
- **Upload:** drag-and-drop na janela inteira (overlay de soltar) + botão clipe no composer; ícone por categoria de arquivo como hoje.
- **MetricsDock:** gaveta recolhível (borda esquerda no desktop, sheet inferior no mobile) com sparklines de CPU/RAM/rede/GPU/temp, uptime, quotas de API. Fechada por padrão em mobile.
- **Controles (header):** mute do mic, dev tools (com trava de confirmação como hoje), fullscreen, settings, indicador de conexão.
- **Settings:** API keys (Gemini/OpenRouter/Moonshot), SO, toggle "acesso mobile" (liga bind 0.0.0.0 + mostra QR), fonte de áudio ativa.
- **Mobile:** stack vertical — cérebro compacto no topo (reativo sempre), chat dominante, composer fixo embaixo com safe-area; alvos ≥44px.

## 7. Segurança (LAN)

- Token aleatório (32 hex) gerado no primeiro boot, salvo em `config/api_keys.json` (`web_token`) — arquivo já está no .gitignore.
- WS e REST exigem token **exceto** requisições de `127.0.0.1` (casca desktop).
- QR code = `http://<ip-local>:<web_port>/?token=<token>`; frontend guarda em `localStorage`.
- Bind `0.0.0.0` é opt-in por settings; padrão é só localhost. Sem TLS nesta fase (rede local doméstica; risco aceito e documentado).

## 8. Robustez e erros

- WS com reconexão exponencial (0,5s→8s) + badge "reconectando"; eventos `hello` re-hidratam o estado completo ao reconectar.
- Backend opera normalmente sem UI conectada (eventos são best-effort; sem fila infinita — só o último estado é re-hidratável).
- Falha de ferramenta → evento `tool fail` + bolha `err`; nunca silencioso.
- Se WebView2 ausente (Win10 antigo): `desktop.py` mostra diálogo com link do runtime e instrução; alternativa: abrir no navegador padrão.
- Conflito de fonte de áudio: servidor rejeita `audio_source phone` se outro cliente já a detém (resposta `err`).

## 9. Testes

- **pytest (server/):** contrato WebUI (cada chamada → evento WS correto), parsing de prefixos de log, auth (com/sem token, localhost bypass), audio_router (alternância e rejeição de conflito) — com TestClient/WS de teste do FastAPI.
- **vitest (webui/):** store zustand (reduções de eventos), parser de mensagens, máquina de estados do Stage.
- **Playwright (smoke):** sobe servidor com backend fake, abre página, WS conecta, envia mensagem, bolha aparece, estado muda o palco.
- **Manual/visual:** checklist por estágio do cérebro; FPS no DevTools; teste de QR + celular real na LAN.

## 10. Marcos de entrega

| Marco | Entrega | Critério de aceite |
| --- | --- | --- |
| **M1 — Fundação** | server/ + WebUI adapter + desktop.py + React mínimo com cérebro provisório (port do demo canvas v2) reagindo a estados reais; chat básico funcional; tela mínima de setup de API keys quando config ausente (reaproveitada no M3) | Conversar com o Nox por texto na janela nova; cérebro muda nos 3 estágios |
| **M2 — Cérebro 3D** | Brain R3F definitivo (malha anatômica, bloom, chip, raios) + sync `viz` com RMS real do TTS | "Falando" pulsa visivelmente com a voz; 60fps desktop |
| **M3 — Interface completa** | Chat com streaming + ToolChips, upload drag-and-drop, settings, MetricsDock, morph ocioso⇄conversa completo | Paridade funcional com a UI antiga + melhorias |
| **M4 — Mobile** | Token+QR, layouts touch, áudio bidirecional pelo celular com alternância de fonte | Conversa por voz completa pelo celular na LAN |
| **M5 — Polimento** | reduced-motion, acessibilidade (foco, contraste 4.5:1), performance mobile, empacotamento; `--legacy-ui` documentado como deprecated | Checklist de pré-entrega da skill ui-ux-pro-max passa |

## 11. Dependências novas

- **Python:** `fastapi`, `uvicorn[standard]`, `pywebview`, `qrcode[pil]`. Corrigir `requirements.txt` (está em UTF-16 com espaçamento quebrado; regravar em UTF-8 e incluir as deps que faltam, ex.: PyQt6 do legacy).
- **Node (dev-only):** react, typescript, vite, tailwindcss, framer-motion, three, @react-three/fiber, @react-three/drei, @react-three/postprocessing, zustand.

## 12. Fora de escopo (desta fase)

- Histórico de conversa persistente entre sessões na UI (a memória do Nox no backend continua como está).
- Acesso fora da LAN (internet/HTTPS/túnel) e apps nativos de loja.
- Mudanças na lógica do agente (planner/executor/ferramentas) além dos hooks opcionais citados.
- Remoção física do `ui.py` (só no M5+, após estabilidade).

## 13. Riscos aceitos

- **WebView2 runtime** necessário (presente no Win11; instalável no Win10).
- **Tráfego LAN sem TLS** — mitigado por token + opt-in do bind externo.
- **Latência de áudio mobile** via WS (~100-300ms) — aceitável para assistente conversacional; se incomodar, otimização futura (WebRTC) fica registrada como evolução.
- **Performance 3D em celulares fracos** — mitigada por degradação de densidade e reduced-motion.
