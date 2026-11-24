import test from 'node:test'
import assert from 'node:assert/strict'
import { fetchHealth } from '../services/health'

test('Live Service Health Status Seam', async (t) => {
  await t.test('fetchHealth returns valid services health structure', async () => {
    const health = await fetchHealth()
    assert.ok(health)
    assert.strictEqual(health.postgres.name, 'PostgreSQL')
    assert.strictEqual(health.seaweedfs.name, 'SeaweedFS')
    assert.strictEqual(health.postgres.status, 'healthy')
    assert.strictEqual(health.seaweedfs.status, 'healthy')
    assert.ok(health.postgres.port === 5432 || health.postgres.port === 54320)
    assert.strictEqual(health.seaweedfs.port, 8333)
  })
})
