require('reflect-metadata');
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { CheckoutService } = require('../dist/checkout/checkout.service');
const { MockShippingService } = require('../dist/checkout/shipping/MockShippingService');

function fixture(orders = { create: async () => ({ id: 'order-1' }) }) {
  const data = new Map();
  const repo = { get: async id => data.get(id), set: async (id, value) => data.set(id, value), remove: async id => data.delete(id) };
  return new CheckoutService(repo, orders, new MockShippingService(''));
}
const item = { id: 'p1', name: 'Product', price: 12, quantity: 3 };
const address = { firstName: 'Test', lastName: 'User', email: 'test@example.org', address1: 'Street 1', city: 'Montevideo', state: 'MO', zip: '11000' };

test('calculates subtotals and persists a checkout without shipping', async () => {
  const service = fixture();
  assert.equal(await service.get('missing'), null);
  const checkout = await service.update('customer', { items: [item] });
  assert.equal(checkout.subtotal, 36);
  assert.equal(checkout.total, 36);
  assert.equal(checkout.items[0].totalCost, 36);
  assert.equal((await service.get('customer')).subtotal, 36);
});
test('adds selected shipping and tax, then removes submitted checkout', async () => {
  const service = fixture();
  const checkout = await service.update('customer', { items: [item], shippingAddress: address, deliveryOptionToken: 'priority-mail' });
  assert.equal(checkout.shipping, 10);
  assert.equal(checkout.tax, 5);
  assert.equal(checkout.total, 51);
  const submitted = await service.submit('customer');
  assert.equal(submitted.orderId, 'order-1');
  assert.equal(submitted.email, address.email);
  assert.equal(await service.get('customer'), null);
  await assert.rejects(service.submit('customer'), /Checkout not found/);
});
test('preserves checkout if the orders service fails', async () => {
  const service = fixture({ create: async () => { throw new Error('orders unavailable'); } });
  await service.update('customer', { items: [item], shippingAddress: address });
  await assert.rejects(service.submit('customer'), /orders unavailable/);
  assert.ok(await service.get('customer'));
});

test('boots Nest providers from the TypeScript build with decorator metadata', async t => {
  const settings = ['RETAIL_CHECKOUT_PERSISTENCE_PROVIDER', 'RETAIL_CHECKOUT_ENDPOINTS_ORDERS'];
  const previous = settings.map(key => process.env[key]);
  process.env.RETAIL_CHECKOUT_PERSISTENCE_PROVIDER = 'in-memory';
  process.env.RETAIL_CHECKOUT_ENDPOINTS_ORDERS = '';
  t.after(() => settings.forEach((key, index) => {
    if (previous[index] === undefined) delete process.env[key];
    else process.env[key] = previous[index];
  }));
  const { NestFactory } = require('@nestjs/core');
  const { AppModule } = require('../dist/app.module');
  const app = await NestFactory.createApplicationContext(AppModule, { logger: false, abortOnError: false });
  t.after(() => app.close());
  const service = app.get(CheckoutService);
  const checkout = await service.update('bootstrap-test', { items: [item] });
  assert.equal(checkout.total, 36);
  assert.equal((await service.get('bootstrap-test')).subtotal, 36);
});
