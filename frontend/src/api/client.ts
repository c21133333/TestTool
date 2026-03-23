import type { ApiResponse } from './types';

const API_PREFIX = '/api/v1';

export class ApiClient {
  constructor(private token: string | null) {}

  async request<T>(path: string, init?: RequestInit): Promise<T> {
    const headers = new Headers(init?.headers);
    if (!headers.has('Content-Type') && !(init?.body instanceof FormData)) {
      headers.set('Content-Type', 'application/json');
    }
    if (this.token) {
      headers.set('Authorization', `Bearer ${this.token}`);
    }
    const response = await fetch(`${API_PREFIX}${path}`, {
      ...init,
      headers,
    });
    const payload = (await response.json()) as ApiResponse<T> | { detail?: string };
    if (!response.ok) {
      throw new Error('detail' in payload ? payload.detail ?? '请求失败。' : '请求失败。');
    }
    return (payload as ApiResponse<T>).data;
  }
}
