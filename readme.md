# 🌑 Genesis

**Genesis** é a plataforma; **Nox** é o assistente que ela executa — uma IA de voz em tempo real que ouve, vê, entende e controla o computador. Persona "dark gentleman noir"; fala no idioma do usuário. Execução local, sem assinaturas.

---

## ✨ O que é

Genesis conecta o sistema operacional à intenção humana. Por diálogo natural, o assistente Nox analisa sua tela, processa arquivos e executa fluxos de trabalho complexos — com voz em tempo real e uma interface adaptável.

## 🚀 Capacidades

| Recurso | Descrição |
|---|---|
| 🎙️ Voz em tempo real | Conversa de baixa latência (Gemini Live, áudio nativo) |
| 🖥️ Controle do sistema | Abre apps, gerencia arquivos, executa comandos |
| 🧩 Tarefas autônomas | Planejamento multi-etapas (planner + executor) |
| 👁️ Visão | Análise de tela e webcam em tempo real |
| 🧠 Memória persistente | Lembra projetos, preferências e contexto pessoal |
| 🏠 Módulo imobiliário/CRM | Imóveis, leads, agendamentos e clientes |
| 🔧 Utilidades | Web, YouTube, clima, voos, jogos (Steam/Epic) e mais |

## ⚡ Quick Start

```bash
pip install -r requirements.txt
playwright install
python main.py
```

Na primeira execução, copie `config/api_keys.example.json` para `config/api_keys.json` e preencha sua chave do **Gemini** (e, opcionalmente, OpenRouter/Moonshot). Para o módulo de CRM, copie `config/crm_config.example.json` para `config/crm_config.json`.

> ⚠️ Os arquivos `config/api_keys.json` e `config/crm_config.json` contêm segredos e estão no `.gitignore` — **nunca** os comite.

## 📋 Requisitos

| Requisito | Detalhe |
|---|---|
| **SO** | Windows 10/11 (referência) |
| **Python** | 3.11 ou 3.12 |
| **Microfone** | Necessário para voz |
| **Chaves** | Gemini (grátis); OpenRouter/Moonshot opcionais |

## ⚖️ Licença & Créditos

Construído sobre o projeto open-source **MARK XXXIX-OR**, por **FatihMakes** ([@FatihMakes](https://www.youtube.com/@FatihMakes)), licenciado sob **[Creative Commons BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/)**. Este fork (Genesis) mantém a mesma licença e atribuição. Uso pessoal e não-comercial.
