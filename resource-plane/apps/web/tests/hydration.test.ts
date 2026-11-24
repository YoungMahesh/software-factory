import test from 'node:test'
import assert from 'node:assert/strict'
import React from 'react'
import { renderToString } from 'react-dom/server'
import { useHydrated } from '../lib/useHydrated'
import { HydrationProgressBar } from '../components/HydrationProgressBar'
import { Devtools } from '../components/Devtools'
import { HydratedButton } from '../components/HydratedButton'

test('Hydration Hook Seam', async (t) => {
  await t.test('useHydrated returns false during server rendering', () => {
    function TestComponent() {
      const isHydrated = useHydrated()
      return React.createElement('div', { 'data-hydrated': String(isHydrated) }, isHydrated ? 'hydrated' : 'unhydrated')
    }

    const html = renderToString(React.createElement(TestComponent))
    assert.ok(html.includes('data-hydrated="false"'))
    assert.ok(html.includes('unhydrated'))
  })

  await t.test('useHydrated contract exposes hydration boolean safely', () => {
    assert.strictEqual(typeof useHydrated, 'function')
  })
})

test('Hydration Loading Bar & Devtools Deferral Seam', async (t) => {
  await t.test('HydrationProgressBar renders neon-green 2px loading bar when unhydrated', () => {
    const html = renderToString(React.createElement(HydrationProgressBar as any, { isHydrated: false }))
    assert.ok(html.includes('data-testid="hydration-progress-bar"'))
    assert.ok(html.includes('opacity-100'))
    assert.ok(html.includes('#00e599') || html.includes('bg-[#00e599]'))
    assert.ok(html.includes('h-[2px]') || html.includes('h-0.5'))
    assert.ok(html.includes('aria-hidden="false"'))
  })

  await t.test('HydrationProgressBar fades out and marks aria-hidden when hydrated', () => {
    const html = renderToString(React.createElement(HydrationProgressBar as any, { isHydrated: true }))
    assert.ok(html.includes('data-testid="hydration-progress-bar"'))
    assert.ok(html.includes('opacity-0'))
    assert.ok(html.includes('aria-hidden="true"'))
  })

  await t.test('Devtools renders null in production environment', () => {
    const prevEnv = process.env.NODE_ENV
    try {
      (process.env as any).NODE_ENV = 'production'
      const html = renderToString(React.createElement(Devtools))
      assert.strictEqual(html, '')
    } finally {
      (process.env as any).NODE_ENV = prevEnv
    }
  })
})

test('Dashboard Control Affordance Seam', async (t) => {
  await t.test('HydratedButton is disabled with cursor-wait and tooltip during unhydrated SSR state', () => {
    const html = renderToString(React.createElement(HydratedButton, {
      className: 'bg-[#00e599]',
      children: '+ New Project',
    }))
    assert.ok(html.includes('disabled=""') || html.includes('disabled'), 'Buttons must have disabled attribute')
    assert.ok(html.includes('title="Connecting to Control Plane..."'), 'Must have Connecting tooltip')
    assert.ok(html.includes('cursor-wait'), 'Must have cursor-wait class')
    assert.ok(html.includes('+ New Project'))
  })

  await t.test('HydratedButton is disabled with cursor-wait and tooltip when isHydrated is explicitly false', () => {
    const html = renderToString(React.createElement(HydratedButton, {
      isHydrated: false,
      children: 'New Database',
    }))
    assert.ok(html.includes('disabled=""') || html.includes('disabled'))
    assert.ok(html.includes('title="Connecting to Control Plane..."'))
    assert.ok(html.includes('cursor-wait'))
  })

  await t.test('HydratedButton becomes interactive and cursor-pointer when hydrated', () => {
    const html = renderToString(React.createElement(HydratedButton, {
      isHydrated: true,
      children: '+ New Project',
    }))
    assert.ok(!html.includes('title="Connecting to Control Plane..."'))
    assert.ok(!html.includes('cursor-wait'))
    assert.ok(html.includes('cursor-pointer'))
    assert.ok(!html.includes('disabled'))
  })

  await t.test('HydratedButton preserves custom title and original disabled state when hydrated', () => {
    const html = renderToString(React.createElement(HydratedButton, {
      isHydrated: true,
      disabled: true,
      title: 'Action Unavailable',
      children: 'Disabled Action',
    }))
    assert.ok(html.includes('disabled=""') || html.includes('disabled'))
    assert.ok(html.includes('title="Action Unavailable"'))
  })

  await t.test('HydratedButton supports custom connectingTitle when unhydrated', () => {
    const html = renderToString(React.createElement(HydratedButton, {
      isHydrated: false,
      connectingTitle: 'Connecting to Database Cluster...',
      children: 'Execute Query',
    }))
    assert.ok(html.includes('title="Connecting to Database Cluster..."'))
    assert.ok(html.includes('cursor-wait'))
  })
})

