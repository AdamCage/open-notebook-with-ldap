import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { getApiUrl } from '@/lib/config'
import { ldapSignIn } from '@/lib/api/ldap'
import type { AuthMode, UserProfile } from '@/lib/types/auth'

interface AuthState {
  isAuthenticated: boolean
  token: string | null
  isLoading: boolean
  error: string | null
  lastAuthCheck: number | null
  isCheckingAuth: boolean
  hasHydrated: boolean
  authRequired: boolean | null
  ldapEnabled: boolean | null
  authMode: AuthMode
  registrationEnabled: boolean
  user: UserProfile | null
  isAdmin: boolean
  setHasHydrated: (state: boolean) => void
  checkAuthRequired: () => Promise<boolean>
  login: (password: string) => Promise<boolean>
  localLogin: (username: string, password: string) => Promise<boolean>
  ldapLogin: (user: string, password: string) => Promise<boolean>
  register: (username: string, email: string, password: string, displayName?: string) => Promise<{ success: boolean; pending?: boolean }>
  fetchProfile: () => Promise<void>
  logout: () => void
  checkAuth: () => Promise<boolean>
}

// Security note: tokens are stored in localStorage via zustand/persist.
// This is a standard SPA pattern but exposes tokens to XSS attacks.
// Mitigate with a strict Content-Security-Policy and HttpOnly cookies
// if a reverse-proxy is available in production.
export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      isAuthenticated: false,
      token: null,
      isLoading: false,
      error: null,
      lastAuthCheck: null,
      isCheckingAuth: false,
      hasHydrated: false,
      authRequired: null,
      ldapEnabled: null,
      authMode: 'none' as AuthMode,
      registrationEnabled: false,
      user: null,
      isAdmin: false,

      setHasHydrated: (state: boolean) => {
        set({ hasHydrated: state })
      },

      checkAuthRequired: async () => {
        try {
          const apiUrl = await getApiUrl()
          const response = await fetch(`${apiUrl}/api/auth/status`, {
            cache: 'no-store',
          })

          if (!response.ok) {
            throw new Error(`Auth status check failed: ${response.status}`)
          }

          const data = await response.json()
          const required = data.auth_enabled || false
          const ldapEnabled = data.ldap_enabled || false
          const authMode: AuthMode = data.auth_mode || 'none'
          const registrationEnabled = data.registration_enabled || false
          set({ authRequired: required, ldapEnabled, authMode, registrationEnabled })

          if (!required) {
            // Intentionally grant admin for backward compat: when auth is
            // disabled everyone should see all UI (models, settings, etc.)
            set({ isAuthenticated: true, token: 'not-required', isAdmin: true })
          }

          return required
        } catch (error) {
          console.error('Failed to check auth status:', error)

          if (error instanceof TypeError && error.message.includes('Failed to fetch')) {
            set({
              error: 'Unable to connect to server. Please check if the API is running.',
              authRequired: null
            })
          } else {
            set({ authRequired: true })
          }

          throw error
        }
      },

      login: async (password: string) => {
        set({ isLoading: true, error: null })
        try {
          const apiUrl = await getApiUrl()

          const response = await fetch(`${apiUrl}/api/notebooks`, {
            method: 'GET',
            headers: {
              'Authorization': `Bearer ${password}`,
              'Content-Type': 'application/json'
            }
          })
          
          if (response.ok) {
            set({ 
              isAuthenticated: true, 
              token: password, 
              isLoading: false,
              lastAuthCheck: Date.now(),
              error: null,
              isAdmin: true,
            })
            return true
          } else {
            let errorMessage = 'Authentication failed'
            if (response.status === 401) {
              errorMessage = 'Invalid password. Please try again.'
            } else if (response.status === 403) {
              errorMessage = 'Access denied. Please check your credentials.'
            } else if (response.status >= 500) {
              errorMessage = 'Server error. Please try again later.'
            } else {
              errorMessage = `Authentication failed (${response.status})`
            }
            
            set({ 
              error: errorMessage,
              isLoading: false,
              isAuthenticated: false,
              token: null
            })
            return false
          }
        } catch (error) {
          console.error('Network error during auth:', error)
          let errorMessage = 'Authentication failed'
          
          if (error instanceof TypeError && error.message.includes('Failed to fetch')) {
            errorMessage = 'Unable to connect to server. Please check if the API is running.'
          } else if (error instanceof Error) {
            errorMessage = `Network error: ${error.message}`
          } else {
            errorMessage = 'An unexpected error occurred during authentication'
          }
          
          set({ 
            error: errorMessage,
            isLoading: false,
            isAuthenticated: false,
            token: null
          })
          return false
        }
      },

      localLogin: async (username: string, password: string) => {
        set({ isLoading: true, error: null })
        try {
          const apiUrl = await getApiUrl()
          const response = await fetch(`${apiUrl}/api/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, password }),
          })

          if (!response.ok) {
            const body = await response.json().catch(() => ({}))
            const detail = body.detail || 'Authentication failed'

            if (response.status === 403 && detail.includes('awaiting')) {
              set({ error: detail, isLoading: false })
              return false
            }

            set({ error: detail, isLoading: false, isAuthenticated: false, token: null })
            return false
          }

          const data = await response.json()
          const userProfile: UserProfile = data.user
          const role = userProfile.role || 'user'
          const isAdmin = role === 'admin' || role === 'super_admin'

          set({
            isAuthenticated: true,
            token: data.token,
            isLoading: false,
            lastAuthCheck: Date.now(),
            error: null,
            user: userProfile,
            isAdmin,
          })
          return true
        } catch (error) {
          console.error('Local login error:', error)
          let errorMessage = 'Authentication failed'
          if (error instanceof TypeError && error.message.includes('Failed to fetch')) {
            errorMessage = 'Unable to connect to server. Please check if the API is running.'
          }
          set({ error: errorMessage, isLoading: false, isAuthenticated: false, token: null })
          return false
        }
      },

      ldapLogin: async (user: string, password: string) => {
        set({ isLoading: true, error: null })
        try {
          const data = await ldapSignIn(user, password)
          const userProfile: UserProfile = data.user
          const role = userProfile?.role || 'user'
          const isAdmin = role === 'admin' || role === 'super_admin'

          set({
            isAuthenticated: true,
            token: data.token,
            isLoading: false,
            lastAuthCheck: Date.now(),
            error: null,
            user: userProfile,
            isAdmin,
          })
          return true
        } catch (error) {
          console.error('LDAP auth error:', error)
          let errorMessage = 'ldapAuthFailed'

          if (error instanceof TypeError && error.message.includes('Failed to fetch')) {
            errorMessage = 'Unable to connect to server. Please check if the API is running.'
          }

          set({
            error: errorMessage,
            isLoading: false,
            isAuthenticated: false,
            token: null,
          })
          return false
        }
      },

      register: async (username: string, email: string, password: string, displayName?: string) => {
        set({ isLoading: true, error: null })
        try {
          const apiUrl = await getApiUrl()
          const response = await fetch(`${apiUrl}/api/auth/register`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ username, email, password, display_name: displayName }),
          })

          if (!response.ok) {
            const body = await response.json().catch(() => ({}))
            set({ error: body.detail || 'Registration failed', isLoading: false })
            return { success: false }
          }

          set({ isLoading: false, error: null })
          return { success: true, pending: true }
        } catch (error) {
          console.error('Registration error:', error)
          let errorMessage = 'Registration failed'
          if (error instanceof TypeError && error.message.includes('Failed to fetch')) {
            errorMessage = 'Unable to connect to server.'
          }
          set({ error: errorMessage, isLoading: false })
          return { success: false }
        }
      },

      fetchProfile: async () => {
        const { token, authMode } = get()
        if (!token || (authMode !== 'local' && authMode !== 'ldap')) return

        try {
          const apiUrl = await getApiUrl()
          const response = await fetch(`${apiUrl}/api/auth/me`, {
            headers: { 'Authorization': `Bearer ${token}` },
          })
          if (response.ok) {
            const profile: UserProfile = await response.json()
            const isAdmin = profile.role === 'admin' || profile.role === 'super_admin'
            set({ user: profile, isAdmin })
          }
        } catch (error) {
          console.error('Failed to fetch profile:', error)
        }
      },
      
      logout: () => {
        set({ 
          isAuthenticated: false, 
          token: null, 
          error: null,
          user: null,
          isAdmin: false,
        })
      },
      
      checkAuth: async () => {
        const state = get()
        const { token, lastAuthCheck, isCheckingAuth, isAuthenticated } = state

        if (isCheckingAuth) {
          return isAuthenticated
        }

        if (!token) {
          return false
        }

        const now = Date.now()
        if (isAuthenticated && lastAuthCheck && (now - lastAuthCheck) < 30000) {
          return true
        }

        set({ isCheckingAuth: true })

        try {
          const apiUrl = await getApiUrl()

          const response = await fetch(`${apiUrl}/api/notebooks`, {
            method: 'GET',
            headers: {
              'Authorization': `Bearer ${token}`,
              'Content-Type': 'application/json'
            }
          })
          
          if (response.ok) {
            set({ 
              isAuthenticated: true, 
              lastAuthCheck: now,
              isCheckingAuth: false 
            })
            return true
          } else {
            set({
              isAuthenticated: false,
              token: null,
              lastAuthCheck: null,
              isCheckingAuth: false,
              user: null,
              isAdmin: false,
            })
            return false
          }
        } catch (error) {
          console.error('checkAuth error:', error)
          set({ 
            isAuthenticated: false, 
            token: null,
            lastAuthCheck: null,
            isCheckingAuth: false,
            user: null,
            isAdmin: false,
          })
          return false
        }
      }
    }),
    {
      name: 'auth-storage',
      partialize: (state) => ({
        token: state.token,
        isAuthenticated: state.isAuthenticated,
        user: state.user,
        isAdmin: state.isAdmin,
        authMode: state.authMode,
      }),
      onRehydrateStorage: () => (state) => {
        state?.setHasHydrated(true)
      }
    }
  )
)
