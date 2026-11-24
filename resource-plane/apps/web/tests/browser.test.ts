import test from 'node:test'
import assert from 'node:assert/strict'
import { createProject } from '../services/projects'
import {
  createObjectStorage,
  deleteObjectStorage,
} from '../services/storage'
import {
  listBucketObjects,
  uploadBucketObject,
  deleteBucketObject,
  getObjectContent,
  listBucketObjectsFn,
  uploadBucketObjectFn,
  deleteBucketObjectFn,
  getObjectContentFn,
} from '../services/browser'
import { db } from '../db/index'
import { projects } from '../db/schema'
import { eq } from 'drizzle-orm'

test('Object Browser Service Seam', async (t) => {
  let testProject: any
  let testStorage: any

  t.before(async () => {
    testProject = await createProject({
      name: 'Browser Test Project',
      slug: `browser-test-${Date.now()}`,
    })
    testStorage = await createObjectStorage({
      projectId: testProject.id,
      bucketName: `bkt-test-${Date.now().toString(36)}`,
    })
  })

  t.after(async () => {
    if (testStorage?.id) {
      await deleteObjectStorage(testStorage.id).catch(() => {})
    }
    if (testProject?.id) {
      await db.delete(projects).where(eq(projects.id, testProject.id)).catch(() => {})
    }
  })

  await t.test('listBucketObjects returns empty array for new bucket', async () => {
    const objects = await listBucketObjects(testStorage.id)
    assert.ok(Array.isArray(objects), 'Objects must be an array')
    assert.strictEqual(objects.length, 0)
  })

  await t.test('uploadBucketObject uploads text and binary content to bucket', async () => {
    // 1. Upload text content
    const textRes = await uploadBucketObject({
      storageId: testStorage.id,
      key: 'notes/readme.txt',
      content: 'Hello Neon Object Browser!',
      contentType: 'text/plain',
    })
    assert.strictEqual(textRes.success, true)
    assert.strictEqual(textRes.key, 'notes/readme.txt')
    assert.ok(textRes.size > 0)

    // 2. Upload binary content (base64 string)
    const rawBinary = Buffer.from('BINARY_PAYLOAD_NEON_DATA_12345')
    const base64Data = rawBinary.toString('base64')
    const binRes = await uploadBucketObject({
      storageId: testStorage.id,
      key: 'data/sample.bin',
      content: base64Data,
      isBase64: true,
      contentType: 'application/octet-stream',
    })
    assert.strictEqual(binRes.success, true)
    assert.strictEqual(binRes.key, 'data/sample.bin')
    assert.strictEqual(binRes.size, rawBinary.length)
  })

  await t.test('listBucketObjects lists all uploaded objects with metadata', async () => {
    const objects = await listBucketObjects(testStorage.id)
    assert.strictEqual(objects.length, 2)

    const keys = objects.map((o) => o.key)
    assert.ok(keys.includes('notes/readme.txt'))
    assert.ok(keys.includes('data/sample.bin'))

    const txtObj = objects.find((o) => o.key === 'notes/readme.txt')
    assert.ok(txtObj)
    assert.ok(txtObj.size > 0)
    assert.ok(txtObj.lastModified)
    assert.ok(txtObj.etag)

    const binObj = objects.find((o) => o.key === 'data/sample.bin')
    assert.ok(binObj)
    assert.strictEqual(binObj.size, Buffer.from('BINARY_PAYLOAD_NEON_DATA_12345').length)
  })

  await t.test('getObjectContent downloads object content with base64 and text', async () => {
    const file = await getObjectContent(testStorage.id, 'notes/readme.txt')
    assert.strictEqual(file.key, 'notes/readme.txt')
    assert.strictEqual(file.text, 'Hello Neon Object Browser!')
    assert.ok(file.base64)
    assert.ok(file.size > 0)
    assert.strictEqual(file.contentType, 'text/plain')

    const binFile = await getObjectContent(testStorage.id, 'data/sample.bin')
    assert.strictEqual(binFile.key, 'data/sample.bin')
    const decoded = Buffer.from(binFile.base64, 'base64').toString()
    assert.strictEqual(decoded, 'BINARY_PAYLOAD_NEON_DATA_12345')
  })

  await t.test('deleteBucketObject deletes object and updates object listing', async () => {
    const delRes = await deleteBucketObject(testStorage.id, 'notes/readme.txt')
    assert.strictEqual(delRes.success, true)
    assert.strictEqual(delRes.key, 'notes/readme.txt')

    const remaining = await listBucketObjects(testStorage.id)
    assert.strictEqual(remaining.length, 1)
    assert.strictEqual(remaining[0].key, 'data/sample.bin')
  })

  await t.test('listBucketObjects throws error for non-existent storage ID', async () => {
    await assert.rejects(
      async () => {
        await listBucketObjects('00000000-0000-0000-0000-000000000000')
      },
      (err: any) => {
        assert.ok(err.message.includes('not found'))
        return true
      },
    )
  })

  await t.test('Server functions are properly defined', async () => {
    assert.strictEqual(typeof listBucketObjectsFn, 'function')
    assert.strictEqual(typeof uploadBucketObjectFn, 'function')
    assert.strictEqual(typeof deleteBucketObjectFn, 'function')
    assert.strictEqual(typeof getObjectContentFn, 'function')
  })
})
