import type { ApiErrorResponse, ApiResponse } from './types';

const API_PREFIX = '/api/v1';

export class ApiClient {
  constructor(private token: string | null) {}

  async readErrorMessage(response: Response, fallback = '请求失败。'): Promise<string> {
    const contentType = response.headers.get('Content-Type') ?? '';
    if (!contentType.includes('application/json')) {
      return fallback;
    }
    try {
      const payload = (await response.json()) as ApiErrorResponse | { detail?: string; message?: string };
      if ('error' in payload && payload.error) {
        return payload.message || fallback;
      }
      if ('detail' in payload && payload.detail) {
        return payload.detail;
      }
      if ('message' in payload && payload.message) {
        return payload.message;
      }
    } catch {
      return fallback;
    }
    return fallback;
  }

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
    const contentType = response.headers.get('Content-Type') ?? '';
    if (!contentType.includes('application/json')) {
      const fallbackMessage = await this.readErrorMessage(response, '服务返回了非 JSON 响应，请检查后端是否已重启并加载最新路由。');
      if (!response.ok) {
        throw new Error(fallbackMessage);
      }
      throw new Error('服务返回了非 JSON 响应，请检查后端是否已重启并加载最新路由。');
    }
    const payload = (await response.json()) as ApiResponse<T> | ApiErrorResponse | { detail?: string };
    if (!response.ok) {
      if ('error' in payload && payload.error) {
        throw new Error(payload.message || '请求失败。');
      }
      throw new Error('detail' in payload ? payload.detail ?? '请求失败。' : '请求失败。');
    }
    return (payload as ApiResponse<T>).data;
  }
}
