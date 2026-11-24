import test from 'node:test'
import assert from 'node:assert/strict'
import {
  createProject,
  listProjects,
  getProject,
  slugify,
} from '../services/projects'
import { db } from '../db/index'
import { projects, databases, objectStorages } from '../db/schema'
import { eq } from 'drizzle-orm'

test('Projects Management Seam', async (t) => {
  await t.test('createProject creates a project with slug, region, and timestamps', async () => {
    const project = await createProject({
      name: 'Alpha App',
    })

    assert.ok(project.id)
    assert.strictEqual(project.name, 'Alpha App')
    assert.strictEqual(project.slug, 'alpha-app')
    assert.strictEqual(project.region, 'us-east-1')
    assert.ok(project.createdAt instanceof Date)
    assert.ok(project.updatedAt instanceof Date)

    // Cleanup
    await db.delete(projects).where(eq(projects.id, project.id))
  })

  await t.test('createProject supports custom slug and region', async () => {
    const project = await createProject({
      name: 'Custom Region App',
      slug: 'custom-region-slug',
      region: 'eu-west-1',
    })

    assert.strictEqual(project.name, 'Custom Region App')
    assert.strictEqual(project.slug, 'custom-region-slug')
    assert.strictEqual(project.region, 'eu-west-1')

    // Cleanup
    await db.delete(projects).where(eq(projects.id, project.id))
  })

  await t.test('createProject handles slug collisions by generating a unique slug', async () => {
    const p1 = await createProject({ name: 'Duplicate Name' })
    const p2 = await createProject({ name: 'Duplicate Name' })

    assert.notStrictEqual(p1.slug, p2.slug)
    assert.match(p2.slug, /^duplicate-name-[a-z0-9]+$/)

    // Cleanup
    await db.delete(projects).where(eq(projects.id, p1.id))
    await db.delete(projects).where(eq(projects.id, p2.id))
  })

  await t.test('listProjects returns all projects with database and storage counts', async () => {
    const p1 = await createProject({ name: 'Project With Resources' })
    const p2 = await createProject({ name: 'Project Empty' })

    // Simulate 1 database and 1 storage for p1
    await db.insert(databases).values({
      projectId: p1.id,
      name: 'prod_db',
      username: 'user_prod',
      password: 'secretpassword',
      host: 'localhost',
      port: 5432,
    })

    await db.insert(objectStorages).values({
      projectId: p1.id,
      bucketName: 'prod-media',
      accessKeyId: 'acc123',
      secretAccessKey: 'sec123',
      endpoint: 'http://localhost:8333',
      region: 'us-east-1',
    })

    const all = await listProjects()
    assert.ok(Array.isArray(all))

    const foundP1 = all.find((p) => p.id === p1.id)
    const foundP2 = all.find((p) => p.id === p2.id)

    assert.ok(foundP1)
    assert.strictEqual(foundP1.databaseCount, 1)
    assert.strictEqual(foundP1.storageCount, 1)

    assert.ok(foundP2)
    assert.strictEqual(foundP2.databaseCount, 0)
    assert.strictEqual(foundP2.storageCount, 0)

    // Cleanup
    await db.delete(projects).where(eq(projects.id, p1.id))
    await db.delete(projects).where(eq(projects.id, p2.id))
  })

  await t.test('getProject retrieves project details by id or slug with counts', async () => {
    const created = await createProject({ name: 'Detail Project' })

    const byId = await getProject(created.id)
    assert.ok(byId)
    assert.strictEqual(byId.id, created.id)
    assert.strictEqual(byId.name, 'Detail Project')
    assert.strictEqual(byId.databaseCount, 0)
    assert.strictEqual(byId.storageCount, 0)

    const bySlug = await getProject(created.slug)
    assert.ok(bySlug)
    assert.strictEqual(bySlug.id, created.id)

    const notFound = await getProject('non-existent-id')
    assert.strictEqual(notFound, null)

    // Cleanup
    await db.delete(projects).where(eq(projects.id, created.id))
  })

  await t.test('createProject validates project name cannot be empty', async () => {
    await assert.rejects(
      async () => {
        await createProject({ name: '   ' })
      },
      {
        message: 'Project name cannot be empty',
      },
    )
  })
})

