'use client'

import { useAuthStore } from '@/lib/stores/auth-store'
import { useTranslation } from '@/lib/hooks/use-translation'
import { useRouter } from 'next/navigation'
import { useEffect } from 'react'

export function useAuth() {
  const router = useRouter()
  const { t } = useTranslation()
  const {
    isAuthenticated,
    isLoading,
    login,
    ldapLogin,
    logout,
    checkAuth,
    checkAuthRequired,
    error,
    hasHydrated,
    authRequired,
    ldapEnabled
  } = useAuthStore()

  useEffect(() => {
    if (hasHydrated) {
      if (authRequired === null) {
        checkAuthRequired().then((required) => {
          if (required) {
            checkAuth()
          }
        })
      } else if (authRequired) {
        checkAuth()
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasHydrated, authRequired])

  const redirectAfterAuth = () => {
    const redirectPath = sessionStorage.getItem('redirectAfterLogin')
    if (redirectPath) {
      sessionStorage.removeItem('redirectAfterLogin')
      router.push(redirectPath)
    } else {
      router.push('/notebooks')
    }
  }

  const handleLogin = async (password: string) => {
    const success = await login(password)
    if (success) {
      redirectAfterAuth()
    }
    return success
  }

  const handleLdapLogin = async (user: string, password: string) => {
    const success = await ldapLogin(user, password)
    if (success) {
      redirectAfterAuth()
    } else {
      const currentError = useAuthStore.getState().error
      if (currentError === 'ldapAuthFailed') {
        useAuthStore.setState({ error: t.auth.ldapAuthFailed })
      }
    }
    return success
  }

  const handleLogout = () => {
    logout()
    router.push('/login')
  }

  return {
    isAuthenticated,
    isLoading: isLoading || !hasHydrated,
    error,
    ldapEnabled,
    login: handleLogin,
    ldapLogin: handleLdapLogin,
    logout: handleLogout
  }
}
