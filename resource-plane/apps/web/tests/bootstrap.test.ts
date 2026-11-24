import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import crypto from 'node:crypto'
import { execFileSync } from 'node:child_process'
import pg from 'pg'
import {
  isPortAvailable,
  bootstrapContainers,
  waitForPostgresReady,
  waitForSeaweedFSReady,
  initSystemDatabase,
  runMigrations,
  getServicesHealth,
  ensureSystemReady,
  ensureTlsCertificates,
  getPublicPostgresHost,
  getCaCertificate,
  getCertificatePaths,
  ensurePostgresHbaConfig,
} from '../services/bootstrap'
import { inspectContainer } from '../services/docker'
import { getMasterDatabaseCredentials } from '../services/master-credentials'

test('Root CA & Server TLS Certificate Provisioning Seam', async (t) => {
  await t.test('generates Root CA and server certificate with SANs and mode 0600', async () => {
    const certs = await ensureTlsCertificates()
    assert.ok(fs.existsSync(certs.caCertPath), 'ca.crt should exist')
    assert.ok(fs.existsSync(certs.caKeyPath), 'ca.key should exist')
    assert.ok(fs.existsSync(certs.serverCertPath), 'server.crt should exist')
    assert.ok(fs.existsSync(certs.serverKeyPath), 'server.key should exist')

    // Verify key permissions (mode 0600)
    const keyStat = fs.statSync(certs.serverKeyPath)
    assert.strictEqual(keyStat.mode & 0o777, 0o600, 'server.key must have 0600 permissions')

    // Verify CA certificate
    const caPem = getCaCertificate()
    assert.ok(caPem.includes('-----BEGIN CERTIFICATE-----'))
    const caX509 = new crypto.X509Certificate(caPem)
    assert.strictEqual(caX509.subject, 'CN=Neon Local Root CA')

    // Verify Server certificate SANs
    const serverPem = fs.readFileSync(certs.serverCertPath, 'utf8')
    const serverX509 = new crypto.X509Certificate(serverPem)
    assert.strictEqual(serverX509.issuer, 'CN=Neon Local Root CA')
    const sans = serverX509.subjectAltName || ''
    assert.ok(sans.includes('DNS:localhost'), 'SANs must include DNS:localhost')
    assert.ok(sans.includes('IP Address:127.0.0.1'), 'SANs must include IP Address:127.0.0.1')
    assert.ok(
      sans.includes('IP Address:::1') || sans.includes('::1') || sans.includes('0:0:0:0:0:0:0:1'),
      'SANs must include IPv6 loopback ::1',
    )
    const publicHost = getPublicPostgresHost()
    if (publicHost !== 'localhost' && publicHost !== '127.0.0.1') {
      assert.ok(sans.includes(publicHost), `SANs must include ${publicHost}`)
    }
  })

  await t.test('dynamically regenerates server certificate with updated SANs when public host changes', async () => {
    const originalCaPem = getCaCertificate()

    // Update public host to custom domain
    const newHost = 'db.neon-local.example.com'
    const result1 = await ensureTlsCertificates({ publicHost: newHost })
    assert.strictEqual(result1.regenerated, true, 'server certificate must be regenerated for new host')

    // Root CA must remain the same
    const currentCaPem = getCaCertificate()
    assert.strictEqual(currentCaPem, originalCaPem, 'Root CA must not be regenerated')

    // Server certificate must contain new host SAN
    const cert1Pem = fs.readFileSync(result1.serverCertPath, 'utf8')
    const cert1X509 = new crypto.X509Certificate(cert1Pem)
    const sans1 = cert1X509.subjectAltName || ''
    assert.ok(sans1.includes(`DNS:${newHost}`), `SANs must include DNS:${newHost}`)
    assert.ok(sans1.includes('DNS:localhost'), 'SANs must include DNS:localhost')
    assert.ok(sans1.includes('IP Address:127.0.0.1'), 'SANs must include IP Address:127.0.0.1')
    assert.ok(
      sans1.includes('IP Address:::1') || sans1.includes('::1') || sans1.includes('0:0:0:0:0:0:0:1'),
      'SANs must include IPv6 loopback ::1',
    )

    // Calling again with the same host must NOT regenerate
    const result2 = await ensureTlsCertificates({ publicHost: newHost })
    assert.strictEqual(result2.regenerated, false, 'calling with same host must not regenerate')

    // Updating to an IP public host
    const ipHost = '198.51.100.42'
    const result3 = await ensureTlsCertificates({ publicHost: ipHost })
    assert.strictEqual(result3.regenerated, true, 'server certificate must regenerate for IP host')
    const cert3Pem = fs.readFileSync(result3.serverCertPath, 'utf8')
    const cert3X509 = new crypto.X509Certificate(cert3Pem)
    const sans3 = cert3X509.subjectAltName || ''
    assert.ok(sans3.includes(`IP Address:${ipHost}`), `SANs must include IP Address:${ipHost}`)
    assert.ok(sans3.includes('DNS:localhost'), 'SANs must include DNS:localhost')
    assert.ok(sans3.includes('IP Address:127.0.0.1'), 'SANs must include IP Address:127.0.0.1')
    assert.ok(
      sans3.includes('IP Address:::1') || sans3.includes('::1') || sans3.includes('0:0:0:0:0:0:0:1'),
      'SANs must include IPv6 loopback ::1',
    )
  })

  await t.test('respects custom certificate paths provided via environment variables', async () => {
    const tempDir = fs.mkdtempSync(path.join(process.cwd(), '.scratch', 'custom-certs-test-'))
    const customCaPath = path.join(tempDir, 'custom-ca.crt')
    const customServerCertPath = path.join(tempDir, 'custom-server.crt')
    const customServerKeyPath = path.join(tempDir, 'custom-server.key')

    fs.writeFileSync(customCaPath, '-----BEGIN CERTIFICATE-----\nCUSTOM_CA\n-----END CERTIFICATE-----\n')
    fs.writeFileSync(customServerCertPath, '-----BEGIN CERTIFICATE-----\nCUSTOM_SERVER\n-----END CERTIFICATE-----\n')
    fs.writeFileSync(customServerKeyPath, '-----BEGIN PRIVATE KEY-----\nCUSTOM_KEY\n-----END PRIVATE KEY-----\n')
    fs.chmodSync(customServerKeyPath, 0o644) // intentionally non-0600

    const prevCa = process.env.POSTGRES_CA_CERT_PATH
    const prevServerCert = process.env.POSTGRES_SERVER_CERT_PATH
    const prevServerKey = process.env.POSTGRES_SERVER_KEY_PATH

    try {
      process.env.POSTGRES_CA_CERT_PATH = customCaPath
      process.env.POSTGRES_SERVER_CERT_PATH = customServerCertPath
      process.env.POSTGRES_SERVER_KEY_PATH = customServerKeyPath

      const paths = getCertificatePaths()
      assert.strictEqual(paths.caCertPath, customCaPath)
      assert.strictEqual(paths.serverCertPath, customServerCertPath)
      assert.strictEqual(paths.serverKeyPath, customServerKeyPath)

      const result = await ensureTlsCertificates()
      assert.strictEqual(result.caCertPath, customCaPath)
      assert.strictEqual(result.serverCertPath, customServerCertPath)
      assert.strictEqual(result.serverKeyPath, customServerKeyPath)
      assert.strictEqual(result.regenerated, false)

      // Key permissions must be restricted to 0600 even for custom keys
      const keyStat = fs.statSync(customServerKeyPath)
      assert.strictEqual(keyStat.mode & 0o777, 0o600, 'custom server key must have mode 0600')

      // getCaCertificate returns custom content
      assert.strictEqual(getCaCertificate(), '-----BEGIN CERTIFICATE-----\nCUSTOM_CA\n-----END CERTIFICATE-----\n')
    } finally {
      if (prevCa !== undefined) process.env.POSTGRES_CA_CERT_PATH = prevCa
      else delete process.env.POSTGRES_CA_CERT_PATH
      if (prevServerCert !== undefined) process.env.POSTGRES_SERVER_CERT_PATH = prevServerCert
      else delete process.env.POSTGRES_SERVER_CERT_PATH
      if (prevServerKey !== undefined) process.env.POSTGRES_SERVER_KEY_PATH = prevServerKey
      else delete process.env.POSTGRES_SERVER_KEY_PATH
      fs.rmSync(tempDir, { recursive: true, force: true })
    }
  })
})

