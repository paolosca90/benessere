# Benessere Android — errori di installazione e firme

## Diagnosi

L'app esistente usa l'ID `com.benessere.app` ed è stata compilata
inizialmente sul PC Windows. GitHub Actions usa una **debug keystore
temporanea** diversa a ogni run: un APK debug compilato in questo modo
non può aggiornare l'app già presente, anche se `versionCode` cresce.

Non disinstallare l'app precedente senza prima annotare in modo sicuro
indirizzo server e token: i dati di Health Connect restano in Health
Connect e sul server, ma le impostazioni locali vengono eliminate.

## APK di test immediato

Il job CI `android-canary` produce
`benessere-v0.2.4-TEST-installabile`. Usa
`com.benessere.app.canary` e il nome `Benessere TEST`. Può
essere installato **accanto** alla versione originale; non ne condivide
impostazioni o token e non la aggiorna. È per prove scanner BLE, FC
standard, permessi parziali e HRV. Impostare sincronizzazione automatica
su una sola app per evitare richieste duplicate.

## Aggiornamenti permanenti con la firma originale

La chiave originale è sul PC dove è stata compilata la versione 0.2.1:
`%USERPROFILE%\.android\debug.keystore`. **Non pubblicarla nel
repository, non inviarla in chat e non allegarla a issue/PR.**

Una volta, direttamente sul **PC Windows**, autenticato su GitHub:

```powershell
gh auth login
$keyPath = Join-Path $env:USERPROFILE ".android\debug.keystore"
if (-not (Test-Path $keyPath)) { throw "Chiave originale non trovata" }
[Convert]::ToBase64String([IO.File]::ReadAllBytes($keyPath)) |
  gh secret set BENESSERE_ANDROID_DEBUG_KEYSTORE_B64 -R paolosca90/benessere
if ($LASTEXITCODE -ne 0) { throw "Configurazione secret fallita" }
gh variable set BENESSERE_SIGNING_READY -R paolosca90/benessere -b true
```

Questi comandi inviano il contenuto della chiave **direttamente a GitHub
come segreto cifrato**, senza stamparla sul terminale. Eseguire solo se
si accetta di conservare la chiave nella sezione Actions Secrets del
proprio repository privato/pubblico. L'APK firmato rimane una *build
debug*, non una release per Play Store.

Dopo questa configurazione, il job `android` produce
`benessere-v0.2.4-compatible` con **la stessa identità di firma**
del vecchio APK. Il job si rifiuta di costruire l'APK compatibile
quando la chiave originale non è disponibile. Il job `android-canary`
rimane indipendente.

L'abilitazione della variabile richiede un nuovo workflow run sulla PR,
oppure il trigger manuale previsto dal workflow.

## In caso di errore dopo il nuovo APK

Collegando Android via USB a un computer con Android Platform Tools:

```sh
adb devices
adb install -r path/to/app-debug.apk
```

Interpretare l'errore specifico:
- `INSTALL_FAILED_UPDATE_INCOMPATIBLE`: firma incompatibile.
- `INSTALL_FAILED_VERSION_DOWNGRADE`: installare un versionCode più alto.
- `INSTALL_PARSE_FAILED_*`: APK corrotto/non valido, riprovare con ZIP estratto.
- `INSTALL_FAILED_INSUFFICIENT_STORAGE`: liberare spazio sul telefono.
- `INSTALL_FAILED_OLDER_SDK`: versione Android inferiore al minimo supportato.

Non procedere a disinstallazioni automatiche o reset dei dati.
