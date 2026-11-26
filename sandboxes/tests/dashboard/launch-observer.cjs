const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const { createLaunchObserver } = vm.runInNewContext(
  fs.readFileSync(path.join(__dirname, '../../sandbox/static/launch-observer.js'), 'utf8') + '\n({createLaunchObserver})',
  { AbortController, setTimeout, clearTimeout, console },
);
const deferred = () => {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
};
const reply = (status = 'queued', extra = {}) => ({ ok: true, status: 200, json: async () => ({ request: { status, ...extra } }) });
function harness() {
  const calls = [], published = [], urls = [], redirects = [], errors = [];
  const timers = new Map();
  let seq = 0;
  const refresh = deferred();
  refresh.resolve();
  const observer = createLaunchObserver({
    request(id, signal) {
      const task = deferred();
      calls.push({ id, signal, ...task });
      return task.promise;
    },
    publish: value => published.push(value),
    setRequestId: id => urls.push(id),
    navigate: url => redirects.push(url),
    refresh: () => refresh.promise,
    reportError: err => errors.push(err),
    schedule: fn => { timers.set(++seq, fn); return seq; },
    cancel: key => timers.delete(key),
  });
  function tick() {
    const [key, fn] = timers.entries().next().value;
    timers.delete(key);
    return fn();
  }
  return { observer, calls, published, urls, redirects, errors, timers, tick };
}

test('dismissal rejects a late ready response, even when transport ignores abort', async () => {
  const h = harness();
  const pending = h.observer.track('old');
  h.observer.dismiss();
  assert.equal(h.calls[0].signal.aborted, true);
  h.calls[0].resolve(reply('ready', { handoff_url: 'old-thread' }));
  await pending;
  assert.equal(h.published.at(-1), null);
  assert.deepEqual(h.redirects, []);
  assert.equal(h.urls.at(-1), null);
  assert.equal(h.timers.size, 0);
});

test('switching requests ignores old replies and preserves the new polling lifetime', async () => {
  const h = harness();
  const old = h.observer.track('old');
  const current = h.observer.track('new');
  h.calls[1].resolve(reply());
  await current;
  h.calls[0].resolve(reply('ready', { handoff_url: 'old-thread' }));
  await old;
  assert.equal(h.published.at(-1).request.status, 'queued');
  assert.equal(h.urls.at(-1), 'new');
  assert.equal(h.timers.size, 1);
  assert.deepEqual(h.redirects, []);
  h.observer.destroy();
});

test('switching while reading JSON also rejects the old response', async () => {
  const h = harness(), json = deferred();
  const old = h.observer.track('old');
  h.calls[0].resolve({ ok: true, json: () => json.promise });
  await Promise.resolve();
  const current = h.observer.track('new');
  json.resolve({ request: { status: 'ready', handoff_url: 'old-thread' } });
  h.calls[1].resolve(reply('failed'));
  await Promise.all([old, current]);
  assert.equal(h.published.at(-1).request.status, 'failed');
  assert.deepEqual(h.redirects, []);
});

test('polls never overlap; transient failure retries; terminal failure stops', async () => {
  const h = harness();
  const initial = h.observer.track('one');
  assert.equal(h.timers.size, 0);
  h.calls[0].reject(new Error('offline'));
  await initial;
  assert.equal(h.errors.length, 1);
  const next = h.tick();
  assert.equal(h.timers.size, 0);
  h.calls[1].resolve(reply('failed'));
  await next;
  assert.equal(h.timers.size, 0);
});

test('404 clears progress and URL and stops polling', async () => {
  const h = harness();
  const task = h.observer.track('gone');
  h.calls[0].resolve({ ok: false, status: 404 });
  await task;
  assert.equal(h.published.at(-1), null);
  assert.equal(h.urls.at(-1), null);
  assert.equal(h.timers.size, 0);
});

test('ready hands off once per request, including repeated tracking', async () => {
  const h = harness();
  for (let i = 0; i < 2; i++) {
    const task = h.observer.track('one');
    h.calls[i].resolve(reply('ready', { handoff_url: 'thread' }));
    await task;
  }
  assert.deepEqual(h.redirects, ['thread']);
  assert.equal(h.timers.size, 0);
});

test('dismissal during refresh prevents navigation', async () => {
  const refresh = deferred(), response = deferred();
  const redirects = [];
  const observer = createLaunchObserver({
    request: () => response.promise, publish() {}, setRequestId() {},
    refresh: () => refresh.promise, navigate: url => redirects.push(url),
  });
  const task = observer.track('one');
  response.resolve(reply('ready', { handoff_url: 'thread' }));
  await Promise.resolve(); await Promise.resolve();
  observer.dismiss();
  refresh.resolve();
  await task;
  assert.deepEqual(redirects, []);
});

test('destroy cancels observation while preserving URL for reload restoration', async () => {
  const h = harness(), task = h.observer.track('one');
  h.calls[0].resolve(reply());
  await task;
  h.observer.destroy();
  assert.equal(h.timers.size, 0);
  assert.equal(h.urls.at(-1), 'one');
});
