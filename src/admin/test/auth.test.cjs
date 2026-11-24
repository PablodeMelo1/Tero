const { test, before, after } = require('node:test');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
process.env.ADMIN_USERNAME = 'ci-admin';
process.env.ADMIN_PASSWORD = crypto.randomBytes(24).toString('hex');
process.env.ADMIN_JWT_SECRET = crypto.randomBytes(32).toString('hex');
const { app } = require('../dist/app');
let server, base;
before(async () => {
  server = app.listen(0, '127.0.0.1');
  await new Promise(resolve => server.once('listening', resolve));
  base = `http://127.0.0.1:${server.address().port}`;
});
after(() => new Promise(resolve => server.close(resolve)));
const login = body => fetch(`${base}/auth/login`, {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
});

test('rejects missing and invalid credentials', async () => {
  for (const body of [{}, { username: 'wrong', password: 'wrong' },
    { username: process.env.ADMIN_USERNAME, password: 'wrong' }]) {
    assert.equal((await login(body)).status, 401);
  }
  assert.equal((await fetch(`${base}/auth/me`)).status, 401);
  assert.equal((await fetch(`${base}/auth/me`, { headers: { Cookie: 'token=invalid' } })).status, 401);
  for (const route of ['/admin/api/products', '/admin/api/orders']) {
    assert.equal((await fetch(base + route)).status, 401);
  }
});

test('issues an HTTP-only cookie and authenticates it', async () => {
  const response = await login({ username: process.env.ADMIN_USERNAME, password: process.env.ADMIN_PASSWORD });
  assert.equal(response.status, 200);
  const cookie = response.headers.get('set-cookie');
  assert.match(cookie, /HttpOnly/i);
  assert.match(cookie, /SameSite=Strict/i);
  assert.equal((await fetch(`${base}/auth/me`, { headers: { Cookie: cookie.split(';')[0] } })).status, 200);
  const logout = await fetch(`${base}/auth/logout`, { method: 'POST' });
  assert.equal(logout.status, 200);
  assert.match(logout.headers.get('set-cookie'), /Expires=/i);
});

test('health and login page are available without authentication', async () => {
  assert.equal(await (await fetch(`${base}/health`)).text(), 'OK');
  assert.equal((await fetch(base)).status, 200);
});
