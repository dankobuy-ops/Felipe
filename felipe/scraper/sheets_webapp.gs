/**
 * Google Apps Script web app — upsert scraped JPL data into tabs:
 *   Juzgados, RUTs, Causas, Trámites, Documentos, Patentes,
 *   Causa-RUT, Causa-Patente
 *
 * Keyed by the unique ID in column A of each tab. Each export upserts by that ID:
 *   - existing rows with a matching col-A id are overwritten
 *   - new ids are appended
 * This lets you export multiple RUTs into the same sheet without duplicates.
 *
 * SETUP (one time, ~2 min):
 *   1. Open your target Google Sheet.
 *   2. Extensions -> Apps Script.
 *   3. Delete any boilerplate, paste this whole file, Save.
 *   4. Deploy -> New deployment -> gear icon -> "Web app".
 *        - Execute as: Me
 *        - Who has access: Anyone
 *      Deploy, authorize, copy the /exec URL.
 */
function doPost(e) {
  try {
    var body = JSON.parse(e.postData.contents);
    var ss   = body.spreadsheet_id
      ? SpreadsheetApp.openById(body.spreadsheet_id)
      : SpreadsheetApp.getActiveSpreadsheet();
    var j  = upsertTab_(ss, "Juzgados",      body.juzgados);
    var ru = upsertTab_(ss, "RUTs",          body.ruts);
    var c  = upsertTab_(ss, "Causas",        body.causas);
    var t  = upsertTab_(ss, "Trámites",      body.tramites);
    var x  = upsertTab_(ss, "Documentos",    body.documentos);
    var p  = upsertTab_(ss, "Patentes",      body.patentes);
    var cr = upsertTab_(ss, "Causa-RUT",     body.causa_rut);
    var cp = upsertTab_(ss, "Causa-Patente", body.causa_patente);
    return json_({ ok: true, juzgados: j, ruts: ru, causas: c, tramites: t,
                   documentos: x, patentes: p, causa_rut: cr, causa_patente: cp });
  } catch (err) {
    return json_({ ok: false, error: String(err) });
  }
}

/**
 * Upsert rows into a tab keyed by Caso ID (column A).
 * Creates the tab + header if it doesn't exist.
 * Returns the number of rows written (inserted + updated).
 */
function upsertTab_(ss, name, table) {
  if (!table || !table.header || !table.rows) return 0;
  var sh = ss.getSheetByName(name);

  // First time: create tab with header
  if (!sh) {
    sh = ss.insertSheet(name);
    sh.getRange(1, 1, 1, table.header.length).setValues([table.header]);
    sh.setFrozenRows(1);
    sh.getRange(1, 1, 1, table.header.length).setFontWeight("bold");
  }

  var newRows = table.rows;
  if (!newRows.length) return 0;

  // Build index of existing Caso IDs → row number (1-based, skipping header)
  var lastRow = sh.getLastRow();
  var existingIndex = {};
  if (lastRow > 1) {
    var existingIds = sh.getRange(2, 1, lastRow - 1, 1).getValues();
    for (var i = 0; i < existingIds.length; i++) {
      var id = String(existingIds[i][0]);
      if (id) existingIndex[id] = i + 2; // +2: 1-based + header offset
    }
  }

  var toAppend = [];
  for (var r = 0; r < newRows.length; r++) {
    var row    = newRows[r];
    var casoId = String(row[0]);
    if (existingIndex[casoId] !== undefined) {
      // Overwrite existing row in place
      sh.getRange(existingIndex[casoId], 1, 1, row.length).setValues([row]);
    } else {
      toAppend.push(row);
    }
  }

  if (toAppend.length) {
    sh.getRange(sh.getLastRow() + 1, 1, toAppend.length, toAppend[0].length).setValues(toAppend);
  }

  return newRows.length;
}

function json_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
