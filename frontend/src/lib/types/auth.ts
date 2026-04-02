export interface AuthState {
  isAuthenticated: boolean
  token: string | null
  isLoading: boolean
  error: string | null
}

export interface LoginCredentials {
  password: string
}

export interface LdapLoginCredentials {
  user: string
  password: string
}

export type AuthMode = 'password' | 'ldap'

export interface AuthStatusResponse {
  auth_enabled: boolean
  ldap_enabled: boolean
  message: string
}

export interface LdapLoginResponse {
  token: string
  token_type: string
  user: string
  email: string
  name: string
}
