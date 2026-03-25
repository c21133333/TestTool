import { App, Button, Card, Col, Form, Input, Popconfirm, Row, Segmented, Select, Space, Table, Tabs, Typography, Upload } from 'antd';
import type { UploadFile } from 'antd/es/upload/interface';
import { useEffect, useMemo, useState } from 'react';

import { Alert as AlertBox } from 'antd';
import { createApi } from '../api/services';
import type {
  AiArtifactLineage,
  AiArtifactHistoryItem,
  AiAssertionResult,
  AiAssertionSuggestion,
  AiCopilotPreview,
  AiCoverageResult,
  AiMockResult,
  AiTestDataResult,
} from '../api/types';
import type { ApiCase, Environment, Execution, Project, Suite } from '../api/types';
import { useAuth } from '../auth/AuthContext';
import { AiArtifactHistoryDrawer } from '../components/ai-copilot/AiArtifactHistoryDrawer';
import { AiCapabilityActionCard } from '../components/ai-copilot/AiCapabilityActionCard';
import { AiCoveragePanel } from '../components/ai-copilot/AiCoveragePanel';
import { AiExecutionPreparationPanel } from '../components/ai-copilot/AiExecutionPreparationPanel';
import { AiPreparationAssetsPanel } from '../components/ai-copilot/AiPreparationAssetsPanel';
import { AiSuggestionPanel } from '../components/ai-copilot/AiSuggestionPanel';
import { canManageWorkspace } from '../auth/permissions';
import { AiCaseGenerationPanel } from '../components/ai/AiCaseGenerationPanel';
import { AssertionEditor, type AssertionEditorRow } from '../components/editors/AssertionEditor';
import { KeyValueEditor, type KeyValueEditorRow } from '../components/editors/KeyValueEditor';
import { ProcessorEditor, type ProcessorEditorRow } from '../components/editors/ProcessorEditor';

const TABLE_PAGINATION = {
  pageSize: 10,
  showSizeChanger: false,
  hideOnSinglePage: true,
};

function stringifyJson(value: unknown, fallback: string) {
  try {
    return JSON.stringify(value ?? JSON.parse(fallback), null, 2);
  } catch {
    return fallback;
  }
}

function parseJsonField(value: string, fieldName: string) {
  if (!value.trim()) {
    return {};
  }
  try {
    return JSON.parse(value);
  } catch {
    throw new Error(`${fieldName} 必须是合法 JSON。`);
  }
}

function parseLooseValue(value: string): unknown {
  if (!value.trim()) {
    return '';
  }
  try {
    return JSON.parse(value);
  } catch {
    return value;
  }
}