test('Code-Split Tab Panels Seam', async (t) => {
  const scratchpadMod: any = await import('../components/SqlScratchpadPanel.js').catch(() => null)
  const browserMod: any = await import('../components/ObjectBrowserPanel.js').catch(() => null)

  await t.test('SqlScratchpadPanel is extracted into an isolated component module', () => {
    assert.ok(scratchpadMod, 'SqlScratchpadPanel module must exist')
    assert.strictEqual(typeof (scratchpadMod.SqlScratchpadPanel ?? scratchpadMod.default), 'function')
  })

  await t.test('ObjectBrowserPanel is extracted into an isolated component module', () => {
    assert.ok(browserMod, 'ObjectBrowserPanel module must exist')
    assert.strictEqual(typeof (browserMod.ObjectBrowserPanel ?? browserMod.default), 'function')
  })

  await t.test('SqlScratchpadPanel buttons reflect hydration affordance state', () => {
    assert.ok(scratchpadMod)
    const Component = scratchpadMod.SqlScratchpadPanel ?? scratchpadMod.default
    const unhydratedHtml = renderToString(React.createElement(Component, {
      databases: [{ id: 'db_1', name: 'demo_db', username: 'demo_user', host: 'localhost', port: 5432, connectionString: '', createdAt: new Date() } as any],
      onProvisionDatabase: () => {},
      isHydrated: false,
    }))
    assert.ok(unhydratedHtml.includes('title="Connecting to Control Plane..."'))
    assert.ok(unhydratedHtml.includes('cursor-wait'))

    const hydratedHtml = renderToString(React.createElement(Component, {
      databases: [{ id: 'db_1', name: 'demo_db', username: 'demo_user', host: 'localhost', port: 5432, connectionString: '', createdAt: new Date() } as any],
      onProvisionDatabase: () => {},
      isHydrated: true,
    }))
    assert.ok(!hydratedHtml.includes('title="Connecting to Control Plane..."'))
    assert.ok(!hydratedHtml.includes('cursor-wait'))
  })

  await t.test('ObjectBrowserPanel buttons reflect hydration affordance state', () => {
    assert.ok(browserMod)
    const Component = browserMod.ObjectBrowserPanel ?? browserMod.default
    const unhydratedHtml = renderToString(React.createElement(Component, {
      storages: [{ id: 'stor_1', bucketName: 'demo-bucket', region: 'us-east-1', endpoint: 'http://localhost', accessKeyId: 'key', secretAccessKey: 'sec', createdAt: new Date() } as any],
      onProvisionStorage: () => {},
      isHydrated: false,
    }))
    assert.ok(unhydratedHtml.includes('title="Connecting to Control Plane..."'))
    assert.ok(unhydratedHtml.includes('cursor-wait'))

    const hydratedHtml = renderToString(React.createElement(Component, {
      storages: [{ id: 'stor_1', bucketName: 'demo-bucket', region: 'us-east-1', endpoint: 'http://localhost', accessKeyId: 'key', secretAccessKey: 'sec', createdAt: new Date() } as any],
      onProvisionStorage: () => {},
      isHydrated: true,
    }))
    assert.ok(!hydratedHtml.includes('title="Connecting to Control Plane..."'))
    assert.ok(!hydratedHtml.includes('cursor-wait'))
  })
})
