export type ApiResponse<T> = {
  success: boolean;
  message: string;
  data: T;
};

export type ApiErrorResponse = {
  success: false;
  message: string;
  error: {
    code: string;
    status: number;
    details?: unknown;
    request_id?: string | null;
  };
  data: null;
};

export type PaginatedResult<T> = {
  items: T[];
  total: number;
  page: number;
  page_size: number;
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
  issued_at: string;
  expires_at: string;
  expires_in_seconds: number;
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

export type AiExecutionPreparationSelection = {
  selected_test_data_variant_ids: string[];
  selected_mock_template_ids: string[];
};

export type AiExecutionPreparation = {
  case_id: number;
  request_body: unknown;
  selected_test_data_variants: Record<string, unknown>[];
  selected_mock_templates: Record<string, unknown>[];
  summary: Record<string, unknown>;
};

export type ExecutionListResult = PaginatedResult<Execution>;

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

export type AuditLogListResult = PaginatedResult<AuditLog>;

export type LegacyImportPolicy = {
  mode: string;
  status: 'migration_only' | 'sunset_scheduled' | 'disabled' | 'expired';
  legacy_imports_enabled: boolean;
  sunset_date: string | null;
  rules: string[];
  capabilities: Array<{
    id: string;
    label: string;
    status: string;
    target: string;
  }>;
  retirement_plan: string[];
};

export type AiCaseDraftValidationStatus = 'valid' | 'warning' | 'invalid';
export type AiCaseDraftExportView = 'human' | 'program' | 'both';

export type AiCaseDraftPayload = {
  name: string;
  method: string;
  url: string;
  description: string;
  headers_json: Record<string, string>;
  body_json: unknown;
  assertions_json: Record<string, unknown>[];
  metadata_json: Record<string, unknown>;
};

export type AiCaseDraft = {
  draft_id: string;
  selected: boolean;
  validation_status: AiCaseDraftValidationStatus;
  validation_errors: string[];
  review_warnings: string[];
  case: AiCaseDraftPayload;
  source_excerpt: string;
  source_location: Record<string, unknown>;
};

export type AiCaseDraftBatch = {
  history_id: string;
  created_at: string;
  suite_name: string;
  doc_summary: {
    section_count: number;
    endpoint_count: number;
  };
  drafts: AiCaseDraft[];
  warnings: string[];
  prompt_preset: string;
  prompt_hints_effective: string;
};

export type AiCaseDraftImportResult = {
  suite_id: number;
  suite_name: string;
  created_cases: number;
  skipped_cases: number;
  failures: Array<{
    draft_id: string;
    reason: string;
  }>;
};

export type AiCaseDraftHistorySummary = {
  history_id: string;
  created_at: string;
  project_id: number;
  suite_name: string;
  provider: string;
  model: string;
  prompt_preset: string;
  draft_count: number;
  warning_count: number;
};

export type AiCaseDraftHistoryList = {
  items: AiCaseDraftHistorySummary[];
};

export type AiCopilotPreview<T> = {
  artifact_id: string;
  capability: 'test_point' | 'coverage' | 'diagnosis' | 'assertion' | 'test_data' | 'mock' | 'report_summary';
  status: 'draft' | 'accepted' | 'rejected' | 'applied' | 'superseded';
  warnings: string[];
  result: T;
  call_trace?: AiCallTrace | null;
};

export type AiArtifactHistoryItem = {
  artifact_id: string;
  capability: 'test_point' | 'coverage' | 'diagnosis' | 'assertion' | 'test_data' | 'mock' | 'report_summary';
  target_type: 'project' | 'suite' | 'case' | 'execution' | 'report';
  target_id: number;
  project_id: number | null;
  suite_id: number | null;
  case_id: number | null;
  execution_id: number | null;
  report_id: number | null;
  input_json: Record<string, unknown>;
  output_json: Record<string, unknown>;
  warnings_json: string[];
  status: 'draft' | 'accepted' | 'rejected' | 'applied' | 'superseded';
  provider: string;
  model: string;
  call_trace?: AiCallTrace | null;
};

export type AiArtifactHistoryList = {
  items: AiArtifactHistoryItem[];
};

export type AiProviderConfig = {
  provider: string;
  model: string;
  base_url: string;
  timeout_seconds?: number | null;
};

export type AiCallTrace = {
  call_mode: string;
  provider?: AiProviderConfig | null;
  latency_ms?: number | null;
  failure_category: string;
  trace_json: Record<string, unknown>;
};

export type AiArtifactLineageNode = {
  artifact_id: string;
  resource_type: string;
  resource_key: string;
  link_type: string;
  capability?: 'test_point' | 'coverage' | 'diagnosis' | 'assertion' | 'test_data' | 'mock' | 'report_summary' | null;
  status?: 'draft' | 'accepted' | 'rejected' | 'applied' | 'superseded' | null;
  created_at?: string;
};

export type AiArtifactLineage = {
  root_artifact_id: string;
  items: AiArtifactLineageNode[];
};

export type AiDesignTargetType = 'project' | 'suite';

export type AiTestPoint = {
  id: string;
  title: string;
  category: string;
  risk_level: string;
  reason: string;
  covered_by_existing_cases: boolean;
  suggested_case_count: number;
  confidence: number;
};

export type AiTestPointResult = {
  test_points: AiTestPoint[];
};

export type AiCoverageMissingDimension = {
  endpoint: string;
  dimension: string;
  reason: string;
};

export type AiCoverageSuggestedPoint = {
  title: string;
  category: string;
  priority: string;
  reason: string;
};

export type AiCoverageResult = {
  coverage_score: number;
  missing_dimensions: AiCoverageMissingDimension[];
  suggested_points: AiCoverageSuggestedPoint[];
};

export type AiDiagnosisResult = {
  diagnosis_category: string;
  root_cause_hypothesis: string;
  confidence: number;
  next_actions: string[];
};

export type AiAssertionSuggestion = {
  type: string;
  operator: string;
  path?: string;
  header?: string;
  expected: unknown;
  enabled: boolean;
  reason: string;
  confidence: number;
};

export type AiAssertionResult = {
  suggested_assertions: AiAssertionSuggestion[];
};

export type AiTestDataVariant = {
  variant_id: string;
  name: string;
  category: string;
  payload_patch: Record<string, unknown>;
  target_fields: string[];
  reason: string;
  suggested_assertions: Record<string, unknown>[];
  confidence: number;
};

export type AiTestDataResult = {
  data_variants: AiTestDataVariant[];
};

export type AiMockTemplate = {
  template_id: string;
  scenario_name: string;
  status_code: number;
  response_template: Record<string, unknown>;
  mock_rules: Record<string, unknown>[];
  reason: string;
  confidence: number;
};

export type AiMockResult = {
  mock_templates: AiMockTemplate[];
};

export type AiReportSummaryResult = {
  executive_summary: string;
  risk_summary: string;
  top_failures: Array<{
    category: string;
    count: number;
  }>;
  recommended_actions: string[];
};

export type AiChatMode = 'project' | 'free';

export type AiChatHistoryMessage = {
  message_id: number;
  role: 'user' | 'assistant';
  content: string;
  created_at: string;
};

export type AiChatSessionSummary = {
  session_id: number;
  title: string;
  chat_mode: AiChatMode;
  project_id: number | null;
  project_name: string | null;
  latest_message_preview: string;
  message_count: number;
  updated_at: string;
};

export type AiChatSessionList = {
  items: AiChatSessionSummary[];
};

export type AiChatSession = AiChatSessionSummary & {
  page_path: string;
  page_title: string;
  messages: AiChatHistoryMessage[];
};
