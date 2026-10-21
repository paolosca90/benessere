# 07 — Collegare i dati a ChatGPT via MCP (con flusso foto)

Il server MCP di Benessere espone i tuoi dati come **tool** per ChatGPT: leggere readiness/allenamenti/WOD/PR/nutrizione e **scrivere** (pasti, sessioni, risultati). Da ChatGPT i "plugin" oggi si chiamano **Connettori (MCP)**: il nostro server è esattamente quello.

## Flusso foto (il caso d'uso principale)

Allega una foto in chat e chiedi — il modello legge l'immagine, estrae i dati e chiama i tool:

| Foto | Prompt esempio | Cosa succede |
|---|---|---|
| 🍽️ piatto mangiato | *"Logga questo pasto come pranzo"* | ChatGPT stima kcal/macro → `log_meal` con descrizione dei cibi |
| 📋 lavagnetta del box | *"Salvami questo WOD e logga la sessione di oggi"* | `add_wod` (WOD trascritto) + `log_workout` (tipo/durata/RPE) |
| ⏱️ risultato sul timer | *"Ho fatto questo WOD in 4:32, registralo"* | `log_wod_result` → PR automatico se battuto |
| ⚖️ bilancia | *"Peso di oggi: aggiorna"* | `set_profile` |

Le descrizioni dei tool contengono già queste istruzioni: non serve configurare nulla.

## Avvio del server

```bash
cd C:\Users\Paolo\Desktop\BRAIN\sources\benessere

# Locale (desktop ChatGPT sullo stesso PC):
python mcp_server.py --http 8000
#   → http://localhost:8000/mcp

# Esposto per il telefono (tunnel + token), vedi sotto:
MCP_TOKEN=tua-frase-segreta python mcp_server.py --http 8000
```

## Collegamento in ChatGPT

**Importante**: i connettori remoti vengono chiamati dai server di OpenAI, quindi:
- **ChatGPT desktop sul PC dove gira il server** → `http://localhost:8000/mcp` funziona direttamente
- **ChatGPT da telefono/browser** → serve un URL pubblico: tunnel `cloudflared` (sotto) + `MCP_TOKEN`

Passi (una volta):
1. ChatGPT → *Impostazioni* → **Connectors** → sezione *Advanced* → attiva **Developer mode**
2. *Connectors* → **Create** → nome `Benessere` → tipo **MCP server**
3. URL: `http://localhost:8000/mcp` (desktop) o l'URL del tunnel (telefono)
4. Se usi `MCP_TOKEN`: in autenticazione scegli **Bearer token** e incolla la stessa frase
5. In una chat nuova: attiva Developer mode nel selettore strumenti → spunta il connettore **Benessere**

### Tunnel per l'uso da telefono (10 minuti, una volta)

```bash
winget install Cloudflare.cloudflared        # oppure scarica cloudflared.exe
cloudflared tunnel --url http://localhost:8000
#   → stampa un URL https://…trycloudflare.com : usalo come URL del connettore
```

Con `MCP_TOKEN` attivo, il server risponde 401 a chiunque non presenti il token — verificato con test (401 senza / 200 con). Chiudi il tunnel quando non serve.

## Claude Desktop (stdio, opzionale)

`claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "benessere": {
      "command": "python",
      "args": ["C:\\Users\\Paolo\\Desktop\\BRAIN\\sources\\benessere\\mcp_server.py"]
    }
  }
}
```

## I 14 tool

| Tool | Cosa fa |
|---|---|
| `today_snapshot` | readiness + target + pasti + reminder + carico di oggi |
| `get_readiness(days)` | storico readiness con componenti |
| `get_workouts(days)` / `log_workout(…)` | leggi/registra sessioni (foto-friendly) |
| `get_training_load(days)` | CTL/ATL/TSB giorno per giorno |
| `list_wods` / `add_wod(…)` / `log_wod_result(…)` / `get_wod_history(wod)` / `get_prs()` | WOD completo con PR (foto-friendly) |
| `get_nutrition(date)` / `log_meal(…)` | target vs mangiato, log pasti (foto-friendly) |
| `sync_zepp(days)` | scarica dati Helio Strap dal cloud Zepp (serve token docs/04) |
| `export_all()` | dump JSON completo del DB |

## Prompt pronti

- *(con foto piatto)* "Logga il pranzo"
- *(con foto lavagnetta)* "Crea il WOD di oggi e registra la sessione: 55 minuti, RPE 8"
- "Com'è andata la mia settimana? Readiness, carico e sonno."
- "Domani ho un metcon pesante: aggiustami i carboidrati."
- "Confronta i miei Fran: sto migliorando?"
