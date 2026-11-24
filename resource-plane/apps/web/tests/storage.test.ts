import test from 'node:test'
import assert from 'node:assert/strict'
import {
  createObjectStorage,
  listObjectStorages,
  getStorageCredentials,
  deleteObjectStorage,
  formatStorageCredentials,
  validateBucketName,
  getAdminS3Client,
} from '../services/storage'
import { createProject } from '../services/projects'
import { db } from '../db/index'
import { projects, objectStorages } from '../db/schema'
import { eq } from 'drizzle-orm'
import {
  S3Client,
  PutObjectCommand,
  ListObjectsV2Command,
  GetObjectCommand,
  CreateBucketCommand,
  DeleteBucketCommand,
} from '@aws-sdk/client-s3'

test('Storage Provisioning Service Seam', async (t) => {
  let testProject: any

  t.before(async () => {
    testProject = await createProject({
      name: 'Storage Test Project',
      slug: `storage-test-${Date.now()}`,
    })
  })

  t.after(async () => {
    if (testProject?.id) {
      await db.delete(projects).where(eq(projects.id, testProject.id))
    }
  })

  await t.test('createObjectStorage provisions a bucket, generates keys, and updates IAM', async () => {
    const bucketName = `test-bkt-${Date.now().toString(36)}`
    const storage = await createObjectStorage({
      projectId: testProject.id,
      bucketName,
    })

    assert.ok(storage.id, 'Storage ID must be defined')
    assert.strictEqual(storage.projectId, testProject.id)
    assert.strictEqual(storage.bucketName, bucketName)
    assert.ok(storage.accessKeyId, 'AccessKeyId must be generated')
    assert.ok(storage.secretAccessKey, 'SecretAccessKey must be generated')
    assert.strictEqual(storage.endpoint, 'http://localhost:8333')
    assert.strictEqual(storage.region, 'us-east-1')

    // Cleanup
    await deleteObjectStorage(storage.id)
  })

  await t.test('createObjectStorage rejects duplicate bucket collision if bucket exists in DB', async () => {
    const bucketName = `dup-bkt-${Date.now().toString(36)}`
    const storage = await createObjectStorage({
      projectId: testProject.id,
      bucketName,
    })

    await assert.rejects(
      async () => {
        await createObjectStorage({
          projectId: testProject.id,
          bucketName,
        })
      },
      (err: any) => {
        assert.ok(err instanceof Error)
        assert.strictEqual(err.message, `Bucket "${bucketName}" already exists`)
        return true
      },
    )

    // Cleanup
    await deleteObjectStorage(storage.id)
  })

  await t.test('createObjectStorage rejects collision if bucket already exists in SeaweedFS directly', async () => {
    const orphanBucket = `orphan-bkt-${Date.now().toString(36)}`
    const adminClient = getAdminS3Client()
    await adminClient.send(new CreateBucketCommand({ Bucket: orphanBucket }))

    await assert.rejects(
      async () => {
        await createObjectStorage({
          projectId: testProject.id,
          bucketName: orphanBucket,
        })
      },
      (err: any) => {
        assert.ok(err instanceof Error)
        assert.strictEqual(err.message, `Bucket "${orphanBucket}" already exists`)
        return true
      },
    )

    // Cleanup orphan bucket
    await adminClient.send(new DeleteBucketCommand({ Bucket: orphanBucket }))
  })

  await t.test('listObjectStorages returns storages for a given projectId', async () => {
    const bkt1 = `list-bkt1-${Date.now().toString(36)}`
    const bkt2 = `list-bkt2-${Date.now().toString(36)}`

    const s1 = await createObjectStorage({
      projectId: testProject.id,
      bucketName: bkt1,
    })
    const s2 = await createObjectStorage({
      projectId: testProject.id,
      bucketName: bkt2,
    })

    const list = await listObjectStorages(testProject.id)
    assert.ok(Array.isArray(list))
    const ids = list.map((s) => s.id)
    assert.ok(ids.includes(s1.id))
    assert.ok(ids.includes(s2.id))

    // Cleanup
    await deleteObjectStorage(s1.id)
    await deleteObjectStorage(s2.id)
  })

  await t.test('getStorageCredentials returns discrete credentials for a storage', async () => {
    const bkt = `cred-bkt-${Date.now().toString(36)}`
    const created = await createObjectStorage({
      projectId: testProject.id,
      bucketName: bkt,
    })

    const creds = await getStorageCredentials(created.id)
    assert.ok(creds)
    assert.strictEqual(creds.id, created.id)
    assert.strictEqual(creds.bucketName, bkt)
    assert.strictEqual(creds.accessKeyId, created.accessKeyId)
    assert.strictEqual(creds.secretAccessKey, created.secretAccessKey)
    assert.strictEqual(creds.endpoint, 'http://localhost:8333')
    assert.strictEqual(creds.region, 'us-east-1')

    // Cleanup
    await deleteObjectStorage(created.id)
  })

  await t.test('deleteObjectStorage removes bucket, IAM identity, and database record', async () => {
    const bkt = `del-bkt-${Date.now().toString(36)}`
    const created = await createObjectStorage({
      projectId: testProject.id,
      bucketName: bkt,
    })

    const deleted = await deleteObjectStorage(created.id)
    assert.strictEqual(deleted, true)

    // DB record should be gone
    const inDb = await db
      .select()
      .from(objectStorages)
      .where(eq(objectStorages.id, created.id))
    assert.strictEqual(inDb.length, 0)

    // Credential fetch should return null
    const credsAfter = await getStorageCredentials(created.id)
    assert.strictEqual(credsAfter, null)
  })

  await t.test('validateBucketName enforces S3 naming rules', () => {
    assert.strictEqual(validateBucketName('valid-bucket-1').valid, true)
    assert.strictEqual(validateBucketName('ab').valid, false) // too short
    assert.strictEqual(validateBucketName('INVALID_UPPERCASE').valid, false)
    assert.strictEqual(validateBucketName('has space').valid, false)
    assert.strictEqual(validateBucketName('-start-hyphen').valid, false)
    assert.strictEqual(validateBucketName('end-hyphen-').valid, false)
  })
})

