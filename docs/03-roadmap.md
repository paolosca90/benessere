# 03 — Roadmap

Ogni fase ha un criterio di uscita verificabile. Nessuna fase dipende da hardware aggiuntivo oltre a strap + telefono + PC.

## F0 — Validazione accesso dati (in corso)

**Obiettivo**: provare con l'account reale che i canali promessi funzionano e capire la granularità effettiva dei dati.

- [x] Account Zepp operativo e strap sincronizzato da settimane (storico già presente)
- [x] Clonato `zepp-health-cli` in `vendor/` (MIT) e analizzate le API disponibili
- [ ] Ottenere il token una tantum: cattura HAR del traffico app Zepp (guida in `docs/04-report-dati.md`) → `python vendor/zepp-health-cli/zepp_health.py init capture.har`
- [ ] Eseguire `python f0_probe.py` → dump grezzi in `data/raw/f0/` + report granularità
- [ ] Sessione REA sull'APK Zepp estratto dal telefono (guida completa in `docs/06-rea-analisi.md`): conferma frame FC live, sveglie BLE, endpoint zip FC 1 s e cibo
- [ ] Prima build della nostra app (`app-android/`) sul telefono: permessi + lettura Health Connect coi dati reali
- [ ] Verificare la granularità reale: FC a 1 s o a 1 min? HRV (SDNN/RMSSD) presente? Fasi sonno a che risoluzione? Temperatura con baseline?
- [ ] Verificare cosa Zepp scrive su Health Connect (lista tipi effettivi + frequenza di scrittura giorno/notte, vedi docs/05)
- [ ] Decisione: canale primario confermato (atteso: C) e fallback

**Uscita**: `docs/04-report-dati.md` compilato con la tabella "campo → granularità → canale → esempio JSON".

Nota operativa: il token catturato scade dopo ~30 giorni → il backend dovrà rilevare il fallimento e richiedere una nuova cattura (rituale mensile di 5 minuti).

## F1 — MVP: ingest + storage + dashboard

- [ ] Pacchetto Python `benessere/` con CLI `sync` (pull incrementale dal canale primario, dedup)
- [ ] Schema SQLite del doc 02 implementato + migrazioni
- [ ] Metriche base: RHR, HRV baseline (7/30 gg), durata/efficienza sonno, debito sonno 7 gg, CTL/ATL/TSB, calorie attive
- [ ] Tag rapido post-sessione (tipo CrossFit: forza/metcon/gymnastics/mista o tennis + RPE) con notifica
- [ ] Dashboard Streamlit: home con readiness di oggi, trend settimanali, elenco sessioni con tag e carico ibrido
- [ ] Report mattutino (testo/HTML): readiness + sonno + carico + "cosa fare oggi"

**Uscita**: sync mattutino automatico + dashboard consultabile in < 5 s con dati del giorno.

## F2 — Nutrizione

- [ ] TDEE adattivo (BMR + calorie attive, media 7 gg) e target in base all'obiettivo
- [ ] Macro con periodizzazione carboidrati sulle sessioni
- [ ] Log pasti con pasti ricorrenti; bilancia kcal/macro target vs reale
- [ ] Timing pre/post allenamento legato alle sessioni rilevate

**Uscita**: ogni giorno il report mattutino contiene i target del giorno e il consuntivo di ieri.

## F3 — Sveglia intelligente

- [ ] L1: previsione finestra ottimale + sveglie telefoniche multiple nella finestra (già implementata in `app-android`)
- [ ] L2: prototipo `HuamiBleClient` che legge FC live durante la finestra — usa i frame confermati dalla sessione REA (docs/06) — e lancia la sveglia sul telefono nel momento giusto
- [ ] Estrazione chiave di pairing (docs/06) e test di coesistenza con l'app Zepp
- [ ] Confronto A/B personale: L2 vs sveglia fissa → metrica "grogginess" autovalutata

**Uscita**: sveglia che nella maggior parte dei giorni suona entro la finestra prevista per il sonno leggero.

## F4 — Coaching adattivo e raffinamenti

- [ ] Regole readiness+TSB → suggerimento sessione del giorno
- [ ] Ricalibrazione pesi del readiness sui propri dati storici
- [ ] Report settimanale con correlazioni (sonno↔HRV↔performance)
- [ ] Valutare L3 (vibrazione strap) e foto-pasti con AI

**Uscita**: suggerimenti quotidiani usati stabilmente e verificati contro i trend.

## Rischi principali e mitigazioni

| Rischio | Impatto | Mitigazione |
|---|---|---|
| API non ufficiale Zepp si rompe | Alto (canale primario) | Cache locale completa; fallback Health Connect; zepp-health-cli aggiornato dalla community |
| HRV non esposta da nessun canale | Medio (readiness più povero) | Proxy da FC notturna (variabilità della FC a 1 s è un indicatore debole ma usabile); F0 lo chiarisce subito |
| FC live non ottenibile senza spostare il pairing | Medio (sveglia L2) | L1 non ne dipende; fallback: telefono come sensore di risveglio (accelerometro) + vibrazione telefono |
| Calorie attive Zepp inaccurate | Basso | Media mobile + correzione con trend peso reale (aggiustamento statistico del TDEE) |
