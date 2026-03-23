export type ApiResponse<T> = {
  success: boolean;
  message: string;
  data: T;
};

export type User = {
  id: number;
  username: string;
  display_name: string;
  role: 'admin' | 'tester' | 'developer';
  is_active: boolean;
  created_at: string;
};

export type AuthSession = {
  access_token: string;
  token_type: string;
  expires_at: string;
  user: User;
};

export type Project = {
  id: number;
  name: string;
  description: string;
  created_at: string;
  suites: Suite[];
  environments: Environment[];
};

export type Suite = {
  id: number;
  project_id: number;
  name: string;
  description: string;
  created_at: string;
  cases: ApiCase[];
};

export type ApiCase = {
  id: number;
  suite_id: number;
  name: string;
  method: string;
  url: string;
  description: string;
  headers_json: Record<string, string>;
  body_json: unknown;
  assertions_json: Record<string, unknown>[];
  pre_processors_json: Record<string, unknown>[];
  post_processors_json: Record<string, unknown>[];
  metadata_json: Record<string, unknown>;
  created_at: string;
};

export type Environment = {
  id: number;
  project_id: number;
  name: string;
  base_url: string;
  description: string;
  headers_json: Record<string, string>;
  variables_json: Record<string, unknown>;
  created_at: string;
};

export type ExecutionItem = {
  id: number;
  case_id: number | null;
  order_index: number;
  case_name: string;
  status: string;
  elapsed_ms: number | null;
  request_json: Record<string, unknown>;
  response_json: Record<string, unknown>;
  assertion_results_json: Record<string, unknown>[];
  failure_message: string;
};

export type Execution = {
  id: number;
  project_id: number;
  suite_id: number | null;
  environment_id: number | null;
  scope: 'case' | 'suite';
  status: 'pending' | 'running' | 'success' | 'failed';
  target_name: string;
  summary_json: Record<string, unknown>;
  error_message: string;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  items: ExecutionItem[];
};

export type ExecutionListResult = {
  items: Execution[];
  total: number;
  page: number;
  page_size: number;
};

export type Report = {
  id: number;
  execution_id: number;
  report_type: string;
  file_path: string;
  metadata_json: Record<string, unknown>;
  created_at: string;
};

export type AuditLog = {
  id: number;
  user_id: number | null;
  action: string;
  resource_type: string;
  resource_id: string;
  summary: string;
  details_json: Record<string, unknown>;
  actor_username: string | null;
  actor_display_name: string | null;
  actor_role: 'admin' | 'tester' | 'developer' | null;
  created_at: string;
};

export type AuditLogListResult = {
  items: AuditLog[];
  total: number;
  page: number;
  page_size: number;
};
