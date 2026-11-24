import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import os from 'node:os'
import {
  ensureMasterDatabaseCredentials,
  getMasterDatabaseCredentials,
  ensureStorageAdminCredentials,
  getStorageAdminCredentials,
  parseEnvContent,
} from '../services/master-credentials'
import {
  ensureAdminIdentity,
  type S3Config,
} from '../services/storage'

test('Master & Storage Admin Credentials Seam', async (t) => {
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), 'neon-cred-test-'))
  const testEnvFile = path.join(tmpDir, '.env.test')

  t.after(() => {
    fs.rmSync(tmpDir, { recursive: true, force: true })
  })

  await t.test('parseEnvContent accurately extracts key-value pairs', () => {
    const raw = `
# Comment line
POSTGRES_USER="postgres"
POSTGRES_PASSWORD='mysecretpassword'
UNQUOTED_VAL=some_value
`
    const parsed = parseEnvContent(raw)
    assert.strictEqual(parsed.POSTGRES_USER, 'postgres')
    assert.strictEqual(parsed.POSTGRES_PASSWORD, 'mysecretpassword')
    assert.strictEqual(parsed.UNQUOTED_VAL, 'some_value')
  })

  await t.test('ensureMasterDatabaseCredentials generates secure random password when missing', () => {
    const origUser = process.env.POSTGRES_USER
    const origPass = process.env.POSTGRES_PASSWORD
    delete process.env.POSTGRES_USER
    delete process.env.POSTGRES_PASSWORD

    try {
      const creds = ensureMasterDatabaseCredentials(testEnvFile)
      assert.strictEqual(creds.username, 'postgres')
      assert.strictEqual(typeof creds.password, 'string')
      assert.strictEqual(creds.password.length, 32)
      assert.notStrictEqual(creds.password, 'postgres')

      // Verify written to testEnvFile
      assert.ok(fs.existsSync(testEnvFile))
      const content = fs.readFileSync(testEnvFile, 'utf-8')
      assert.ok(content.includes(`POSTGRES_PASSWORD="${creds.password}"`))

      // getMasterDatabaseCredentials returns the same credentials
      const retrieved = getMasterDatabaseCredentials(testEnvFile)
      assert.strictEqual(retrieved.password, creds.password)
    } finally {
      if (origUser) process.env.POSTGRES_USER = origUser
      if (origPass) process.env.POSTGRES_PASSWORD = origPass
    }
  })

  await t.test('ensureStorageAdminCredentials generates discrete admin credentials when missing', () => {
    const origKey = process.env.SEAWEEDFS_ADMIN_ACCESS_KEY
    const origSecret = process.env.SEAWEEDFS_ADMIN_SECRET_KEY
    delete process.env.SEAWEEDFS_ADMIN_ACCESS_KEY
    delete process.env.SEAWEEDFS_ADMIN_SECRET_KEY

    try {
      const creds = ensureStorageAdminCredentials(testEnvFile)
      assert.ok(creds.accessKeyId.startsWith('AKIA'))
      assert.strictEqual(typeof creds.secretAccessKey, 'string')
      assert.ok(creds.secretAccessKey.length >= 32)
      assert.notStrictEqual(creds.accessKeyId, 'neonadmin')
      assert.notStrictEqual(creds.secretAccessKey, 'neonadminsecret')

      const content = fs.readFileSync(testEnvFile, 'utf-8')
      assert.ok(content.includes(`SEAWEEDFS_ADMIN_ACCESS_KEY="${creds.accessKeyId}"`))
      assert.ok(content.includes(`SEAWEEDFS_ADMIN_SECRET_KEY="${creds.secretAccessKey}"`))
    } finally {
      if (origKey) process.env.SEAWEEDFS_ADMIN_ACCESS_KEY = origKey
      if (origSecret) process.env.SEAWEEDFS_ADMIN_SECRET_KEY = origSecret
    }
  })

  await t.test('ensureAdminIdentity updates legacy neonadmin credentials in s3.json config', () => {
    const legacyConfig: S3Config = {
      identities: [
        {
          name: 'admin',
          credentials: [
            {
              accessKey: 'neonadmin',
              secretKey: 'neonadminsecret',
            },
          ],
          actions: ['Admin', 'Read', 'List', 'Tagging', 'Write'],
        },
      ],
    }

    ensureAdminIdentity(legacyConfig)
    const admin = legacyConfig.identities.find((i) => i.name === 'admin')
    assert.ok(admin)
    assert.notStrictEqual(admin.credentials[0].accessKey, 'neonadmin')
    assert.notStrictEqual(admin.credentials[0].secretKey, 'neonadminsecret')
  })
})
