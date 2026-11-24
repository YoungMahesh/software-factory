import test from 'node:test'
import assert from 'node:assert/strict'
import React from 'react'
import { renderToString } from 'react-dom/server'
import { CaCertificateSection } from '../routes/projects/$projectId'
import fs from 'node:fs'
import path from 'node:path'

test('Dashboard TLS UI Affordances Seam', async (t) => {
  await t.test('CaCertificateSection renders Download ca.crt link pointing to /api/ca.crt', () => {
    const html = renderToString(React.createElement(CaCertificateSection, { copied: false }))
    assert.ok(html.includes('href="/api/ca.crt"'), 'Link must point to /api/ca.crt')
    assert.ok(html.includes('download="ca.crt"'), 'Link must have download attribute for ca.crt')
    assert.ok(html.includes('Download ca.crt'), 'Must display Download ca.crt text')
  })

  await t.test('CaCertificateSection renders Copy PEM button and updates state when copied', () => {
    const uncopiedHtml = renderToString(React.createElement(CaCertificateSection, { copied: false }))
    assert.ok(uncopiedHtml.includes('Copy PEM'))

    const copiedHtml = renderToString(React.createElement(CaCertificateSection, { copied: true }))
    assert.ok(copiedHtml.includes('Copied!'))
  })

  await t.test('CaCertificateSection copy button is gated on hydration (ADR 0016)', () => {
    // Unhydrated (SSR default): disabled with cursor-wait
    const unhydratedHtml = renderToString(React.createElement(CaCertificateSection, { copied: false }))
    assert.ok(unhydratedHtml.includes('disabled=""'), 'Copy button must be disabled in unhydrated state')
    assert.ok(unhydratedHtml.includes('cursor-wait'), 'Copy button must show cursor-wait in unhydrated state')

    // Explicitly unhydrated: disabled with cursor-wait
    const explicitUnhydratedHtml = renderToString(React.createElement(CaCertificateSection, { copied: false, isHydrated: false }))
    assert.ok(explicitUnhydratedHtml.includes('disabled=""'))
    assert.ok(explicitUnhydratedHtml.includes('cursor-wait'))

    // Hydrated: interactive with cursor-pointer
    const hydratedHtml = renderToString(React.createElement(CaCertificateSection, { copied: false, isHydrated: true }))
    assert.ok(!hydratedHtml.includes('disabled=""'), 'Copy button must not be disabled when hydrated')
    assert.ok(hydratedHtml.includes('cursor-pointer'), 'Copy button must show cursor-pointer when hydrated')
  })

  await t.test('src/routes/projects/$projectId.tsx embeds CA Certificate section in Credentials Modal', () => {
    const filePath = path.resolve(process.cwd(), 'src/routes/projects/$projectId.tsx')
    const fileContent = fs.readFileSync(filePath, 'utf8')

    // Find credentials modal section
    const credsModalIdx = fileContent.indexOf('credsModalDb &&')
    assert.ok(credsModalIdx > 0, 'Credentials modal must exist')

    const credsModalCode = fileContent.slice(credsModalIdx, fileContent.indexOf('resetModalDb &&'))
    assert.ok(
      credsModalCode.includes('CaCertificateSection') || credsModalCode.includes('Download ca.crt'),
      'Credentials modal must include CA certificate download/copy affordances',
    )
  })

  await t.test('src/routes/projects/$projectId.tsx embeds CA Certificate section in Reset Password Success view', () => {
    const filePath = path.resolve(process.cwd(), 'src/routes/projects/$projectId.tsx')
    const fileContent = fs.readFileSync(filePath, 'utf8')

    const resetSuccessIdx = fileContent.indexOf('resetSuccessCreds ?')
    assert.ok(resetSuccessIdx > 0, 'Reset success section must exist')

    const resetSuccessCode = fileContent.slice(resetSuccessIdx, fileContent.indexOf('deleteModalDb &&'))
    assert.ok(
      resetSuccessCode.includes('CaCertificateSection') || resetSuccessCode.includes('Download ca.crt'),
      'Reset success section must include CA certificate affordances',
    )
    assert.ok(resetSuccessCode.includes('connectionString'), 'Reset success must display connection string')
  })
})
