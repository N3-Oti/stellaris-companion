import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  ADVISOR_PROVIDER_VALUES,
  type AdvisorProvider,
  type ChronicleProvider,
  type Settings,
} from '../../hooks/useSettings'
import { useChatGPT } from '../../hooks/useChatGPT'
import { HUDButton } from '../hud/HUDButton'
import { HUDInput } from '../hud/HUDInput'
import { HUDSelect } from '../hud/HUDForm'
import { HUDLabel, HUDMicro } from '../hud/HUDText'

type ChronicleValues = Pick<
  Settings,
  | 'chronicleProvider'
  | 'chronicleModel'
  | 'chronicleBaseUrl'
  | 'googleApiKey'
  | 'openRouterApiKey'
  | 'chronicleProviderApiKey'
>
interface CheckResult {
  ok: boolean
  errorCode?: string
  error?: string
  chronicleReady?: boolean
}
interface Props {
  initialSettings?: Partial<Settings> | null
  onSave: (values: Partial<ChronicleValues>) => Promise<boolean>
  onSaved?: () => void
}

const names: Record<AdvisorProvider, string> = {
  chatgpt: 'ChatGPT',
  gemini: 'Gemini',
  openrouter: 'OpenRouter',
  ollama: 'Ollama',
  lm_studio: 'LM Studio',
  custom: 'Custom',
}
const errorKeys: Record<string, string> = {
  PROVIDER_AUTH_FAILED: 'providerAuthFailed',
  PROVIDER_MODEL_NOT_FOUND: 'providerModelNotFound',
  PROVIDER_UNAVAILABLE: 'providerUnavailable',
  PROVIDER_TIMEOUT: 'providerTimeout',
  PROVIDER_RATE_LIMITED: 'providerRateLimited',
  PROVIDER_BILLING_FAILED: 'providerBillingFailed',
  PROVIDER_CONTEXT_LIMIT: 'providerContextLimit',
  PROVIDER_EMPTY_RESPONSE: 'providerEmptyResponse',
  PROVIDER_REQUEST_FAILED: 'providerRequestFailed',
}
// Mounted ChatGPT pickers re-read whether Chronicle has its own model.
export const CHRONICLE_PROVIDER_SAVED_EVENT = 'chronicle-provider-saved'

const keyFields = {
  gemini: 'googleApiKey',
  openrouter: 'openRouterApiKey',
  custom: 'chronicleProviderApiKey',
} as const

function initialValues(settings?: Partial<Settings> | null): ChronicleValues {
  return {
    chronicleProvider: settings?.chronicleProvider || '',
    chronicleModel: settings?.chronicleModel || '',
    chronicleBaseUrl: settings?.chronicleBaseUrl || '',
    googleApiKey: settings?.googleApiKey || '',
    openRouterApiKey: settings?.openRouterApiKey || '',
    chronicleProviderApiKey: settings?.chronicleProviderApiKey || '',
  }
}

