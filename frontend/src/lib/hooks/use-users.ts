'use client'

import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { usersApi } from '@/lib/api/users'
import { toast } from 'sonner'
import { useTranslation } from '@/lib/hooks/use-translation'

export const USER_QUERY_KEYS = {
  all: ['users'] as const,
  filtered: (status?: string) => ['users', status] as const,
  detail: (id: string) => ['users', id] as const,
}

export function useUsers(status?: string) {
  return useQuery({
    queryKey: USER_QUERY_KEYS.filtered(status),
    queryFn: () => usersApi.list(status),
  })
}

export function useApproveUser() {
  const queryClient = useQueryClient()
  const { t } = useTranslation()

  return useMutation({
    mutationFn: (userId: string) => usersApi.approve(userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: USER_QUERY_KEYS.all })
      toast.success((t.admin as Record<string, string>).userApproved || 'User approved successfully')
    },
    onError: () => {
      toast.error((t.admin as Record<string, string>).actionFailed || 'Action failed')
    },
  })
}

export function useDeactivateUser() {
  const queryClient = useQueryClient()
  const { t } = useTranslation()

  return useMutation({
    mutationFn: (userId: string) => usersApi.deactivate(userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: USER_QUERY_KEYS.all })
      toast.success((t.admin as Record<string, string>).userDeactivated || 'User deactivated')
    },
    onError: () => {
      toast.error((t.admin as Record<string, string>).actionFailed || 'Action failed')
    },
  })
}

export function useActivateUser() {
  const queryClient = useQueryClient()
  const { t } = useTranslation()

  return useMutation({
    mutationFn: (userId: string) => usersApi.activate(userId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: USER_QUERY_KEYS.all })
      toast.success((t.admin as Record<string, string>).userActivated || 'User activated')
    },
    onError: () => {
      toast.error((t.admin as Record<string, string>).actionFailed || 'Action failed')
    },
  })
}

export function useUpdateUserRole() {
  const queryClient = useQueryClient()
  const { t } = useTranslation()

  return useMutation({
    mutationFn: ({ userId, role }: { userId: string; role: string }) =>
      usersApi.updateRole(userId, role),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: USER_QUERY_KEYS.all })
      toast.success((t.admin as Record<string, string>).roleUpdated || 'Role updated')
    },
    onError: () => {
      toast.error((t.admin as Record<string, string>).actionFailed || 'Action failed')
    },
  })
}
