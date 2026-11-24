import test from 'node:test'
import assert from 'node:assert/strict'
import {
  pingDocker,
  listContainers,
  inspectContainer,
  isContainerRunning,
} from '../services/docker'

test('Docker Engine Socket Client', async (t) => {
  await t.test('pingDocker connects to /var/run/docker.sock and returns OK', async () => {
    const isOk = await pingDocker()
    assert.strictEqual(isOk, true)
  })

  await t.test('listContainers returns an array of containers', async () => {
    const containers = await listContainers(true)
    assert.ok(Array.isArray(containers))
  })

  await t.test('inspectContainer returns null for non-existent container', async () => {
    const info = await inspectContainer('non-existent-container-xyz-99999')
    assert.strictEqual(info, null)
  })

  await t.test('isContainerRunning returns false for non-existent container', async () => {
    const running = await isContainerRunning('non-existent-container-xyz-99999')
    assert.strictEqual(running, false)
  })
})
