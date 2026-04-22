# Garmin Connect — Setup Guide (v2, April 2026)

**Status:** Aguardando login interativo de Renato (terça-feira, 22/04)
**Solução escolhida:** `garmin-givemydata` (browser-based, bypass Cloudflare)

---

## Por que mudamos de abordagem

Em março de 2026, o Garmin deployou proteções agressivas de Cloudflare que quebraram **toda a comunidade Python**:
- `garth` → **deprecated** oficialmente em 28/03/2026
- `python-garminconnect` → **broken** (depende do garth)
- `garmy` → mesma auth por baixo, alto risco

A solução que funciona: **`garmin-givemydata`** — usa Chrome headless (SeleniumBase UC mode) para bypassar o bot detection. Testado no macOS, OpenClaw listado explicitamente na documentação.

---

## O que você vai ganhar

- **47 tabelas** de dados no SQLite local
- **10+ anos** de histórico no primeiro sync (~30 min)
- **44 ferramentas MCP** — Body Battery, HRV, Training Readiness, sono, atividades, VO2max, tudo
- **Sync incremental** depois disso (segundos por dia)
- **Dados ficam 100% locais** — nada vai para nenhum servidor externo

---

## Setup (5 minutos no terminal, terça-feira)

### Passo 1: Instalar via Homebrew (mais simples no Mac)

```bash
brew install nrvim/tap/garmin-givemydata
```

### Passo 2: Primeiro sync (vai pedir email + senha do Garmin)

```bash
garmin-givemydata
```

Vai abrir um Chrome headless, fazer login no Garmin Connect, e começar a puxar o histórico completo. Vai levar ~20-30 minutos para 10 anos de dados. **Não feche o terminal**.

Se pedir MFA (código no app Garmin ou email), digita quando aparecer.

### Passo 3: Verificar o que foi baixado

```bash
garmin-givemydata --status
```

### Passo 4: Integrar com o Health Dashboard

Depois que o sync terminar, avisa o Alfred. Ele configura o MCP server e integra com o dashboard automaticamente.

---

## Onde ficam os dados

```
~/.garmin-givemydata/
├── garmin.db          # SQLite com tudo (47 tabelas)
├── browser_profile/   # Sessão do Chrome (válida por semanas/meses)
├── .env               # Credenciais salvas (nunca compartilhar)
└── fit/               # Arquivos FIT originais de cada atividade
```

---

## Syncs futuros (automático)

Depois do primeiro setup, sync diário é só:

```bash
garmin-givemydata
```

Vai levar segundos (só dados novos desde o último sync).

---

## Troubleshooting

**"Login failed":** Delete o browser profile e tente de novo:
```bash
rm -rf ~/.garmin-givemydata/browser_profile
garmin-givemydata
```

**Chrome não abre:** Verifica se o Google Chrome está instalado em `/Applications/Google Chrome.app`

**Session expirou (403):** Acontece se o IP mudou. Delete o browser profile e refaz o login.

---

## Próximos passos (Alfred configura depois do sync)

1. Configurar MCP server no Claude Desktop / OpenClaw
2. Integrar `garmin.db` com o `daily_health_report.py` (substituir `garmin: null`)
3. Adicionar Body Battery + Training Readiness no Health Dashboard
4. Configurar sync incremental automático diário (cron)

---

**Lembre-se:** Terça-feira 09:00 — abrir o terminal e rodar os Passos 1 e 2 acima.
