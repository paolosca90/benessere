# Benessere — attivazione pratica (Windows + Android)

## 1. Aprire la dashboard sul PC

Doppio clic su `AVVIA_BENESSERE.cmd` nella cartella del progetto.
Il file controlla le dipendenze, apre `http://127.0.0.1:8501` e avvia, se non è già in ascolto, il server MCP **solo sul PC** (`127.0.0.1:8000`). Se una porta è già occupata, non termina il processo esistente.

Se mancano dipendenze, apri un terminale nella cartella ed esegui:

```powershell
python -m pip install -r requirements.txt
```

## 2. Usarla immediatamente, anche senza Amazfit

- **Impostazioni**: verifica i dati personali, il peso, l'obiettivo, il fabbisogno di sonno e la FC a riposo. Sono valori da confermare, non misure automatiche.
- **Allenamenti**: registra tipo, durata e RPE di una sessione effettivamente svolta.
- **WOD**: registra un risultato reale, separando Rx/Scaled, poi consulta i PR.
- **Alimentazione**: aggiungi un pasto con calorie e macro stimati.

Il database centrale vive in `data/benessere.db`. Non eliminare il file; fai backup prima di cambiare PC.

## 3. Collegare il telefono all'Helio Strap

L'APK Android è già compilato in `dist/benessere-v0.1.0-debug.apk`.

Se il server di download (porta 8001) è attivo e PC e telefono sono sulla stessa rete Wi-Fi, apri sul telefono:

`http://192.168.1.100:8001/benessere-v0.1.0-debug.apk`

**Nota:** `192.168.1.100` era l'IPv4 locale verificato il 21 ottobre 2026: può cambiare. Per verificare l'IP attuale sul PC usa `ipconfig`; se il server non è in ascolto puoi avviarlo temporaneamente dalla cartella progetto con `python -m http.server 8001 --bind 0.0.0.0 --directory dist`. Chiudilo dopo aver scaricato l'APK: espone i file della cartella `dist` sulla LAN.

Sul telefono:

1. Installa Benessere e consenti i permessi necessari.
2. Apri Zepp, sincronizza il tuo Amazfit Helio Strap e abilita la condivisione verso Health Connect, se disponibile per la tua versione di Zepp.
3. Concedi a Benessere i permessi di lettura di Health Connect e premi **Aggiorna**.
4. Verifica che compaiano effettivamente i dati (non basta che i permessi risultino attivi).

**Limite attuale:** le letture Health Connect sono sul **telefono** e **non vengono ancora trasferite automaticamente al database del PC**. Il backend PC riceve dati dello strap tramite la sincronizzazione cloud Zepp descritta nel punto 4.

## 4. Attivare i dati reali nella dashboard PC

In **Impostazioni → Sincronizzazione Helio Strap**, controlla lo stato del token Zepp. Se manca:

1. Segui `docs/04-report-dati.md` per acquisire il token **del tuo account** e inizializzare il client.
2. Non inviare file HAR o token in chat e non caricarli su servizi esterni.
3. Quando il token è presente, premi **Sincronizza ora (ultimi 7 giorni)**.
4. Controlla le quantità importate e gli errori riportati: gli endpoint sono non ufficiali e alcuni dati potrebbero non essere disponibili.

In assenza di dati HRV, sonno e altri indicatori non interpretare un readiness vuoto come un punteggio basso.

## 5. Collegare ChatGPT

Il server MCP locale (`http://127.0.0.1:8000/mcp`) è utilizzabile dai client MCP locali.
**ChatGPT non può raggiungere direttamente un indirizzo localhost**, nemmeno dal browser del medesimo PC: richiede una connessione MCP remota tramite un **Secure MCP Tunnel** supportato o un endpoint HTTPS raggiungibile, con autenticazione e permessi adeguati. Le funzioni di scrittura possono dipendere dal piano e dai permessi dell'account.

Vedi `docs/07-mcp-chatgpt.md` e la documentazione ufficiale:
https://help.openai.com/en/articles/12584461-connecting-custom-mcp-servers-in-chatgpt

Non esporre pubblicamente il database o il server MCP senza configurare accesso sicuro: contengono dati sulla salute.
