# Benessere 0.2 — sincronizzazione Android → PC (o VPS)

La v0.2 raccoglie da **Health Connect** i dati già sincronizzati dall'Helio Strap tramite Zepp, quindi li invia al backend senza usare token non ufficiali Zepp. **Non sostituisce Zepp** e non comunica in BLE direttamente con lo strap.

## 1. Avvia il server sul PC Windows

Sul PC Windows puoi avviare il backend con un doppio clic su **`AVVIA_SYNC_ANDROID.cmd`** nella cartella del progetto. La finestra rimane aperta finché vuoi ricevere dati. In alternativa apri un terminale nel progetto:

```cmd
cd C:\Users\Paolo\Desktop\BRAIN\sources\benessere
python sync_server.py --lan
```

Il terminale mostra un **token casuale** creato al primo avvio e salvato in `data/android_sync_token.txt`. Non divulgarlo e non caricarlo su GitHub.

- Per uso **solo locale**, usa `python sync_server.py` (ascolta 127.0.0.1, non raggiungibile da Android).
- `--lan` apre la porta **8766** sulla rete locale. Windows Firewall: consenti Python sulla sola **rete privata**. Non aprire la porta su Internet/router.
- Controlla l'IP corrente con `ipconfig`. L'ultimo IP noto del PC era **192.168.1.100**: potrebbe cambiare.
- Controllo (dallo smartphone sulla stessa Wi-Fi): `http://192.168.1.100:8766/health` dovrebbe rispondere `{"status":"ok"}`. Nessun dato medico è esposto da questo endpoint.
- **Avvertenza**: `--lan` usa HTTP senza TLS. I dati sanitari e il token sono trasmessi in chiaro sulla LAN. È adatto solo a una prova con Wi-Fi privata fidata. Per uso continuativo o da reti esterne configurare **HTTPS** (reverse proxy e certificato valido) e usare un accesso dedicato. Non portare il server pubblico così com'è.

## 2. Installa l'APK 0.2.0 dal Mac

Con il PC e il Mac sulla stessa Wi-Fi, e ADB già scaricato sul Mac:

```bash
cd ~/Desktop/Benessere
curl -fL http://192.168.1.100:8001/benessere-v0.2.0-debug.apk -o benessere-v0.2.0-debug.apk
./platform-tools/adb install -r benessere-v0.2.0-debug.apk
./platform-tools/adb shell am force-stop com.benessere.app
./platform-tools/adb shell am start -n com.benessere.app/.MainActivity
```

L'APK è servito dal server di download **8001** sul PC (se non attivo, dalla cartella del progetto: `python -m http.server 8001 --directory dist`). APK 0.2.0 e backend devono essere entrambi aggiornati.

## 3. Configura il telefono

Nell'app **Benessere → Sincronizzazione dati — PC / VPS**:

1. URL: `http://192.168.1.100:8766` (sostituisci con l'IP PC attuale).
2. Token: copia quello mostrato nella finestra `sync_server.py` sul PC.
3. Per la prova, seleziona **Consento HTTP non cifrato solo sulla mia Wi-Fi privata**.
4. Tocca **Salva** e **Sincronizza ora**.
5. Attiva **Sincronizza all'apertura + ogni ora...** solo se desideri automatizzarla; nelle versioni Android che supportano lettura in background, premi prima **Autorizza lettura in background** e concedi il permesso. Poi premi nuovamente **Salva**.

Il pulsante riporta l'esito dell'invio (numero campioni FC nuovi, sessioni ricevute, giorni). Se non riesce, mostra un errore; non elimina i dati originali da Health Connect.

### Cosa viene trasferito

| Tipo | Trattamento |
|---|---|
| Campioni frequenza cardiaca | Timestamp UTC, deduplica sul timestamp; nessun raddoppio su reimportazione |
| Sonno | Conserva sessioni con identificativo+origine; per ogni notte sceglie una sola sessione, con fasi dove disponibili. Senza fasi tratta la durata come stima |
| Passi | **Aggregate Health Connect**, riduce sovrapposizioni e duplicati fra sorgenti |
| Calorie attive e totali | Aggregate Health Connect per giorno: **sostituzione**, mai somma a ogni sync |
| Sessioni attività/allenamenti | Conservate come record grezzi separati per origine e ID, **non** convertite automaticamente in WOD né in carico CTL/ATL senza classificazione |

Le calorie attive alimentano il TDEE, purché non sovrascritte da una fonte Zepp preesistente. Le sessioni importate non modificano automaticamente il diario WOD. I dati Health Connect già presenti in altre app possono essere aggiornati con ritardo.

### Sincronizzazione automatica — limiti

- **All'apertura**: se attivata, l'app prova a importare gli ultimi 3 giorni quando viene aperta.
- **Periodica**: con permesso background effettivamente concesso e Android compatibile, il sistema pianifica un job ogni ~1 ora; **l'orario non è esatto** e dipende da Doze, rete, batteria e restrizioni Android.
- Quando Health Connect non consente la lettura in background, la sincronizzazione periodica viene disattivata ma restano l'aggiornamento all'apertura e il pulsante manuale.
- Richiede la raggiungibilità del backend: con PC spento, fuori dalla LAN e senza endpoint HTTPS raggiungibile, i tentativi falliscono. L'upload successivo riporta gli ultimi 3 giorni.
- **Cancellazioni o correzioni di record già importati**: questa prima versione non propaga automaticamente ogni eliminazione lato Health Connect al database PC. Conserva gli originali nel DB e usa la manutenzione manuale per rimozioni.

### Verifica sul backend

Nella dashboard Streamlit `http://localhost:8501`, apri **Impostazioni → Stato sincronizzazione Android**. Mostra l'ultimo sync e il numero di record importati.

## 4. Futuro VPS Vultr

La stessa app accetta un URL HTTPS pubblico, ad esempio `https://benessere.tuodominio.it`, quando saranno pronti DNS, reverse proxy TLS, firewall e backup cifrati. La VPS non è stata ancora configurata e **non serve** per il primo test.

### Privacy

Benessere memorizza il token nelle preferenze private Android e disabilita il backup Android. Il server lo conserva in `data/`, cartella ignorata da Git. Non pubblicare database, token, file HAR o endpoint HTTP su Internet.
