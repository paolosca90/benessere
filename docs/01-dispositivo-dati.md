# 01 — Dispositivo e accesso ai dati

Ricerca di fattibilità completata il 2026-10-20. Fonti in fondo al documento.

## Amazfit Helio Strap — cosa misura

Dispositivo senza schermo (~99 $), indossabile al polso o al braccio, batteria fino a 10 giorni, pensato come alternativa a Whoop senza abbonamento. Si configura tramite l'app **Zepp** (Android/iOS), che sincronizza con il cloud Zepp.

| Sensore / funzione | Dettaglio | Qualità del dato per noi |
|---|---|---|
| **Frequenza cardiaca (PPG)** | Campionata **ogni secondo**, 24/7 (sonno, attività, allenamento) | ⭐⭐⭐ Il dato più prezioso: granularità 1 Hz permette analisi fine (HRV notturna di Zepp, RHR, risposta al carico) |
| **SpO2** | Misurazione notturna / on-demand | ⭐⭐ Trend utile come segnale di recupero/affaticamento |
| **Temperatura cutanea** | Notturna, deviazione dalla baseline personale | ⭐⭐ Segnale di recupero / incombenza malattia |
| **Accelerometro + giroscopio** | Movimento, sonno, rilevamento attività | ⭐⭐ Non accessibile direttamente: usato dagli algoritmi Zepp |
| **Sonno** | Fasi (leggero/profondo/REM), risvegli, punteggio, cicli | ⭐⭐⭐ Dato in uscita già processato da Zepp |
| **Modalità sportive** | ~27–50 modalità, inclusa la forza; auto-rilevamento camminata/corsa | ⭐⭐ Sessioni con FC media/max, calorie, durata |
| **Passi / distanza / calorie attive** | Stime da IMU; distanza reale solo con **connected GPS** del telefono | ⭐⭐ Le calorie attive sono stime grossolane ma usabili come serie |
| **Vibrazione** | Motore per notifiche e fino a **10 sveglie** impostabili dall'app Zepp | ⭐⭐⭐ Chiave per la sveglia intelligente |

### Limiti da tenere a mente

1. **Nessun GPS integrato**: per trace, ritmo e distanza precisa serve il telefono connesso. Il software non deve dipendere dal GPS.
2. **Nessuna sveglia intelligente nativa**: lo strap vibra solo a orari fissi impostati via app Zepp. La "smart wake" va costruita noi (vedi `02-architettura.md`).
3. **Accuratezza PPG in palestra**: la FC durante esercizi di forza/isometrie è nota come poco affidabile (compressione del tessuto). I carichi di forza vanno trattati con modelli più tolleranti (RPE/durata) anziché FC pura.
4. **HRV vera richiede intervalli RR**: Zepp calcola internamente una HRV notturna e la espone nel proprio ecosistema; la FC a 1 Hz non basta per ricalcolare RMSSD da soli. Il piano è usare la HRV di Zepp dove disponibile.
5. **Piattaforma chiusa**: niente API pubblica; terze parti (es. Sleep as Android) confermano che non esiste integrazione ufficiale in tempo reale.

## I quattro canali di accesso ai dati

### A. Health Connect (Android) — via app Zepp

La app Zepp (Android) può scrivere la maggior parte dei dati in **Health Connect**, leggibile con la Health Connect API. Tipi attesi: sessioni di esercizio, sonno con fasi, FC, RHR, SpO2, passi, distanza, calorie.

- ✅ Ufficiale, stabile, privacy controllabile
- ❌ Serve una componente **su telefono Android** (Health Connect non è accessibile da PC); granularità dipende da cosa Zepp scrive; HRV non garantita
- Ruolo nel progetto: canale "sicuro" di backup e dati near-real-time

### B. Apple Health (iOS) — via app Zepp

Equivalentemente su iPhone tramite HealthKit. Stesso ruolo del canale A, altra piattaforma.

### C. API cloud non ufficiale Zepp/Huami — da PC 🔑 canale primario proposto

L'app mobile Zepp parla con i server Huami/Zepp tramite API private, **reverse-engineered** dalla community e funzionanti con le normali credenziali dell'account. Strumenti esistenti: `zepp-health-cli` (wrapper Python single-file), vari MCP server community, connettori commerciali (Terra).

- ✅ Da PC, nessuna componente mobile; **storico completo**; il set più ricco: FC, HRV, temperatura cutanea, sonno dettagliato, sessioni
- ❌ API privata: può rompersi senza preavviso; area grigia dei ToS; serve gestione login (a volte CAPTCHA/2FA)
- Mitigazione: cache locale completa (una volta importato, il dato è nostro) + canale A come fallback

### D. Gadgetbridge (Android, FOSS) — controllo locale e tempo reale

Gadgetbridge elenca l'Helio Strap come **"mostly supported"**: notifiche (con vibrazione dello strap!), FC live, configurazione misurazioni. Non trasmette FC via standard BLE Heart Rate Service verso app terze.

- ✅ Vibrazione dello strap pilotabile da notifiche → **meccanismo di sveglia intelligente**; FC in tempo reale durante la notte
- ❌ **Il pairing è esclusivo**: lo strap può parlare con una sola app host (Zepp *oppure* Gadgetbridge). Sostituire Zepp significa perdere i suoi algoritmi sonno/HRV e il canale C
- Ruolo nel progetto: sorgente sperimentale per la sveglia intelligente livello "live" (da valutare il trade-off, vedi architettura)

### Sintesi della strategia dati

```
Helio Strap ─BLE─> app Zepp ──> cloud Zepp ──(API non ufficiale, canale C)──> Backend Python [canale primario]
                      │
                      └─> Health Connect / Apple Health ──(bridge)──────────> Backend Python [fallback/near-realtime]
```

Per la sveglia intelligente in tempo reale (fase 3 della roadmap): FC live durante la notte tramite protocollo live-HR Huami (ispirato al codice open di Gadgetbridge) in una piccola app Android nostra, **senza** spostare il pairing da Zepp; oppure valutare l'hosting su Gadgetbridge come configurazione alternativa.

## Fonti

- [Pagina ufficiale Helio Strap](https://us.amazfit.com/products/helio-strap)
- [DC Rainmaker — recensione approfondita (giugno 2025)](https://www.dcrainmaker.com/2025/06/amazfit-helio-band-in-depth-review-99-no-sub-fee-but-worth-it.html)
- [Reddit r/amazfit — dati/API su Helio Strap e Health Connect](https://www.reddit.com/r/amazfit/comments/1nuiv97/considering_the_helio_strap_but_worried_about)
- [m4ary/zepp-health-cli — CLI non ufficiale per dati Zepp/Huami](https://github.com/m4ary/zepp-health-cli)
- [Gadgetbridge — supporto Amazfit (Helio Strap "mostly supported")](https://gadgetbridge.org/gadgets/wearables/amazfit)
- [Reddit r/amazfit — Helio Strap e smart alarm (assente)](https://www.reddit.com/r/amazfit/comments/1m77urd/helio_strap_and_smart_alarm)
- [Forum Urbandroid — integrazione terze parti chiusa](https://forum.urbandroid.org/t/amazfit-helio-strap/15296)
- [Supporto Amazfit — sveglie sullo strap](https://support.amazfit.com/us/amazfit_helio_strap/docs/OsPQdAr2OoZ8FUx8A8scSBzFnXz)
- [Reddit r/amazfit — condivisione BLE HR non disponibile](https://www.reddit.com/r/amazfit/comments/1i5eh20/ble_heart_rate_sharing)