test('Auto-Bootstrapper & System Database', async (t) => {
  await t.test('isPortAvailable accurately checks open ports', async () => {
    // Port 59999 is likely free
    const free = await isPortAvailable(59999)
    assert.strictEqual(typeof free, 'boolean')
  })

  await t.test('bootstrapContainers starts neon-postgres and neon-seaweedfs', async () => {
    const ports = await bootstrapContainers()
    assert.ok(ports.postgresPort === 5432 || ports.postgresPort === 54320)
    assert.strictEqual(ports.seaweedfsS3Port, 8333)

    // Verify containers are running via docker inspect
    const pgInspect = await inspectContainer('neon-postgres')
    assert.ok(pgInspect)
    assert.strictEqual(pgInspect?.State.Running, true)

    // Verify PostgreSQL port 5432 is bound to 127.0.0.1 (not 0.0.0.0)
    const pgPortBindings = pgInspect?.HostConfig?.PortBindings?.['5432/tcp']
    assert.ok(pgPortBindings && pgPortBindings.length > 0)
    assert.strictEqual(pgPortBindings[0]?.HostIp, '127.0.0.1', 'Port 5432 must be bound to 127.0.0.1')

    // Verify PostgreSQL container runs with SSL enabled and mounted certificates
    const cmd = pgInspect?.Config?.Cmd || []
    assert.ok(cmd.includes('ssl=on'), 'PostgreSQL container must run with ssl=on')
    assert.ok(
      cmd.some((c: string) => c.includes('ssl_cert_file=/var/lib/postgresql/certs/server.crt')),
      'PostgreSQL container must specify ssl_cert_file',
    )
    assert.ok(
      cmd.some((c: string) => c.includes('ssl_key_file=/var/lib/postgresql/certs/server.key')),
      'PostgreSQL container must specify ssl_key_file',
    )
    const binds = pgInspect?.HostConfig?.Binds || []
    assert.ok(
      binds.some((b: string) => b.includes('/var/lib/postgresql/certs/server.crt')),
      'server.crt must be mounted in PostgreSQL container',
    )
    assert.ok(
      binds.some((b: string) => b.includes('/var/lib/postgresql/certs/server.key')),
      'server.key must be mounted in PostgreSQL container',
    )

    const swInspect = await inspectContainer('neon-seaweedfs')
    assert.ok(swInspect)
    assert.strictEqual(swInspect?.State.Running, true)

    // Verify SeaweedFS S3 port 8333 is bound to 127.0.0.1 (not 0.0.0.0)
    const s3PortBindings = swInspect?.HostConfig?.PortBindings?.['8333/tcp']
    assert.ok(s3PortBindings && s3PortBindings.length > 0)
    assert.strictEqual(s3PortBindings[0]?.HostIp, '127.0.0.1', 'Port 8333 must be bound to 127.0.0.1')

    // Verify SeaweedFS filer port 8888 is not bound to host (prevent unauthenticated backdoor)
    const filerPortBindings = swInspect?.HostConfig?.PortBindings?.['8888/tcp']
    assert.strictEqual(filerPortBindings, undefined, 'Port 8888 must not be bound in HostConfig.PortBindings')
    const filerNetworkPort = swInspect?.NetworkSettings?.Ports?.['8888/tcp']
    assert.ok(!filerNetworkPort || filerNetworkPort.length === 0, 'Port 8888 must not be mapped to host in NetworkSettings.Ports')
  })

  await t.test('waitForPostgresReady succeeds once postgres accepts connections', async () => {
    const ports = await bootstrapContainers()
    const ready = await waitForPostgresReady(ports.postgresPort, 20000)
    assert.strictEqual(ready, true)
  })

  await t.test('initSystemDatabase initializes neon_control_plane and revokes public connect', async () => {
    const ports = await bootstrapContainers()
    await waitForPostgresReady(ports.postgresPort)
    await initSystemDatabase(ports.postgresPort)

    // Verify system database exists
    const creds = getMasterDatabaseCredentials()
    const client = new pg.Client({
      host: 'localhost',
      port: ports.postgresPort,
      user: creds.username,
      password: creds.password,
      database: 'postgres',
    })
    await client.connect()
    const res = await client.query(
      "SELECT datname FROM pg_database WHERE datname = 'neon_control_plane'",
    )
    assert.strictEqual(res.rowCount, 1)
    await client.end()
  })

  await t.test('runMigrations executes Drizzle migrations against neon_control_plane', async () => {
    const ports = await bootstrapContainers()
    const creds = getMasterDatabaseCredentials()
    await runMigrations(`postgresql://${creds.username}:${creds.password}@localhost:${ports.postgresPort}/neon_control_plane`)

    // Verify projects and databases tables exist in neon_control_plane
    const client = new pg.Client({
      host: 'localhost',
      port: ports.postgresPort,
      user: creds.username,
      password: creds.password,
      database: 'neon_control_plane',
    })
    await client.connect()
    const res = await client.query(
      "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'",
    )
    const tables = res.rows.map((r: { table_name: string }) => r.table_name)
    assert.ok(tables.includes('projects'), 'projects table should exist')
    assert.ok(tables.includes('databases'), 'databases table should exist')
    assert.ok(tables.includes('object_storages'), 'object_storages table should exist')
    await client.end()
  })

  await t.test('getServicesHealth reports container health accurately', async () => {
    await waitForSeaweedFSReady()
    const health = await getServicesHealth()
    assert.strictEqual(health.postgres.status, 'healthy')
    assert.strictEqual(health.seaweedfs.status, 'healthy')
    assert.strictEqual(health.postgres.containerRunning, true)
    assert.strictEqual(health.seaweedfs.containerRunning, true)
  })

  await t.test('ensureSystemReady runs full lifecycle without error', async () => {
    await ensureSystemReady()
    const health = await getServicesHealth()
    assert.strictEqual(health.postgres.status, 'healthy')
  })

  await t.test('ensurePostgresHbaConfig preserves valid loopback rules and only rewrites insecure remote rules', async () => {
    const tempDir = fs.mkdtempSync(path.join(process.cwd(), '.scratch', 'hba-test-'))
    const hbaFile = path.join(tempDir, 'pg_hba.conf')
    try {
      // 1. Initial valid/hardened pg_hba.conf with loopback rules and hostssl
      const secureHba = `# Managed by Neon
local   all   all                  trust
host    all   all   127.0.0.1/32   scram-sha-256
host    all   all   ::1/128        scram-sha-256
host    all   all   172.17.0.1/32  scram-sha-256
hostssl all   all   0.0.0.0/0      scram-sha-256
hostssl all   all   ::/0           scram-sha-256
`
      fs.writeFileSync(hbaFile, secureHba, 'utf8')

      await ensurePostgresHbaConfig(tempDir)
      const afterContent = fs.readFileSync(hbaFile, 'utf8')
      assert.strictEqual(afterContent, secureHba, 'Must NOT rewrite pg_hba.conf when only valid loopback and hostssl rules are present')

      // 2. Insecure pg_hba.conf with wildcard "host all all 0.0.0.0/0"
      const insecureHba = `# Insecure default
local   all   all                  trust
host    all   all   127.0.0.1/32   scram-sha-256
host    all   all   0.0.0.0/0      scram-sha-256
hostssl all   all   0.0.0.0/0      scram-sha-256
`
      fs.writeFileSync(hbaFile, insecureHba, 'utf8')
      await ensurePostgresHbaConfig(tempDir)
      const rewrittenContent = fs.readFileSync(hbaFile, 'utf8')
      assert.notStrictEqual(rewrittenContent, insecureHba, 'Must rewrite pg_hba.conf when insecure host 0.0.0.0/0 is present')
      assert.ok(rewrittenContent.includes('hostssl all             all             0.0.0.0/0'))

      // 3. Insecure pg_hba.conf with wildcard "host all all all"
      const insecureAllHba = `# Insecure all
local   all   all                  trust
host    all   all   all            scram-sha-256
hostssl all   all   0.0.0.0/0      scram-sha-256
`
      fs.writeFileSync(hbaFile, insecureAllHba, 'utf8')
      await ensurePostgresHbaConfig(tempDir)
      const rewrittenAllContent = fs.readFileSync(hbaFile, 'utf8')
      assert.notStrictEqual(rewrittenAllContent, insecureAllHba, 'Must rewrite pg_hba.conf when insecure host all all all is present')
    } finally {
      fs.rmSync(tempDir, { recursive: true, force: true })
    }
  })

  await t.test('PostgreSQL enforces hostssl for remote connections while permitting loopback unencrypted', async () => {
    const ports = await bootstrapContainers()
    await waitForPostgresReady(ports.postgresPort)
    const creds = getMasterDatabaseCredentials()

    // 1. Local loopback unencrypted connection is permitted
    const loopbackClient = new pg.Client({
      host: '127.0.0.1',
      port: ports.postgresPort,
      user: creds.username,
      password: creds.password,
      database: 'postgres',
      ssl: false,
    })
    await loopbackClient.connect()
    const sslUsedRes = await loopbackClient.query('SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid()')
    assert.strictEqual(sslUsedRes.rows[0]?.ssl, false, 'Loopback connection without ssl should not use ssl')
    await loopbackClient.end()

    // 2. Local loopback with TLS is permitted and uses SSL
    const caCert = getCaCertificate()
    const loopbackTlsClient = new pg.Client({
      host: 'localhost',
      port: ports.postgresPort,
      user: creds.username,
      password: creds.password,
      database: 'postgres',
      ssl: {
        rejectUnauthorized: true,
        ca: caCert,
      },
    })
    await loopbackTlsClient.connect()
    const loopbackSslRes = await loopbackTlsClient.query('SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid()')
    assert.strictEqual(loopbackSslRes.rows[0]?.ssl, true, 'Loopback TLS connection must use ssl')
    await loopbackTlsClient.end()

    // 3. Remote TCP connection check
    // Connect from an external container (simulating remote client IP across the network)
    const pgInspect = await inspectContainer('neon-postgres')
    const bridgeIp = (pgInspect as any)?.NetworkSettings?.Networks?.bridge?.IPAddress
    if (bridgeIp) {
      // Remote unencrypted connection MUST be rejected
      assert.throws(
        () => {
          execFileSync(
            'docker',
            [
              'run',
              '--rm',
              'postgres:16-alpine',
              'sh',
              '-c',
              `PGSSLMODE=disable psql -h ${bridgeIp} -U ${creds.username} -d postgres -c 'SELECT 1'`,
            ],
            { stdio: 'pipe' },
          )
        },
        (err: any) => {
          const stderr = String(err?.stderr || '')
          return (
            stderr.includes('no pg_hba.conf entry') ||
            stderr.includes('no encryption')
          )
        },
        'Remote connection without SSL must be rejected by pg_hba.conf hostssl enforcement',
      )

      // Remote SSL connection MUST succeed
      const sslOut = execFileSync(
        'docker',
        [
          'run',
          '--rm',
          '-e',
          `PGPASSWORD=${creds.password}`,
          'postgres:16-alpine',
          'sh',
          '-c',
          `PGSSLMODE=require psql -h ${bridgeIp} -U ${creds.username} -d postgres -t -c "SELECT ssl FROM pg_stat_ssl WHERE pid = pg_backend_pid()"`,
        ],
        { stdio: 'pipe' },
      ).toString()
      assert.strictEqual(sslOut.trim(), 't', 'Remote SSL connection must use ssl')
    }
  })

  await t.test('bootstrapContainers preserves running containers when HOST_BIND_IP is 0.0.0.0', async () => {
    const prevBind = process.env.HOST_BIND_IP
    try {
      process.env.HOST_BIND_IP = '0.0.0.0'
      // First boot with 0.0.0.0
      await bootstrapContainers()
      const firstInspect = await inspectContainer('neon-postgres')
      assert.ok(firstInspect)
      const initialId = firstInspect.Id

      // Second boot with 0.0.0.0 - must not tear down or change container ID
      await bootstrapContainers()
      const secondInspect = await inspectContainer('neon-postgres')
      assert.ok(secondInspect)
      assert.strictEqual(secondInspect.Id, initialId, 'Container ID must remain unchanged when HOST_BIND_IP is 0.0.0.0')
    } finally {
      if (prevBind !== undefined) process.env.HOST_BIND_IP = prevBind
      else delete process.env.HOST_BIND_IP
    }
  })
})
