import test from 'node:test'
import assert from 'node:assert/strict'
import { createProject } from '../services/projects'
import { createDatabase, deleteDatabase } from '../services/databases'
import {
  executeSqlQuery,
  executeSqlQueryFn,
} from '../services/scratchpad'
import { db } from '../db/index'
import { projects, databases } from '../db/schema'
import { eq } from 'drizzle-orm'

test('SQL Scratchpad Service Seam', async (t) => {
  let testProject: any
  let testDb: any

  t.before(async () => {
    testProject = await createProject({
      name: 'Scratchpad Test Project',
      slug: `scratchpad-test-${Date.now()}`,
    })
    testDb = await createDatabase({
      projectId: testProject.id,
      name: `scratch_db_${Date.now()}`,
    })
  })

  t.after(async () => {
    if (testDb?.id) {
      await deleteDatabase(testDb.id).catch(() => {})
    }
    if (testProject?.id) {
      await db.delete(projects).where(eq(projects.id, testProject.id)).catch(() => {})
    }
  })

  await t.test('executeSqlQuery executes read query and returns structured results', async () => {
    const result = await executeSqlQuery({
      databaseId: testDb.id,
      query: 'SELECT 1 AS num, \'neon\' AS platform, NOW() AS ts',
    })

    assert.ok(result, 'Result must be returned')
    assert.deepStrictEqual(result.columns, ['num', 'platform', 'ts'])
    assert.strictEqual(result.rowCount, 1)
    assert.strictEqual(result.rows.length, 1)
    assert.strictEqual(result.rows[0].num, 1)
    assert.strictEqual(result.rows[0].platform, 'neon')
    assert.ok(result.rows[0].ts)
    assert.ok(typeof result.executionTimeMs === 'number', 'executionTimeMs must be a number')
    assert.ok(result.executionTimeMs >= 0, 'executionTimeMs must be non-negative')
  })

  await t.test('executeSqlQuery executes write query (DDL and DML) successfully', async () => {
    // 1. DDL: Create table
    const createRes = await executeSqlQuery({
      databaseId: testDb.id,
      query: 'CREATE TABLE notes (id serial primary key, title text, done boolean default false);',
    })
    assert.ok(createRes, 'DDL should succeed')
    assert.ok(typeof createRes.executionTimeMs === 'number')

    // 2. DML: Insert row
    const insertRes = await executeSqlQuery({
      databaseId: testDb.id,
      query: 'INSERT INTO notes (title, done) VALUES (\'First note\', true), (\'Second note\', false) RETURNING *;',
    })
    assert.strictEqual(insertRes.rowCount, 2)
    assert.strictEqual(insertRes.rows.length, 2)
    assert.strictEqual(insertRes.rows[0].title, 'First note')
    assert.strictEqual(insertRes.rows[0].done, true)
    assert.strictEqual(insertRes.rows[1].title, 'Second note')
    assert.strictEqual(insertRes.rows[1].done, false)

    // 3. Query rows back
    const selectRes = await executeSqlQuery({
      databaseId: testDb.id,
      query: 'SELECT title, done FROM notes ORDER BY id ASC;',
    })
    assert.deepStrictEqual(selectRes.columns, ['title', 'done'])
    assert.strictEqual(selectRes.rowCount, 2)
    assert.strictEqual(selectRes.rows[0].title, 'First note')
  })

  await t.test('executeSqlQuery handles syntax error cleanly with informative error message', async () => {
    await assert.rejects(
      async () => {
        await executeSqlQuery({
          databaseId: testDb.id,
          query: 'SELECT FROM WHERE INVALID SYNTAX;',
        })
      },
      (err: any) => {
        assert.ok(err instanceof Error)
        assert.ok(
          err.message.toLowerCase().includes('syntax error'),
          `Error message should mention syntax error, got: ${err.message}`,
        )
        return true
      },
    )
  })

  await t.test('executeSqlQuery throws error if database does not exist', async () => {
    await assert.rejects(
      async () => {
        await executeSqlQuery({
          databaseId: '00000000-0000-0000-0000-000000000000',
          query: 'SELECT 1;',
        })
      },
      (err: any) => {
        assert.ok(err instanceof Error)
        assert.ok(err.message.includes('not found'))
        return true
      },
    )
  })

  await t.test('executeSqlQuery does not fallback to superuser when resource role connection fails', async () => {
    // Insert a database record with invalid password for the dedicated role
    const [badDb] = await db
      .insert(databases)
      .values({
        projectId: testProject.id,
        name: testDb.name,
        host: testDb.host,
        port: testDb.port,
        username: testDb.username,
        password: 'incorrect_password_12345',
      })
      .returning()

    await assert.rejects(
      async () => {
        await executeSqlQuery({
          databaseId: badDb.id,
          query: 'SELECT 1;',
        })
      },
      (err: any) => {
        assert.ok(err instanceof Error)
        assert.ok(
          err.message.includes('Database connection failed') ||
          err.message.includes('password authentication failed'),
          `Error should be connection failure, got: ${err.message}`,
        )
        return true
      },
    )

    // Cleanup
    await db.delete(databases).where(eq(databases.id, badDb.id)).catch(() => {})
  })

  await t.test('executeSqlQueryFn server function is properly defined', async () => {
    assert.strictEqual(typeof executeSqlQueryFn, 'function')
    assert.ok(executeSqlQueryFn.url || typeof executeSqlQueryFn === 'function')
  })
})
