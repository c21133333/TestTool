import { App, Button, Input, Modal, Select, Space, Table, Tag, Typography, Upload } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import type { UploadFile } from 'antd/es/upload/interface';
import { useEffect, useMemo, useState } from 'react';

import { createApi } from '../../api/services';
import type {
  AiArtifactHistoryItem,
  AiCaseDraft,
  AiCaseDraftHistorySummary,
  AiCopilotPreview,
  AiDesignTargetType,
  AiTestPoint,
  AiTestPointResult,
  Project,
  Suite,
} from '../../api/types';
import { formatDateTime } from '../../utils/display';
import { AiArtifactHistoryDrawer } from '../ai-copilot/AiArtifactHistoryDrawer';
import { AiCapabilityActionCard } from '../ai-copilot/AiCapabilityActionCard';
import { AiTestPointTable } from '../ai-copilot/AiTestPointTable';
import { AiCaseDraftTable } from './AiCaseDraftTable';
import { AiJsonEditorModal } from './AiJsonEditorModal';

const promptPresetOptions = [
  { value: 'balanced', label: '平衡覆盖', description: '同时兼顾主链路、失败链路和关键断言。' },
  { value: 'smoke', label: 'Smoke 优先', description: '优先生成最关键的 happy path 和冒烟用例。' },
  { value: 'negative', label: '负向优先', description: '更偏向参数校验、权限和失败路径。' },
  { value: 'boundary', label: '边界优先', description: '更偏向空值、边界值和枚举极端情况。' },
] as const;

type JsonEditorState = {
  draftId: string;
  field: 'headers_json' | 'body_json' | 'assertions_json' | 'metadata_json';
} | null;

type Props = {
  api: ReturnType<typeof createApi>;
  projects: Project[];
  suites: Suite[];
  canEdit: boolean;
  onImported: () => Promise<void>;
  defaultProjectId?: number | null;
  defaultSuiteId?: number | null;
  seedPromptHints?: string;
};

function validateDraft(draft: AiCaseDraft): AiCaseDraft {
  const validationErrors: string[] = [];
  const reviewWarnings = draft.review_warnings.filter((warning) => !warning.includes('Duplicate draft detected'));
  const method = draft.case.method.trim().toUpperCase();

  if (!draft.case.name.trim()) {
    validationErrors.push('用例名不能为空。');
  }
  if (!draft.case.url.trim()) {
    validationErrors.push('URL 不能为空。');
  }
  if (!['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS'].includes(method)) {
    validationErrors.push(`不支持的 Method: ${draft.case.method}`);
  }

  let validationStatus: AiCaseDraft['validation_status'] = validationErrors.length ? 'invalid' : 'valid';
  if (!validationErrors.length && draft.case.assertions_json.length === 0) {
    validationStatus = 'warning';
    if (!reviewWarnings.includes('当前没有断言。') && !reviewWarnings.includes('No assertions were generated for this case.')) {
      reviewWarnings.push('当前没有断言。');
    }
  }
  if (!validationErrors.length && reviewWarnings.length) {
    validationStatus = 'warning';
  }

  return {
    ...draft,
    case: {
      ...draft.case,
      method,
    },
    validation_status: validationStatus,
    validation_errors: Array.from(new Set(validationErrors)),
    review_warnings: Array.from(new Set(reviewWarnings)),
  };
}

function applyClientDerivedState(drafts: AiCaseDraft[]): AiCaseDraft[] {
  const normalizedDrafts = drafts.map(validateDraft);
  const duplicateMap = new Map<string, string[]>();
  for (const draft of normalizedDrafts) {
    const key = `${draft.case.method.trim().toUpperCase()} ${draft.case.url.trim()}`;
    if (!draft.case.url.trim()) {
      continue;
    }
    duplicateMap.set(key, [...(duplicateMap.get(key) ?? []), draft.draft_id]);
  }

  return normalizedDrafts.map((draft) => {
    const key = `${draft.case.method.trim().toUpperCase()} ${draft.case.url.trim()}`;
    const duplicateIds = duplicateMap.get(key) ?? [];
    if (duplicateIds.length < 2) {
      return draft;
    }
    return {
      ...draft,
      validation_status: draft.validation_status === 'invalid' ? 'invalid' : 'warning',
      review_warnings: Array.from(new Set([...draft.review_warnings, `Duplicate draft detected for ${key}.`])),
    };
  });
}

