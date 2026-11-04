import { createClient } from '@supabase/supabase-js'
import { configureAuth } from '../../shared/api/transport'

const runtime = (window as unknown as {__SPECTRAPLAN_CONFIG__?: {url: string; key: string}}).__SPECTRAPLAN_CONFIG__
const url = runtime?.url || import.meta.env.VITE_SUPABASE_URL
const key = runtime?.key || import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY
export const signupEnabled = !runtime
export const supabase = url && key ? createClient(url, key) : null

configureAuth(async () => {
  if (!supabase) return null
  const { data, error } = await supabase.auth.getSession()
  if (error) throw new Error('Unable to restore your sign-in session.')
  return data.session?.access_token ?? null
})
