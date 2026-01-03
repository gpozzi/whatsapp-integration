function onEdit(e) {
  var range = e.range;
  var sheet = range.getSheet();

  // Ajusta esto al nombre de tu hoja de inventario
  if (sheet.getName() !== "Inventario") {
    return;
  }

  var row = range.getRow();
  var numColumns = sheet.getLastColumn();

  // Obtenemos los headers (primera fila)
  var headers = sheet.getRange(1, 1, 1, numColumns).getValues()[0];

  // Obtenemos los valores de la fila editada
  var rowValues = sheet.getRange(row, 1, 1, numColumns).getValues()[0];

  // Construimos el objeto JSON
  var payload = {};
  for (var i = 0; i < headers.length; i++) {
    payload[headers[i]] = rowValues[i];
  }

  var options = {
    'method' : 'post',
    'contentType': 'application/json',
    'headers': {
      'Authorization': 'Bearer ' + 'YOUR_SYNC_API_KEY' // Reemplaza con tu clave real o usa PropertiesService
    },
    'payload' : JSON.stringify(payload),
    'muteHttpExceptions': true
  };

  // Reemplaza con tu URL real de Cloud Run
  var url = "YOUR_CLOUD_RUN_URL/sync-inventory";

  try {
    var response = UrlFetchApp.fetch(url, options);
    Logger.log(response.getContentText());
  } catch (error) {
    Logger.log("Error syncing inventory: " + error);
  }
}