function downloadBlob(blob: Blob, filename: string) {
  const url = window.URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  window.URL.revokeObjectURL(url);
}

function normalizeHistoryTestPoints(outputJson: Record<string, unknown>): AiTestPoint[] {
  const rawItems = Array.isArray(outputJson.test_points) ? outputJson.test_points : [];
  return rawItems.reduce<AiTestPoint[]>((result, item, index) => {
    if (!item || typeof item !== 'object') {
      return result;
    }
    const entry = item as Record<string, unknown>;
    result.push({
      id: String(entry.id ?? `history-test-point-${index}`),
      title: String(entry.title ?? 'Untitled test point'),
      category: String(entry.category ?? 'unknown'),
      risk_level: String(entry.risk_level ?? 'medium'),
      reason: String(entry.reason ?? ''),
      covered_by_existing_cases: Boolean(entry.covered_by_existing_cases),
      suggested_case_count: Number(entry.suggested_case_count ?? 1),
    });
    return result;
  }, []);
}

export function AiCaseGenerationPanel({
  api,
  projects,
  suites,
  canEdit,
  onImported,
  defaultProjectId = null,
  defaultSuiteId = null,
  seedPromptHints = '',
}: Props) {
  const { message } = App.useApp();
  const [open, setOpen] = useState(false);
  const [projectId, setProjectId] = useState<number | null>(defaultProjectId);
  const [suiteId, setSuiteId] = useState<number | null>(defaultSuiteId);
  const [suiteName, setSuiteName] = useState('');
  const [provider, setProvider] = useState('openai_compatible');
  const [model, setModel] = useState('');
  const [baseUrl, setBaseUrl] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [promptPreset, setPromptPreset] = useState<string>('balanced');
  const [promptHints, setPromptHints] = useState(seedPromptHints.trim());
  const [fileList, setFileList] = useState<UploadFile[]>([]);
  const [drafts, setDrafts] = useState<AiCaseDraft[]>([]);
  const [warnings, setWarnings] = useState<string[]>([]);
  const [docSummary, setDocSummary] = useState<{ section_count: number; endpoint_count: number } | null>(null);
  const [effectiveHints, setEffectiveHints] = useState('');
  const [historyId, setHistoryId] = useState('');
  const [historyItems, setHistoryItems] = useState<AiCaseDraftHistorySummary[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [testPointPreview, setTestPointPreview] = useState<AiCopilotPreview<AiTestPointResult> | null>(null);
  const [testPointLoading, setTestPointLoading] = useState(false);
  const [testPointHistory, setTestPointHistory] = useState<AiArtifactHistoryItem[]>([]);
  const [testPointHistoryLoading, setTestPointHistoryLoading] = useState(false);
  const [testPointHistoryError, setTestPointHistoryError] = useState<string | null>(null);
  const [testPointHistoryOpen, setTestPointHistoryOpen] = useState(false);
  const [selectedPointIds, setSelectedPointIds] = useState<string[]>([]);
  const [draftGenerationLoading, setDraftGenerationLoading] = useState(false);
  const [importLoading, setImportLoading] = useState(false);
  const [rerunLoadingId, setRerunLoadingId] = useState<string | null>(null);
  const [jsonEditor, setJsonEditor] = useState<JsonEditorState>(null);

  const projectSuites = useMemo(() => suites.filter((suite) => suite.project_id === projectId), [suites, projectId]);
  const selectedSuite = useMemo(() => projectSuites.find((suite) => suite.id === suiteId) ?? null, [projectSuites, suiteId]);
  const designTargetType: AiDesignTargetType | null = suiteId ? 'suite' : projectId ? 'project' : null;
  const designTargetId = suiteId ?? projectId;
  const testPoints = testPointPreview?.result.test_points ?? [];
  const selectedValidCount = useMemo(() => drafts.filter((draft) => draft.selected && draft.validation_status !== 'invalid').length, [drafts]);
  const invalidCount = useMemo(() => drafts.filter((draft) => draft.validation_status === 'invalid').length, [drafts]);
  const warningCount = useMemo(() => drafts.filter((draft) => draft.validation_status === 'warning').length, [drafts]);
  const duplicateCount = useMemo(
    () => drafts.filter((draft) => draft.review_warnings.some((warning) => warning.includes('Duplicate draft detected'))).length,
    [drafts],
  );
  const editingDraft = useMemo(
    () => (jsonEditor ? drafts.find((draft) => draft.draft_id === jsonEditor.draftId) ?? null : null),
    [drafts, jsonEditor],
  );

  useEffect(() => {
    if (!open) {
      return;
    }
    void refreshHistory(projectId ?? undefined);
  }, [open, projectId]);

  useEffect(() => {
    setProjectId(defaultProjectId);
  }, [defaultProjectId]);

  useEffect(() => {
    setSuiteId(defaultSuiteId);
  }, [defaultSuiteId]);

  useEffect(() => {
    const nextSeed = seedPromptHints.trim();
    if (!nextSeed) {
      return;
    }
    setPromptHints((current) => {
      const trimmedCurrent = current.trim();
      if (!trimmedCurrent) {
        return nextSeed;
      }
      return trimmedCurrent.includes(nextSeed) ? trimmedCurrent : `${trimmedCurrent}\n${nextSeed}`;
    });
  }, [seedPromptHints]);

  useEffect(() => {
    if (suiteId && !projectSuites.some((suite) => suite.id === suiteId)) {
      setSuiteId(null);
    }
  }, [projectSuites, suiteId]);

  useEffect(() => {
    if (selectedSuite && !suiteName.trim()) {
      setSuiteName(selectedSuite.name);
    }
  }, [selectedSuite, suiteName]);

  async function refreshHistory(targetProjectId?: number) {
    setHistoryLoading(true);
    try {
      const result = await api.listAiCaseDraftHistory(targetProjectId);
      setHistoryItems(result.items);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加载 AI 草稿历史失败。');
    } finally {
      setHistoryLoading(false);
    }
  }

  async function refreshTestPointHistory(targetType: AiDesignTargetType, targetId: number) {
    setTestPointHistoryLoading(true);
    setTestPointHistoryError(null);
    try {
      const result = await api.listAiTestPointHistory(targetType, targetId);
      setTestPointHistory(result.items);
    } catch (error) {
      setTestPointHistoryError(error instanceof Error ? error.message : '加载测试点历史失败。');
    } finally {
      setTestPointHistoryLoading(false);
    }
  }

  function resetState() {
    setProjectId(defaultProjectId);
    setSuiteId(defaultSuiteId);
    setSuiteName(defaultSuiteId ? suites.find((suite) => suite.id === defaultSuiteId)?.name ?? '' : '');
    setProvider('openai_compatible');
    setModel('');
    setBaseUrl('');
    setApiKey('');
    setPromptPreset('balanced');
    setPromptHints(seedPromptHints.trim());
    setFileList([]);
    setDrafts([]);
    setWarnings([]);
    setDocSummary(null);
    setEffectiveHints('');
    setHistoryId('');
    setTestPointPreview(null);
    setTestPointHistory([]);
    setTestPointHistoryError(null);
    setSelectedPointIds([]);
    setJsonEditor(null);
  }

  function applyBatchToState(batch: {
    history_id?: string;
    suite_name: string;
    doc_summary: { section_count: number; endpoint_count: number };
    drafts: AiCaseDraft[];
    warnings: string[];
    prompt_preset?: string;
    prompt_hints_effective?: string;
  }) {
    setHistoryId(batch.history_id ?? '');
    setSuiteName(batch.suite_name);
    setDocSummary(batch.doc_summary);
    setDrafts(applyClientDerivedState(batch.drafts));
    setWarnings(batch.warnings);
    setPromptPreset(batch.prompt_preset ?? 'balanced');
    setEffectiveHints(batch.prompt_hints_effective ?? '');
  }

  function updateDraft(draftId: string, updater: (draft: AiCaseDraft) => AiCaseDraft) {
    setDrafts((current) => applyClientDerivedState(current.map((draft) => (draft.draft_id === draftId ? updater(draft) : draft))));
  }

  function duplicateDraft(draft: AiCaseDraft) {
    setDrafts((current) =>
      applyClientDerivedState([
        ...current,
        {
          ...draft,
          draft_id: crypto.randomUUID(),
          selected: false,
          case: {
            ...draft.case,
            name: `${draft.case.name || '未命名'} - 副本`,
          },
        },
      ]),
    );
  }

  function applyHistoryTestPoints(item: AiArtifactHistoryItem) {
    const nextPoints = normalizeHistoryTestPoints(item.output_json);
    setTestPointPreview({
      artifact_id: item.artifact_id,
      capability: 'test_point',
      status: item.status,
      warnings: item.warnings_json,
      result: { test_points: nextPoints },
    });
    const defaultSelection = nextPoints.filter((point) => !point.covered_by_existing_cases).map((point) => point.id);
    setSelectedPointIds(defaultSelection.length ? defaultSelection : nextPoints.map((point) => point.id));
    setTestPointHistoryOpen(false);
  }

  async function handlePreviewTestPoints() {
    if (!designTargetType || !designTargetId) {
      message.warning('请先选择测试设计的目标项目或套件。');
      return;
    }

    setTestPointLoading(true);
    try {
      const markdownText = fileList[0]?.originFileObj ? await fileList[0].originFileObj.text() : undefined;
      const result = await api.previewAiTestPoints({
        project_id: designTargetType === 'project' ? designTargetId : undefined,
        suite_id: designTargetType === 'suite' ? designTargetId : undefined,
        markdown_text: markdownText?.trim() ? markdownText : undefined,
        prompt_hints: promptHints.trim() || undefined,
      });
      setTestPointPreview(result);
      const defaultSelection = result.result.test_points.filter((point) => !point.covered_by_existing_cases).map((point) => point.id);
      setSelectedPointIds(defaultSelection.length ? defaultSelection : result.result.test_points.map((point) => point.id));
      message.success(`已生成 ${result.result.test_points.length} 条测试点。`);
      await refreshTestPointHistory(designTargetType, designTargetId);
    } catch (error) {
      message.error(error instanceof Error ? error.message : 'AI 测试点生成失败。');
    } finally {
      setTestPointLoading(false);
    }
  }

  async function handleGenerateDrafts() {
    if (!projectId) {
      message.warning('请先选择目标项目。');
      return;
    }
    if (!suiteName.trim()) {
      message.warning('请先填写落草稿的套件名称。');
      return;
    }
    if (!testPointPreview) {
      message.warning('请先生成测试点。');
      return;
    }
    if (!selectedPointIds.length) {
      message.warning('至少选择一个测试点再生成草稿。');
      return;
    }

    setDraftGenerationLoading(true);
    try {
      const result = await api.generateAiDraftsFromTestPoints({
        artifact_id: testPointPreview.artifact_id,
        selected_point_ids: selectedPointIds,
        project_id: projectId,
        suite_name: suiteName.trim(),
        provider: provider.trim(),
        model: model.trim(),
        base_url: baseUrl.trim(),
        api_key: apiKey.trim(),
      });
      applyBatchToState(result);
      message.success(`已基于 ${selectedPointIds.length} 条测试点生成 ${result.drafts.length} 条草稿。`);
      await refreshHistory(projectId);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '基于测试点生成草稿失败。');
    } finally {
      setDraftGenerationLoading(false);
    }
  }

  async function handleImport() {
    if (!projectId) {
      message.warning('请先选择目标项目。');
      return;
    }
    if (!suiteName.trim()) {
      message.warning('请先填写目标套件名称。');
      return;
    }
    if (!selectedValidCount) {
      message.warning('至少选择一条有效草稿再导入。');
      return;
    }

    setImportLoading(true);
    try {
      const result = await api.importAiCaseDrafts({
        project_id: projectId,
        suite_name: suiteName.trim(),
        drafts: drafts.map((draft) => ({
          draft_id: draft.draft_id,
          selected: draft.selected,
          case: draft.case,
          source_excerpt: draft.source_excerpt,
          source_location: draft.source_location,
        })),
      });
      message.success(`已导入 ${result.created_cases} 条用例到套件 ${result.suite_name}。`);
      if (result.failures.length) {
        message.warning(`有 ${result.failures.length} 条草稿导入失败，请检查预览表。`);
      }
      await onImported();
      await refreshHistory(projectId);
      setOpen(false);
      resetState();
    } catch (error) {
      message.error(error instanceof Error ? error.message : '导入失败。');
    } finally {
      setImportLoading(false);
    }
  }

  async function handleLoadHistory(targetHistoryId: string) {
    try {
      const result = await api.getAiCaseDraftHistory(targetHistoryId);
      const historySummary = historyItems.find((item) => item.history_id === targetHistoryId);
      if (historySummary) {
        setProjectId(historySummary.project_id);
      }
      applyBatchToState(result);
      message.success('已加载历史草稿。');
    } catch (error) {
      message.error(error instanceof Error ? error.message : '加载历史草稿失败。');
    }
  }

  async function handleRerunHistory(targetHistoryId: string) {
    setRerunLoadingId(targetHistoryId);
    try {
      const result = await api.rerunAiCaseDraftHistory(targetHistoryId, {
        provider: provider.trim(),
        model: model.trim(),
        base_url: baseUrl.trim(),
        api_key: apiKey.trim(),
      });
      const historySummary = historyItems.find((item) => item.history_id === targetHistoryId);
      if (historySummary) {
        setProjectId(historySummary.project_id);
      }
      applyBatchToState(result);
      message.success(`已基于历史 ${targetHistoryId} 重跑生成。`);
      await refreshHistory(historySummary?.project_id ?? projectId ?? undefined);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '历史重跑失败。');
    } finally {
      setRerunLoadingId(null);
    }
  }

  async function handleExportHistory(targetHistoryId: string) {
    try {
      const blob = await api.fetchAiCaseDraftHistoryExcel(targetHistoryId);
      downloadBlob(blob, `ai-case-drafts-${targetHistoryId}.xlsx`);
    } catch (error) {
      message.error(error instanceof Error ? error.message : '导出 Excel 失败。');
    }
  }

  const historyColumns: ColumnsType<AiCaseDraftHistorySummary> = [
    { title: '时间', dataIndex: 'created_at', width: 180, render: (value: string) => formatDateTime(value) },
    { title: '套件', dataIndex: 'suite_name', width: 180 },
    { title: '模型', dataIndex: 'model', width: 140 },
    { title: '预设', dataIndex: 'prompt_preset', width: 120 },
    { title: '草稿数', dataIndex: 'draft_count', width: 90 },
    { title: '告警数', dataIndex: 'warning_count', width: 90 },
    {
      title: '操作',
      width: 240,
      render: (_, item) => (
        <Space>
          <Button size="small" onClick={() => void handleLoadHistory(item.history_id)}>
            加载
          </Button>
          <Button size="small" loading={rerunLoadingId === item.history_id} onClick={() => void handleRerunHistory(item.history_id)}>
            重跑
          </Button>
          <Button size="small" onClick={() => void handleExportHistory(item.history_id)}>
            导出 Excel
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <>
      <Space direction="vertical" style={{ width: '100%' }}>
        <Typography.Text type="secondary">先产出测试点，再决定哪些点落成草稿，最后复用原有导入闭环。</Typography.Text>
        <Button type="primary" onClick={() => setOpen(true)} disabled={!canEdit}>
          打开 AI 设计器
        </Button>
      </Space>

      <Modal
        title="AI 生成接口测试用例"
        open={open}
        onCancel={() => {
          setOpen(false);
          resetState();
        }}
        width={1360}
        footer={
          <Space>
            <Button
              onClick={() => {
                setOpen(false);
                resetState();
              }}
            >
              关闭
            </Button>
            <Button type="primary" onClick={() => void handleImport()} loading={importLoading} disabled={!canEdit || !selectedValidCount}>
              审批并导入
            </Button>
          </Space>
        }
      >
        <Space direction="vertical" style={{ width: '100%' }} size="large">
          <Space wrap style={{ width: '100%' }}>
            <Select
              placeholder="目标项目"
              value={projectId ?? undefined}
              onChange={setProjectId}
              options={projects.map((project) => ({ value: project.id, label: project.name }))}
              style={{ width: 180 }}
              disabled={!canEdit}
            />
            <Select
              allowClear
              placeholder="测试设计上下文套件（可选）"
              value={suiteId ?? undefined}
              onChange={(value) => setSuiteId(value ?? null)}
              options={projectSuites.map((suite) => ({ value: suite.id, label: suite.name }))}
              style={{ width: 220 }}
              disabled={!canEdit || !projectId}
            />
            <Input
              placeholder="落草稿套件名称"
              value={suiteName}
              onChange={(event) => setSuiteName(event.target.value)}
              style={{ width: 220 }}
              disabled={!canEdit}
            />
            <Input
              placeholder="Provider，留空走后端默认"
              value={provider}
              onChange={(event) => setProvider(event.target.value)}
              style={{ width: 180 }}
              disabled={!canEdit}
            />
            <Input
              placeholder="Model，留空走后端默认"
              value={model}
              onChange={(event) => setModel(event.target.value)}
              style={{ width: 180 }}
              disabled={!canEdit}
            />
            <Input
              placeholder="Base URL，留空走后端默认"
              value={baseUrl}
              onChange={(event) => setBaseUrl(event.target.value)}
              style={{ width: 220 }}
              disabled={!canEdit}
            />
            <Input.Password
              placeholder="API Key，留空走后端默认"
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
              style={{ width: 240 }}
              disabled={!canEdit}
            />
          </Space>

          <Space wrap style={{ width: '100%' }}>
            <Select
              value={promptPreset}
              onChange={setPromptPreset}
              options={promptPresetOptions.map((item) => ({ value: item.value, label: item.label }))}
              style={{ width: 180 }}
              disabled={!canEdit}
            />
            <Upload
              beforeUpload={() => false}
              maxCount={1}
              accept=".md,.markdown,text/markdown"
              fileList={fileList}
              onChange={({ fileList: nextFileList }) => setFileList(nextFileList)}
              disabled={!canEdit}
            >
              <Button disabled={!canEdit}>选择 Markdown</Button>
            </Upload>
            <Button type="primary" loading={testPointLoading} disabled={!canEdit} onClick={() => void handlePreviewTestPoints()}>
              生成测试点
            </Button>
            <Button
              onClick={() => (designTargetType && designTargetId ? void refreshTestPointHistory(designTargetType, designTargetId) : undefined)}
              disabled={!designTargetType}
            >
              刷新测试点历史
            </Button>
            <Button
              type="primary"
              loading={draftGenerationLoading}
              disabled={!canEdit || !testPointPreview || !selectedPointIds.length}
              onClick={() => void handleGenerateDrafts()}
            >
              基于测试点生成草稿
            </Button>
            <Button onClick={() => void refreshHistory(projectId ?? undefined)} loading={historyLoading}>
              刷新草稿历史
            </Button>
          </Space>

          <Typography.Text type="secondary">{promptPresetOptions.find((option) => option.value === promptPreset)?.description}</Typography.Text>

          <Input.TextArea
            rows={3}
            placeholder="可选附加提示词，例如：登录接口必须覆盖 token 失效场景。"
            value={promptHints}
            onChange={(event) => setPromptHints(event.target.value)}
            disabled={!canEdit}
          />

          <AiCapabilityActionCard
            title="测试点预览"
            actions={
              <Space wrap>
                <Tag color="processing">{designTargetType ? `${designTargetType} #${designTargetId}` : '未选择 target'}</Tag>
                <Tag color="blue">已选 {selectedPointIds.length}</Tag>
                <Button size="small" onClick={() => setTestPointHistoryOpen(true)} disabled={!designTargetType}>
                  历史
                </Button>
              </Space>
            }
            warnings={testPointPreview?.warnings ?? []}
            hasContent={Boolean(testPointPreview)}
            empty={<Typography.Text type="secondary">选定 target 后生成测试点，这里会进入可选择、可回放的 design 预览。</Typography.Text>}
          >
            {testPointPreview ? (
              <Space direction="vertical" style={{ width: '100%' }}>
                <Space wrap>
                  <Tag color="green">测试点 {testPoints.length}</Tag>
                  <Tag color="cyan">待落草稿 {selectedPointIds.length}</Tag>
                  <Tag color="default">artifact {testPointPreview.artifact_id.slice(0, 8)}</Tag>
                </Space>
                <AiTestPointTable
                  testPoints={testPoints}
                  selectedPointIds={selectedPointIds}
                  canEdit={canEdit}
                  onSelectionChange={setSelectedPointIds}
                />
              </Space>
            ) : null}
          </AiCapabilityActionCard>

          {effectiveHints ? (
            <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
              最终提示策略：{effectiveHints}
            </Typography.Paragraph>
          ) : null}

          <Space direction="vertical" style={{ width: '100%' }} size={4}>
            <Typography.Title level={5} style={{ margin: 0 }}>
              草稿历史
            </Typography.Title>
            <Table<AiCaseDraftHistorySummary>
              rowKey="history_id"
              dataSource={historyItems}
              columns={historyColumns}
              size="small"
              pagination={false}
              loading={historyLoading}
              scroll={{ x: 980, y: 180 }}
              locale={{ emptyText: '当前没有草稿历史记录。' }}
            />
          </Space>

          {docSummary ? (
            <Space wrap>
              <Tag color="blue">章节 {docSummary.section_count}</Tag>
              <Tag color="geekblue">接口线索 {docSummary.endpoint_count}</Tag>
              <Tag color="green">草稿 {drafts.length}</Tag>
              <Tag color="gold">告警 {warningCount}</Tag>
              <Tag color="red">无效 {invalidCount}</Tag>
              <Tag color="purple">重复候选 {duplicateCount}</Tag>
              <Tag color="cyan">已选有效 {selectedValidCount}</Tag>
              {historyId ? <Tag color="magenta">历史 ID {historyId.slice(0, 8)}</Tag> : null}
            </Space>
          ) : null}

          {warnings.length ? (
            <Space direction="vertical" style={{ width: '100%' }} size={4}>
              {warnings.map((warning) => (
                <Typography.Paragraph key={warning} type="warning" style={{ marginBottom: 0 }}>
                  {warning}
                </Typography.Paragraph>
              ))}
            </Space>
          ) : null}

          <AiCaseDraftTable
            drafts={drafts}
            canEdit={canEdit}
            onDraftChange={updateDraft}
            onDraftDuplicate={duplicateDraft}
            onDraftDelete={(draftId) => setDrafts((current) => applyClientDerivedState(current.filter((item) => item.draft_id !== draftId)))}
            onEditJson={(draft, field) => setJsonEditor({ draftId: draft.draft_id, field })}
          />

          {historyId ? (
            <Space>
              <Button onClick={() => void handleExportHistory(historyId)}>导出当前历史 Excel</Button>
              <Button onClick={() => void handleRerunHistory(historyId)} loading={rerunLoadingId === historyId}>
                基于当前历史重跑
              </Button>
            </Space>
          ) : null}
        </Space>
      </Modal>

      <AiArtifactHistoryDrawer
        title="AI 测试点历史"
        open={testPointHistoryOpen}
        onClose={() => setTestPointHistoryOpen(false)}
        loading={testPointHistoryLoading}
        error={testPointHistoryError}
        items={testPointHistory.map((item) => {
          const historyTestPoints = normalizeHistoryTestPoints(item.output_json);
          return {
            key: item.artifact_id,
            label: `${item.artifact_id.slice(0, 8)} · ${historyTestPoints.length} points · ${item.status}`,
            content: (
              <Space direction="vertical" style={{ width: '100%' }}>
                <Typography.Text type="secondary">
                  target: {item.target_type} #{item.target_id}
                </Typography.Text>
                <Typography.Text>
                  {historyTestPoints.slice(0, 3).map((point) => point.title).join(' / ') || '该 artifact 没有可回放的测试点。'}
                </Typography.Text>
                <Button size="small" onClick={() => applyHistoryTestPoints(item)}>
                  加载为当前预览
                </Button>
              </Space>
            ),
          };
        })}
        emptyText="当前 target 还没有 AI 测试点历史。"
      />

      <AiJsonEditorModal
        open={jsonEditor !== null}
        field={jsonEditor?.field ?? null}
        value={jsonEditor && editingDraft ? editingDraft.case[jsonEditor.field] : null}
        onCancel={() => setJsonEditor(null)}
        onSave={(value) => {
          if (!jsonEditor) {
            return;
          }
          updateDraft(jsonEditor.draftId, (current) => ({
            ...current,
            case: {
              ...current.case,
              [jsonEditor.field]: value,
            },
          }));
          setJsonEditor(null);
        }}
      />
    </>
  );
}
