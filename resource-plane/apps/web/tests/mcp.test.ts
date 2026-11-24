import test from 'node:test'
import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { db } from '../db/index'
import { projects, databases, objectStorages } from '../db/schema'
import { eq } from 'drizzle-orm'
import { createProject } from '../services/projects'
import { getOrCreateAdminToken } from '../services/admin-token'
import { createNeonMcpServer, resolveProject } from '../mcp/server'
import { handleMcpRequest } from '../utils/mcp-handler'

test('MCP Server Suite (HTTP & Stdio) Seam', async (t) => {
  let adminToken: string
  let testProject: any

  t.before(async () => {
    adminToken = await getOrCreateAdminToken()
    testProject = await createProject({
      name: `MCP Test Project ${Date.now()}`,
    })
  })

  t.after(async () => {
    if (testProject?.id) {
      // Cleanup project and cascade
      await db.delete(projects).where(eq(projects.id, testProject.id)).catch(() => {})
    }
  })

  await t.test('HTTP Auth: rejects requests with missing or invalid token with 401', async () => {
    const server = createNeonMcpServer()

    // 1. Missing Authorization header
    const reqNoAuth = new Request('http://localhost:3000/mcp', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        jsonrpc: '2.0',
        id: 1,
        method: 'tools/list',
        params: {},
      }),
    })

    // Import route handler to test HTTP auth seam
    const { handleAuthenticatedMcpRequest } = await import('../routes/mcp.js')
    const resNoAuth = await handleAuthenticatedMcpRequest(reqNoAuth)
    assert.strictEqual(resNoAuth.status, 401)
    const dataNoAuth = await resNoAuth.json()
    assert.ok(dataNoAuth.error)

    // 2. Invalid token
    const reqBadAuth = new Request('http://localhost:3000/mcp', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: 'Bearer invalid-token-xyz',
      },
      body: JSON.stringify({
        jsonrpc: '2.0',
        id: 2,
        method: 'tools/list',
        params: {},
      }),
    })
    const resBadAuth = await handleAuthenticatedMcpRequest(reqBadAuth)
    assert.strictEqual(resBadAuth.status, 401)

    // 3. Valid token succeeds with 200
    const reqValidAuth = new Request('http://localhost:3000/mcp', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${adminToken}`,
      },
      body: JSON.stringify({
        jsonrpc: '2.0',
        id: 3,
        method: 'tools/list',
        params: {},
      }),
    })
    const resValidAuth = await handleAuthenticatedMcpRequest(reqValidAuth)
    assert.strictEqual(resValidAuth.status, 200)
    const validData = await resValidAuth.json()
    assert.strictEqual(validData.id, 3)
    assert.ok(validData.result?.tools)
  })

  await t.test('Exposes the non-destructive MCP tool suite (Spec US 18, 19 & ADR 0013)', async () => {
    const server = createNeonMcpServer()
    const req = new Request('http://localhost:3000/mcp', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        jsonrpc: '2.0',
        id: 10,
        method: 'tools/list',
        params: {},
      }),
    })

    const res = await handleMcpRequest(req, server)
    assert.strictEqual(res.status, 200)
    const data = await res.json()
    assert.ok(Array.isArray(data.result?.tools))

    const toolNames = data.result.tools.map((t: any) => t.name)
    const expectedTools = [
      'list_projects',
      'create_project',
      'create_database',
      'list_databases',
      'get_database_credentials',
      'create_object_storage',
      'list_object_storages',
      'get_storage_credentials',
    ]

    for (const exp of expectedTools) {
      assert.ok(toolNames.includes(exp), `Expected tool ${exp} to be registered`)
    }

    // Ensure destructive tools are excluded
    assert.ok(!toolNames.includes('delete_database'))
    assert.ok(!toolNames.includes('delete_object_storage'))
    assert.ok(!toolNames.includes('reset_database_password'))
    assert.ok(!toolNames.includes('delete_project'))
  })

  await t.test('Tool: list_projects returns all projects with stats', async () => {
    const server = createNeonMcpServer()
    const req = new Request('http://localhost:3000/mcp', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        jsonrpc: '2.0',
        id: 11,
        method: 'tools/call',
        params: {
          name: 'list_projects',
          arguments: {},
        },
      }),
    })

    const res = await handleMcpRequest(req, server)
    const data = await res.json()
    assert.strictEqual(data.id, 11)
    assert.ok(!data.error)
    assert.ok(data.result?.content?.[0]?.text)

    const projectsList = JSON.parse(data.result.content[0].text)
    assert.ok(Array.isArray(projectsList))
    const found = projectsList.find((p: any) => p.id === testProject.id)
    assert.ok(found, 'Should include testProject in list_projects')
    assert.strictEqual(found.name, testProject.name)
    assert.strictEqual(found.slug, testProject.slug)
    assert.strictEqual(found.region, testProject.region)
    assert.strictEqual(typeof found.databaseCount, 'number')
    assert.strictEqual(typeof found.storageCount, 'number')
    assert.ok(found.createdAt)
  })

  let mcpCreatedProject: any
  await t.test('Tool: create_project creates a project and returns its details', async () => {
    const server = createNeonMcpServer()
    const projName = `MCP Created Project ${Date.now()}`
    const req = new Request('http://localhost:3000/mcp', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        jsonrpc: '2.0',
        id: 12,
        method: 'tools/call',
        params: {
          name: 'create_project',
          arguments: {
            name: projName,
            region: 'us-west-2',
          },
        },
      }),
    })

    const res = await handleMcpRequest(req, server)
    const data = await res.json()
    assert.strictEqual(data.id, 12)
    assert.ok(!data.error)
    assert.ok(data.result?.content?.[0]?.text)

    mcpCreatedProject = JSON.parse(data.result.content[0].text)
    assert.ok(mcpCreatedProject.id)
    assert.strictEqual(mcpCreatedProject.name, projName)
    assert.strictEqual(mcpCreatedProject.region, 'us-west-2')
    assert.ok(mcpCreatedProject.slug)
    assert.ok(mcpCreatedProject.createdAt)

    // Cleanup
    await db.delete(projects).where(eq(projects.id, mcpCreatedProject.id)).catch(() => {})
  })

  await t.test('resolveProject resolves project by id or by name/slug', async () => {
    const byId = await resolveProject({ projectId: testProject.id })
    assert.strictEqual(byId.id, testProject.id)

    const byName = await resolveProject({ projectName: testProject.name })
    assert.strictEqual(byName.id, testProject.id)

    const bySlug = await resolveProject({ projectName: testProject.slug })
    assert.strictEqual(bySlug.id, testProject.id)

    await assert.rejects(async () => {
      await resolveProject({})
    }, /Either projectId or projectName must be provided/)

    await assert.rejects(async () => {
      await resolveProject({ projectId: '00000000-0000-0000-0000-000000000000' })
    }, /Project not found/)
  })

  let createdDatabase: any
  let createdStorage: any

  await t.test('Tool: create_database provisions database and returns connection URI', async () => {
    const server = createNeonMcpServer()
    const dbName = `mcp_db_${Date.now()}`
    const req = new Request('http://localhost:3000/mcp', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        jsonrpc: '2.0',
        id: 20,
        method: 'tools/call',
        params: {
          name: 'create_database',
          arguments: {
            projectName: testProject.name,
            databaseName: dbName,
          },
        },
      }),
    })

    const res = await handleMcpRequest(req, server)
    const data = await res.json()
    assert.strictEqual(data.id, 20)
    assert.ok(!data.error)
    assert.ok(data.result?.content?.[0]?.text)

    createdDatabase = JSON.parse(data.result.content[0].text)
    assert.ok(createdDatabase.id)
    assert.strictEqual(createdDatabase.projectId, testProject.id)
    assert.strictEqual(createdDatabase.name, dbName)
    assert.ok(createdDatabase.connectionString)
    assert.ok(createdDatabase.connectionString.startsWith('postgresql://'))
    assert.ok(createdDatabase.username)
    assert.ok(createdDatabase.password)
  })

  await t.test('Tool: list_databases returns databases for project', async () => {
    const server = createNeonMcpServer()
    const req = new Request('http://localhost:3000/mcp', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        jsonrpc: '2.0',
        id: 21,
        method: 'tools/call',
        params: {
          name: 'list_databases',
          arguments: {
            projectId: testProject.id,
          },
        },
      }),
    })

    const res = await handleMcpRequest(req, server)
    const data = await res.json()
    assert.ok(!data.error)
    const list = JSON.parse(data.result.content[0].text)
    assert.ok(Array.isArray(list))
    const found = list.find((d: any) => d.id === createdDatabase.id)
    assert.ok(found)
    assert.strictEqual(found.name, createdDatabase.name)
  })

  await t.test('Tool: get_database_credentials retrieves credentials by ID or name', async () => {
    const server = createNeonMcpServer()

    // By ID
    const reqById = new Request('http://localhost:3000/mcp', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        jsonrpc: '2.0',
        id: 22,
        method: 'tools/call',
        params: {
          name: 'get_database_credentials',
          arguments: {
            databaseId: createdDatabase.id,
          },
        },
      }),
    })

    const resById = await handleMcpRequest(reqById, server)
    const dataById = await resById.json()
    assert.ok(!dataById.error)
    const credsById = JSON.parse(dataById.result.content[0].text)
    assert.strictEqual(credsById.id, createdDatabase.id)
    assert.strictEqual(credsById.connectionString, createdDatabase.connectionString)
    assert.ok(typeof credsById.caCertificate === 'string', 'caCertificate must be returned')
    assert.ok(credsById.caCertificate.includes('-----BEGIN CERTIFICATE-----'), 'caCertificate must be valid PEM')
    const expectedDownloadUrl = `http://${process.env.PUBLIC_POSTGRES_HOST || process.env.PUBLIC_HOST || 'localhost'}:${process.env.PORT || '3000'}/api/ca.crt`
    assert.strictEqual(credsById.caDownloadUrl, expectedDownloadUrl)

    // By name
    const reqByName = new Request('http://localhost:3000/mcp', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        jsonrpc: '2.0',
        id: 23,
        method: 'tools/call',
        params: {
          name: 'get_database_credentials',
          arguments: {
            databaseName: createdDatabase.name,
            projectId: testProject.id,
          },
        },
      }),
    })

    const resByName = await handleMcpRequest(reqByName, server)
    const dataByName = await resByName.json()
    assert.ok(!dataByName.error)
    const credsByName = JSON.parse(dataByName.result.content[0].text)
    assert.strictEqual(credsByName.id, createdDatabase.id)
    assert.ok(typeof credsByName.caCertificate === 'string', 'caCertificate must be returned')
    assert.ok(credsByName.caCertificate.includes('-----BEGIN CERTIFICATE-----'), 'caCertificate must be valid PEM')
    assert.strictEqual(credsByName.caDownloadUrl, expectedDownloadUrl)
  })

  await t.test('Tool: create_object_storage provisions S3 bucket and returns credentials', async () => {
    const server = createNeonMcpServer()
    const bucketName = `mcp-bucket-${Date.now()}`
    const req = new Request('http://localhost:3000/mcp', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        jsonrpc: '2.0',
        id: 30,
        method: 'tools/call',
        params: {
          name: 'create_object_storage',
          arguments: {
            projectName: testProject.name,
            bucketName,
          },
        },
      }),
    })

    const res = await handleMcpRequest(req, server)
    const data = await res.json()
    assert.strictEqual(data.id, 30)
    assert.ok(!data.error)
    createdStorage = JSON.parse(data.result.content[0].text)
    assert.ok(createdStorage.id)
    assert.strictEqual(createdStorage.bucketName, bucketName)
    assert.ok(createdStorage.accessKeyId)
    assert.ok(createdStorage.secretAccessKey)
    assert.ok(createdStorage.endpoint)
  })

  await t.test('Tool: list_object_storages returns all buckets for project', async () => {
    const server = createNeonMcpServer()
    const req = new Request('http://localhost:3000/mcp', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        jsonrpc: '2.0',
        id: 31,
        method: 'tools/call',
        params: {
          name: 'list_object_storages',
          arguments: {
            projectId: testProject.id,
          },
        },
      }),
    })

    const res = await handleMcpRequest(req, server)
    const data = await res.json()
    assert.ok(!data.error)
    const list = JSON.parse(data.result.content[0].text)
    assert.ok(Array.isArray(list))
    const found = list.find((s: any) => s.id === createdStorage.id)
    assert.ok(found)
    assert.strictEqual(found.bucketName, createdStorage.bucketName)
  })

  await t.test('Tool: get_storage_credentials returns S3 config bundle by ID or bucketName', async () => {
    const server = createNeonMcpServer()

    // By ID
    const reqById = new Request('http://localhost:3000/mcp', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        jsonrpc: '2.0',
        id: 32,
        method: 'tools/call',
        params: {
          name: 'get_storage_credentials',
          arguments: {
            storageId: createdStorage.id,
          },
        },
      }),
    })

    const resById = await handleMcpRequest(reqById, server)
    const dataById = await resById.json()
    assert.ok(!dataById.error)
    const credsById = JSON.parse(dataById.result.content[0].text)
    assert.strictEqual(credsById.id, createdStorage.id)
    assert.strictEqual(credsById.accessKeyId, createdStorage.accessKeyId)
    assert.ok(credsById.formatted?.env)

    // By bucket name
    const reqByName = new Request('http://localhost:3000/mcp', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        jsonrpc: '2.0',
        id: 33,
        method: 'tools/call',
        params: {
          name: 'get_storage_credentials',
          arguments: {
            bucketName: createdStorage.bucketName,
          },
        },
      }),
    })

    const resByName = await handleMcpRequest(reqByName, server)
    const dataByName = await resByName.json()
    assert.ok(!dataByName.error)
    const credsByName = JSON.parse(dataByName.result.content[0].text)
    assert.strictEqual(credsByName.id, createdStorage.id)
  })

  await t.test('Stdio CLI: rejects invalid or missing token and exits with code 1', async () => {
    const proc = spawn('node', ['./node_modules/tsx/dist/cli.mjs', 'src/mcp/stdio.ts', '--token', 'wrong-token'], {
      cwd: process.cwd(),
      env: { ...process.env, ADMIN_TOKEN: '' },
    })

    const exitCode = await new Promise<number | null>((resolve) => {
      proc.on('close', (code) => resolve(code))
    })

    assert.strictEqual(exitCode, 1)
  })

  await t.test('Stdio CLI: accepts valid token and handles JSON-RPC request over stdio', async () => {
    const proc = spawn('node', ['./node_modules/tsx/dist/cli.mjs', 'src/mcp/stdio.ts', '--token', adminToken], {
      cwd: process.cwd(),
      env: { ...process.env },
    })

    const rpcRequest = JSON.stringify({
      jsonrpc: '2.0',
      id: 99,
      method: 'tools/list',
      params: {},
    }) + '\n'

    let stdoutData = ''
    const receivedPromise = new Promise<void>((resolve) => {
      proc.stdout.on('data', (chunk) => {
        stdoutData += chunk.toString()
        if (stdoutData.includes('"tools"')) {
          resolve()
        }
      })
    })

    proc.stdin.write(rpcRequest)

    await Promise.race([
      receivedPromise,
      new Promise((_, reject) =>
        setTimeout(() => reject(new Error('Stdio response timeout')), 5000),
      ),
    ])

    proc.kill()

    assert.ok(stdoutData.includes('"tools"'))
    assert.ok(stdoutData.includes('create_database'))
  })
})
