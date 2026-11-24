import test from 'node:test'
import assert from 'node:assert/strict'
import pg from 'pg'
import {
  createDatabase,
  listDatabases,
  getDatabaseCredentials,
  resetDatabasePassword,
  deleteDatabase,
  getDatabase,
  sanitizeDatabaseName,
  formatDatabaseCredentials,
} from '../services/databases'
import { createProject } from '../services/projects'
import { db } from '../db/index'
import { projects, databases } from '../db/schema'
import { eq } from 'drizzle-orm'

test('Database Provisioning & Security Isolation Seam', async (t) => {
  let testProject: any

  t.before(async () => {
    testProject = await createProject({ name: 'DB Test Project' })
  })

  t.after(async () => {
    if (testProject?.id) {
      // Deleting project cascades to databases records if any remain
      await db.delete(projects).where(eq(projects.id, testProject.id))
    }
  })

  await t.test('sanitizeDatabaseName normalizes database names', () => {
    assert.strictEqual(sanitizeDatabaseName('My App DB'), 'my_app_db')
    assert.strictEqual(sanitizeDatabaseName('Prod-Database-1'), 'prod_database_1')
    assert.strictEqual(sanitizeDatabaseName('special!@#$%chars'), 'specialchars')
  })

  await t.test('createDatabase provisions isolated database, role, and permissions', async () => {
    const dbName = `test_db_${Date.now()}`
    const result = await createDatabase({
      projectId: testProject.id,
      name: dbName,
    })

    assert.ok(result.id)
    assert.strictEqual(result.projectId, testProject.id)
    assert.strictEqual(result.name, dbName)
    assert.ok(result.username)
    assert.ok(result.password)
    assert.ok(result.connectionString)
    assert.strictEqual(result.host, 'localhost')
    assert.ok(result.port > 0)

    // Verify resource role can connect and execute queries on its allocated database
    const roleClient = new pg.Client({
      host: result.host,
      port: result.port,
      user: result.username,
      password: result.password,
      database: result.name,
    })
    await roleClient.connect()
    const queryRes = await roleClient.query('SELECT 1 + 1 AS solution')
    assert.strictEqual(queryRes.rows[0].solution, 2)

    // Verify resource role can create tables and insert data in its own database
    await roleClient.query('CREATE TABLE project_items (id serial primary key, name text)')
    await roleClient.query("INSERT INTO project_items (name) VALUES ('neon-item')")
    const itemsRes = await roleClient.query('SELECT * FROM project_items')
    assert.strictEqual(itemsRes.rows.length, 1)
    assert.strictEqual(itemsRes.rows[0].name, 'neon-item')
    await roleClient.end()

    // Clean up
    await deleteDatabase(result.id)
  })

  await t.test('resource role is isolated and blocked from accessing other databases (ADR 0009)', async () => {
    const dbName1 = `iso_db1_${Date.now()}`
    const dbName2 = `iso_db2_${Date.now()}`

    const db1 = await createDatabase({
      projectId: testProject.id,
      name: dbName1,
    })
    const db2 = await createDatabase({
      projectId: testProject.id,
      name: dbName2,
    })

    // 1. db1 resource role user connecting to system database neon_control_plane -> MUST BE REJECTED
    const sysClient = new pg.Client({
      host: db1.host,
      port: db1.port,
      user: db1.username,
      password: db1.password,
      database: 'neon_control_plane',
    })
    await assert.rejects(
      async () => {
        await sysClient.connect()
      },
      (err: any) => {
        return err.message.includes('permission denied') || err.code === '42501'
      },
      'Resource role should NOT connect to neon_control_plane',
    )
    sysClient.end().catch(() => {})

    // 2. db1 resource role user connecting to default postgres database -> MUST BE REJECTED
    const pgClient = new pg.Client({
      host: db1.host,
      port: db1.port,
      user: db1.username,
      password: db1.password,
      database: 'postgres',
    })
    await assert.rejects(
      async () => {
        await pgClient.connect()
      },
      (err: any) => {
        return err.message.includes('permission denied') || err.code === '42501'
      },
      'Resource role should NOT connect to postgres database',
    )
    pgClient.end().catch(() => {})

    // 3. db1 resource role user connecting to db2 database -> MUST BE REJECTED
    const crossClient = new pg.Client({
      host: db1.host,
      port: db1.port,
      user: db1.username,
      password: db1.password,
      database: db2.name,
    })
    await assert.rejects(
      async () => {
        await crossClient.connect()
      },
      (err: any) => {
        return err.message.includes('permission denied') || err.code === '42501'
      },
      'Resource role should NOT connect to another project database',
    )
    crossClient.end().catch(() => {})

    // Cleanup
    await deleteDatabase(db1.id)
    await deleteDatabase(db2.id)
  })

  await t.test('listDatabases returns all databases for a project', async () => {
    const dbName = `list_db_${Date.now()}`
    const created = await createDatabase({
      projectId: testProject.id,
      name: dbName,
    })

    const list = await listDatabases(testProject.id)
    assert.ok(Array.isArray(list))
    const found = list.find((d) => d.id === created.id)
    assert.ok(found)
    assert.strictEqual(found.name, dbName)
    assert.ok(found.connectionString)

    await deleteDatabase(created.id)
  })

  await t.test('getDatabaseCredentials returns full credential bundles', async () => {
    const dbName = `creds_db_${Date.now()}`
    const created = await createDatabase({
      projectId: testProject.id,
      name: dbName,
    })

    const creds = await getDatabaseCredentials(created.id)
    assert.ok(creds)
    assert.strictEqual(creds.id, created.id)
    assert.strictEqual(creds.name, dbName)
    assert.ok(creds.connectionString.startsWith('postgresql://'))
    assert.ok(creds.envSnippet.includes('DATABASE_URL='))
    assert.ok(creds.psqlCommand.includes('psql'))
    assert.ok(creds.prismaSnippet.includes('datasource db'))
    assert.ok(creds.drizzleSnippet.includes('drizzle'))

    await deleteDatabase(created.id)
  })

  await t.test('connectionString appends transport encryption query parameters ?sslmode=verify-full&sslrootcert=ca.crt', () => {
    const creds = formatDatabaseCredentials({
      id: 'test-id',
      projectId: 'test-proj',
      name: 'test_db',
      username: 'test_user',
      password: 'test_password',
      host: 'localhost',
      port: 5432,
      createdAt: new Date(),
    })

    assert.ok(creds.connectionString.endsWith('?sslmode=verify-full&sslrootcert=ca.crt'))
    assert.strictEqual(
      creds.connectionString,
      'postgresql://test_user:test_password@localhost:5432/test_db?sslmode=verify-full&sslrootcert=ca.crt',
    )
  })

  await t.test('dynamic host resolution prioritizes PUBLIC_POSTGRES_HOST, then PUBLIC_HOST, then dbRecord.host', () => {
    const origPostgresHost = process.env.PUBLIC_POSTGRES_HOST
    const origHost = process.env.PUBLIC_HOST
    try {
      // 1. PUBLIC_POSTGRES_HOST takes top precedence
      process.env.PUBLIC_POSTGRES_HOST = 'postgres.neon.tech'
      process.env.PUBLIC_HOST = 'general.neon.tech'
      const creds1 = formatDatabaseCredentials({
        id: '1',
        projectId: 'p1',
        name: 'db1',
        username: 'u1',
        password: 'pw1',
        host: 'localhost',
        port: 5432,
        createdAt: new Date(),
      })
      assert.strictEqual(creds1.host, 'postgres.neon.tech')
      assert.ok(creds1.connectionString.includes('@postgres.neon.tech:5432/'))

      // 2. PUBLIC_HOST takes precedence if PUBLIC_POSTGRES_HOST is unset
      delete process.env.PUBLIC_POSTGRES_HOST
      process.env.PUBLIC_HOST = 'general.neon.tech'
      const creds2 = formatDatabaseCredentials({
        id: '2',
        projectId: 'p1',
        name: 'db2',
        username: 'u2',
        password: 'pw2',
        host: 'localhost',
        port: 5432,
        createdAt: new Date(),
      })
      assert.strictEqual(creds2.host, 'general.neon.tech')
      assert.ok(creds2.connectionString.includes('@general.neon.tech:5432/'))

      // 3. Fallback to dbRecord.host when neither env var is set
      delete process.env.PUBLIC_POSTGRES_HOST
      delete process.env.PUBLIC_HOST
      const creds3 = formatDatabaseCredentials({
        id: '3',
        projectId: 'p1',
        name: 'db3',
        username: 'u3',
        password: 'pw3',
        host: 'custom.db.internal',
        port: 5432,
        createdAt: new Date(),
      })
      assert.strictEqual(creds3.host, 'custom.db.internal')
      assert.ok(creds3.connectionString.includes('@custom.db.internal:5432/'))

      // 4. Default to localhost if dbRecord.host is empty
      const creds4 = formatDatabaseCredentials({
        id: '4',
        projectId: 'p1',
        name: 'db4',
        username: 'u4',
        password: 'pw4',
        host: '',
        port: 5432,
        createdAt: new Date(),
      })
      assert.strictEqual(creds4.host, 'localhost')
      assert.ok(creds4.connectionString.includes('@localhost:5432/'))
    } finally {
      if (origPostgresHost !== undefined) {
        process.env.PUBLIC_POSTGRES_HOST = origPostgresHost
      } else {
        delete process.env.PUBLIC_POSTGRES_HOST
      }
      if (origHost !== undefined) {
        process.env.PUBLIC_HOST = origHost
      } else {
        delete process.env.PUBLIC_HOST
      }
    }
  })

  await t.test('existing databases stored with localhost dynamically resolve to Public Host without migration', async () => {
    const origPostgresHost = process.env.PUBLIC_POSTGRES_HOST
    try {
      const dbName = `legacy_db_${Date.now()}`
      const created = await createDatabase({
        projectId: testProject.id,
        name: dbName,
      })

      // Simulate a legacy database record with host stored as 'localhost'
      process.env.PUBLIC_POSTGRES_HOST = 'public.neon.domain'
      const retrieved = await getDatabaseCredentials(created.id)
      assert.strictEqual(retrieved.host, 'public.neon.domain')
      assert.ok(retrieved.connectionString.includes('@public.neon.domain:'))
      assert.ok(retrieved.connectionString.includes('?sslmode=verify-full&sslrootcert=ca.crt'))

      await deleteDatabase(created.id)
    } finally {
      if (origPostgresHost !== undefined) {
        process.env.PUBLIC_POSTGRES_HOST = origPostgresHost
      } else {
        delete process.env.PUBLIC_POSTGRES_HOST
      }
    }
  })

  await t.test('all credential snippets reflect TLS parameters and CA certificate configuration', () => {
    const creds = formatDatabaseCredentials({
      id: 'test-id',
      projectId: 'test-proj',
      name: 'production_app',
      username: 'prod_user',
      password: 'secret_password_123',
      host: 'db.example.com',
      port: 5432,
      createdAt: new Date(),
    })

    // envSnippet contains the full TLS connection string
    assert.strictEqual(
      creds.envSnippet,
      'DATABASE_URL="postgresql://prod_user:secret_password_123@db.example.com:5432/production_app?sslmode=verify-full&sslrootcert=ca.crt"',
    )

    // psqlCommand contains connection URI with sslmode and sslrootcert
    assert.ok(creds.psqlCommand.includes('psql "postgresql://'))
    assert.ok(creds.psqlCommand.includes('sslmode=verify-full'))
    assert.ok(creds.psqlCommand.includes('sslrootcert=ca.crt'))

    // psqlCommandRaw shows complete TLS configuration with CA certificate usage
    assert.ok(creds.psqlCommandRaw.includes('PGSSLMODE=verify-full') || creds.psqlCommandRaw.includes('sslmode=verify-full'))
    assert.ok(creds.psqlCommandRaw.includes('PGSSLROOTCERT=ca.crt') || creds.psqlCommandRaw.includes('sslrootcert=ca.crt'))

    // prismaSnippet shows CA certificate guidance and TLS connection URI
    assert.ok(creds.prismaSnippet.includes('ca.crt'))
    assert.ok(creds.prismaSnippet.includes('DATABASE_URL='))
    assert.ok(creds.prismaSnippet.includes('sslmode=verify-full'))

    // drizzleSnippet shows node-postgres SSL configuration with CA certificate file read
    assert.ok(creds.drizzleSnippet.includes("ca: fs.readFileSync('ca.crt').toString()") || creds.drizzleSnippet.includes('ca: fs.readFileSync("ca.crt")') || creds.drizzleSnippet.includes('ca.crt'))
    assert.ok(creds.drizzleSnippet.includes('rejectUnauthorized: true'))
  })

  await t.test('resetDatabasePassword updates role password in Postgres and Drizzle record', async () => {
    const dbName = `reset_db_${Date.now()}`
    const created = await createDatabase({
      projectId: testProject.id,
      name: dbName,
    })
    const oldPassword = created.password

    const resetResult = await resetDatabasePassword(created.id)
    assert.notStrictEqual(resetResult.password, oldPassword)

    // Old password connection should fail
    const oldClient = new pg.Client({
      host: created.host,
      port: created.port,
      user: created.username,
      password: oldPassword,
      database: created.name,
    })
    await assert.rejects(
      async () => {
        await oldClient.connect()
      },
      (err: any) => {
        return err.message.includes('password authentication failed') || err.code === '28P01'
      },
      'Old password must fail authentication after reset',
    )
    oldClient.end().catch(() => {})

    // New password connection should succeed
    const newClient = new pg.Client({
      host: created.host,
      port: created.port,
      user: created.username,
      password: resetResult.password,
      database: created.name,
    })
    await newClient.connect()
    const res = await newClient.query('SELECT 1 as connected')
    assert.strictEqual(res.rows[0].connected, 1)
    await newClient.end()

    await deleteDatabase(created.id)
  })

  await t.test('deleteDatabase terminates connections, drops DB, drops role, and removes record', async () => {
    const dbName = `del_db_${Date.now()}`
    const created = await createDatabase({
      projectId: testProject.id,
      name: dbName,
    })

    // Establish an active connection to test connection termination
    const activeClient = new pg.Client({
      host: created.host,
      port: created.port,
      user: created.username,
      password: created.password,
      database: created.name,
    })
    activeClient.on('error', () => {
      // Expected to be terminated by administrator command
    })
    await activeClient.connect()

    const delResult = await deleteDatabase(created.id)
    assert.strictEqual(delResult.success, true)

    // Wait a brief moment for socket to register termination
    activeClient.end().catch(() => {})

    // Record should no longer exist in Drizzle
    const found = await getDatabase(created.id)
    assert.strictEqual(found, null)

    // Connecting to dropped DB should fail
    const reconnectClient = new pg.Client({
      host: created.host,
      port: created.port,
      user: created.username,
      password: created.password,
      database: created.name,
    })
    await assert.rejects(async () => {
      await reconnectClient.connect()
    })
    reconnectClient.end().catch(() => {})
  })

  await t.test('createDatabase rejects invalid or non-existent project id', async () => {
    await assert.rejects(
      async () => {
        await createDatabase({
          projectId: '00000000-0000-0000-0000-000000000000',
          name: 'invalid_proj_db',
        })
      },
      {
        message: 'Project not found',
      },
    )
  })

  await t.test('createDatabase rejects empty or whitespace database name', async () => {
    await assert.rejects(
      async () => {
        await createDatabase({
          projectId: testProject.id,
          name: '   ',
        })
      },
      {
        message: 'Database name cannot be empty',
      },
    )
  })

  await t.test('server functions (createDatabaseFn, listDatabasesFn, getDatabaseCredentialsFn, resetDatabasePasswordFn, deleteDatabaseFn) are properly defined', async () => {
    const {
      createDatabaseFn,
      listDatabasesFn,
      getDatabaseCredentialsFn,
      resetDatabasePasswordFn,
      deleteDatabaseFn,
    } = await import('../services/databases.js')

    assert.strictEqual(typeof createDatabaseFn, 'function')
    assert.strictEqual(typeof listDatabasesFn, 'function')
    assert.strictEqual(typeof getDatabaseCredentialsFn, 'function')
    assert.strictEqual(typeof resetDatabasePasswordFn, 'function')
    assert.strictEqual(typeof deleteDatabaseFn, 'function')
  })
})

