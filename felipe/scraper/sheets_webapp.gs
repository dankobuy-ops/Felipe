/**
 * Google Apps Script web app to receive scraped JPL data and write it into THIS
 * spreadsheet as four linked tabs, all keyed by "Caso ID" (job-prefix/ROL):
 *
 *   Causas      — one row per causa (case header + remisor)
 *   Demandados  — one row per demandado per causa (party + vehicle details)
 *   Trámites    — one row per trámite from Sección C
 *   Documentos  — one row per adjunto from Sección D
 *
 * SETUP (one time, ~2 min):
 *   1. Open your target Google Sheet.
 *   2. Extensions -> Apps Script.
 *   3. Delete any boilerplate, paste this whole file, Save.
 *   4. Deploy -> New deployment -> gear icon -> "Web app".
 *        - Description: JPL export
 *        - Execute as: Me
 *        - Who has access: Anyone     (the URL is the only secret)
 *      Deploy, authorize when prompted, copy the "/exec" Web app URL.
 *   5. Give that URL to export_sheets.py via --webhook (or SHEETS_WEBHOOK_URL).
 *
 * Each export REPLACES the contents of all tabs (full refresh).
 */
function doPost(e) {
  try {
    var body = JSON.parse(e.postData.contents);
    var ss   = body.spreadsheet_id
      ? SpreadsheetApp.openById(body.spreadsheet_id)
      : SpreadsheetApp.getActiveSpreadsheet();
    var c = writeTab_(ss, "Causas",     body.causas);
    var d = writeTab_(ss, "Demandados", body.demandados);
    var t = writeTab_(ss, "Trámites",   body.tramites);
    var x = writeTab_(ss, "Documentos", body.documentos);
    return json_({ ok: true, causas: c, demandados: d, tramites: t, documentos: x });
  } catch (err) {
    return json_({ ok: false, error: String(err) });
  }
}

function writeTab_(ss, name, table) {
  if (!table || !table.header) return 0;
  var sh = ss.getSheetByName(name) || ss.insertSheet(name);
  sh.clearContents();
  var rows = table.rows || [];
  var data = [table.header].concat(rows);
  sh.getRange(1, 1, data.length, table.header.length).setValues(data);
  sh.setFrozenRows(1);
  sh.getRange(1, 1, 1, table.header.length).setFontWeight("bold");
  return rows.length;
}

function json_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
