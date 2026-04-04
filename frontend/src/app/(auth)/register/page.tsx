'use client'

import { useState, useEffect } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { useAuth } from '@/lib/hooks/use-auth'
import { useAuthStore } from '@/lib/stores/auth-store'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { AlertCircle } from 'lucide-react'
import { LoadingSpinner } from '@/components/common/LoadingSpinner'
import { useTranslation } from '@/lib/hooks/use-translation'

export default function RegisterPage() {
  const { t } = useTranslation()
  const router = useRouter()
  const { register, isLoading, error, authMode, registrationEnabled } = useAuth()
  const { hasHydrated, checkAuthRequired, authRequired } = useAuthStore()
  const [isReady, setIsReady] = useState(false)

  const [username, setUsername] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [localError, setLocalError] = useState<string | null>(null)

  useEffect(() => {
    if (!hasHydrated) return
    if (authRequired === null) {
      checkAuthRequired().finally(() => setIsReady(true))
    } else {
      setIsReady(true)
    }
  }, [hasHydrated, authRequired, checkAuthRequired])

  useEffect(() => {
    if (isReady && !registrationEnabled) {
      router.push('/login')
    }
  }, [isReady, registrationEnabled, router])

  if (!hasHydrated || !isReady) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-background">
        <LoadingSpinner />
      </div>
    )
  }

  if (!registrationEnabled) return null

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setLocalError(null)

    if (password !== confirmPassword) {
      setLocalError(t.auth.passwordMismatch || 'Passwords do not match')
      return
    }

    if (password.length < 6) {
      setLocalError(t.auth.passwordTooShort || 'Password must be at least 6 characters')
      return
    }

    const result = await register(username, email, password, displayName || undefined)
    if (result.success && result.pending) {
      router.push('/pending')
    }
  }

  const canSubmit = username.trim() && email.trim() && password.trim() && confirmPassword.trim()
  const displayError = localError || error

  return (
    <div className="min-h-screen flex items-center justify-center bg-background p-4">
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <CardTitle>{t.auth.registerTitle || 'Create Account'}</CardTitle>
          <CardDescription>{t.auth.registerDesc || 'Register for a new account'}</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <Input
              type="text"
              placeholder={t.auth.usernamePlaceholder || 'Username'}
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={isLoading}
              autoComplete="username"
            />
            <Input
              type="email"
              placeholder={t.auth.emailPlaceholder || 'Email'}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={isLoading}
              autoComplete="email"
            />
            <Input
              type="text"
              placeholder={t.auth.displayNamePlaceholder || 'Display name (optional)'}
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              disabled={isLoading}
            />
            <Input
              type="password"
              placeholder={t.auth.passwordPlaceholder || 'Password'}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={isLoading}
              autoComplete="new-password"
            />
            <Input
              type="password"
              placeholder={t.auth.confirmPasswordPlaceholder || 'Confirm password'}
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              disabled={isLoading}
              autoComplete="new-password"
            />

            {displayError && (
              <div className="flex items-center gap-2 text-red-600 text-sm">
                <AlertCircle className="h-4 w-4" />
                {displayError}
              </div>
            )}

            <Button
              type="submit"
              className="w-full"
              disabled={isLoading || !canSubmit}
            >
              {isLoading ? t.auth.registering || 'Registering...' : t.auth.registerButton || 'Register'}
            </Button>

            <div className="text-center text-sm text-muted-foreground">
              {t.auth.alreadyHaveAccount || 'Already have an account?'}{' '}
              <Link href="/login" className="text-primary hover:underline font-medium">
                {t.auth.signIn || 'Sign in'}
              </Link>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
