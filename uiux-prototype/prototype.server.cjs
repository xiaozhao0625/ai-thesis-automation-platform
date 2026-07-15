const http = require('node:http');
const fs = require('node:fs/promises');
const fsSync = require('node:fs');
const path = require('node:path');
const {spawn} = require('node:child_process');

const prototype = path.join(__dirname, 'prototype.html');
const projectFactPayload = path.join(__dirname, 'project-fact-r5.json');
const port = Number(process.env.PORT || 4173);
let intakeConfirmed = false;
let conflictConfirmation = null;
const executableRoot = fsSync.existsSync(path.join(__dirname, '..', 'project-fact-p0-r5'))
  ? path.join(__dirname, '..', 'project-fact-p0-r5')
  : path.join(__dirname, '..', 'executable');

function sendJson(response, status, body) {
  response.writeHead(status, {'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store'});
  response.end(JSON.stringify(body));
}

function readJsonBody(request) {
  return new Promise((resolve, reject) => {
    let source = '';
    request.setEncoding('utf8');
    request.on('data', chunk => { source += chunk; });
    request.on('end', () => {
      if (!source.trim()) return reject(new Error('CONFIRMATION_REQUEST_BODY_REQUIRED'));
      try { resolve(JSON.parse(source)); } catch { reject(new Error('CONFIRMATION_REQUEST_BODY_INVALID')); }
    });
    request.on('error', reject);
  });
}

function resolveConflictWithExecutable(requestBody) {
  return new Promise((resolve, reject) => {
    const child = spawn(process.env.PYTHON || 'python', [
      '-B', '-m', 'project_fact_r5.cli', 'resolve-conflict', '--fixtures', 'fixtures'
    ], {cwd: executableRoot, windowsHide: true});
    let stdout = '', stderr = '';
    child.stdout.setEncoding('utf8');
    child.stderr.setEncoding('utf8');
    child.stdout.on('data', chunk => { stdout += chunk; });
    child.stderr.on('data', chunk => { stderr += chunk; });
    child.on('error', reject);
    child.on('close', code => {
      if (code !== 0) return reject(new Error(stderr.trim() || 'CONFLICT_CONFIRMATION_REJECTED'));
      try { resolve(JSON.parse(stdout)); } catch { reject(new Error('CONFLICT_CONFIRMATION_RESPONSE_INVALID')); }
    });
    child.stdin.end(JSON.stringify(requestBody));
  });
}

async function handler(request, response) {
  try {
    const url = new URL(request.url, 'http://127.0.0.1');
    if (url.pathname.startsWith('/api/project-facts')) {
      const payload = JSON.parse(await fs.readFile(projectFactPayload, 'utf8'));
      let body;
      if (url.pathname === '/api/project-facts') body = intakeConfirmed ? payload.intake_confirmation : payload.initial;
      else if (url.pathname === '/api/project-facts/confirm-intake') {
        if (request.method !== 'POST') return sendJson(response, 405, {error: 'METHOD_NOT_ALLOWED'});
        intakeConfirmed = true;
        body = payload.intake_confirmation;
      }
      else if (url.pathname === '/api/project-facts/conflict') {
        if (!intakeConfirmed) return sendJson(response, 409, {error: 'PROJECT_FACT_INTAKE_CONFIRMATION_REQUIRED'});
        body = payload.conflict;
      }
      else if (url.pathname === '/api/project-facts/impact') body = payload.conflict.impact;
      else if (url.pathname === '/api/project-facts/confirm') {
        if (!intakeConfirmed) return sendJson(response, 409, {error: 'PROJECT_FACT_INTAKE_CONFIRMATION_REQUIRED'});
        if (request.method !== 'POST') return sendJson(response, 405, {error: 'METHOD_NOT_ALLOWED'});
        if (conflictConfirmation) return sendJson(response, 409, {error: 'PROJECT_FACT_CONFLICT_ALREADY_RESOLVED'});
        try {
          body = await resolveConflictWithExecutable(await readJsonBody(request));
          conflictConfirmation = body;
        } catch (error) {
          return sendJson(response, 400, {error: 'PROJECT_FACT_CONFLICT_CONFIRMATION_REJECTED', message: error.message});
        }
      }
      else {
        sendJson(response, 404, {error: 'PROJECT_FACT_API_NOT_FOUND'});
        return;
      }
      sendJson(response, 200, body);
      return;
    }
    if (request.headers.accept?.includes('text/html')) {
      intakeConfirmed = false;
      conflictConfirmation = null;
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
