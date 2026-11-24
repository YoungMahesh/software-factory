import test from 'node:test'
import assert from 'node:assert/strict'
import { db } from '../db/index'
import { settings } from '../db/schema'
import { eq } from 'drizzle-orm'
import {
  getOrCreateAdminToken,
  validateAdminToken,
  extractBearerToken,
} from '../services/admin-token'
import { ensureSystemReady } from '../services/bootstrap'

test('Admin Token Management Seam', async (t) => {
  const originalEnvAdmin = process.env.ADMIN_TOKEN
  const originalEnvNeonAdmin = process.env.NEON_ADMIN_TOKEN

  t.before(async () => {
    await ensureSystemReady().catch(() => {})
  })

  t.beforeEach(async () => {
    delete process.env.ADMIN_TOKEN
    delete process.env.NEON_ADMIN_TOKEN
  })

  t.after(async () => {
    if (originalEnvAdmin) process.env.ADMIN_TOKEN = originalEnvAdmin
    else delete process.env.ADMIN_TOKEN
    if (originalEnvNeonAdmin) process.env.NEON_ADMIN_TOKEN = originalEnvNeonAdmin
    else delete process.env.NEON_ADMIN_TOKEN
  })

  await t.test('extractBearerToken extracts token from Authorization header', () => {
    assert.strictEqual(extractBearerToken('Bearer my-secret-token'), 'my-secret-token')
    assert.strictEqual(extractBearerToken('bearer lower-token'), 'lower-token')
    assert.strictEqual(extractBearerToken('Basic xyz'), null)
    assert.strictEqual(extractBearerToken(undefined), null)
    assert.strictEqual(extractBearerToken(''), null)
  })

  await t.test('getOrCreateAdminToken generates and persists token if none exists', async () => {
    // Clear any existing db setting for clean test
    await db.delete(settings).where(eq(settings.key, 'admin_token'))

    const token = await getOrCreateAdminToken()
    assert.ok(token)
    assert.ok(token.length >= 32)

    // Second call should return the exact same token
    const token2 = await getOrCreateAdminToken()
    assert.strictEqual(token2, token)

    // Verify in db
    const [row] = await db.select().from(settings).where(eq(settings.key, 'admin_token'))
    assert.ok(row)
    assert.strictEqual(row.value, token)
  })

  await t.test('getOrCreateAdminToken respects ADMIN_TOKEN or NEON_ADMIN_TOKEN env variable', async () => {
    process.env.ADMIN_TOKEN = 'env-override-secret-123'
    const token = await getOrCreateAdminToken()
    assert.strictEqual(token, 'env-override-secret-123')

    const isValid = await validateAdminToken('env-override-secret-123')
    assert.strictEqual(isValid, true)

    const isInvalid = await validateAdminToken('wrong-token')
    assert.strictEqual(isInvalid, false)
  })
})
