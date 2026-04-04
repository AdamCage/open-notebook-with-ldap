import apiClient from './client'
import type { UserProfile } from '@/lib/types/auth'

export const usersApi = {
  list: async (status?: string): Promise<UserProfile[]> => {
    const params = status ? { status } : {}
    const response = await apiClient.get('/users', { params })
    return response.data
  },

  get: async (userId: string): Promise<UserProfile> => {
    const response = await apiClient.get(`/users/${userId}`)
    return response.data
  },

  approve: async (userId: string): Promise<UserProfile> => {
    const response = await apiClient.put(`/users/${userId}/approve`)
    return response.data
  },

  deactivate: async (userId: string): Promise<UserProfile> => {
    const response = await apiClient.put(`/users/${userId}/deactivate`)
    return response.data
  },

  activate: async (userId: string): Promise<UserProfile> => {
    const response = await apiClient.put(`/users/${userId}/activate`)
    return response.data
  },

  updateRole: async (userId: string, role: string): Promise<UserProfile> => {
    const response = await apiClient.put(`/users/${userId}/role`, { role })
    return response.data
  },
}
