import test from 'node:test'
import assert from 'node:assert/strict'
import crypto from 'node:crypto'
import { getCaCertificate, ensureTlsCertificates } from '../services/bootstrap'

test('Public Root CA Certificate HTTP Route Seam (/api/ca.crt)', async (t) => {
  // Ensure certificates exist before running route tests
  await ensureTlsCertificates()

  await t.test('GET /api/ca.crt serves raw PEM Root CA certificate with proper headers', async () => {
    // Dynamic import of the route module
    const routeModule = await import('../routes/api/ca[.]crt.js')
    const route = routeModule.Route

    assert.ok(route, 'Route must be exported from route module')

    // Find GET handler from route server handlers
    const handlers = (route.options as any)?.server?.handlers
    assert.ok(handlers, 'Route must have server handlers defined')
    assert.strictEqual(typeof handlers.GET, 'function', 'Route must define a GET handler')

    const request = new Request('http://localhost:3000/api/ca.crt', {
      method: 'GET',
    })

    const response = await handlers.GET({ request })
    assert.strictEqual(response.status, 200)

    // Verify headers
    const contentType = response.headers.get('content-type')
    assert.strictEqual(contentType, 'application/x-x509-ca-cert')

    const contentDisposition = response.headers.get('content-disposition')
    assert.strictEqual(contentDisposition, 'inline; filename="ca.crt"')

    // Verify body content
    const pem = await response.text()
    assert.ok(pem.includes('-----BEGIN CERTIFICATE-----'))
    assert.ok(pem.includes('-----END CERTIFICATE-----'))

    // Verify it matches getCaCertificate()
    const expectedCa = getCaCertificate()
    assert.strictEqual(pem.trim(), expectedCa.trim())

    // Verify certificate validity
    const x509 = new crypto.X509Certificate(pem)
    assert.strictEqual(x509.subject, 'CN=Neon Local Root CA')
  })

  await t.test('GET /api/ca.crt lazily provisions certificates if not yet generated', async () => {
    const routeModule = await import('../routes/api/ca[.]crt.js')
    const handlers = (routeModule.Route.options as any)?.server?.handlers
    assert.ok(handlers?.GET)

    const request = new Request('http://localhost:3000/api/ca.crt', {
      method: 'GET',
    })
    const response = await handlers.GET({ request })
    assert.strictEqual(response.status, 200)
    const pem = await response.text()
    assert.ok(pem.includes('-----BEGIN CERTIFICATE-----'))
  })
})
