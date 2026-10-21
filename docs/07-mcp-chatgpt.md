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

## Avvio del server locale

Su Windows, fai doppio clic su `AVVIA_BENESSERE.cmd`, oppure esegui nella cartella del progetto:

```powershell
python mcp_server.py --http 8000
# Server MCP locale: http://127.0.0.1:8000/mcp
```

Questo URL può essere usato da client MCP **installati sul PC**, non direttamente da ChatGPT.

## Collegamento in ChatGPT

**Attenzione:** ChatGPT non può raggiungere `localhost`, neppure quando lo usi sul browser del medesimo PC. Il collegamento va effettuato tramite un **Secure MCP Tunnel** compatibile o un endpoint HTTPS remoto autenticato. La disponibilità degli strumenti e delle operazioni di scrittura dipende dal piano e dai permessi del tuo account.

1. Verifica di avere l'autorizzazione a collegare un server MCP personalizzato.
2. In **Plugin → + → Aggiungi server MCP personalizzato** (quando disponibile), configura il tunnel sicuro oppure l'URL HTTPS del server e l'autenticazione.
3. Controlla gli strumenti rilevati e autorizza solo le operazioni necessarie.
4. Esegui una prima prova di sola lettura (`today_snapshot`) prima di usare le funzioni di scrittura.

La modalità alternativa **Quick Tunnel Cloudflare** crea un URL accessibile da Internet: **non usarla senza prima verificare correttamente autenticazione, policy e protezione dei dati sanitari**. Il server prevede `MCP_TOKEN` (variabile d'ambiente) per proteggere l'accesso quando necessario, ma non installa/configura automaticamente alcun tunnel. Non pubblicare token o export del database.

Istruzioni ufficiali aggiornate: https://help.openai.com/en/articles/12584461-connecting-custom-mcp-servers-in-chatgpt

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

## I 15 tool

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
