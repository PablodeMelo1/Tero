const { test, before, after } = require('node:test');
const assert = require('node:assert/strict');
const http = require('node:http');

let proxy, server, base;
before(async () => {
  proxy = http.createServer((req, res) => {
    res.setHeader('Content-Type', 'application/json');
    res.end(JSON.stringify({ path: req.url }));
  });
  await new Promise(resolve => proxy.listen(0, '127.0.0.1', resolve));
  for (const service of ['CATALOG', 'CARTS', 'CHECKOUT', 'ORDERS']) {
    process.env[`RETAIL_UI_ENDPOINTS_${service}`] = `http://127.0.0.1:${proxy.address().port}`;
  }
  const { app } = require('../dist/app');
  server = app.listen(0, '127.0.0.1');
  await new Promise(resolve => server.once('listening', resolve));
  base = `http://127.0.0.1:${server.address().port}`;
});
after(async () => {
  await Promise.all([server, proxy].map(s => new Promise(resolve => s.close(resolve))));
});

test('serves the storefront and health endpoint', async () => {
  assert.equal(await (await fetch(`${base}/health`)).text(), 'OK');
  const page = await fetch(base);
  assert.equal(page.status, 200);
  assert.match(await page.text(), /<html/i);
});

for (const route of ['catalog', 'carts', 'checkout', 'orders']) {
  test(`preserves paths and queries when proxying ${route}`, async () => {
    const response = await fetch(`${base}/api/${route}/sample?size=2`);
    assert.equal(response.status, 200);
    assert.deepEqual(await response.json(), { path: `/${route}/sample?size=2` });
    assert.deepEqual(await (await fetch(`${base}/api/${route}`)).json(), { path: `/${route}` });
  });
}
