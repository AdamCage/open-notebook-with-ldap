'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { useAuthStore } from '@/lib/stores/auth-store'
import {
  useUsers,
  useApproveUser,
  useDeactivateUser,
  useActivateUser,
  useUpdateUserRole,
} from '@/lib/hooks/use-users'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert'
import { LoadingSpinner } from '@/components/common/LoadingSpinner'
import { useTranslation } from '@/lib/hooks/use-translation'
import { CheckCircle, XCircle, ShieldCheck, ShieldOff, AlertTriangle } from 'lucide-react'
import type { UserProfile } from '@/lib/types/auth'

export default function AdminUsersPage() {
  const { t } = useTranslation()
  const router = useRouter()
  const [statusFilter, setStatusFilter] = useState<string | undefined>(undefined)
  const { user: currentUser, isAdmin, authMode } = useAuthStore()
  const isSuperAdmin = currentUser?.role === 'super_admin'

  const needsGuard = (authMode === 'local' || authMode === 'ldap') && !isAdmin
  if (needsGuard) {
    router.replace('/notebooks')
    return null
  }

  const { data: users, isLoading, isError, error } = useUsers(statusFilter)
  const approveUser = useApproveUser()
  const deactivateUser = useDeactivateUser()
  const activateUser = useActivateUser()
  const updateRole = useUpdateUserRole()

  const admin = (t.admin || {}) as Record<string, string>

  const statusBadge = (status: string) => {
    switch (status) {
      case 'active':
        return <Badge variant="default" className="bg-green-600">{admin.statusActive || 'Active'}</Badge>
      case 'pending':
        return <Badge variant="secondary" className="bg-amber-500 text-white">{admin.statusPending || 'Pending'}</Badge>
      case 'deactivated':
        return <Badge variant="destructive">{admin.statusDeactivated || 'Deactivated'}</Badge>
      default:
        return <Badge variant="outline">{status}</Badge>
    }
  }

  const roleBadge = (role: string) => {
    switch (role) {
      case 'super_admin':
        return <Badge variant="default">{admin.roleSuperAdmin || 'Super Admin'}</Badge>
      case 'admin':
        return <Badge variant="secondary">{admin.roleAdmin || 'Admin'}</Badge>
      default:
        return <Badge variant="outline">{admin.roleUser || 'User'}</Badge>
    }
  }

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <LoadingSpinner />
      </div>
    )
  }

  if (isError) {
    return (
      <div className="container mx-auto py-6 px-4 max-w-6xl">
        <Alert variant="destructive">
          <AlertTriangle className="h-4 w-4" />
          <AlertTitle>{admin.errorTitle || 'Error'}</AlertTitle>
          <AlertDescription>
            {(error as Error)?.message || admin.actionFailed || 'Failed to load users'}
          </AlertDescription>
        </Alert>
      </div>
    )
  }

  return (
    <div className="container mx-auto py-6 px-4 max-w-6xl">
      <Card>
        <CardHeader>
          <CardTitle>{admin.usersTitle || 'User Management'}</CardTitle>
          <CardDescription>
            {admin.usersDesc || 'Manage user accounts, approvals, and roles.'}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="mb-4 flex items-center gap-4">
            <Select
              value={statusFilter || 'all'}
              onValueChange={(v) => setStatusFilter(v === 'all' ? undefined : v)}
            >
              <SelectTrigger className="w-48">
                <SelectValue placeholder={admin.filterByStatus || 'Filter by status'} />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">{admin.allStatuses || 'All'}</SelectItem>
                <SelectItem value="pending">{admin.statusPending || 'Pending'}</SelectItem>
                <SelectItem value="active">{admin.statusActive || 'Active'}</SelectItem>
                <SelectItem value="deactivated">{admin.statusDeactivated || 'Deactivated'}</SelectItem>
              </SelectContent>
            </Select>
          </div>

          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{admin.colUsername || 'Username'}</TableHead>
                <TableHead>{admin.colEmail || 'Email'}</TableHead>
                <TableHead>{admin.colRole || 'Role'}</TableHead>
                <TableHead>{admin.colStatus || 'Status'}</TableHead>
                <TableHead>{admin.colProvider || 'Provider'}</TableHead>
                <TableHead>{admin.colLastLogin || 'Last Login'}</TableHead>
                <TableHead className="text-right">{admin.colActions || 'Actions'}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {users && users.length > 0 ? (
                users.map((u: UserProfile) => (
                  <TableRow key={u.id}>
                    <TableCell className="font-medium">{u.username}</TableCell>
                    <TableCell>{u.email}</TableCell>
                    <TableCell>{roleBadge(u.role)}</TableCell>
                    <TableCell>{statusBadge(u.status)}</TableCell>
                    <TableCell>{u.auth_provider}</TableCell>
                    <TableCell>
                      {u.last_login
                        ? new Date(u.last_login).toLocaleDateString()
                        : '-'}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-1">
                        {u.status === 'pending' && (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => approveUser.mutate(u.id)}
                            disabled={approveUser.isPending}
                            title={admin.approveUser || 'Approve'}
                          >
                            <CheckCircle className="h-4 w-4 text-green-600" />
                          </Button>
                        )}
                        {u.status === 'active' && u.role !== 'super_admin' && (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => deactivateUser.mutate(u.id)}
                            disabled={deactivateUser.isPending}
                            title={admin.deactivateUser || 'Deactivate'}
                          >
                            <XCircle className="h-4 w-4 text-red-600" />
                          </Button>
                        )}
                        {u.status === 'deactivated' && (
                          <Button
                            size="sm"
                            variant="outline"
                            onClick={() => activateUser.mutate(u.id)}
                            disabled={activateUser.isPending}
                            title={admin.activateUser || 'Activate'}
                          >
                            <CheckCircle className="h-4 w-4 text-green-600" />
                          </Button>
                        )}
                        {isSuperAdmin && u.role !== 'super_admin' && (
                          <>
                            {u.role === 'user' ? (
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => updateRole.mutate({ userId: u.id, role: 'admin' })}
                                disabled={updateRole.isPending}
                                title={admin.grantAdmin || 'Grant Admin'}
                              >
                                <ShieldCheck className="h-4 w-4 text-blue-600" />
                              </Button>
                            ) : (
                              <Button
                                size="sm"
                                variant="outline"
                                onClick={() => updateRole.mutate({ userId: u.id, role: 'user' })}
                                disabled={updateRole.isPending}
                                title={admin.revokeAdmin || 'Revoke Admin'}
                              >
                                <ShieldOff className="h-4 w-4 text-orange-600" />
                              </Button>
                            )}
                          </>
                        )}
                      </div>
                    </TableCell>
                  </TableRow>
                ))
              ) : (
                <TableRow>
                  <TableCell colSpan={7} className="text-center text-muted-foreground py-8">
                    {admin.noUsers || 'No users found'}
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  )
}