// Chronicle can run on its own provider, e.g. a lighter or local model, while
// the Advisor keeps its own. Leaving it empty preserves the shared setup.
export function ChronicleProviderForm({ initialSettings, onSave, onSaved }: Props) {
  const { t } = useTranslation()
  const { status: chatgpt, accept } = useChatGPT()
  const [values, setValues] = useState(() => initialValues(initialSettings))
  const [models, setModels] = useState<Array<{ id: string; name: string }>>([])
  const [busy, setBusy] = useState<'models' | 'check' | 'connect' | null>(null)
  const [result, setResult] = useState<CheckResult | null>(null)
  const [saved, setSaved] = useState(false)
  // Open when a separate provider is saved; later saves must not collapse it.
  const [initiallyOpen] = useState(() => Boolean(initialSettings?.chronicleProvider))
  const request = useRef(0)
  const mounted = useRef(true)
  const provider = values.chronicleProvider
  const isLocal = provider === 'ollama' || provider === 'lm_studio'
  const keyField = provider === 'gemini' || provider === 'openrouter' || provider === 'custom' ? keyFields[provider] : null
  const apiKey = keyField ? values[keyField] : ''
  const api = window.electronAPI?.advisorProviders

  useEffect(() => {
    mounted.current = true
    return () => {
      mounted.current = false
      request.current += 1
    }
  }, [])

  const change = (next: Partial<ChronicleValues>) => {
    request.current += 1
    setResult(null)
    setSaved(false)
    if (next.chronicleProvider !== undefined || next.chronicleBaseUrl !== undefined || next.openRouterApiKey !== undefined || next.chronicleProviderApiKey !== undefined)
      setModels([])
    if (next.chronicleProvider !== undefined && next.chronicleProvider !== provider) {
      next.chronicleModel = ''
      next.chronicleBaseUrl = ''
    }
    setValues(current => ({ ...current, ...next }))
  }

  const config = () => ({
    provider,
    baseUrl: values.chronicleBaseUrl,
    model: values.chronicleModel,
    apiKey: apiKey || undefined,
    target: 'chronicle' as const,
  })

  const findModels = async () => {
    if (!api || !provider) return
    const id = ++request.current
    setBusy('models')
    setResult(null)
    try {
      const found = await api.listModels(config())
      if (!mounted.current || id !== request.current) return
      if (!found.ok) {
        setResult(found)
        return
      }
      setModels(found.models || [])
      if (found.models?.length === 1 && !values.chronicleModel)
        setValues(current => ({ ...current, chronicleModel: found.models![0].id }))
    } catch {
      if (mounted.current && id === request.current) setResult({ ok: false, errorCode: 'PROVIDER_UNAVAILABLE' })
    } finally {
      if (mounted.current && id === request.current) setBusy(null)
    }
  }

  const connectChatGPT = async () => {
    const chatgptApi = window.electronAPI?.chatgpt
    if (!chatgptApi) return
    setBusy('connect')
    setResult(null)
    try {
      const connected = accept(await chatgptApi.connect({ target: 'chronicle' }))
      if (!connected.ok) setResult({ ok: false, errorCode: connected.code || 'CHATGPT_UNAVAILABLE' })
    } catch {
      setResult({ ok: false, errorCode: 'CHATGPT_UNAVAILABLE' })
    } finally {
      if (mounted.current) setBusy(null)
    }
  }

  const checkAndSave = async () => {
    if (!api) return
    if (provider && provider !== 'gemini' && provider !== 'chatgpt' && !values.chronicleModel.trim()) {
      await findModels()
      return
    }
    const id = ++request.current
    setBusy('check')
    setResult(null)
    setSaved(false)
    try {
      // ChatGPT is verified when it connects; other providers get the same
      // sample check as the Advisor, and must support structured output.
      if (provider && provider !== 'chatgpt') {
        const checked = await api.testModel(config())
        if (!mounted.current || id !== request.current) return
        if (!checked.ok || checked.chronicleReady === false) {
          setResult(checked.ok ? { ok: false, errorCode: 'CHRONICLE_INCOMPATIBLE' } : checked)
          return
        }
      }
      const next: Partial<ChronicleValues> = {
        chronicleProvider: provider,
        chronicleModel: provider && provider !== 'gemini' ? values.chronicleModel.trim() : '',
        chronicleBaseUrl: provider === 'custom' || isLocal ? values.chronicleBaseUrl.trim() : '',
      }
      if (keyField && !apiKey.includes('...')) next[keyField] = apiKey.trim()
      const ok = await onSave(next)
      if (!mounted.current || id !== request.current) return
      if (!ok) {
        setResult({ ok: false, errorCode: 'SAVE_FAILED' })
        return
      }
      setSaved(true)
      window.dispatchEvent(new Event(CHRONICLE_PROVIDER_SAVED_EVENT))
      onSaved?.()
    } catch {
      if (mounted.current && id === request.current) setResult({ ok: false, errorCode: 'SAVE_FAILED' })
    } finally {
      if (mounted.current && id === request.current) setBusy(null)
    }
  }

  const providerOptions = [
    { value: '', label: t('settings.chronicleModel.sameAsAdvisor') },
    ...ADVISOR_PROVIDER_VALUES.map(value => ({ value, label: names[value] })),
  ]
  const modelOptions = [
    { value: '', label: t('settings.advisor.selectModel') },
    ...(provider === 'chatgpt' ? chatgpt?.models || [] : models).map(model => ({ value: model.id, label: model.name })),
  ]
  if (values.chronicleModel && !modelOptions.some(option => option.value === values.chronicleModel))
    modelOptions.push({ value: values.chronicleModel, label: values.chronicleModel })
  if (provider === 'chatgpt') modelOptions[0] = { value: '', label: t('settings.chronicleModel.chatgptAccountModel') }
  const requiresKey = provider === 'gemini' || provider === 'openrouter'
  const missingRequired =
    (requiresKey && !apiKey.trim()) ||
    (provider === 'custom' && !values.chronicleBaseUrl.trim()) ||
    (provider === 'chatgpt' && !chatgpt?.ready)
  const errorMessage = () => {
    const code = result?.errorCode || ''
    if (code === 'SAVE_FAILED') return t('settings.aiSetup.saveFailed')
    if (code === 'CHRONICLE_INCOMPATIBLE') return t('settings.advisor.modelTestError')
    if (code.startsWith('CHATGPT_')) return t(`chatgpt.errors.${code}`, { defaultValue: t('chatgpt.errors.CHATGPT_UNAVAILABLE') })
    return t(`chat.errors.${errorKeys[code] || 'providerRequestFailed'}`, { provider: provider ? names[provider] : '' })
  }
  const savedProvider = initialSettings?.chronicleProvider || ''
  // Distinct accessible names from the Advisor fields shown on the same page.
  const fieldName = (label: string) => `${t('app.tabs.chronicle')} ${label}`

  return (
    <details className="border-t border-white/10 pt-4" open={initiallyOpen || undefined} data-testid="chronicle-provider-form">
      <summary className="flex cursor-pointer items-center justify-between gap-3">
        <HUDLabel>{t('settings.chronicleModel.label')}</HUDLabel>
        <span className="text-xs text-text-secondary">
          {savedProvider ? names[savedProvider] : t('settings.chronicleModel.sameAsAdvisor')}
        </span>
      </summary>
      <div className="mt-3 space-y-3">
        <p className="text-xs leading-relaxed text-text-secondary">{t('settings.chronicleModel.help')}</p>
        <fieldset disabled={Boolean(busy)} className="min-w-0 space-y-3 disabled:opacity-70">
          <HUDSelect
            label={t('settings.chronicleModel.providerLabel')}
            aria-label={t('settings.chronicleModel.providerLabel')}
            value={provider}
            options={providerOptions}
            onChange={event => change({ chronicleProvider: event.target.value as ChronicleProvider })}
          />
          {provider === 'chatgpt' && !chatgpt?.ready && (
            <HUDButton type="button" variant="secondary" onClick={() => void connectChatGPT()}>
              {t('chatgpt.continue')}
            </HUDButton>
          )}
          {(provider === 'custom' || isLocal) && (
            <HUDInput
              label={t('settings.advisor.baseUrlLabel')}
              aria-label={fieldName(t('settings.advisor.baseUrlLabel'))}
              value={values.chronicleBaseUrl}
              onChange={event => change({ chronicleBaseUrl: event.target.value })}
              placeholder={provider === 'ollama' ? 'http://127.0.0.1:11434/v1' : provider === 'lm_studio' ? 'http://127.0.0.1:1234/v1' : 'https://provider.example/v1'}
            />
          )}
          {keyField && (
            <>
              <HUDInput
                label={t(provider === 'custom' ? 'settings.advisor.optionalApiKeyLabel' : provider === 'gemini' ? 'onboarding.ai.geminiKey' : 'settings.advisor.apiKeyLabel')}
                aria-label={fieldName(t(provider === 'custom' ? 'settings.advisor.optionalApiKeyLabel' : provider === 'gemini' ? 'onboarding.ai.geminiKey' : 'settings.advisor.apiKeyLabel'))}
                type="password"
                autoComplete="off"
                value={apiKey}
                onChange={event => change({ [keyField]: event.target.value })}
                placeholder={provider === 'custom' ? t('settings.advisor.optional') : undefined}
              />
              {provider !== 'custom' && (
                <HUDMicro className="block normal-case leading-relaxed">
                  {t('settings.chronicleModel.sharedKey', { provider: names[provider as AdvisorProvider] })}
                </HUDMicro>
              )}
            </>
          )}
          {provider === 'gemini' && <p className="text-xs text-text-secondary">{t('settings.chronicleModel.geminiAutomatic')}</p>}
          {provider && provider !== 'gemini' && (provider !== 'chatgpt' || chatgpt?.ready) && (
            <div className="space-y-3">
              <HUDSelect
                label={t('settings.advisor.modelLabel')}
                aria-label={t('settings.chronicleModel.modelLabel')}
                value={values.chronicleModel}
                options={modelOptions}
                onChange={event => change({ chronicleModel: event.target.value })}
              />
              {provider !== 'chatgpt' && (
                <>
                  <HUDInput
                    label={t('settings.aiSetup.modelId')}
                    aria-label={fieldName(t('settings.aiSetup.modelId'))}
                    value={values.chronicleModel}
                    onChange={event => change({ chronicleModel: event.target.value })}
                  />
                  <HUDButton type="button" variant="secondary" disabled={missingRequired} onClick={() => void findModels()}>
                    {t('settings.aiSetup.refreshModels')}
                  </HUDButton>
                </>
              )}
            </div>
          )}
          {isLocal && !values.chronicleModel.includes(':cloud') && (
            <p className="text-xs leading-relaxed text-text-secondary">{t('settings.chronicleModel.localPrivacy')}</p>
          )}
          {(provider === 'openrouter' || provider === 'custom' || provider === 'gemini' || values.chronicleModel.includes(':cloud')) && (
            <p className="text-xs leading-relaxed text-text-secondary">{t('settings.chronicleModel.remoteNotice')}</p>
          )}
        </fieldset>
        <HUDButton
          type="button"
          variant="primary"
          disabled={Boolean(busy) || missingRequired}
          onClick={() => void checkAndSave()}
        >
          {t(busy ? 'settings.aiSetup.checking' : provider ? 'settings.aiSetup.checkSave' : 'settings.chronicleModel.useAdvisor')}
        </HUDButton>
        {saved && <p role="status" className="text-sm text-accent-green">{t('settings.chronicleModel.saved')}</p>}
        {result && !result.ok && (
          <div role="alert" className="space-y-2 text-sm text-accent-yellow">
            <p>{errorMessage()}</p>
            {result.error && (
              <details>
                <summary className="cursor-pointer">{t('settings.aiSetup.details')}</summary>
                <p className="mt-1 break-words font-mono text-xs">{result.error}</p>
              </details>
            )}
          </div>
        )}
      </div>
    </details>
  )
}
