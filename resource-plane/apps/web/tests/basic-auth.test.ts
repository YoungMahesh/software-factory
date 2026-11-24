import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import os from 'node:os'
import {
  extractBasicAuthCredentials,
  getOrCreateControlPlaneCredentials,
  ensureControlPlaneCredentialsInEnv,
  validateControlPlaneCredentials,
  createBasicAuthChallengeResponse,
  isExemptFromBasicAuth,
} from '../services/basic-auth'

test('Control Plane Basic Authentication Seam (Strict .env-only)', async (t) => {
  const originalEnvUser = process.env.BASIC_AUTH_USERNAME
  const originalEnvPass = process.env.BASIC_AUTH_PASSWORD
  const originalEnvCpUser = process.env.CONTROL_PLANE_USERNAME
  const originalEnvCpPass = process.env.CONTROL_PLANE_PASSWORD

  const clearEnv = () => {
    delete process.env.BASIC_AUTH_USERNAME
    delete process.env.BASIC_AUTH_PASSWORD
    delete process.env.CONTROL_PLANE_USERNAME
    delete process.env.CONTROL_PLANE_PASSWORD
  }

  t.beforeEach(async () => {
    clearEnv()
  })

  t.after(async () => {
    clearEnv()
    if (originalEnvUser) process.env.BASIC_AUTH_USERNAME = originalEnvUser
    if (originalEnvPass) process.env.BASIC_AUTH_PASSWORD = originalEnvPass
    if (originalEnvCpUser) process.env.CONTROL_PLANE_USERNAME = originalEnvCpUser
    if (originalEnvCpPass) process.env.CONTROL_PLANE_PASSWORD = originalEnvCpPass
  })

  await t.test('extractBasicAuthCredentials extracts username and password from Authorization header', () => {
    // Standard user:pass
    const creds = extractBasicAuthCredentials('Basic ' + Buffer.from('admin:secret123').toString('base64'))
    assert.deepStrictEqual(creds, { username: 'admin', password: 'secret123' })

    // Case insensitive scheme
    const lowerCreds = extractBasicAuthCredentials('basic ' + Buffer.from('operator:pass!@#').toString('base64'))
    assert.deepStrictEqual(lowerCreds, { username: 'operator', password: 'pass!@#' })

    // Password containing colons
    const colonsCreds = extractBasicAuthCredentials('Basic ' + Buffer.from('admin:pass:with:colons').toString('base64'))
    assert.deepStrictEqual(colonsCreds, { username: 'admin', password: 'pass:with:colons' })

    // Invalid / missing headers
    assert.strictEqual(extractBasicAuthCredentials(undefined), null)
    assert.strictEqual(extractBasicAuthCredentials(''), null)
    assert.strictEqual(extractBasicAuthCredentials('Bearer token123'), null)
    assert.strictEqual(extractBasicAuthCredentials('Basic notbase64:invalid!'), null)
    assert.strictEqual(extractBasicAuthCredentials('Basic ' + Buffer.from('nocolon').toString('base64')), null)
  })

  await t.test('getOrCreateControlPlaneCredentials respects environment variables', async () => {
    process.env.BASIC_AUTH_USERNAME = 'custom-admin'
    process.env.BASIC_AUTH_PASSWORD = 'custom-env-password'

    const creds = await getOrCreateControlPlaneCredentials()
    assert.strictEqual(creds.username, 'custom-admin')
    assert.strictEqual(creds.password, 'custom-env-password')

    const isValid = await validateControlPlaneCredentials({
      username: 'custom-admin',
      password: 'custom-env-password',
    })
    assert.strictEqual(isValid, true)

    const isInvalidPass = await validateControlPlaneCredentials({
      username: 'custom-admin',
      password: 'wrong-password',
    })
    assert.strictEqual(isInvalidPass, false)

    const isInvalidUser = await validateControlPlaneCredentials({
      username: 'wrong-user',
      password: 'custom-env-password',
    })
    assert.strictEqual(isInvalidUser, false)
  })

  await t.test('ensureControlPlaneCredentialsInEnv writes credentials strictly to target env file if unset', async () => {
    const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'neon-auth-test-'))
    const tempEnvFile = path.join(tempDir, '.env.local')
    fs.writeFileSync(tempEnvFile, '# Existing config\nFOO=bar\n', 'utf-8')

    try {
      const creds = ensureControlPlaneCredentialsInEnv(tempEnvFile)
      assert.strictEqual(creds.username, 'admin')
      assert.ok(creds.password)
      assert.ok(creds.password.length >= 16)

      // Verify file content has been updated
      const fileContent = fs.readFileSync(tempEnvFile, 'utf-8')
      assert.ok(fileContent.includes('FOO=bar'))
      assert.ok(fileContent.includes('BASIC_AUTH_USERNAME="admin"'))
      assert.ok(fileContent.includes(`BASIC_AUTH_PASSWORD="${creds.password}"`))

      // Verify process.env was updated
      assert.strictEqual(process.env.BASIC_AUTH_USERNAME, 'admin')
      assert.strictEqual(process.env.BASIC_AUTH_PASSWORD, creds.password)

      // Subsequent call does not re-generate, it reads existing from file
      const creds2 = ensureControlPlaneCredentialsInEnv(tempEnvFile)
      assert.deepStrictEqual(creds2, creds)
    } finally {
      fs.rmSync(tempDir, { recursive: true, force: true })
    }
  })

  await t.test('validateControlPlaneCredentials rejects invalid or missing candidates', async () => {
    assert.strictEqual(await validateControlPlaneCredentials(null), false)
    assert.strictEqual(await validateControlPlaneCredentials(undefined), false)
    assert.strictEqual(await validateControlPlaneCredentials({ username: '', password: '' }), false)
    assert.strictEqual(await validateControlPlaneCredentials({ username: 'admin', password: null }), false)
  })

  await t.test('createBasicAuthChallengeResponse returns 401 with standard WWW-Authenticate header', () => {
    const res = createBasicAuthChallengeResponse()
    assert.strictEqual(res.status, 401)
    assert.strictEqual(res.headers.get('WWW-Authenticate'), 'Basic realm="Neon Control Plane", charset="UTF-8"')
    assert.ok(res.headers.get('Content-Type')?.includes('text/plain'))
  })

  await t.test('isExemptFromBasicAuth correctly identifies exempted endpoints', () => {
    // MCP endpoints must be exempt (secured via Bearer Admin Token)
    assert.strictEqual(isExemptFromBasicAuth('/mcp'), true)
    assert.strictEqual(isExemptFromBasicAuth('/mcp/'), true)
    assert.strictEqual(isExemptFromBasicAuth('http://localhost:3000/mcp'), true)
    assert.strictEqual(isExemptFromBasicAuth('http://localhost:3000/mcp?foo=bar'), true)

    // Internal Vite and static assets
    assert.strictEqual(isExemptFromBasicAuth('/@vite/client'), true)
    assert.strictEqual(isExemptFromBasicAuth('/@fs/some/path'), true)
    assert.strictEqual(isExemptFromBasicAuth('/@id/some/module'), true)
    assert.strictEqual(isExemptFromBasicAuth('/favicon.ico'), true)

    // Public Root CA certificate endpoint
    assert.strictEqual(isExemptFromBasicAuth('/api/ca.crt'), true)
    assert.strictEqual(isExemptFromBasicAuth('http://localhost:3000/api/ca.crt'), true)
    assert.strictEqual(isExemptFromBasicAuth('http://localhost:3000/api/ca.crt?download=1'), true)

    // Dashboard routes and server functions must NOT be exempt
    assert.strictEqual(isExemptFromBasicAuth('/'), false)
    assert.strictEqual(isExemptFromBasicAuth('/projects'), false)
    assert.strictEqual(isExemptFromBasicAuth('/projects/c8bb6c38-842c-47bc-9b65-bf9c9d469278'), false)
    assert.strictEqual(isExemptFromBasicAuth('http://localhost:3000/'), false)
    assert.strictEqual(isExemptFromBasicAuth('/_server'), false)
    assert.strictEqual(isExemptFromBasicAuth('/_server/listProjectsFn'), false)
  })

  await t.test('basicAuthMiddleware enforces authentication on protected routes', async () => {
    process.env.BASIC_AUTH_USERNAME = 'admin'
    process.env.BASIC_AUTH_PASSWORD = 'super-secret-password'

    const { basicAuthMiddleware } = await import('../start.js')
    const middlewareFn = basicAuthMiddleware.options.server as any

    // 1. Unauthenticated request to protected route returns 401 challenge
    let nextCalled = false
    const unauthReq = new Request('http://localhost:3000/projects', {
      headers: {},
    })
    const unauthRes = await middlewareFn({
      request: unauthReq,
      next: async () => {
        nextCalled = true
        return { ok: true }
      },
    })
    assert.strictEqual(nextCalled, false)
    assert.strictEqual(unauthRes.status, 401)
    assert.strictEqual(unauthRes.headers.get('WWW-Authenticate'), 'Basic realm="Neon Control Plane", charset="UTF-8"')

    // 2. Request with invalid credentials returns 401 challenge
    const invalidCreds = Buffer.from('admin:wrong-pass').toString('base64')
    const invalidReq = new Request('http://localhost:3000/projects', {
      headers: {
        authorization: `Basic ${invalidCreds}`,
      },
    })
    const invalidRes = await middlewareFn({
      request: invalidReq,
      next: async () => {
        nextCalled = true
        return { ok: true }
      },
    })
    assert.strictEqual(nextCalled, false)
    assert.strictEqual(invalidRes.status, 401)

    // 3. Request with valid credentials proceeds through next()
    nextCalled = false
    const validCreds = Buffer.from('admin:super-secret-password').toString('base64')
    const validReq = new Request('http://localhost:3000/projects', {
      headers: {
        authorization: `Basic ${validCreds}`,
      },
    })
    const validRes = await middlewareFn({
      request: validReq,
      next: async () => {
        nextCalled = true
        return { status: 200 }
      },
    })
    assert.strictEqual(nextCalled, true)
    assert.deepStrictEqual(validRes, { status: 200 })

    // 4. Request to exempted /mcp route bypasses basic auth completely
    nextCalled = false
    const mcpReq = new Request('http://localhost:3000/mcp', {
      headers: {},
    })
    const mcpRes = await middlewareFn({
      request: mcpReq,
      next: async () => {
        nextCalled = true
        return { status: 'mcp-passthrough' }
      },
    })
    assert.strictEqual(nextCalled, true)
    assert.deepStrictEqual(mcpRes, { status: 'mcp-passthrough' })

    // 5. Request to exempted /api/ca.crt route bypasses basic auth completely
    nextCalled = false
    const caReq = new Request('http://localhost:3000/api/ca.crt', {
      headers: {},
    })
    const caRes = await middlewareFn({
      request: caReq,
      next: async () => {
        nextCalled = true
        return { status: 'ca-passthrough' }
      },
    })
    assert.strictEqual(nextCalled, true)
    assert.deepStrictEqual(caRes, { status: 'ca-passthrough' })
  })
})
