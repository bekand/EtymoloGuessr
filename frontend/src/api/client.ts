const API_BASE = (import.meta.env.VITE_API_URL ?? '/api').replace(/\/$/, '')

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export async function apiJson<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, init)
  if (!response.ok) {
    let message = response.statusText
    try {
      const body = (await response.json()) as { error?: string }
      if (body.error) {
        message = body.error
      }
    } catch {
      // keep statusText
    }
    throw new ApiError(response.status, message)
  }
  return response.json() as Promise<T>
}
