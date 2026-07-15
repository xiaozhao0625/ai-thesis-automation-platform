const http = require('node:http');
const fs = require('node:fs/promises');
const path = require('node:path');

const prototype = path.join(__dirname, 'prototype.html');
const projectFactPayload = path.join(__dirname, 'project-fact-r2.json');
const port = Number(process.env.PORT || 4173);

async function handler(request, response) {
  try {
    const url = new URL(request.url, 'http://127.0.0.1');
    if (url.pathname.startsWith('/api/project-facts')) {
      const payload = JSON.parse(await fs.readFile(projectFactPayload, 'utf8'));
      let body;
      if (url.pathname === '/api/project-facts') body = payload.initial;
      else if (url.pathname === '/api/project-facts/conflict') body = payload.conflict;
      else if (url.pathname === '/api/project-facts/impact') body = payload.conflict.impact;
      else if (url.pathname === '/api/project-facts/confirm') body = payload.confirmation;
      else {
        response.writeHead(404, {'content-type': 'application/json; charset=utf-8'});
        response.end(JSON.stringify({error: 'PROJECT_FACT_API_NOT_FOUND'}));
        return;
      }
      response.writeHead(200, {'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store'});
      response.end(JSON.stringify(body));
      return;
    }
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
}

function createPrototypeServer() {
  return http.createServer(handler);
}

if (require.main === module) {
  createPrototypeServer().listen(port, '127.0.0.1', () => {
    console.log(`Prototype server: http://127.0.0.1:${port}`);
  });
}

module.exports = {createPrototypeServer};
