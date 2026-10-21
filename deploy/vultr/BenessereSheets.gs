/** Benessere – Google Sheets -> VPS. Incollare in Estensioni > Apps Script.
 * Impostare Script Properties: BENESSERE_BRIDGE_URL, BENESSERE_BRIDGE_TOKEN.
 * Eseguire installaTrigger() UNA volta per autorizzare il trigger ogni 5 minuti.
 */
const TAB = 'Coda';
function syncBenessere() {
  const props = PropertiesService.getScriptProperties();
  const url = props.getProperty('BENESSERE_BRIDGE_URL');
  const token = props.getProperty('BENESSERE_BRIDGE_TOKEN');
  if (!url || !/^https:\/\//.test(url) || !token || token.length < 32) throw Error('Configurare URL HTTPS e token in Script Properties');
  const lock = LockService.getScriptLock();
  if (!lock.tryLock(15000)) return;
  try {
    const sheet = SpreadsheetApp.getActive().getSheetByName(TAB);
    const last = sheet.getLastRow();
    if (last < 2) return;
    const rows = sheet.getRange(2, 1, Math.min(last - 1, 500), 10).getDisplayValues();
    let processed = 0;
    for (let i = 0; i < rows.length && processed < 25; i++) {
      const [id, kind, , , , payload, status] = rows[i];
      if (status !== 'PENDING') continue;
      const row = i + 2;
      let state = 'ERROR', message = '';
      try {
        if (!id || !['meal','workout','max','profile'].includes(kind)) throw Error('ID/tipo non valido');
        const data = JSON.parse(payload);
        const response = UrlFetchApp.fetch(url, {
          method: 'post',
          contentType: 'application/json',
          headers: {'Authorization': 'Bearer ' + token},
          payload: JSON.stringify({id:id, type:kind, data:data}),
          muteHttpExceptions: true,
          followRedirects: false
        });
        const http = response.getResponseCode();
        const result = JSON.parse(response.getContentText());
        if (http === 200 && ['saved','duplicate'].includes(result.status)) {
          state = 'SAVED';
          message = result.status + ': ' + JSON.stringify(result.result);
        } else if (http === 400) {
          message = 'Validazione: ' + (result.error || 'errore');
        } else {
          // 5xx/401/timeout: pending, ritenta al prossimo trigger. ID evita duplicati.
          state = 'PENDING'; message = 'HTTP ' + http + ' - verificare connessione/credenziali';
        }
      } catch(e) {
        state = 'PENDING';
        message = 'Riprova: ' + String(e.message).slice(0, 140);
      }
      sheet.getRange(row,7,1,3).setValues([[state,new Date(),message.slice(0,450)]]);
      processed++;
    }
  } finally {
    lock.releaseLock();
  }
}
function installaTrigger() {
  ScriptApp.getProjectTriggers()
    .filter(t => t.getHandlerFunction() === 'syncBenessere')
    .forEach(t => ScriptApp.deleteTrigger(t));
  ScriptApp.newTrigger('syncBenessere').timeBased().everyMinutes(5).create();
}
