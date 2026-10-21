# 04 — Report dati F0 (da compilare dopo il primo run)

Stato: **in attesa del token**. Una volta eseguito `python f0_probe.py --days 7`, compila le tabelle qui sotto.

## Ottenere il token Zepp (una tantum, ~ogni 30 giorni)

L'API non ufficiale non supporta login email/password: serve il token `apptoken` che l'app Zepp invia a ogni richiesta. Si ottiene catturando il traffico HTTPS dell'app **una volta**, poi il PC lavora da solo finché il token non scade (~30 gg: quando `f0_probe.py` inizia a dare 401/403, si rifà la cattura).

### Opzione A — Android + HTTP Toolkit (5–10 minuti, provare per prima)

1. Installa [HTTP Toolkit](https://httptoolkit.com/) sul PC (la versione free basta).
2. Sul telefono: attiva il **debug USB**, collegalo al PC via cavo.
3. In HTTP Toolkit: *Intercept → Android device (via ADB)* e segui la procedura (installa il certificato, imposta il proxy).
4. Apri l'app **Zepp** sul telefono, vai sulla scheda Salute, scrolla, apri il sonno di ieri e un allenamento (così genera chiamate API varie).
5. In HTTP Toolkit: seleziona le richieste → *Export as HAR* → salva come `capture.har` nella cartella `benessere/`.
6. ```
   python vendor/zepp-health-cli/zepp_health.py init capture.har
   python f0_probe.py --days 7
   ```

⚠️ Su Android recenti alcune app rifiutano i certificati utente: se Zepp dà **errori di rete** durante la cattura, passa all'opzione B.

### Opzione B — iPhone qualsiasi con lo stesso account Zepp

L'app Zepp su iPhone, dopo il login con lo stesso account, mostra gli stessi dati da cloud **senza ricollegare lo strap** (il pairing del device non cambia). Su iOS i certificati utente del proxy funzionano senza problemi:
1. Installa l'app Zepp su un iPhone di fiducia, login col tuo account.
2. Proxy HTTP Toolkit/mitmproxy sull'iPhone (installa il profilo CA dalle impostazioni).
3. Naviga nell'app, esporta HAR, poi `init` e `f0_probe.py` come sopra.

### Opzione C — login via password (riserva di sviluppo)

I vecchi endpoint Huami di login con email/password a volte funzionano ma sono rate-limited/deprecati. Da implementare solo se A e B falliscono entrambe.

**Sicurezza**: `capture.har` e `config.json` contengono il token — non condividerli; sono già in `.gitignore`. Se un token "va in giro", esci dall'app Zepp per invalidarlo e rifai la cattura.

## Tabella granularità (compilare dai file in `data/raw/f0/`)

| Dato | File probe | Item nella finestra | Intervallo reale | Campi utili | Verdetto |
|---|---|---|---|---|---|
| FC (serie eventi) | `heart_rate.json` | | | | |
| FC 1 secondo (manifest) | `second_hr_index.json` | | | | |
| HRV SDNN | `events_hrv.json` | | | | |
| HRV RMSSD | `events_hrv-rmssd.json` | | | | |
| Readiness + temp | `events_readiness.json` | | | | |
| Salute giornaliera / RHR | `events_daily-health.json` | | | | |
| Body battery | `events_body-battery.json` | | | | |
| Stress | `events_stress.json`, `user_events_all-day-stress.json` | | | | |
| Respirazione | `events_respiratory.json` | | | | |
| Sonno | `band_data_sleep.json` | | | | |
| Sessioni sport | `sport_history_*.json` | | | | |
| Carico giornaliero | `sport_load.json` | | | | |
| Peso | `weight.json` | | | | |
| Profilo | `user_info.json` | | | | |

## Domande a cui il run deve rispondere

1. La FC in `heart_rate` è al minuto o più fitta? L'indice `second_hr_index` contiene URL zip scaricabili (FC 1 Hz completa)?
2. HRV notturna presente (SDNN e/o RMSSD)? Con che frequenza (per notte / per 5 min)?
3. Temperatura: `skinTempCalibrated` (delta centesimi di °C), `skinTempScore`, `skinTempBaseLine` presenti?
4. Sonno in `band_data`: la sezione fasi è decodificabile (struttura binaria/base64 nota in Gadgetbridge) o serve il parser?
5. Le sessioni di forza/CrossFit appaiono in qualche `sport_history_*`? Con quale segmento?
6. RHR dove vive: `events_daily-health` o altrove?

## Decisioni da prendere dopo il run

- [ ] Canale primario confermato (atteso: API cloud non ufficiale)
- [ ] FC ad alta frequenza: da eventi o da zip 1 s?
- [ ] Parser `band_data` necessario (probabile) — task F1
- [ ] Granularità HRV sufficiente per il readiness (atteso: sì)
