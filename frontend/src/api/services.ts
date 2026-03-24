import { ApiClient } from './client';
import type {
  ApiCase,
  AuditLogListResult,
  AuthSession,
  Environment,
  Execution,
  ExecutionListResult,
  LegacyImportPolicy,
  PaginatedResult,
  Project,
  Report,
  Suite,
  User,
} from './types';

export function createApi(token: string | null) {
  const client = new ApiClient(token);
  const authHeaders: HeadersInit | undefined = token ? { Authorization: `Bearer ${token}` } : undefined;
  const listPageSize = 200;

  return {
    listAuditLogs: (params?: {
      page?: number;
      page_size?: number;
      search?: string;
      action?: string;
      actor?: string;
      start_at?: string;
      end_at?: string;
    }) => {
      const query = new URLSearchParams();
      if (params?.page) {
        query.set('page', String(params.page));
      }
      if (params?.page_size) {
        query.set('page_size', String(params.page_size));
      }
      if (params?.search) {
        query.set('search', params.search);
      }
      if (params?.action) {
        query.set('action', params.action);
      }
      if (params?.actor) {
        query.set('actor', params.actor);
      }
      if (params?.start_at) {
        query.set('start_at', params.start_at);
      }
      if (params?.end_at) {
        query.set('end_at', params.end_at);
      }
      const suffix = query.toString() ? `?${query.toString()}` : '';
      return client.request<AuditLogListResult>(`/audit-logs${suffix}`);
    },
    getImportPolicy: () => client.request<LegacyImportPolicy>('/imports/policy'),
    login: (username: string, password: string) =>
      client.request<AuthSession>('/auth/login', {
        method: 'POST',
        body: JSON.stringify({ username, password }),
      }),
    me: () => client.request<User>('/auth/me'),
    logout: () => client.request<null>('/auth/logout', { method: 'POST' }),
    listProjects: async () => {
      const result = await client.request<PaginatedResult<Project>>(`/projects?page=1&page_size=${listPageSize}`);
      return result.items;
    },
    createProject: (payload: { name: string; description: string }) =>
      client.request<Project>('/projects', { method: 'POST', body: JSON.stringify(payload) }),
    updateProject: (projectId: number, payload: { name: string; description: string }) =>
      client.request<Project>(`/projects/${projectId}`, { method: 'PUT', body: JSON.stringify(payload) }),
    deleteProject: (projectId: number) => client.request<null>(`/projects/${projectId}`, { method: 'DELETE' }),
    listSuites: async (projectId?: number) => {
      const query = new URLSearchParams({ page: '1', page_size: String(listPageSize) });
      if (projectId) {
        query.set('project_id', String(projectId));
      }
      const result = await client.request<PaginatedResult<Suite>>(`/suites?${query.toString()}`);
      return result.items;
    },
    createSuite: (payload: { project_id: number; name: string; description: string }) =>
      client.request<Suite>('/suites', { method: 'POST', body: JSON.stringify(payload) }),
    updateSuite: (suiteId: number, payload: { project_id: number; name: string; description: string }) =>
      client.request<Suite>(`/suites/${suiteId}`, { method: 'PUT', body: JSON.stringify(payload) }),
    deleteSuite: (suiteId: number) => client.request<null>(`/suites/${suiteId}`, { method: 'DELETE' }),
    listCases: async (suiteId?: number) => {
      const query = new URLSearchParams({ page: '1', page_size: String(listPageSize) });
      if (suiteId) {
        query.set('suite_id', String(suiteId));
      }
      const result = await client.request<PaginatedResult<ApiCase>>(`/cases?${query.toString()}`);
      return result.items;
    },
    createCase: (payload: Record<string, unknown>) =>
      client.request<ApiCase>('/cases', { method: 'POST', body: JSON.stringify(payload) }),
    updateCase: (caseId: number, payload: Record<string, unknown>) =>
      client.request<ApiCase>(`/cases/${caseId}`, { method: 'PUT', body: JSON.stringify(payload) }),
    deleteCase: (caseId: number) => client.request<null>(`/cases/${caseId}`, { method: 'DELETE' }),
    listEnvironments: async (projectId?: number) => {
      const query = new URLSearchParams({ page: '1', page_size: String(listPageSize) });
      if (projectId) {
        query.set('project_id', String(projectId));
      }
      const result = await client.request<PaginatedResult<Environment>>(`/environments?${query.toString()}`);
      return result.items;
    },
    createEnvironment: (payload: Record<string, unknown>) =>
      client.request<Environment>('/environments', { method: 'POST', body: JSON.stringify(payload) }),
    updateEnvironment: (environmentId: number, payload: Record<string, unknown>) =>
      client.request<Environment>(`/environments/${environmentId}`, { method: 'PUT', body: JSON.stringify(payload) }),
    deleteEnvironment: (environmentId: number) => client.request<null>(`/environments/${environmentId}`, { method: 'DELETE' }),
    listExecutions: (params?: {
      page?: number;
      page_size?: number;
      status?: Execution['status'];
      scope?: Execution['scope'];
      search?: string;
      failed_only?: boolean;
    }) => {
      const query = new URLSearchParams();
      if (params?.page) {
        query.set('page', String(params.page));
      }
      if (params?.page_size) {
        query.set('page_size', String(params.page_size));
      }
      if (params?.status) {
        query.set('status', params.status);
      }
      if (params?.scope) {
        query.set('scope', params.scope);
      }
      if (params?.search) {
        query.set('search', params.search);
      }
      if (params?.failed_only) {
        query.set('failed_only', 'true');
      }
      const suffix = query.toString() ? `?${query.toString()}` : '';
      return client.request<ExecutionListResult>(`/executions${suffix}`);
    },
    runExecution: (payload: { scope: 'case' | 'suite'; target_id: number; environment_id?: number }) =>
      client.request<Execution>('/executions', { method: 'POST', body: JSON.stringify(payload) }),
    getExecution: (executionId: number) => client.request<Execution>(`/executions/${executionId}`),
    cancelExecution: (executionId: number) =>
      client.request<Execution>(`/executions/${executionId}/cancel`, { method: 'POST' }),
    retryExecution: (executionId: number) =>
      client.request<Execution>(`/executions/${executionId}/retry`, { method: 'POST' }),
    listReports: async () => {
      const result = await client.request<PaginatedResult<Report>>(`/reports?page=1&page_size=${listPageSize}`);
      return result.items;
    },
    fetchReportText: async (reportId: number) => {
      const response = await fetch(`/api/v1/reports/${reportId}/content`, { headers: authHeaders });
      if (!response.ok) {
        throw new Error(await client.readErrorMessage(response, '加载报告内容失败。'));
      }
      return response.text();
    },
    fetchReportBlob: async (reportId: number) => {
      const response = await fetch(`/api/v1/reports/${reportId}/content`, { headers: authHeaders });
      if (!response.ok) {
        throw new Error(await client.readErrorMessage(response, '加载报告内容失败。'));
      }
      return response.blob();
    },
    importExcel: async (projectId: number, file: File) => {
      const formData = new FormData();
      formData.set('project_id', String(projectId));
      formData.set('file', file);
      return client.request<{ suite_id: number; suite_name: string; created_cases: number; failures: { row: number; reason: string }[] }>(
        '/imports/excel',
        { method: 'POST', body: formData },
      );
    },
    importLegacyProject: async (projectId: number, file: File) => {
      const formData = new FormData();
      formData.set('project_id', String(projectId));
      formData.set('file', file);
      return client.request<{
        project_id: number;
        created_environments: number;
        created_suites: number;
        created_cases: number;
        created_executions: number;
        created_reports: number;
        skipped_runs: number;
      }>(
        '/imports/legacy-project',
        { method: 'POST', body: formData },
      );
    },
    listUsers: async () => {
      const result = await client.request<PaginatedResult<User>>(`/users?page=1&page_size=${listPageSize}`);
      return result.items;
    },
    createUser: (payload: Record<string, unknown>) =>
      client.request<User>('/users', { method: 'POST', body: JSON.stringify(payload) }),
  };
}
