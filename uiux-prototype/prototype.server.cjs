const http = require('node:http');
const fs = require('node:fs/promises');
const path = require('node:path');

const prototype = path.join(__dirname, 'prototype.html');
const port = Number(process.env.PORT || 4173);

http.createServer(async (_request, response) => {
  try {
    const html = await fs.readFile(prototype);
    response.writeHead(200, {
      'content-type': 'text/html; charset=utf-8',
      'cache-control': 'no-store'
    });
    response.end(html);
  } catch (error) {
    response.writeHead(500, {'content-type': 'text/plain; charset=utf-8'});
    response.end(error.message);
  }
}).listen(port, '127.0.0.1', () => {
  console.log(`Prototype server: http://127.0.0.1:${port}`);
});
