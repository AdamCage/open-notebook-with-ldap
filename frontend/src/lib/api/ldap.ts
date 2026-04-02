import { getApiUrl } from '@/lib/config'
import type { LdapLoginResponse } from '@/lib/types/auth'
import apiClient from './client'

export async function ldapSignIn(
  user: string,
  password: string
): Promise<LdapLoginResponse> {
  const apiUrl = await getApiUrl()
  const response = await fetch(`${apiUrl}/api/auth/ldap`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user, password }),
  })

  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    throw new Error(body.detail || `LDAP authentication failed (${response.status})`)
  }

  return response.json()
}

export async function getLdapConfig(): Promise<Record<string, unknown>> {
  const response = await apiClient.get('/auth/ldap/config')
  return response.data
}

export async function updateLdapConfig(
  config: Record<string, unknown>
): Promise<Record<string, unknown>> {
  const response = await apiClient.post('/auth/ldap/config', config)
  return response.data
}
