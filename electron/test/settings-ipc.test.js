const assert = require('node:assert/strict')
const test = require('node:test')
const { registerSettingsIpcHandlers } = require('../main/ipc/settings')

function setup() {
  const handlers = new Map()
  const state = {
    advisorProvider: 'gemini',
    googleApiKey: 'saved-google-key',
    openRouterApiKey: 'saved-router-key',
    customProviderApiKey: 'saved-advisor-custom-key',
    chronicleProviderApiKey: 'saved-chronicle-custom-key',
  }
  let pendingKey = 'browser-key'
  let failSave = false
  registerSettingsIpcHandlers({
    ipcMain: { handle: (channel, handler) => handlers.set(channel, handler) },
    validateSender: (event) => {
      if (event !== 'trusted') throw new Error('Untrusted sender')
    },
    getSettings: () => ({ ...state, googleApiKey: '****...****', openRouterApiKey: '****...****' }),
    getSettingsWithSecrets: async () => ({ ...state }),
    saveSettings: async (values) => {
      if (failSave) throw new Error('Storage unavailable')
      Object.assign(state, values)
    },
    onSettingsSaved: async () => {},
    testAdvisorModel: async (options) => options,
    discoverAdvisorModels: async (options) => options,
    openRouterOAuth: {
      getKey: (id) => {
        if (id !== 'pending-id' || !pendingKey) throw new Error('Expired')
        return pendingKey
      },
      discard: () => {
        pendingKey = null
      },
      connect: async () => ({ ok: true, credentialId: 'pending-id' }),
      cancel: () => {
        pendingKey = null
      },
    },
  })
  return {
    state,
    invoke: (name, values, sender = 'trusted') => handlers.get(name)(sender, values),
    failSave: () => {
      failSave = true
    },
  }
}

test('model checks resolve saved masked keys and respect explicit empty keys', async () => {
  const app = setup()
  for (const channel of ['advisor-provider:list-models', 'advisor-provider:test-model']) {
    assert.equal(
      (await app.invoke(channel, { provider: 'gemini', apiKey: '****...****' })).apiKey,
      'saved-google-key'
    )
    assert.equal((await app.invoke(channel, { provider: 'gemini', apiKey: '' })).apiKey, '')
    assert.equal(
      (await app.invoke(channel, { provider: 'openrouter', credentialId: 'pending-id' })).apiKey,
      'browser-key'
    )
    assert.equal(
      (await app.invoke(channel, { provider: 'openrouter', credentialId: 'bad-id' })).errorCode,
      'PROVIDER_AUTH_FAILED'
    )
    await assert.rejects(app.invoke(channel, {}, 'untrusted'), /Untrusted/)
  }
})

test('Chronicle checks use the Chronicle key and never send a key to a local server', async () => {
  const app = setup()
  const check = payload => app.invoke('advisor-provider:test-model', { target: 'chronicle', apiKey: '****...****', ...payload })
  assert.equal((await check({ provider: 'custom' })).apiKey, 'saved-chronicle-custom-key')
  assert.equal((await check({ provider: 'ollama' })).apiKey, '')
  assert.equal((await check({ provider: 'lm_studio' })).apiKey, '')
  assert.equal((await check({ provider: 'openrouter' })).apiKey, 'saved-router-key')
  assert.equal((await check({ provider: 'gemini' })).apiKey, 'saved-google-key')
  assert.equal((await app.invoke('advisor-provider:test-model', { provider: 'custom', apiKey: '****...****' })).apiKey, 'saved-advisor-custom-key')
})

test('browser credentials are saved only when requested and are not exposed to the renderer', async () => {
  const app = setup()
  await app.invoke('advisor-provider:test-model', {
    provider: 'openrouter',
    credentialId: 'pending-id',
  })
  assert.equal(app.state.openRouterApiKey, 'saved-router-key')
  const result = await app.invoke('save-settings', {
    advisorProvider: 'openrouter',
    openRouterCredentialId: 'pending-id',
    openRouterApiKey: '',
  })
  assert.equal(app.state.openRouterApiKey, 'browser-key')
  assert.equal('openRouterCredentialId' in app.state, false)
  assert.equal(JSON.stringify(result).includes('browser-key'), false)
  assert.equal(
    (
      await app.invoke('advisor-provider:test-model', {
        provider: 'openrouter',
        credentialId: 'pending-id',
      })
    ).errorCode,
    'PROVIDER_AUTH_FAILED'
  )
})

test('failed persistence retains both the saved key and pending authorization for retry', async () => {
  const app = setup()
  app.failSave()
  await assert.rejects(
    app.invoke('save-settings', { openRouterCredentialId: 'pending-id' }),
    /Storage unavailable/
  )
  assert.equal(app.state.openRouterApiKey, 'saved-router-key')
  assert.equal(
    (
      await app.invoke('advisor-provider:test-model', {
        provider: 'openrouter',
        credentialId: 'pending-id',
      })
    ).apiKey,
    'browser-key'
  )
})