function stringifyValue(value: unknown): string {
  if (typeof value === 'string') {
    return value;
  }
  if (value === null || value === undefined) {
    return '';
  }
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function mapToRows(value: Record<string, unknown> | undefined, prefix: string): KeyValueEditorRow[] {
  return Object.entries(value ?? {}).map(([field, entryValue], index) => ({
    key: `${prefix}-${field}-${index}`,
    field,
    value: stringifyValue(entryValue),
  }));
}

function rowsToHeaderMap(rows: KeyValueEditorRow[]): Record<string, string> {
  return rows.reduce<Record<string, string>>((result, row) => {
    const trimmedKey = row.field.trim();
    if (!trimmedKey) {
      return result;
    }
    result[trimmedKey] = row.value;
    return result;
  }, {});
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function rowsToObjectPayload(rows: KeyValueEditorRow[]): Record<string, unknown> {
  return rows.reduce<Record<string, unknown>>((result, row) => {
    const trimmedKey = row.field.trim();
    if (!trimmedKey) {
      return result;
    }
    result[trimmedKey] = parseLooseValue(row.value);
    return result;
  }, {});
}

const structuredMetadataKeys = ['category', 'precondition', 'priority', 'owner', 'tags', 'timeout_ms'] as const;

type StructuredMetadataForm = {
  category: string;
  precondition: string;
  priority: string;
  owner: string;
  tags: string;
  timeout_ms: string;
  metadata_extra_json: string;
};

function splitMetadata(metadata: Record<string, unknown> | undefined): StructuredMetadataForm {
  const source = metadata ?? {};
  const extras = Object.fromEntries(
    Object.entries(source).filter(([key]) => !structuredMetadataKeys.includes(key as (typeof structuredMetadataKeys)[number])),
  );
  const tagsValue = source.tags;
  return {
    category: typeof source.category === 'string' ? source.category : '',
    precondition: typeof source.precondition === 'string' ? source.precondition : '',
    priority: typeof source.priority === 'string' ? source.priority : '',
    owner: typeof source.owner === 'string' ? source.owner : '',
    tags: Array.isArray(tagsValue)
      ? tagsValue.map((item) => String(item)).join(', ')
      : typeof tagsValue === 'string'
        ? tagsValue
        : '',
    timeout_ms: source.timeout_ms === undefined || source.timeout_ms === null ? '' : String(source.timeout_ms),
    metadata_extra_json: JSON.stringify(extras, null, 2),
  };
}

function buildMetadataPayload(values: StructuredMetadataForm): Record<string, unknown> {
  const payload = parseJsonField(values.metadata_extra_json, '扩展元数据 JSON') as Record<string, unknown>;
  if (values.category.trim()) payload.category = values.category.trim();
  if (values.precondition.trim()) payload.precondition = values.precondition.trim();
  if (values.priority.trim()) payload.priority = values.priority.trim();
  if (values.owner.trim()) payload.owner = values.owner.trim();
  if (values.tags.trim()) payload.tags = values.tags.split(',').map((tag) => tag.trim()).filter(Boolean);
  if (values.timeout_ms.trim()) {
    const parsedTimeout = Number(values.timeout_ms.trim());
    if (!Number.isFinite(parsedTimeout) || parsedTimeout < 0) {
      throw new Error('超时时间必须是非负数字。');
    }
    payload.timeout_ms = parsedTimeout;
  }
  return payload;
}

function assertionRowsFromCase(apiCase: ApiCase): AssertionEditorRow[] {
  return (apiCase.assertions_json ?? []).map((item, index) => ({
    key: `${apiCase.id}-assertion-${index}`,
    type: String(item.type ?? 'status_code'),
    operator: String(item.operator ?? '=='),
    path: String(item.path ?? ''),
    header: String(item.header ?? item.target ?? ''),
    expected: item.expected === undefined ? '' : String(item.expected),
    enabled: item.enabled !== false,
  }));
}

function processorRowsFromCase(processors: Record<string, unknown>[], prefix: string): ProcessorEditorRow[] {
  return (processors ?? []).map((item, index) => ({
    key: `${prefix}-${index}`,
    type: String(item.type ?? 'set_variable'),
    enabled: item.enabled !== false,
    configText: stringifyJson(item.config ?? {}, '{}'),
    language: String(item.language ?? 'js'),
    code: String(item.code ?? ''),
  }));
}

function assertionRowsToPayload(rows: AssertionEditorRow[]) {
  return rows.map((row) => {
    const payload: Record<string, unknown> = {
      type: row.type,
      operator: row.operator,
      expected: parseLooseValue(row.expected),
      enabled: row.enabled,
    };
    if (row.type === 'json_path' && row.path) payload.path = row.path;
    if (row.type === 'header' && row.header) payload.header = row.header;
    return payload;
  });
}

function processorRowsToPayload(rows: ProcessorEditorRow[]) {
  return rows.map((row) => {
    if (row.type === 'script') {
      return { type: row.type, enabled: row.enabled, language: row.language || 'js', code: row.code, config: {} };
    }
    return { type: row.type, enabled: row.enabled, config: parseJsonField(row.configText, '处理器配置') };
  });
}

function assertionPayloadKey(assertion: Record<string, unknown>): string {
  return JSON.stringify({
    type: assertion.type ?? '',
    operator: assertion.operator ?? '',
    path: assertion.path ?? '',
    header: assertion.header ?? '',
    expected: assertion.expected ?? null,
  });
}

function assertionSuggestionToPayload(suggestion: AiAssertionSuggestion): Record<string, unknown> {
  const payload: Record<string, unknown> = {
    type: suggestion.type,
    operator: suggestion.operator,
    expected: suggestion.expected,
    enabled: suggestion.enabled,
  };
  if (suggestion.path) payload.path = suggestion.path;
  if (suggestion.header) payload.header = suggestion.header;
  return payload;
}

function mergeAssertionPayloads(existing: Record<string, unknown>[], suggestions: AiAssertionSuggestion[]): Record<string, unknown>[] {
  const seen = new Set(existing.map(assertionPayloadKey));
  const merged = [...existing];
  for (const suggestion of suggestions) {
    const payload = assertionSuggestionToPayload(suggestion);
    const key = assertionPayloadKey(payload);
    if (seen.has(key)) {
      continue;
    }
    merged.push(payload);
    seen.add(key);
  }
  return merged;
}

function normalizeCoverageHistoryResult(outputJson: Record<string, unknown>): AiCoverageResult {
  const missingDimensions = Array.isArray(outputJson.missing_dimensions) ? outputJson.missing_dimensions : [];
  const suggestedPoints = Array.isArray(outputJson.suggested_points) ? outputJson.suggested_points : [];
  return {
    coverage_score: Number(outputJson.coverage_score ?? 0),
    missing_dimensions: missingDimensions.map((item, index) => {
      const entry = item as Record<string, unknown>;
      return {
        endpoint: String(entry.endpoint ?? `unknown-endpoint-${index}`),
        dimension: String(entry.dimension ?? 'unknown'),
        reason: String(entry.reason ?? ''),
      };
    }),
    suggested_points: suggestedPoints.map((item, index) => {
      const entry = item as Record<string, unknown>;
      return {
        title: String(entry.title ?? `coverage-point-${index}`),
        category: String(entry.category ?? 'unknown'),
        priority: String(entry.priority ?? 'medium'),
        reason: String(entry.reason ?? ''),
      };
    }),
  };
}

function coverageLabel(value: string): string {
  const labels: Record<string, string> = {
    happy_path: '主流程',
    negative_path: '异常流程',
    boundary_path: '边界场景',
    auth: '鉴权场景',
    idempotent: '幂等场景',
    pagination: '分页场景',
    assertion_hardening: '断言加固',
    status: '状态码断言',
    business_code: '业务码断言',
    body_field: '响应字段断言',
    schema: '响应结构断言',
    latency: '时延断言',
    project: '项目',
    suite: '套件',
    draft: '草稿',
    accepted: '已接受',
    rejected: '已拒绝',
    applied: '已应用',
    superseded: '已替代',
  };
  return labels[value] ?? value;
}

function assertionTypeLabel(value: string): string {
  const labels: Record<string, string> = {
    status_code: '状态码断言',
    json_path: 'JSON 路径断言',
    header: '请求头断言',
  };
  return labels[value] ?? value;
}

function assertionOperatorLabel(value: string): string {
  const labels: Record<string, string> = {
    '==': '等于',
    contains: '包含',
    not_null: '非空',
    schema: '结构匹配',
    matches_schema: '结构匹配',
  };
  return labels[value] ?? value;
}

function buildCoveragePromptSeed(result: AiCoverageResult): string {
  const suggestionLines = result.suggested_points.map((item) => `- ${item.title}: ${item.reason}`);
  const gapLines = result.missing_dimensions
    .slice(0, 5)
    .map((item) => `- ${item.endpoint} 缺少${coverageLabel(item.dimension)}: ${item.reason}`);
  return ['请优先补齐以下 coverage 缺口：', ...suggestionLines, ...gapLines].join('\n').trim();
}

function downloadBlob(blob: Blob, filename: string) {
  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  window.URL.revokeObjectURL(url);
}

function normalizeSavedTestDataVariants(apiCase: ApiCase | null): AiTestDataResult['data_variants'] {
  const rawItems = Array.isArray(apiCase?.metadata_json?.ai_test_data_variants) ? apiCase?.metadata_json.ai_test_data_variants : [];
  return rawItems.reduce<AiTestDataResult['data_variants']>((result, item, index) => {
    if (!item || typeof item !== 'object') {
      return result;
    }
    const entry = item as Record<string, unknown>;
    result.push({
      variant_id: String(entry.variant_id ?? `saved-variant-${index}`),
      name: String(entry.name ?? 'unnamed_variant'),
      category: String(entry.category ?? 'unknown'),
      payload_patch: typeof entry.payload_patch === 'object' && entry.payload_patch !== null ? (entry.payload_patch as Record<string, unknown>) : {},
      target_fields: Array.isArray(entry.target_fields) ? entry.target_fields.map((field) => String(field)) : [],
      reason: String(entry.reason ?? ''),
      suggested_assertions: Array.isArray(entry.suggested_assertions)
        ? entry.suggested_assertions.filter((assertion): assertion is Record<string, unknown> => Boolean(assertion && typeof assertion === 'object'))
        : [],
      confidence: Number(entry.confidence ?? 0),
    });
    return result;
  }, []);
}

function normalizeSavedMockTemplates(apiCase: ApiCase | null): AiMockResult['mock_templates'] {
  const rawItems = Array.isArray(apiCase?.metadata_json?.ai_mock_templates) ? apiCase?.metadata_json.ai_mock_templates : [];
  return rawItems.reduce<AiMockResult['mock_templates']>((result, item, index) => {
    if (!item || typeof item !== 'object') {
      return result;
    }
    const entry = item as Record<string, unknown>;
    result.push({
      template_id: String(entry.template_id ?? `saved-template-${index}`),
      scenario_name: String(entry.scenario_name ?? 'unnamed_template'),
      status_code: Number(entry.status_code ?? 200),
      response_template: typeof entry.response_template === 'object' && entry.response_template !== null ? (entry.response_template as Record<string, unknown>) : {},
      mock_rules: Array.isArray(entry.mock_rules)
        ? entry.mock_rules.filter((rule): rule is Record<string, unknown> => Boolean(rule && typeof rule === 'object'))
        : [],
      reason: String(entry.reason ?? ''),
      confidence: Number(entry.confidence ?? 0),
    });
    return result;
  }, []);
}

export function WorkspacePage() {
  const { token, user } = useAuth();
  const api = useMemo(() => createApi(token), [token]);
  const { message } = App.useApp();
  const canEdit = canManageWorkspace(user);
  const [projects, setProjects] = useState<Project[]>([]);
  const [suites, setSuites] = useState<Suite[]>([]);
  const [cases, setCases] = useState<ApiCase[]>([]);
  const [editingProjectId, setEditingProjectId] = useState<number | null>(null);
  const [editingSuiteId, setEditingSuiteId] = useState<number | null>(null);
  const [editingCaseId, setEditingCaseId] = useState<number | null>(null);
  const [importProjectId, setImportProjectId] = useState<number | null>(null);
  const [importFileList, setImportFileList] = useState<UploadFile[]>([]);
  const [legacyImportProjectId, setLegacyImportProjectId] = useState<number | null>(null);
  const [legacyImportFileList, setLegacyImportFileList] = useState<UploadFile[]>([]);
  const [projectKeyword, setProjectKeyword] = useState('');
  const [suiteKeyword, setSuiteKeyword] = useState('');
  const [suiteProjectFilter, setSuiteProjectFilter] = useState<number | undefined>(undefined);
  const [caseKeyword, setCaseKeyword] = useState('');
  const [caseSuiteFilter, setCaseSuiteFilter] = useState<number | undefined>(undefined);
  const [caseMethodFilter, setCaseMethodFilter] = useState<string | undefined>(undefined);
  const [isCaseEditorVisible, setIsCaseEditorVisible] = useState(false);
  const [headerRows, setHeaderRows] = useState<KeyValueEditorRow[]>([]);
  const [bodyMode, setBodyMode] = useState<'structured' | 'raw'>('structured');
  const [bodyRows, setBodyRows] = useState<KeyValueEditorRow[]>([]);
  const [assertionRows, setAssertionRows] = useState<AssertionEditorRow[]>([]);
  const [preProcessorRows, setPreProcessorRows] = useState<ProcessorEditorRow[]>([]);
  const [postProcessorRows, setPostProcessorRows] = useState<ProcessorEditorRow[]>([]);
  const [assertionPreview, setAssertionPreview] = useState<AiCopilotPreview<AiAssertionResult> | null>(null);
  const [assertionLoading, setAssertionLoading] = useState(false);
  const [assertionApplyLoading, setAssertionApplyLoading] = useState(false);
  const [assertionError, setAssertionError] = useState<string | null>(null);
  const [testDataPreview, setTestDataPreview] = useState<AiCopilotPreview<AiTestDataResult> | null>(null);
  const [testDataSelectedIds, setTestDataSelectedIds] = useState<string[]>([]);
  const [testDataLoading, setTestDataLoading] = useState(false);
  const [testDataApplyLoading, setTestDataApplyLoading] = useState(false);
  const [testDataExportLoading, setTestDataExportLoading] = useState(false);
  const [testDataError, setTestDataError] = useState<string | null>(null);
  const [testDataHistoryOpen, setTestDataHistoryOpen] = useState(false);
  const [testDataHistoryLoading, setTestDataHistoryLoading] = useState(false);
  const [testDataHistoryError, setTestDataHistoryError] = useState<string | null>(null);
  const [testDataHistory, setTestDataHistory] = useState<AiArtifactHistoryItem[]>([]);
  const [mockPreview, setMockPreview] = useState<AiCopilotPreview<AiMockResult> | null>(null);
  const [mockSelectedIds, setMockSelectedIds] = useState<string[]>([]);
  const [mockLoading, setMockLoading] = useState(false);
  const [mockApplyLoading, setMockApplyLoading] = useState(false);
  const [mockExportLoading, setMockExportLoading] = useState(false);
  const [mockError, setMockError] = useState<string | null>(null);
  const [mockHistoryOpen, setMockHistoryOpen] = useState(false);
  const [mockHistoryLoading, setMockHistoryLoading] = useState(false);
  const [mockHistoryError, setMockHistoryError] = useState<string | null>(null);
  const [mockHistory, setMockHistory] = useState<AiArtifactHistoryItem[]>([]);
  const [designProjectId, setDesignProjectId] = useState<number | null>(null);
  const [designSuiteId, setDesignSuiteId] = useState<number | null>(null);
  const [coveragePreview, setCoveragePreview] = useState<AiCopilotPreview<AiCoverageResult> | null>(null);
  const [coverageLoading, setCoverageLoading] = useState(false);
  const [coverageError, setCoverageError] = useState<string | null>(null);
  const [coverageHistoryOpen, setCoverageHistoryOpen] = useState(false);
  const [coverageHistoryLoading, setCoverageHistoryLoading] = useState(false);
  const [coverageHistoryError, setCoverageHistoryError] = useState<string | null>(null);
  const [coverageHistory, setCoverageHistory] = useState<AiArtifactHistoryItem[]>([]);
  const [coveragePromptSeed, setCoveragePromptSeed] = useState('');
  const [executionPreparationVariantIds, setExecutionPreparationVariantIds] = useState<string[]>([]);
  const [executionPreparationTemplateIds, setExecutionPreparationTemplateIds] = useState<string[]>([]);
  const [executionPreparationEnvironmentId, setExecutionPreparationEnvironmentId] = useState<number | null>(null);
  const [executionPreparationLoading, setExecutionPreparationLoading] = useState(false);
  const [executionPreparationError, setExecutionPreparationError] = useState<string | null>(null);
  const [executionPreparationResult, setExecutionPreparationResult] = useState<Execution | null>(null);
  const [lineageOpen, setLineageOpen] = useState(false);
  const [lineageLoading, setLineageLoading] = useState(false);
  const [lineageError, setLineageError] = useState<string | null>(null);
  const [lineageData, setLineageData] = useState<AiArtifactLineage | null>(null);
  const [lineageTitle, setLineageTitle] = useState('AI Artifact Lineage');
  const [projectForm] = Form.useForm<{ name: string; description: string }>();
  const [suiteForm] = Form.useForm<{ project_id: number; name: string; description: string }>();
  const [caseForm] = Form.useForm<{
    suite_id: number;
    name: string;
    method: string;
    url: string;
    description: string;
    body_json: string;
    category: string;
    precondition: string;
    priority: string;
    owner: string;
    tags: string;
    timeout_ms: string;
    metadata_extra_json: string;
  }>();
  const editingCase = useMemo(() => cases.find((item) => item.id === editingCaseId) ?? null, [cases, editingCaseId]);
  const editingSuite = useMemo(() => suites.find((item) => item.id === editingCase?.suite_id) ?? null, [suites, editingCase]);
  const editingProject = useMemo(() => projects.find((item) => item.id === editingSuite?.project_id) ?? null, [projects, editingSuite]);
  const suiteNameById = useMemo(() => new Map(suites.map((suite) => [suite.id, suite.name])), [suites]);
  const suiteProjectIdById = useMemo(() => new Map(suites.map((suite) => [suite.id, suite.project_id])), [suites]);
  const projectNameById = useMemo(() => new Map(projects.map((project) => [project.id, project.name])), [projects]);
  const filteredProjects = useMemo(() => {
    const keyword = projectKeyword.trim().toLowerCase();
    if (!keyword) {
      return projects;
    }
    return projects.filter(
      (project) =>
        project.name.toLowerCase().includes(keyword) ||
        project.description.toLowerCase().includes(keyword),
    );
  }, [projectKeyword, projects]);
  const filteredSuites = useMemo(() => {
    const keyword = suiteKeyword.trim().toLowerCase();
    return suites.filter((suite) => {
      const matchesProject = suiteProjectFilter === undefined || suite.project_id === suiteProjectFilter;
      const matchesKeyword =
        !keyword ||
        suite.name.toLowerCase().includes(keyword) ||
        suite.description.toLowerCase().includes(keyword);
      return matchesProject && matchesKeyword;
    });
  }, [suiteKeyword, suiteProjectFilter, suites]);
  const filteredCases = useMemo(() => {
    const keyword = caseKeyword.trim().toLowerCase();
    return cases.filter((apiCase) => {
      const matchesSuite = caseSuiteFilter === undefined || apiCase.suite_id === caseSuiteFilter;
      const matchesMethod = !caseMethodFilter || apiCase.method === caseMethodFilter;
      const matchesKeyword =
        !keyword ||
        apiCase.name.toLowerCase().includes(keyword) ||
        apiCase.url.toLowerCase().includes(keyword) ||
        apiCase.description.toLowerCase().includes(keyword);
      return matchesSuite && matchesMethod && matchesKeyword;
    });
  }, [caseKeyword, caseMethodFilter, caseSuiteFilter, cases]);
  const editingEnvironments = useMemo(() => editingProject?.environments ?? [], [editingProject]);
  const savedTestDataVariants = useMemo(() => normalizeSavedTestDataVariants(editingCase), [editingCase]);
  const savedMockTemplates = useMemo(() => normalizeSavedMockTemplates(editingCase), [editingCase]);
  const executionAvailableVariants = useMemo(
    () => (testDataPreview?.result.data_variants.length ? testDataPreview.result.data_variants : savedTestDataVariants),
    [savedTestDataVariants, testDataPreview],
  );
  const executionAvailableTemplates = useMemo(
    () => (mockPreview?.result.mock_templates.length ? mockPreview.result.mock_templates : savedMockTemplates),
    [mockPreview, savedMockTemplates],
  );
  const savedAssertions = useMemo(
    () => ((editingCase?.assertions_json ?? []).filter((item): item is Record<string, unknown> => Boolean(item && typeof item === 'object'))),
    [editingCase],
  );
  const suggestedAssertions = assertionPreview?.result.suggested_assertions ?? [];
  const appendPreviewAssertions = useMemo(() => mergeAssertionPayloads(savedAssertions, suggestedAssertions), [savedAssertions, suggestedAssertions]);
  const unsavedAssertionChanges =
    JSON.stringify(assertionRowsToPayload(assertionRows)) !== JSON.stringify(editingCase?.assertions_json ?? []);

  function syncEditingCaseMetadata(apiCase: ApiCase) {
    const metadataFields = splitMetadata(apiCase.metadata_json);
    caseForm.setFieldsValue({
      category: metadataFields.category,
      precondition: metadataFields.precondition,
      priority: metadataFields.priority,
      owner: metadataFields.owner,
      tags: metadataFields.tags,
      timeout_ms: metadataFields.timeout_ms,
      metadata_extra_json: metadataFields.metadata_extra_json,
    });
  }

  async function refresh() {
    const [nextProjects, nextSuites, nextCases] = await Promise.all([api.listProjects(), api.listSuites(), api.listCases()]);
    setProjects(nextProjects);
    setSuites(nextSuites);
    setCases(nextCases);
  }

  useEffect(() => {
    void refresh();
  }, [api]);

  useEffect(() => {
    if (designProjectId !== null) {
      return;
    }
    if (projects.length) {
      setDesignProjectId(projects[0].id);
    }
  }, [projects, designProjectId]);

  useEffect(() => {
    if (designSuiteId === null) {
      return;
    }
    if (!suites.some((suite) => suite.id === designSuiteId && suite.project_id === designProjectId)) {
      setDesignSuiteId(null);
    }
  }, [designProjectId, designSuiteId, suites]);

  useEffect(() => {
    if (suiteProjectFilter !== undefined && !projects.some((project) => project.id === suiteProjectFilter)) {
      setSuiteProjectFilter(undefined);
    }
  }, [projects, suiteProjectFilter]);

  useEffect(() => {
    if (caseSuiteFilter !== undefined && !suites.some((suite) => suite.id === caseSuiteFilter)) {
      setCaseSuiteFilter(undefined);
    }
  }, [caseSuiteFilter, suites]);

  useEffect(() => {
    setExecutionPreparationVariantIds(executionAvailableVariants.map((item) => item.variant_id));
    setExecutionPreparationTemplateIds(executionAvailableTemplates.map((item) => item.template_id));
    setExecutionPreparationEnvironmentId(null);
    setExecutionPreparationResult(null);
    setExecutionPreparationError(null);
  }, [editingCaseId, executionAvailableTemplates, executionAvailableVariants]);

  function resetProjectForm() {
    setEditingProjectId(null);
    projectForm.resetFields();
  }

  function resetSuiteForm() {
    setEditingSuiteId(null);
    suiteForm.resetFields();
  }

  function resetCaseForm(closeEditor = false) {
    setEditingCaseId(null);
    if (closeEditor) {
      setIsCaseEditorVisible(false);
    }
    caseForm.setFieldsValue({
      method: 'GET',
      body_json: '{}',
      description: '',
      category: '',
      precondition: '',
      priority: '',
      owner: '',
      tags: '',
      timeout_ms: '',
      metadata_extra_json: '{}',
    });
    setHeaderRows([]);
    setBodyMode('structured');
    setBodyRows([]);
    setAssertionRows([]);
    setPreProcessorRows([]);
    setPostProcessorRows([]);
    setAssertionPreview(null);
    setAssertionError(null);
    setTestDataPreview(null);
    setTestDataSelectedIds([]);
    setTestDataError(null);
    setTestDataHistory([]);
    setTestDataHistoryError(null);
    setTestDataHistoryOpen(false);
    setMockPreview(null);
    setMockSelectedIds([]);
    setMockError(null);
    setMockHistory([]);
    setMockHistoryError(null);
    setMockHistoryOpen(false);
  }

  useEffect(() => {
    resetCaseForm();
  }, []);

  function handleStartCreateCase() {
    resetCaseForm();
    setIsCaseEditorVisible(true);
  }

  async function submitProject(values: { name: string; description: string }) {
    if (editingProjectId === null) {
      await api.createProject(values);
      message.success('项目已创建。');
    } else {
      await api.updateProject(editingProjectId, values);
      message.success('项目已更新。');
    }
    resetProjectForm();
    await refresh();
  }

  async function submitSuite(values: { project_id: number; name: string; description: string }) {
    if (editingSuiteId === null) {
      await api.createSuite(values);
      message.success('套件已创建。');
    } else {
      await api.updateSuite(editingSuiteId, values);
      message.success('套件已更新。');
    }
    resetSuiteForm();
    await refresh();
  }

  async function submitCase(values: {
    suite_id: number;
    name: string;
    method: string;
    url: string;
    description: string;
    body_json: string;
    category: string;
    precondition: string;
    priority: string;
    owner: string;
    tags: string;
    timeout_ms: string;
    metadata_extra_json: string;
  }) {
    const payload = {
      suite_id: values.suite_id,
      name: values.name,
      method: values.method,
      url: values.url,
      description: values.description,
      headers_json: rowsToHeaderMap(headerRows),
      body_json: bodyMode === 'structured' ? rowsToObjectPayload(bodyRows) : parseJsonField(values.body_json, '请求体 JSON'),
      assertions_json: assertionRowsToPayload(assertionRows),
      pre_processors_json: processorRowsToPayload(preProcessorRows),
      post_processors_json: processorRowsToPayload(postProcessorRows),
      metadata_json: buildMetadataPayload(values),
    };
    if (editingCaseId === null) {
      await api.createCase(payload);
      message.success('用例已创建。');
    } else {
      await api.updateCase(editingCaseId, payload);
      message.success('用例已更新。');
    }
    resetCaseForm(true);
    await refresh();
  }

  async function handleExcelImport() {
    if (!importProjectId || importFileList.length === 0 || !importFileList[0].originFileObj) {
      message.warning('请先选择目标项目和 Excel 文件。');
      return;
    }
    const result = await api.importExcel(importProjectId, importFileList[0].originFileObj);
    message.success(`已导入 ${result.created_cases} 条用例到套件 ${result.suite_name}。`);
    setImportFileList([]);
    await refresh();
  }

  async function handleLegacyProjectImport() {
    if (!legacyImportProjectId || legacyImportFileList.length === 0 || !legacyImportFileList[0].originFileObj) {
      message.warning('请先选择目标项目和桌面端 project.json 文件。');
      return;
    }
    const result = await api.importLegacyProject(legacyImportProjectId, legacyImportFileList[0].originFileObj);
    message.success(
      `已导入 ${result.created_suites} 个套件、${result.created_cases} 条用例、${result.created_environments} 个环境和 ${result.created_executions} 条执行记录。`,
    );
    setLegacyImportFileList([]);
    await refresh();
  }

  async function handlePreviewAssertions() {
    if (editingCaseId === null) {
      message.warning('AI 补断言只支持已保存的用例。');
      return;
    }
    setAssertionLoading(true);
    setAssertionError(null);
    try {
      const result = await api.previewAiAssertions({ case_id: editingCaseId });
      setAssertionPreview(result);
      if (result.result.suggested_assertions.length) {
        message.success('AI 补断言建议已生成。');
      } else {
        message.warning('AI 没有生成新的断言建议。');
      }
    } catch (error) {
      const nextError = error instanceof Error ? error.message : '生成 AI 补断言失败。';
      setAssertionError(nextError);
      message.error(nextError);
    } finally {
      setAssertionLoading(false);
    }
  }

  async function handleApplyAssertions(overrideExisting: boolean) {
    if (!assertionPreview) {
      return;
    }
    setAssertionApplyLoading(true);
    setAssertionError(null);
    try {
      const updatedCase = await api.applyAiAssertions(assertionPreview.artifact_id, { override_existing: overrideExisting });
      setCases((current) => current.map((item) => (item.id === updatedCase.id ? updatedCase : item)));
      if (updatedCase.id === editingCaseId) {
        setAssertionRows(assertionRowsFromCase(updatedCase));
      }
      setAssertionPreview((current) => (current ? { ...current, status: 'applied' } : current));
      message.success(overrideExisting ? 'AI 断言建议已覆盖应用。' : 'AI 断言建议已追加应用。');
    } catch (error) {
      const nextError = error instanceof Error ? error.message : '应用 AI 断言失败。';
      setAssertionError(nextError);
      message.error(nextError);
    } finally {
      setAssertionApplyLoading(false);
    }
  }

  async function handlePreviewTestData() {
    if (editingCaseId === null) {
      message.warning('AI 测试数据只支持已保存的用例。');
      return;
    }
    setTestDataLoading(true);
    setTestDataError(null);
    try {
      const result = await api.previewAiTestData({ case_id: editingCaseId });
      setTestDataPreview(result);
      setTestDataSelectedIds(result.result.data_variants.map((item) => item.variant_id));
      if (result.result.data_variants.length) {
        message.success('AI 测试数据变体已生成。');
      } else {
        message.warning('AI 没有生成新的测试数据变体。');
      }
    } catch (error) {
      const nextError = error instanceof Error ? error.message : '生成 AI 测试数据失败。';
      setTestDataError(nextError);
      message.error(nextError);
    } finally {
      setTestDataLoading(false);
    }
  }

  async function handleOpenTestDataHistory() {
    if (editingCaseId === null) {
      message.warning('请先选择已保存的用例。');
      return;
    }
    setTestDataHistoryOpen(true);
    setTestDataHistoryLoading(true);
    setTestDataHistoryError(null);
    try {
      const result = await api.listAiTestDataHistory(editingCaseId);
      setTestDataHistory(result.items);
    } catch (error) {
      setTestDataHistoryError(error instanceof Error ? error.message : '加载 AI 测试数据历史失败。');
    } finally {
      setTestDataHistoryLoading(false);
    }
  }

  async function handleApplyTestData(overrideExisting: boolean) {
    if (!testDataPreview) {
      return;
    }
    setTestDataApplyLoading(true);
    setTestDataError(null);
    try {
      const updatedCase = await api.applyAiTestData(testDataPreview.artifact_id, {
        selected_variant_ids: testDataSelectedIds,
        override_existing: overrideExisting,
      });
      setCases((current) => current.map((item) => (item.id === updatedCase.id ? updatedCase : item)));
      if (updatedCase.id === editingCaseId) {
        syncEditingCaseMetadata(updatedCase);
      }
      setTestDataPreview((current) => (current ? { ...current, status: 'applied' } : current));
      message.success(overrideExisting ? 'AI 测试数据已覆盖应用。' : 'AI 测试数据已追加应用。');
    } catch (error) {
      const nextError = error instanceof Error ? error.message : '应用 AI 测试数据失败。';
      setTestDataError(nextError);
      message.error(nextError);
    } finally {
      setTestDataApplyLoading(false);
    }
  }

  async function handleExportTestData() {
    if (!testDataPreview) {
      return;
    }
    setTestDataExportLoading(true);
    setTestDataError(null);
    try {
      const blob = await api.exportAiTestData(testDataPreview.artifact_id);
      downloadBlob(blob, `ai-test-data-${testDataPreview.artifact_id}.json`);
      message.success('AI 测试数据 JSON 已导出。');
    } catch (error) {
      const nextError = error instanceof Error ? error.message : '导出 AI 测试数据失败。';
      setTestDataError(nextError);
      message.error(nextError);
    } finally {
      setTestDataExportLoading(false);
    }
  }

  async function handlePreviewMock() {
    if (editingCaseId === null) {
      message.warning('AI Mock 只支持已保存的用例。');
      return;
    }
    setMockLoading(true);
    setMockError(null);
    try {
      const result = await api.previewAiMock({ case_id: editingCaseId });
      setMockPreview(result);
      setMockSelectedIds(result.result.mock_templates.map((item) => item.template_id));
      if (result.result.mock_templates.length) {
        message.success('AI Mock 模板已生成。');
      } else {
        message.warning('AI 没有生成新的 Mock 模板。');
      }
    } catch (error) {
      const nextError = error instanceof Error ? error.message : '生成 AI Mock 失败。';
      setMockError(nextError);
      message.error(nextError);
    } finally {
      setMockLoading(false);
    }
  }

  async function handleOpenMockHistory() {
    if (editingCaseId === null) {
      message.warning('请先选择已保存的用例。');
      return;
    }
    setMockHistoryOpen(true);
    setMockHistoryLoading(true);
    setMockHistoryError(null);
    try {
      const result = await api.listAiMockHistory(editingCaseId);
      setMockHistory(result.items);
    } catch (error) {
      setMockHistoryError(error instanceof Error ? error.message : '加载 AI Mock 历史失败。');
    } finally {
      setMockHistoryLoading(false);
    }
  }

  async function handleApplyMock(overrideExisting: boolean) {
    if (!mockPreview) {
      return;
    }
    setMockApplyLoading(true);
    setMockError(null);
    try {
      const updatedCase = await api.applyAiMock(mockPreview.artifact_id, {
        selected_template_ids: mockSelectedIds,
        override_existing: overrideExisting,
      });
      setCases((current) => current.map((item) => (item.id === updatedCase.id ? updatedCase : item)));
      if (updatedCase.id === editingCaseId) {
        syncEditingCaseMetadata(updatedCase);
      }
      setMockPreview((current) => (current ? { ...current, status: 'applied' } : current));
      message.success(overrideExisting ? 'AI Mock 模板已覆盖应用。' : 'AI Mock 模板已追加应用。');
    } catch (error) {
      const nextError = error instanceof Error ? error.message : '应用 AI Mock 失败。';
      setMockError(nextError);
      message.error(nextError);
    } finally {
      setMockApplyLoading(false);
    }
  }

  async function handleRunPreparedExecution() {
    if (editingCaseId === null) {
      return;
    }
    setExecutionPreparationLoading(true);
    setExecutionPreparationError(null);
    try {
      const execution = await api.runExecution({
        scope: 'case',
        target_id: editingCaseId,
        environment_id: executionPreparationEnvironmentId ?? undefined,
        ai_preparation: {
          selected_test_data_variant_ids: executionPreparationVariantIds,
          selected_mock_template_ids: executionPreparationTemplateIds,
        },
      });
      setExecutionPreparationResult(execution);
      message.success(`已触发 case execution #${execution.id}。`);
    } catch (error) {
      const nextError = error instanceof Error ? error.message : '执行 AI 准备后的用例失败。';
      setExecutionPreparationError(nextError);
      message.error(nextError);
    } finally {
      setExecutionPreparationLoading(false);
    }
  }

  async function handleExportMock() {
    if (!mockPreview) {
      return;
    }
    setMockExportLoading(true);
    setMockError(null);
    try {
      const blob = await api.exportAiMock(mockPreview.artifact_id);
      downloadBlob(blob, `ai-mock-${mockPreview.artifact_id}.json`);
      message.success('AI Mock JSON 已导出。');
    } catch (error) {
      const nextError = error instanceof Error ? error.message : '导出 AI Mock 失败。';
      setMockError(nextError);
      message.error(nextError);
    } finally {
      setMockExportLoading(false);
    }
  }

  async function handleScanCoverage() {
    if (!designProjectId && !designSuiteId) {
      message.warning('请先选择 coverage 扫描目标。');
      return;
    }
    setCoverageLoading(true);
    setCoverageError(null);
    try {
      const result = await api.scanAiCoverage({
        project_id: designSuiteId ? undefined : designProjectId ?? undefined,
        suite_id: designSuiteId ?? undefined,
      });
      setCoveragePreview(result);
      message.success('AI coverage 扫描已生成。');
    } catch (error) {
      const nextError = error instanceof Error ? error.message : 'AI coverage 扫描失败。';
      setCoverageError(nextError);
      message.error(nextError);
    } finally {
      setCoverageLoading(false);
    }
  }

  async function handleOpenCoverageHistory() {
    const targetType = designSuiteId ? 'suite' : 'project';
    const targetId = designSuiteId ?? designProjectId;
    if (!targetId) {
      message.warning('请先选择 coverage 历史的 target。');
      return;
    }
    setCoverageHistoryOpen(true);
    setCoverageHistoryLoading(true);
    setCoverageHistoryError(null);
    try {
      const result = await api.listAiCoverageHistory(targetType, targetId);
      setCoverageHistory(result.items);
    } catch (error) {
      setCoverageHistoryError(error instanceof Error ? error.message : '加载 coverage 历史失败。');
    } finally {
      setCoverageHistoryLoading(false);
    }
  }

  function handleTransferCoverageToPrompt() {
    if (!coveragePreview) {
      return;
    }
    setCoveragePromptSeed(buildCoveragePromptSeed(coveragePreview.result));
    message.success('已把 coverage 缺口带入测试点提示词。');
  }

  function applyCoverageHistoryItem(item: AiArtifactHistoryItem) {
    setCoveragePreview({
      artifact_id: item.artifact_id,
      capability: 'coverage',
      status: item.status,
      warnings: item.warnings_json,
      result: normalizeCoverageHistoryResult(item.output_json),
    });
    setCoverageHistoryOpen(false);
  }

  function applyTestDataHistoryItem(item: AiArtifactHistoryItem, result: AiTestDataResult) {
    setTestDataPreview({
      artifact_id: item.artifact_id,
      capability: 'test_data',
      status: item.status,
      warnings: item.warnings_json,
      result,
    });
    setTestDataSelectedIds(result.data_variants.map((entry) => entry.variant_id));
    setTestDataHistoryOpen(false);
  }

  function applyMockHistoryItem(item: AiArtifactHistoryItem, result: AiMockResult) {
    setMockPreview({
      artifact_id: item.artifact_id,
      capability: 'mock',
      status: item.status,
      warnings: item.warnings_json,
      result,
    });
    setMockSelectedIds(result.mock_templates.map((entry) => entry.template_id));
    setMockHistoryOpen(false);
  }

  async function handleViewLineage(item: AiArtifactHistoryItem) {
    setLineageOpen(true);
    setLineageLoading(true);
    setLineageError(null);
    setLineageTitle(`Artifact ${item.artifact_id.slice(0, 8)} Lineage`);
    try {
      const result = await api.getAiArtifactLineage(item.artifact_id);
      setLineageData(result);
    } catch (error) {
      const nextError = error instanceof Error ? error.message : '加载 lineage 失败。';
      setLineageError(nextError);
      message.error(nextError);
    } finally {
      setLineageLoading(false);
    }
  }

  function loadCaseIntoEditor(apiCase: ApiCase) {
    setIsCaseEditorVisible(true);
    const caseBodyText = stringifyJson(apiCase.body_json, '{}');
    const caseBodyMode = isPlainObject(apiCase.body_json) ? 'structured' : 'raw';
    const metadataFields = splitMetadata(apiCase.metadata_json);
    setEditingCaseId(apiCase.id);
    caseForm.setFieldsValue({
      suite_id: apiCase.suite_id,
      name: apiCase.name,
      method: apiCase.method,
      url: apiCase.url,
      description: apiCase.description,
      body_json: caseBodyText,
      category: metadataFields.category,
      precondition: metadataFields.precondition,
      priority: metadataFields.priority,
      owner: metadataFields.owner,
      tags: metadataFields.tags,
      timeout_ms: metadataFields.timeout_ms,
      metadata_extra_json: metadataFields.metadata_extra_json,
    });
    setHeaderRows(mapToRows(apiCase.headers_json, `headers-${apiCase.id}`));
    setBodyMode(caseBodyMode);
    setBodyRows(caseBodyMode === 'structured' && isPlainObject(apiCase.body_json) ? mapToRows(apiCase.body_json, `body-${apiCase.id}`) : []);
    setAssertionRows(assertionRowsFromCase(apiCase));
    setPreProcessorRows(processorRowsFromCase(apiCase.pre_processors_json, `pre-${apiCase.id}`));
    setPostProcessorRows(processorRowsFromCase(apiCase.post_processors_json, `post-${apiCase.id}`));
    setAssertionPreview(null);
    setAssertionError(null);
    setTestDataPreview(null);
    setTestDataSelectedIds([]);
    setTestDataError(null);
    setTestDataHistory([]);
    setTestDataHistoryError(null);
    setTestDataHistoryOpen(false);
    setMockPreview(null);
    setMockSelectedIds([]);
    setMockError(null);
    setMockHistory([]);
    setMockHistoryError(null);
    setMockHistoryOpen(false);
  }

  function handleBodyModeChange(nextMode: string) {
    if (nextMode === bodyMode) return;
    if (nextMode === 'raw') {
      caseForm.setFieldValue('body_json', JSON.stringify(rowsToObjectPayload(bodyRows), null, 2));
      setBodyMode('raw');
      return;
    }

    const rawBodyText = String(caseForm.getFieldValue('body_json') ?? '').trim();
    if (!rawBodyText) {
      setBodyRows([]);
      setBodyMode('structured');
      caseForm.setFieldValue('body_json', '{}');
      return;
    }

    try {
      const parsedBody = JSON.parse(rawBodyText);
      if (!isPlainObject(parsedBody)) {
        message.warning('结构化请求体只支持 JSON 对象。');
        return;
      }
      setBodyRows(mapToRows(parsedBody, `body-${editingCaseId ?? 'new'}`));
      setBodyMode('structured');
    } catch {
      message.warning('切换到结构化模式前，请先保证原始请求体是合法 JSON。');
    }
  }

  return (
    <div className="page-stack">
      <div className="page-hero">
        <Typography.Title>工作台</Typography.Title>
      </div>

      <Tabs
        items={[
          {
            key: 'projects',
            label: '项目',
            children: (
              <Row gutter={[18, 18]}>
                <Col xs={24} xl={8}>
                  <Card className="glass-card" title={editingProjectId ? '编辑项目' : '新建项目'}>
                    <Form form={projectForm} layout="vertical" onFinish={(values) => void submitProject(values)} disabled={!canEdit}>
                      <Form.Item name="name" label="名称" rules={[{ required: true }]}>
                        <Input />
                      </Form.Item>
                      <Form.Item name="description" label="描述">
                        <Input.TextArea rows={4} />
                      </Form.Item>
                      <Space>
                        <Button type="primary" htmlType="submit" disabled={!canEdit}>
                          {editingProjectId ? '保存' : '创建'}
                        </Button>
                        <Button onClick={resetProjectForm}>重置</Button>
                      </Space>
                    </Form>
                  </Card>
                </Col>

                <Col xs={24} xl={16}>
                  <Card
                    className="glass-card"
                    title="项目列表"
                    extra={<Typography.Text type="secondary">{`共 ${filteredProjects.length} / ${projects.length} 个项目`}</Typography.Text>}
                  >
                    <div className="workspace-filter-bar">
                      <Input
                        allowClear
                        value={projectKeyword}
                        onChange={(event) => setProjectKeyword(event.target.value)}
                        placeholder="按项目名称或描述筛选"
                      />
                      <Button onClick={() => setProjectKeyword('')}>重置筛选</Button>
                    </div>
                    <Table<Project>
                      rowKey="id"
                      pagination={TABLE_PAGINATION}
                      dataSource={filteredProjects}
                      scroll={{ x: 900 }}
                      columns={[
                        { title: '项目', dataIndex: 'name' },
                        { title: '描述', dataIndex: 'description' },
                        { title: '套件数', render: (_, project) => project.suites.length },
                        { title: '环境数', render: (_, project) => project.environments.length },
                        {
                          title: '操作',
                          render: (_, project) => (
                            <Space>
                              <Button
                                size="small"
                                disabled={!canEdit}
                                onClick={() => {
                                  setEditingProjectId(project.id);
                                  projectForm.setFieldsValue({ name: project.name, description: project.description });
                                }}
                              >
                                编辑
                              </Button>
                              <Popconfirm title="确认删除项目？" disabled={!canEdit} onConfirm={() => void api.deleteProject(project.id).then(refresh)}>
                                <Button size="small" danger disabled={!canEdit}>
                                  删除
                                </Button>
                              </Popconfirm>
                            </Space>
                          ),
                        },
                      ]}
                    />
                  </Card>
                </Col>
              </Row>
            ),
          },
          {
            key: 'suites',
            label: '套件',
            children: (
              <Row gutter={[18, 18]}>
                <Col xs={24} xl={8}>
                  <Space direction="vertical" style={{ width: '100%' }} size="large">
                    <Card className="glass-card" title={editingSuiteId ? '编辑套件' : '新建套件'}>
                      <Form form={suiteForm} layout="vertical" onFinish={(values) => void submitSuite(values)} disabled={!canEdit}>
                        <Form.Item name="project_id" label="所属项目" rules={[{ required: true }]}>
                          <Select options={projects.map((project) => ({ value: project.id, label: project.name }))} />
                        </Form.Item>
                        <Form.Item name="name" label="名称" rules={[{ required: true }]}>
                          <Input />
                        </Form.Item>
                        <Form.Item name="description" label="描述">
                          <Input.TextArea rows={4} />
                        </Form.Item>
                        <Space>
                          <Button type="primary" htmlType="submit" disabled={!canEdit}>
                            {editingSuiteId ? '保存' : '创建'}
                          </Button>
                          <Button onClick={resetSuiteForm}>重置</Button>
                        </Space>
                      </Form>
                    </Card>

                    <Card className="glass-card" title="导入 Excel">
                      <Space direction="vertical" style={{ width: '100%' }}>
                        <Select
                          placeholder="选择目标项目"
                          value={importProjectId ?? undefined}
                          onChange={setImportProjectId}
                          options={projects.map((project) => ({ value: project.id, label: project.name }))}
                          disabled={!canEdit}
                        />
                        <Upload
                          beforeUpload={() => false}
                          maxCount={1}
                          fileList={importFileList}
                          onChange={({ fileList }) => setImportFileList(fileList)}
                          disabled={!canEdit}
                        >
                          <Button disabled={!canEdit}>选择 Excel</Button>
                        </Upload>
                        <Button type="primary" onClick={() => void handleExcelImport()} disabled={!canEdit}>
                          开始导入
                        </Button>
                      </Space>
                    </Card>

                    <Card className="glass-card" title="导入桌面端项目">
                      <Space direction="vertical" style={{ width: '100%' }}>
                        <Typography.Text type="secondary">
                          将旧版桌面端 `project.json` 树导入当前 Web 项目，加速桌面端资产迁移。
                        </Typography.Text>
                        <Select
                          placeholder="选择目标项目"
                          value={legacyImportProjectId ?? undefined}
                          onChange={setLegacyImportProjectId}
                          options={projects.map((project) => ({ value: project.id, label: project.name }))}
                          disabled={!canEdit}
                        />
                        <Upload
                          beforeUpload={() => false}
                          maxCount={1}
                          fileList={legacyImportFileList}
                          onChange={({ fileList }) => setLegacyImportFileList(fileList)}
                          disabled={!canEdit}
                        >
                          <Button disabled={!canEdit}>选择 project.json</Button>
                        </Upload>
                        <Button type="primary" onClick={() => void handleLegacyProjectImport()} disabled={!canEdit}>
                          开始导入
                        </Button>
                      </Space>
                    </Card>

                    <Card className="glass-card" title="AI 生成接口用例">
                      <Space direction="vertical" style={{ width: '100%' }} size="large">
                        <Space wrap style={{ width: '100%' }}>
                          <Select
                            placeholder="选择设计项目"
                            value={designProjectId ?? undefined}
                            onChange={setDesignProjectId}
                            options={projects.map((project) => ({ value: project.id, label: project.name }))}
                            disabled={!canEdit}
                            style={{ width: 200 }}
                          />
                          <Select
                            allowClear
                            placeholder="基于套件扫描/设计（可选）"
                            value={designSuiteId ?? undefined}
                            onChange={(value) => setDesignSuiteId(value ?? null)}
                            options={suites
                              .filter((suite) => !designProjectId || suite.project_id === designProjectId)
                              .map((suite) => ({ value: suite.id, label: suite.name }))}
                            disabled={!canEdit || !designProjectId}
                            style={{ width: 220 }}
                          />
                        </Space>
                        <AiCoveragePanel
                          targetLabel={designSuiteId ? `suite #${designSuiteId}` : designProjectId ? `project #${designProjectId}` : '未选择 target'}
                          preview={coveragePreview}
                          loading={coverageLoading}
                          error={coverageError}
                          onScan={() => void handleScanCoverage()}
                          onOpenHistory={() => void handleOpenCoverageHistory()}
                          onUseSuggestedPoints={handleTransferCoverageToPrompt}
                        />
                        <AiCaseGenerationPanel
                          api={api}
                          projects={projects}
                          suites={suites}
                          canEdit={canEdit}
                          onImported={refresh}
                          defaultProjectId={designProjectId}
                          defaultSuiteId={designSuiteId}
                          seedPromptHints={coveragePromptSeed}
                        />
                      </Space>
                    </Card>
                  </Space>
                </Col>

                <Col xs={24} xl={16}>
                  <Card
                    className="glass-card"
                    title="套件列表"
                    extra={<Typography.Text type="secondary">{`共 ${filteredSuites.length} / ${suites.length} 个套件`}</Typography.Text>}
                  >
                    <div className="workspace-filter-bar">
                      <Select
                        allowClear
                        value={suiteProjectFilter}
                        onChange={(value) => setSuiteProjectFilter(value)}
                        placeholder="按项目筛选"
                        options={projects.map((project) => ({ value: project.id, label: project.name }))}
                        style={{ width: 220 }}
                      />
                      <Input
                        allowClear
                        value={suiteKeyword}
                        onChange={(event) => setSuiteKeyword(event.target.value)}
                        placeholder="按套件名称或描述筛选"
                      />
                      <Button
                        onClick={() => {
                          setSuiteProjectFilter(undefined);
                          setSuiteKeyword('');
                        }}
                      >
                        重置筛选
                      </Button>
                    </div>
                    <Table<Suite>
                      rowKey="id"
                      pagination={TABLE_PAGINATION}
                      dataSource={filteredSuites}
                      scroll={{ x: 900 }}
                      columns={[
                        { title: '套件', dataIndex: 'name' },
                        { title: '所属项目', dataIndex: 'project_id', render: (value: number) => projectNameById.get(value) ?? `项目 #${value}` },
                        { title: '描述', dataIndex: 'description' },
                        { title: '用例数', render: (_, suite) => suite.cases.length },
                        {
                          title: '操作',
                          render: (_, suite) => (
                            <Space>
                              <Button
                                size="small"
                                disabled={!canEdit}
                                onClick={() => {
                                  setEditingSuiteId(suite.id);
                                  suiteForm.setFieldsValue({ project_id: suite.project_id, name: suite.name, description: suite.description });
                                }}
                              >
                                编辑
                              </Button>
                              <Popconfirm title="确认删除套件？" disabled={!canEdit} onConfirm={() => void api.deleteSuite(suite.id).then(refresh)}>
                                <Button size="small" danger disabled={!canEdit}>
                                  删除
                                </Button>
                              </Popconfirm>
                            </Space>
                          ),
                        },
                      ]}
                    />
                  </Card>
                </Col>
              </Row>
            ),
          },
          {
            key: 'cases',
            label: '用例',
            children: (
              <Space direction="vertical" size="large" style={{ width: '100%' }}>
                {isCaseEditorVisible ? (
                  <div>
                    <Card
                      className="glass-card workspace-section-card"
                      title={editingCaseId ? `编辑区 · ${editingCase?.name ?? `用例 #${editingCaseId}`}` : '编辑区 · 新建用例'}
                      extra={
                        <Space>
                          {editingCase ? (
                            <Typography.Text type="secondary">
                              {`${projectNameById.get(editingProject?.id ?? -1) ?? '未归属项目'} / ${suiteNameById.get(editingCase.suite_id) ?? `套件 #${editingCase.suite_id}`}`}
                            </Typography.Text>
                          ) : null}
                          <Button onClick={() => resetCaseForm(true)}>收起编辑区</Button>
                        </Space>
                      }
                    >
                      <Form form={caseForm} layout="vertical" onFinish={(values) => void submitCase(values)} disabled={!canEdit}>
                      <Form.Item name="suite_id" label="所属套件" rules={[{ required: true }]}>
                        <Select options={suites.map((suite) => ({ value: suite.id, label: suite.name }))} />
                      </Form.Item>
                      <Form.Item name="name" label="名称" rules={[{ required: true }]}>
                        <Input />
                      </Form.Item>
                      <Space.Compact block>
                        <Form.Item name="method" label="请求方法" initialValue="GET" style={{ width: 160 }}>
                          <Select options={['GET', 'POST', 'PUT', 'DELETE'].map((method) => ({ value: method, label: method }))} />
                        </Form.Item>
                        <Form.Item name="url" label="URL" rules={[{ required: true }]} style={{ flex: 1 }}>
                          <Input placeholder="/api/demo" />
                        </Form.Item>
                      </Space.Compact>
                      <Form.Item name="description" label="描述">
                        <Input.TextArea rows={2} />
                      </Form.Item>
                      <Form.Item label="请求头">
                        <KeyValueEditor
                          rows={headerRows}
                          onChange={setHeaderRows}
                          disabled={!canEdit}
                          addLabel="新增请求头"
                          keyPlaceholder="Content-Type"
                          valuePlaceholder="application/json"
                        />
                      </Form.Item>
                      <Form.Item label="请求体">
                        <Space direction="vertical" style={{ width: '100%' }}>
                          <Segmented
                            value={bodyMode}
                            onChange={(value) => handleBodyModeChange(String(value))}
                            options={[
                              { label: '结构化对象', value: 'structured' },
                              { label: '原始 JSON', value: 'raw' },
                            ]}
                            disabled={!canEdit}
                          />
                          {bodyMode === 'structured' ? (
                            <KeyValueEditor
                              rows={bodyRows}
                              onChange={setBodyRows}
                              disabled={!canEdit}
                              addLabel="新增字段"
                              keyPlaceholder="name"
                              valuePlaceholder={'123、true 或 "text"'}
                            />
                          ) : (
                            <Form.Item name="body_json" noStyle>
                              <Input.TextArea rows={6} spellCheck={false} />
                            </Form.Item>
                          )}
                          {bodyMode === 'structured' ? (
                            <Typography.Text type="secondary">
                              值支持 number、boolean、array、object，按 JSON 字面量输入即可。
                            </Typography.Text>
                          ) : null}
                        </Space>
                      </Form.Item>
                      <Form.Item label="断言">
                        <Space direction="vertical" style={{ width: '100%' }} size="middle">
                          {editingCaseId !== null ? (
                            <AiCapabilityActionCard
                              title="AI 补断言"
                              actions={(
                                <Space wrap>
                                  <Button loading={assertionLoading} onClick={() => void handlePreviewAssertions()} disabled={!canEdit}>
                                    AI 补断言
                                  </Button>
                                  <Button
                                    type="primary"
                                    loading={assertionApplyLoading}
                                    disabled={!canEdit || !assertionPreview || !suggestedAssertions.length}
                                    onClick={() => void handleApplyAssertions(false)}
                                  >
                                    应用追加
                                  </Button>
                                  <Popconfirm
                                    title="覆盖后会用 AI 建议替换当前已保存断言，确认继续？"
                                    onConfirm={() => void handleApplyAssertions(true)}
                                    disabled={!canEdit || !assertionPreview || !suggestedAssertions.length}
                                  >
                                    <Button danger loading={assertionApplyLoading} disabled={!canEdit || !assertionPreview || !suggestedAssertions.length}>
                                      覆盖应用
                                    </Button>
                                  </Popconfirm>
                                </Space>
                              )}
                              error={assertionError}
                              warnings={assertionPreview?.warnings ?? []}
                              hasContent={Boolean(assertionPreview) || unsavedAssertionChanges}
                              empty={<Typography.Text type="secondary">生成后会在这里展示建议列表、追加后结果和覆盖后的差异。</Typography.Text>}
                            >
                              <>
                                {unsavedAssertionChanges ? (
                                  <AlertBox
                                    type="warning"
                                    showIcon
                                    message="当前编辑器里有未保存断言改动。AI 应用会以服务端已保存断言为基线，并刷新当前断言编辑区。"
                                  />
                                ) : null}
                                {assertionPreview ? (
                                  <Space direction="vertical" style={{ width: '100%' }}>
                                    <Typography.Text>
                                      当前已保存断言 {savedAssertions.length} 条，追加后 {appendPreviewAssertions.length} 条，覆盖后 {suggestedAssertions.length} 条。
                                    </Typography.Text>
                                      <AiSuggestionPanel
                                        items={suggestedAssertions.map((item, index) => ({
                                          key: `suggestion-${index}-${item.type}-${item.path ?? item.header ?? 'value'}`,
                                          title: `${assertionTypeLabel(item.type)} ${item.path ?? item.header ?? ''}`.trim(),
                                          tags: <Typography.Text type="secondary">{`置信度 ${(item.confidence * 100).toFixed(0)}%`}</Typography.Text>,
                                          content: (
                                            <Space direction="vertical" style={{ width: '100%' }}>
                                              <Typography.Text>{`操作符：${assertionOperatorLabel(item.operator)}`}</Typography.Text>
                                              <Typography.Text>{`期望值：${stringifyValue(item.expected)}`}</Typography.Text>
                                              <Typography.Text type="secondary">{item.reason}</Typography.Text>
                                            </Space>
                                          ),
                                        }))}
                                      emptyText="当前没有可应用的新断言建议。"
                                    />
                                    {suggestedAssertions.length ? (
                                      <Card size="small" title="差异预览">
                                        <Space direction="vertical" style={{ width: '100%' }}>
                                          <Typography.Text>{`追加模式会保留当前 ${savedAssertions.length} 条断言，并新增 ${appendPreviewAssertions.length - savedAssertions.length} 条。`}</Typography.Text>
                                          <Typography.Text>{`覆盖模式会把断言集替换为 AI 建议的 ${suggestedAssertions.length} 条。`}</Typography.Text>
                                        </Space>
                                      </Card>
                                    ) : null}
                                  </Space>
                                ) : null}
                              </>
                            </AiCapabilityActionCard>
                          ) : (
                            <Typography.Text type="secondary">先保存用例，再生成 AI 补断言建议。</Typography.Text>
                          )}
                          <AssertionEditor rows={assertionRows} onChange={setAssertionRows} disabled={!canEdit} />
                        </Space>
                      </Form.Item>
                      <Form.Item label="AI 预执行准备">
                        {editingCaseId !== null ? (
                          <>
                            <AiPreparationAssetsPanel
                              canEdit={canEdit}
                              testDataPreview={testDataPreview}
                              selectedVariantIds={testDataSelectedIds}
                              testDataLoading={testDataLoading}
                              testDataApplyLoading={testDataApplyLoading}
                              testDataExportLoading={testDataExportLoading}
                              testDataError={testDataError}
                              testDataHistoryOpen={testDataHistoryOpen}
                              testDataHistoryLoading={testDataHistoryLoading}
                              testDataHistoryError={testDataHistoryError}
                              testDataHistoryItems={testDataHistory}
                              onPreviewTestData={() => void handlePreviewTestData()}
                              onApplyTestDataAppend={() => void handleApplyTestData(false)}
                              onApplyTestDataOverride={() => void handleApplyTestData(true)}
                              onExportTestData={() => void handleExportTestData()}
                              onSelectionChangeVariantIds={setTestDataSelectedIds}
                              onOpenTestDataHistory={() => void handleOpenTestDataHistory()}
                              onCloseTestDataHistory={() => setTestDataHistoryOpen(false)}
                              onLoadTestDataHistory={applyTestDataHistoryItem}
                              mockPreview={mockPreview}
                              selectedTemplateIds={mockSelectedIds}
                              mockLoading={mockLoading}
                              mockApplyLoading={mockApplyLoading}
                              mockExportLoading={mockExportLoading}
                              mockError={mockError}
                              mockHistoryOpen={mockHistoryOpen}
                              mockHistoryLoading={mockHistoryLoading}
                              mockHistoryError={mockHistoryError}
                              mockHistoryItems={mockHistory}
                              onPreviewMock={() => void handlePreviewMock()}
                              onApplyMockAppend={() => void handleApplyMock(false)}
                              onApplyMockOverride={() => void handleApplyMock(true)}
                              onExportMock={() => void handleExportMock()}
                              onSelectionChangeTemplateIds={setMockSelectedIds}
                              onOpenMockHistory={() => void handleOpenMockHistory()}
                              onCloseMockHistory={() => setMockHistoryOpen(false)}
                              onLoadMockHistory={applyMockHistoryItem}
                              onViewLineage={(item) => void handleViewLineage(item)}
                            />
                            <div style={{ marginTop: 12 }}>
                              <AiExecutionPreparationPanel
                                canEdit={canEdit}
                                availableVariants={executionAvailableVariants}
                                availableTemplates={executionAvailableTemplates}
                                selectedVariantIds={executionPreparationVariantIds}
                                selectedTemplateIds={executionPreparationTemplateIds}
                                selectedEnvironmentId={executionPreparationEnvironmentId}
                                environments={editingEnvironments as Environment[]}
                                loading={executionPreparationLoading}
                                error={executionPreparationError}
                                lastExecution={executionPreparationResult}
                                onChangeVariantIds={setExecutionPreparationVariantIds}
                                onChangeTemplateIds={setExecutionPreparationTemplateIds}
                                onChangeEnvironmentId={setExecutionPreparationEnvironmentId}
                                onRun={() => void handleRunPreparedExecution()}
                              />
                            </div>
                          </>
                        ) : (
                          <Typography.Text type="secondary">先保存用例，再生成 AI 测试数据和 AI Mock 模板。</Typography.Text>
                        )}
                      </Form.Item>
                      <Form.Item label="前置处理器">
                        <ProcessorEditor title="前置处理器" rows={preProcessorRows} onChange={setPreProcessorRows} disabled={!canEdit} />
                      </Form.Item>
                      <Form.Item label="后置处理器">
                        <ProcessorEditor title="后置处理器" rows={postProcessorRows} onChange={setPostProcessorRows} disabled={!canEdit} />
                      </Form.Item>
                      <Form.Item label="元数据">
                        <Space direction="vertical" style={{ width: '100%' }}>
                          <Row gutter={12}>
                            <Col xs={24} xl={12}>
                              <Form.Item name="category" label="分类">
                                <Input placeholder="auth" />
                              </Form.Item>
                            </Col>
                            <Col xs={24} xl={12}>
                              <Form.Item name="priority" label="优先级">
                                <Select allowClear options={[{ value: 'P0', label: 'P0' }, { value: 'P1', label: 'P1' }, { value: 'P2', label: 'P2' }, { value: 'P3', label: 'P3' }]} />
                              </Form.Item>
                            </Col>
                          </Row>
                          <Row gutter={12}>
                            <Col xs={24} xl={12}>
                              <Form.Item name="owner" label="负责人">
                                <Input placeholder="qa-owner" />
                              </Form.Item>
                            </Col>
                            <Col xs={24} xl={12}>
                              <Form.Item name="timeout_ms" label="超时 (ms)">
                                <Input placeholder="5000" />
                              </Form.Item>
                            </Col>
                          </Row>
                          <Form.Item name="tags" label="标签">
                            <Input placeholder="smoke, login, regression" />
                          </Form.Item>
                          <Form.Item name="precondition" label="前置条件">
                            <Input.TextArea rows={2} />
                          </Form.Item>
                          <Form.Item name="metadata_extra_json" label="扩展元数据 JSON">
                            <Input.TextArea rows={5} spellCheck={false} />
                          </Form.Item>
                          <Typography.Text type="secondary">
                            常用元数据已在上方建模；只有超出分类、优先级、负责人、标签、前置条件、超时范围的字段，才放到扩展 JSON。
                          </Typography.Text>
                        </Space>
                      </Form.Item>
                        <Space>
                          <Button type="primary" htmlType="submit" disabled={!canEdit}>
                            {editingCaseId ? '保存' : '创建'}
                          </Button>
                          <Button onClick={() => resetCaseForm()}>重置</Button>
                        </Space>
                      </Form>
                    </Card>
                  </div>
                ) : null}

                <div>
                  <Card
                    className="glass-card workspace-section-card"
                    title="清单区 · 用例列表"
                    extra={
                      <Space>
                        <Typography.Text type="secondary">{`共 ${filteredCases.length} / ${cases.length} 条用例`}</Typography.Text>
                        <Button type="primary" onClick={handleStartCreateCase} disabled={!canEdit}>
                          新增用例
                        </Button>
                      </Space>
                    }
                  >
                    <div className="workspace-filter-bar">
                      <Select
                        allowClear
                        value={caseSuiteFilter}
                        onChange={(value) => setCaseSuiteFilter(value)}
                        placeholder="按套件筛选"
                        options={suites.map((suite) => ({ value: suite.id, label: suite.name }))}
                        style={{ width: 220 }}
                      />
                      <Select
                        allowClear
                        value={caseMethodFilter}
                        onChange={(value) => setCaseMethodFilter(value)}
                        placeholder="按请求方法筛选"
                        options={['GET', 'POST', 'PUT', 'DELETE'].map((method) => ({ value: method, label: method }))}
                        style={{ width: 180 }}
                      />
                      <Input
                        allowClear
                        value={caseKeyword}
                        onChange={(event) => setCaseKeyword(event.target.value)}
                        placeholder="按用例名、URL、描述筛选"
                      />
                      <Button
                        onClick={() => {
                          setCaseSuiteFilter(undefined);
                          setCaseMethodFilter(undefined);
                          setCaseKeyword('');
                        }}
                      >
                        重置筛选
                      </Button>
                    </div>
                    <Table<ApiCase>
                      rowKey="id"
                      pagination={TABLE_PAGINATION}
                      dataSource={filteredCases}
                      scroll={{ x: 1280 }}
                      columns={[
                        { title: '用例', dataIndex: 'name', width: 220 },
                        {
                          title: '所属项目',
                          width: 160,
                          render: (_, apiCase) => {
                            const projectId = suiteProjectIdById.get(apiCase.suite_id);
                            return projectId ? projectNameById.get(projectId) ?? `项目 #${projectId}` : '-';
                          },
                        },
                        {
                          title: '所属套件',
                          dataIndex: 'suite_id',
                          width: 180,
                          render: (value: number) => suiteNameById.get(value) ?? `套件 #${value}`,
                        },
                        { title: '请求方法', dataIndex: 'method', width: 100 },
                        { title: 'URL', dataIndex: 'url' },
                        { title: '断言数', width: 90, render: (_, apiCase) => apiCase.assertions_json.length },
                        { title: '前置', width: 90, render: (_, apiCase) => apiCase.pre_processors_json.length },
                        { title: '后置', width: 90, render: (_, apiCase) => apiCase.post_processors_json.length },
                        {
                          title: '操作',
                          width: 160,
                          render: (_, apiCase) => (
                            <Space>
                              <Button size="small" onClick={() => loadCaseIntoEditor(apiCase)}>
                                {canEdit ? '编辑' : '查看'}
                              </Button>
                              <Popconfirm title="确认删除用例？" disabled={!canEdit} onConfirm={() => void api.deleteCase(apiCase.id).then(refresh)}>
                                <Button size="small" danger disabled={!canEdit}>
                                  删除
                                </Button>
                              </Popconfirm>
                            </Space>
                          ),
                        },
                      ]}
                    />
                  </Card>
                </div>
              </Space>
            ),
          },
        ]}
      />
      <AiArtifactHistoryDrawer
        title="AI Coverage 历史"
        open={coverageHistoryOpen}
        onClose={() => setCoverageHistoryOpen(false)}
        loading={coverageHistoryLoading}
        error={coverageHistoryError}
        items={coverageHistory.map((item) => {
          const result = normalizeCoverageHistoryResult(item.output_json);
          return {
            key: item.artifact_id,
            label: `${item.artifact_id.slice(0, 8)} · 覆盖率 ${result.coverage_score} · ${coverageLabel(item.status)}`,
            content: (
              <Space direction="vertical" style={{ width: '100%' }}>
                <Typography.Text type="secondary">
                  目标: {coverageLabel(item.target_type)} #{item.target_id}
                </Typography.Text>
                <Typography.Text>
                  缺口 {result.missing_dimensions.length}，建议点 {result.suggested_points.length}
                </Typography.Text>
                <Button size="small" onClick={() => applyCoverageHistoryItem(item)}>
                  加载为当前扫描结果
                </Button>
              </Space>
            ),
          };
        })}
        emptyText="当前 target 还没有 AI coverage 历史。"
      />
      <AiArtifactHistoryDrawer
        title={lineageTitle}
        open={lineageOpen}
        onClose={() => setLineageOpen(false)}
        loading={lineageLoading}
        error={lineageError}
        headerContent={lineageData ? <Typography.Text type="secondary">root artifact: {lineageData.root_artifact_id}</Typography.Text> : null}
        items={(lineageData?.items ?? []).map((item, index) => ({
          key: `${item.resource_type}-${item.resource_key}-${index}`,
          label: `${item.resource_type} · ${item.link_type}`,
          content: (
            <Space direction="vertical" style={{ width: '100%' }}>
              <Typography.Text>{item.resource_key}</Typography.Text>
              {item.capability ? <Typography.Text type="secondary">capability: {item.capability}</Typography.Text> : null}
              {item.status ? <Typography.Text type="secondary">status: {item.status}</Typography.Text> : null}
              {item.created_at ? <Typography.Text type="secondary">{item.created_at}</Typography.Text> : null}
            </Space>
          ),
        }))}
        emptyText="当前 artifact 还没有 lineage 记录。"
      />
    </div>
  );
}
