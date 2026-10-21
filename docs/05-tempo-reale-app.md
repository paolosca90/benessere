# 05 — Tempo reale e app Android

Risposta alla domanda: *"un'app da cui prendere i dati in tempo reale ed elaborarli?"*

## Il vincolo di partenza

- Lo strap parla BLE con **una sola app host** (pairing esclusivo: Zepp *oppure* Gadgetbridge *oppure* la nostra).
- **Non expone il servizio BLE Heart Rate standard** verso terze app (verificato in ricerca: r/amazfit, forum Urbandroid).
- Health Connect **non è un canale real-time**: è un datastore che viene scritto quando l'app Zepp sincronizza.

Conseguenza: l'app in tempo reale non esiste pronta — la costruiamo noi, scegliendo il livello di real-time in base al bisogno.

## I tre livelli di real-time

### Livello 1 — Batch (canale C, già pianificato)
Pull giornaliero dal cloud Zepp via API non ufficiale. Latenza: ore. Copre analisi storiche, baseline, report della mattina. È la F0/F1.

### Livello 2 — Near real-time via Health Connect
Zepp app sincronizza in background → scrive su Health Connect → la **nostra app Android** legge (permission READ) con listener sui cambiamenti.
- Latenza attesa: minuti (da misurare: Frequenza reale di scrittura di Zepp, di notte in particolare → test esplicito in F0/F1)
- Copre: conferma post-allenamento (tag CrossFit + RPE), aggiornamento target nutrizionali durante la giornata, dashboard sempre fresca.
- Costo: basso, tutto API ufficiali.

### Livello 3 — Live 1 secondo via protocollo Huami BLE
La nostra app parla direttamente allo strap usando il protocollo Huami (reverse-engineered nel codice open di Gadgetbridge, che supporta l'Helio Strap).
- Serve la **chiave di pairing** (estraibile una volta dall'account/da log).
- **Convivenza con Zepp**: stessa chiave, connessione alternata — durante la finestra di risveglio si connette la nostra app (Zepp app va tenuta "fredda"), poi si rilascia.
- Uso: **solo sveglia intelligente L2** — leggere la FC nella finestra di risveglio e suonare al momento giusto.
- Nota GPL: se riusiamo codice da Gadgetbridge, la nostra app è GPL. Per uso personale irrilevante.
- Alternativa (configurazione B, non consigliata come principale): Gadgetbridge come host al posto di Zepp → live HR e vibrazione subito, ma si perde canale C e gli algoritmi sonno/HRV di Zepp.

## Quale livello serve per cosa

| Bisogno | Livello |
|---|---|
| Report mattutino, baseline, trend, analisi storica | 1 |
| Rilevazione/tag allenamento, target nutrizionali in giornata, dashboard | 2 |
| Sveglia intelligente (FC nella finestra di risveglio) | 3 |
| **FC live durante il WOD/tennis** | **fascia pettorale BLE standard** (vedi sotto) |

## FC live in allenamento: fascia pettorale BLE standard

La PPG da polso sotto sforzo/metcon è rumorosa (compressione tissutale) — il live dello strap sarebbe comunque il dato sbagliato durante il WOD.
Una fascia pettorale BLE standard (~30–40 €, es. CooSpo, Polar H10) trasmette in Heart Rate Service **standard**: la nostra app la legge nativamente senza alcun reverse engineering.
→ Lo strap resta dedicato a recupero/sonno/carico 24/7; la fascia dà FC live affidabile e precisa in allenamento. Le due fonti convivono nel modello dati (`workouts.source`).

## Design dell'app Android (il "bridge")

Kotlin, essenziale, nessuna pretesa di social/cloud:

1. **Reader Health Connect** (permission READ) + WorkManager periodico + change listener → POST JSON al backend PC in LAN (o elaborazione locale se il PC è spento, con coda).
2. **UI minima**: readiness di oggi, target del giorno, notifica post-allenamento per il tag (forza/metcon/gymnastics/tennis + RPE).
3. **Sveglia L1**: AlarmManager + sveglie multiple nella finestra prevista.
4. **Modulo BLE live (fase 3)**: connessione Huami nella finestra di risveglio + lettura fascia pettorale standard.
5. **Backend PC**: archivio SQLite storico, analisi pesanti, dashboard completa.

## Verifiche da aggiungere in F0/F1

- [ ] Frequenza reale di scrittura Zepp → Health Connect (giorno e notte)
- [ ] Elenco tipi effettivamente scritti (HR con che granularità, sonno, SpO2, peso…)
- [ ] (fase 3) Proof-of-concept live HR Huami sull'Helio Strap da app nostra
