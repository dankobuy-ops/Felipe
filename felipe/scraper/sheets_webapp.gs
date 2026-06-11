/**
 * Google Apps Script web app to receive scraped JPL data and write it into THIS
 * spreadsheet as two linked tabs: "Causas" (Level 2) and "Documentos" (Level 3),
 * linked by the ROL column.
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
 * Each export REPLACES the contents of both tabs (full refresh).
 */
function doPost(e) {
  try {
    var body = JSON.parse(e.postData.contents);
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    var c = writeTab_(ss, "Causas", body.causas);
    var d = writeTab_(ss, "Documentos", body.documentos);
    return json_({ ok: true, causas: c, documentos: d });
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