test('IAM Bucket Restrictions Seam', async (t) => {
  let testProject: any
  let storageA: any
  let storageB: any

  t.before(async () => {
    testProject = await createProject({
      name: 'IAM Restriction Project',
      slug: `iam-test-${Date.now()}`,
    })

    storageA = await createObjectStorage({
      projectId: testProject.id,
      bucketName: `iam-bkt-a-${Date.now().toString(36)}`,
    })

    storageB = await createObjectStorage({
      projectId: testProject.id,
      bucketName: `iam-bkt-b-${Date.now().toString(36)}`,
    })
  })

  t.after(async () => {
    if (storageA?.id) await deleteObjectStorage(storageA.id).catch(() => {})
    if (storageB?.id) await deleteObjectStorage(storageB.id).catch(() => {})
    if (testProject?.id) {
      await db.delete(projects).where(eq(projects.id, testProject.id))
    }
  })

  await t.test('Client with storageA credentials can put and get objects in bucketA', async () => {
    const clientA = new S3Client({
      endpoint: storageA.endpoint,
      region: storageA.region,
      credentials: {
        accessKeyId: storageA.accessKeyId,
        secretAccessKey: storageA.secretAccessKey,
      },
      forcePathStyle: true,
    })

    // Put object in bucket A
    await clientA.send(
      new PutObjectCommand({
        Bucket: storageA.bucketName,
        Key: 'test.txt',
        Body: 'Hello Bucket A',
      }),
    )

    // List objects in bucket A
    const listRes = await clientA.send(
      new ListObjectsV2Command({
        Bucket: storageA.bucketName,
      }),
    )
    assert.ok(listRes.Contents?.some((c) => c.Key === 'test.txt'))
  })

  await t.test('Client with storageA credentials CANNOT access bucketB (AccessDenied)', async () => {
    const clientA = new S3Client({
      endpoint: storageA.endpoint,
      region: storageA.region,
      credentials: {
        accessKeyId: storageA.accessKeyId,
        secretAccessKey: storageA.secretAccessKey,
      },
      forcePathStyle: true,
    })

    await assert.rejects(
      async () => {
        await clientA.send(
          new PutObjectCommand({
            Bucket: storageB.bucketName,
            Key: 'forbidden.txt',
            Body: 'Cross resource role attack',
          }),
        )
      },
      (err: any) => {
        // SeaweedFS returns 403 AccessDenied
        return (
          err.name === 'AccessDenied' ||
          err.$metadata?.httpStatusCode === 403 ||
          err.message?.includes('Access Denied')
        )
      },
      'Expected AccessDenied when accessing bucketB with storageA credentials',
    )
  })
})

test('Storage Credential Formatting Seam', async (t) => {
  const sampleCreds = {
    id: 'test-id',
    projectId: 'test-project-id',
    bucketName: 'sample-bucket',
    accessKeyId: 'AKIA_SAMPLE_KEY',
    secretAccessKey: 'SECRET_SAMPLE_KEY',
    endpoint: 'http://localhost:8333',
    region: 'us-east-1',
  }

  await t.test('formats .env snippet correctly', () => {
    const formats = formatStorageCredentials(sampleCreds)
    assert.match(formats.env, /AWS_ACCESS_KEY_ID=AKIA_SAMPLE_KEY/)
    assert.match(formats.env, /AWS_SECRET_ACCESS_KEY=SECRET_SAMPLE_KEY/)
    assert.match(formats.env, /AWS_ENDPOINT_URL_S3=http:\/\/localhost:8333/)
    assert.match(formats.env, /AWS_REGION=us-east-1/)
    assert.match(formats.env, /S3_BUCKET_NAME=sample-bucket/)
  })

  await t.test('formats AWS CLI commands correctly', () => {
    const formats = formatStorageCredentials(sampleCreds)
    assert.match(formats.awsCli, /aws configure set aws_access_key_id AKIA_SAMPLE_KEY/)
    assert.match(formats.awsCli, /aws configure set aws_secret_access_key SECRET_SAMPLE_KEY/)
    assert.match(formats.awsCli, /aws s3 ls s3:\/\/sample-bucket --endpoint-url http:\/\/localhost:8333/)
  })

  await t.test('formats Node AWS SDK code snippet correctly', () => {
    const formats = formatStorageCredentials(sampleCreds)
    assert.match(formats.nodeSdk, /@aws-sdk\/client-s3/)
    assert.match(formats.nodeSdk, /AKIA_SAMPLE_KEY/)
    assert.match(formats.nodeSdk, /SECRET_SAMPLE_KEY/)
    assert.match(formats.nodeSdk, /http:\/\/localhost:8333/)
    assert.match(formats.nodeSdk, /forcePathStyle: true/)
  })
})
