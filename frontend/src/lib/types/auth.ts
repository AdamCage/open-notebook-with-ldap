export interface LoginCredentials {
  password: string
}

export interface LdapLoginCredentials {
  user: string
  password: string
}

export type AuthMode = 'none' | 'password' | 'local' | 'ldap'
export type UserRole = 'super_admin' | 'admin' | 'user'
export type UserStatus = 'pending' | 'active' | 'deactivated'

export interface UserProfile {
  id: string
  username: string
  email: string
  display_name: string | null
  role: UserRole
  status: UserStatus
  auth_provider: string
  last_login: string | null
  created: string | null
  updated: string | null
}

export interface AuthStatusResponse {
  auth_enabled: boolean
  auth_mode: AuthMode
  ldap_enabled: boolean
  registration_enabled: boolean
  message: string
}

export interface LdapLoginResponse {
  token: string
  token_type: string
  user: UserProfile
}

export interface LocalLoginResponse {
  token: string
  token_type: string
  user: UserProfile
}

export interface RegisterResponse {
  message: string
  username: string
  status: string
}
