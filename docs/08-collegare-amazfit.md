# 08 — Collegare l'app all'Helio Strap (Amazfit)

"È già tutto predisposto?" — Sì per il canale **Health Connect** (il più utile day-by-day); mancano solo due azioni tue: installare l'APK e dare i permessi. Lo storico completo dal cloud Zepp arriva con il token (docs/04); la sveglia BLE live è fase 3.

## 1. Installa l'app sul telefono (APK già compilato)

Il file è `dist/benessere-v0.1.0-debug.apk`. Tre modi, il primo è il più semplice (PC e telefono sulla stessa Wi-Fi):

**A. Download dal browser del telefono** (server già attivo sul PC):

1. Sul telefono apri il browser e vai su **`http://192.168.1.100:8001/benessere-v0.1.0-debug.apk`**
2. Il file si scarica → tocca la notifica di download
3. Android chiede di consentire l'installazione da quell'app (Chrome) → **Impostazioni → Consenti installa app sconosciute** → torna indietro → **Installa**
   - Se il download non parte: sul PC, **Windows Security → Firewall → Consungi app → spunta Python** (rete privata), poi riprova

**B. WhatsApp**: mandati l'APK come *Documento* (non come foto) dal PC, aprilo sul telefono → installa

**C. adb dal Mac** (telefono già autorizzato): dopo aver copiato l'APK sul Mac → `adb install ~/Desktop/benessere-v0.1.0-debug.apk`

## 2. Prima apertura dell'app

1. Apri **Benessere** → **"Concedi permessi (Bluetooth + notifiche)"** → consenti
2. Sezione *Dati di oggi — Health Connect* → **Permessi** → si apre Health Connect → attiva tutte le letture (FC, sonno, allenamenti, passi, calorie, SpO2, peso)
   - Percorso manuale se non si apre: *Impostazioni → Sicurezza e privacy → Privacy → Health Connect → Permessi app → Benessere*
3. Tocca **Aggiorna**: appare il riepilogo (campioni FC di oggi, sonno, ecc.)

## 3. Abilita Zepp → Health Connect (il rubinetto dei dati)

Lo strap manda i dati all'app Zepp; perché arrivino anche alla nostra app, Zepp deve scriverli in Health Connect:

1. Apri **Zepp** → *Profilo* (in basso) → ingranaggio ⚙️ *Impostazioni* → cerca **"Health Connect"** (o "Aggiungi dati a Health Connect") → attiva la sincronizzazione e le categorie
2. Poi: *Impostazioni di Android → Sicurezza e privacy → Privacy → Health Connect → Permessi app → **Zepp*** → attiva le categorie (attività fisica, FC, sonno…)
3. Verifica: apri Zepp e scorri la home (forza la sincronizzazione) → torna su Benessere → **Aggiorna** → i numeri si popolano

## 4. Cosa funziona dopo questi passi

| Funzione | Stato |
|---|---|
| Dati di oggi su telefono (FC, sonno, passi, calorie, sessioni) da Health Connect | ✅ subito |
| Sveglia intelligente L1 (finestra + sveglie multiple sul telefono) | ✅ subito |
| Fascia pettorale BLE standard → FC live durante i WOD | ✅ subito (in scansione) |
| Lettura BLE diretta dello strap (auth Huami) | 🟡 sperimentale — il trasporto reale (FED0) è confermato ma il layer protobuf va completato (docs/06) |
| Storico completo dal cloud Zepp (FC 1 s, HRV, temperatura) nel backend PC | ⏳ serve il token (docs/04) |

## Nota architettura

L'app Android legge Health Connect **sul telefono**; le analisi pesanti e la UI completa (Streamlit) vivono sul PC e si alimentano dal canale cloud Zepp (`sync_zepp` / pulsante Sincronizza). L'invio automatico telefono→PC in LAN è il passo successivo previsto (così i dati del telefono arrivano nel DB centrale senza aprire nulla).
