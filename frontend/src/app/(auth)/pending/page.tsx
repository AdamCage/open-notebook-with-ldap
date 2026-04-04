'use client'

import Link from 'next/link'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Clock } from 'lucide-react'
import { useTranslation } from '@/lib/hooks/use-translation'

export default function PendingApprovalPage() {
  const { t } = useTranslation()

  return (
    <div className="min-h-screen flex items-center justify-center bg-background p-4">
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-amber-100 dark:bg-amber-900/30">
            <Clock className="h-6 w-6 text-amber-600 dark:text-amber-400" />
          </div>
          <CardTitle>{t.auth.pendingTitle || 'Account Pending'}</CardTitle>
          <CardDescription className="text-base">
            {t.auth.pendingDesc || 'Your account has been created and is awaiting administrator approval. You will be able to sign in once your account has been activated.'}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Link href="/login">
            <Button variant="outline" className="w-full">
              {t.auth.backToLogin || 'Back to Sign In'}
            </Button>
          </Link>
        </CardContent>
      </Card>
    </div>
  )
}
