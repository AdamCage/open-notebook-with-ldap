---
name: frontend-patterns
description: Frontend development patterns for the Open Notebook Next.js/React/TypeScript UI. Covers Zustand state stores, TanStack Query hooks, Shadcn/ui components, i18n locale files, Axios API client with auth interceptors, and auth integration. Use when building new pages, components, forms, or features in the frontend.
---

# Frontend Patterns

## Tech Stack

- **Next.js 16** (App Router), **React 19**, **TypeScript**
- **Zustand** (client state) + **TanStack Query** (server state)
- **Shadcn/ui** + **Tailwind CSS** (components/styling)
- **Axios** (API client with Bearer interceptor)

## Directory Structure

```
frontend/src/
  app/           — Next.js App Router pages and layouts
  components/    — Reusable UI components (Shadcn-based)
  lib/
    api/         — API client modules (notebooks.ts, ldap.ts, etc.)
    hooks/       — Custom React hooks (useAuth, useNotebook, etc.)
    stores/      — Zustand stores (auth-store.ts, etc.)
    locales/     — i18n translations (en-US/, ru-RU/, etc.)
    types/       — TypeScript type definitions
    config.ts    — Runtime config (API URL)
```

## Zustand Store Pattern

```typescript
import { create } from 'zustand'
import { persist } from 'zustand/middleware'

interface MyState {
  items: Item[]
  isLoading: boolean
  error: string | null
  fetchItems: () => Promise<void>
}

export const useMyStore = create<MyState>()(
  persist(
    (set) => ({
      items: [],
      isLoading: false,
      error: null,
      fetchItems: async () => {
        set({ isLoading: true, error: null })
        try {
          const data = await apiClient.get('/api/myitems')
          set({ items: data.data, isLoading: false })
        } catch (error) {
          set({ error: 'Failed to fetch', isLoading: false })
        }
      },
    }),
    { name: 'my-storage', partialize: (s) => ({ items: s.items }) }
  )
)
```

## API Client

`frontend/src/lib/api/client.ts` exports an Axios instance with a request interceptor that attaches the Bearer token from `auth-storage` in localStorage.

```typescript
import { apiClient } from '@/lib/api/client'

export async function getMyItems(): Promise<Item[]> {
  const response = await apiClient.get('/api/myitems')
  return response.data
}
```

For endpoints that bypass the Axios interceptor (e.g., auth), use raw `fetch`:

```typescript
const apiUrl = await getApiUrl()
const response = await fetch(`${apiUrl}/api/auth/ldap`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ user, password }),
})
```

## i18n — Adding Translation Keys

All 9 locale files must be updated when adding user-facing strings:

```
frontend/src/lib/locales/
  en-US/index.ts   bn-IN/index.ts   fr-FR/index.ts
  ru-RU/index.ts   zh-CN/index.ts   zh-TW/index.ts
  ja-JP/index.ts   pt-BR/index.ts   it-IT/index.ts
```

Pattern: add the key to each file's relevant section (e.g., `auth`, `notebooks`, `settings`).

```typescript
// en-US/index.ts
export default {
  auth: {
    // ... existing keys
    myNewKey: 'My new label',
  },
}
```

Use in components via `useTranslation`:

```typescript
const { t } = useTranslation()
return <p>{t.auth.myNewKey}</p>
```

## Auth Integration

When creating pages or components that need auth context:

```typescript
import { useAuth } from '@/lib/hooks/use-auth'

export function MyPage() {
  const { isAuthenticated, isLoading, ldapEnabled } = useAuth()

  if (isLoading) return <Spinner />
  if (!isAuthenticated) return <Redirect to="/login" />

  return <div>...</div>
}
```

## Component Pattern (Shadcn/ui)

```typescript
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Input } from '@/components/ui/input'

export function MyForm({ onSubmit }: { onSubmit: (data: FormData) => void }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{t.mySection.title}</CardTitle>
      </CardHeader>
      <CardContent>
        <Input placeholder={t.mySection.placeholder} />
        <Button onClick={handleSubmit}>{t.mySection.submit}</Button>
      </CardContent>
    </Card>
  )
}
```
