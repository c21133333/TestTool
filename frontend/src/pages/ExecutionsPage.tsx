import {
  Alert,
  App,
  Button,
  Card,
  Col,
  Collapse,
  Descriptions,
  Drawer,
  Empty,
  Form,
  Input,
  Row,
  Segmented,
  Select,
  Space,
  Statistic,
  Switch,
  Table,
  Tag,
  Typography,
} from 'antd';
import { useEffect, useMemo, useRef, useState } from 'react';

import { createApi } from '../api/services';
import type {
  AiArtifactHistoryItem,
  AiCopilotPreview,
  AiDiagnosisResult,
  ApiCase,
  Environment,
  Execution,
  ExecutionItem,
  Suite,
} from '../api/types';
import { useAuth } from '../auth/AuthContext';
import { AiArtifactHistoryDrawer } from '../components/ai-copilot/AiArtifactHistoryDrawer';
import { AiCapabilityActionCard } from '../components/ai-copilot/AiCapabilityActionCard';
import { AiSuggestionPanel } from '../components/ai-copilot/AiSuggestionPanel';
import { canManageExecutions } from '../auth/permissions';
import { PageHero } from '../components/product/PageHero';
import { StatePanel } from '../components/product/StatePanel';
import { StatusBadge } from '../components/product/StatusBadge';
import { formatDateTime, formatDurationMs, formatPercent } from '../utils/display';
import { artifactStatusMeta, executionItemStatusMeta, executionStatusMeta } from '../utils/status';

function scopeLabel(scope: Execution['scope']) {
  return scope === 'suite' ? '套件' : '用例';
}

function summaryNumber(summary: Record<string, unknown>, key: string): number | null {
  const value = summary[key];
  return typeof value === 'number' ? value : null;
}

function executionPassRate(execution: Execution): number {
  const summaryRate = summaryNumber(execution.summary_json, 'pass_rate');
  if (summaryRate !== null) {
    return summaryRate;
  }
  if (!execution.items.length) {
    return execution.status === 'success' ? 100 : 0;
  }
  const passedCount = execution.items.filter((item) => item.status === 'PASS').length;
  return (passedCount / execution.items.length) * 100;
}

function executionFailureCount(execution: Execution): number {
  return summaryNumber(execution.summary_json, 'ng') ?? execution.items.filter((item) => item.status !== 'PASS').length;
}

function renderSummaryTags(value: unknown) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return <Typography.Text type="secondary">暂无结构化摘要。</Typography.Text>;
  }
  const entries = Object.entries(value as Record<string, unknown>);
  if (!entries.length) {
    return <Typography.Text type="secondary">暂无结构化摘要。</Typography.Text>;
  }
  return (
    <Space wrap>
      {entries.map(([key, itemValue]) => (
        <Tag key={key}>{`${key}: ${String(itemValue)}`}</Tag>
      ))}
    </Space>
  );
}

export function ExecutionsPage() {
  const { token, user } = useAuth();
  const api = useMemo(() => createApi(token), [token]);
  const { message } = App.useApp();
  const canOperate = canManageExecutions(user);
  const [cases, setCases] = useState<ApiCase[]>([]);
  const [suites, setSuites] = useState<Suite[]>([]);
  const [environments, setEnvironments] = useState<Environment[]>([]);
  const [executions, setExecutions] = useState<Execution[]>([]);
  const [selectedExecution, setSelectedExecution] = useState<Execution | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [loadingList, setLoadingList] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [loadingStatic, setLoadingStatic] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const [staticError, setStaticError] = useState<string | null>(null);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [total, setTotal] = useState(0);
  const [searchDraft, setSearchDraft] = useState('');
  const [searchText, setSearchText] = useState('');
  const [statusFilter, setStatusFilter] = useState<Execution['status'] | undefined>();
  const [scopeFilter, setScopeFilter] = useState<Execution['scope'] | undefined>();
  const [failedOnly, setFailedOnly] = useState(false);
  const [detailView, setDetailView] = useState<'all' | 'failed'>('all');
  const [diagnosisPreview, setDiagnosisPreview] = useState<AiCopilotPreview<AiDiagnosisResult> | null>(null);
  const [diagnosisHistory, setDiagnosisHistory] = useState<AiArtifactHistoryItem[]>([]);
  const [diagnosisLoading, setDiagnosisLoading] = useState(false);
  const [diagnosisHistoryLoading, setDiagnosisHistoryLoading] = useState(false);
  const [diagnosisHistoryOpen, setDiagnosisHistoryOpen] = useState(false);
  const [diagnosisError, setDiagnosisError] = useState<string | null>(null);
  const intervalRef = useRef<number | null>(null);

  async function refreshStaticData() {
    setLoadingStatic(true);
    setStaticError(null);
    try {
      const [nextCases, nextSuites, nextEnvironments] = await Promise.all([
        api.listCases(),
        api.listSuites(),
        api.listEnvironments(),
      ]);
      setCases(nextCases);
      setSuites(nextSuites);
      setEnvironments(nextEnvironments);
    } catch (err) {
      setStaticError(err instanceof Error ? err.message : '加载执行目标失败。');
    } finally {
      setLoadingStatic(false);
    }
  }

  async function openExecution(executionId: number, openDrawer = true) {
    setLoadingDetail(true);
    setDetailError(null);
    setDiagnosisPreview(null);
    setDiagnosisHistory([]);
    setDiagnosisError(null);
    try {
      const detail = await api.getExecution(executionId);
      setSelectedExecution(detail);
      const hasFailures = detail.items.some((item) => item.status !== 'PASS');
      setDetailView(hasFailures ? 'failed' : 'all');
      if (openDrawer) {
        setDrawerOpen(true);
      }
    } catch (err) {
      setDetailError(err instanceof Error ? err.message : '加载执行详情失败。');
      if (openDrawer) {
        setDrawerOpen(true);
      }
    } finally {
      setLoadingDetail(false);
    }
  }

  async function handlePreviewDiagnosis() {
    if (!selectedExecution) {
      return;
    }
    setDiagnosisLoading(true);
    setDiagnosisError(null);
    try {
      const preview = await api.previewAiDiagnosis({ execution_id: selectedExecution.id });
      setDiagnosisPreview(preview);
      const history = await api.listAiDiagnosisHistory(selectedExecution.id);
      setDiagnosisHistory(history.items);
      message.success('已生成 AI 诊断。');
    } catch (err) {
      const nextError = err instanceof Error ? err.message : '生成 AI 诊断失败。';
      setDiagnosisError(nextError);
      message.error(nextError);
    } finally {
      setDiagnosisLoading(false);
    }
  }

  async function handleLoadDiagnosisHistory() {
    if (!selectedExecution) {
      return;
    }
    setDiagnosisHistoryLoading(true);
    setDiagnosisError(null);
    setDiagnosisHistoryOpen(true);
    try {
      const history = await api.listAiDiagnosisHistory(selectedExecution.id);
      setDiagnosisHistory(history.items);
    } catch (err) {
      const nextError = err instanceof Error ? err.message : '加载 AI 诊断历史失败。';
      setDiagnosisError(nextError);
      message.error(nextError);
    } finally {
      setDiagnosisHistoryLoading(false);
    }
  }

  async function handleCopyDiagnosis() {
    if (!diagnosisPreview) {
      return;
    }
    const payload = diagnosisPreview.result;
    const content = [
      `分类：${payload.diagnosis_category}`,
      `置信度：${payload.confidence}`,
      `根因假设：${payload.root_cause_hypothesis}`,
      `下一步动作：${payload.next_actions.join(' | ')}`,
    ].join('\n');
    try {
      await navigator.clipboard.writeText(content);
      message.success('已复制 AI 诊断。');
    } catch {
      message.error('复制 AI 诊断失败。');
    }
  }

  async function refreshExecutions() {
    setLoadingList(true);
    setListError(null);
    try {
      const result = await api.listExecutions({
        page,
        page_size: pageSize,
        status: statusFilter,
        scope: scopeFilter,
        search: searchText || undefined,
        failed_only: failedOnly,
      });
      setExecutions(result.items);
      setTotal(result.total);
      if (selectedExecution) {
        const latest = result.items.find((item) => item.id === selectedExecution.id);
        if (latest) {
          await openExecution(latest.id, false);
        }
      }
    } catch (err) {
      setListError(err instanceof Error ? err.message : '加载执行列表失败。');
    } finally {
      setLoadingList(false);
    }
  }

  useEffect(() => {
    void refreshStaticData();
  }, [api]);

  useEffect(() => {
    void refreshExecutions();
  }, [api, failedOnly, page, pageSize, scopeFilter, searchText, statusFilter]);

  useEffect(() => {
    const hasActiveExecution = executions.some((item) => item.status === 'pending' || item.status === 'running');
    if (!hasActiveExecution) {
      if (intervalRef.current !== null) {
        window.clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
      return;
    }
    if (intervalRef.current === null) {
      intervalRef.current = window.setInterval(() => {
        void refreshExecutions();
      }, 3000);
    }
    return () => {
      if (intervalRef.current !== null) {
        window.clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [executions, failedOnly, page, pageSize, scopeFilter, searchText, statusFilter]);

  async function handleRunExecution(values: { scope: 'case' | 'suite'; target_id: number; environment_id?: number }) {
    try {
      const created = await api.runExecution(values);
      message.success(`已创建执行 #${created.id}。`);
      setPage(1);
      await refreshExecutions();
      await openExecution(created.id);
    } catch (err) {
      message.error(err instanceof Error ? err.message : '发起执行失败。');
    }
  }

  async function handleCancel(executionId: number) {
    try {
      await api.cancelExecution(executionId);
      message.success('已发送取消请求。');
      await refreshExecutions();
    } catch (err) {
      message.error(err instanceof Error ? err.message : '取消执行失败。');
    }
  }

  async function handleRetry(executionId: number) {
    try {
      const retry = await api.retryExecution(executionId);
      message.success(`已创建重试执行 #${retry.id}。`);
      setPage(1);
      await refreshExecutions();
      await openExecution(retry.id);
    } catch (err) {
      message.error(err instanceof Error ? err.message : '重试执行失败。');
    }
  }

  function resetExecutionFilters() {
    setSearchDraft('');
    setSearchText('');
    setStatusFilter(undefined);
    setScopeFilter(undefined);
    setFailedOnly(false);
    setPage(1);
  }

  const detailItems = useMemo(() => {
    if (!selectedExecution) {
      return [];
    }
    return detailView === 'failed'
      ? selectedExecution.items.filter((item) => item.status !== 'PASS')
      : selectedExecution.items;
  }, [detailView, selectedExecution]);

  const activeExecutionCount = executions.filter((item) => item.status === 'pending' || item.status === 'running').length;
  const failedExecutionCount = executions.filter((item) => item.status === 'failed').length;
  const passedItemCount = selectedExecution?.items.filter((item) => item.status === 'PASS').length ?? 0;
  const failedItemCount = selectedExecution?.items.filter((item) => item.status !== 'PASS').length ?? 0;

  return (
    <div className="page-stack">
      <PageHero
        eyebrow="OPS / EXECUTION CENTER"
        title="执行中心"
        description="发起执行、观察活跃任务、分析失败项，并结合 AI 诊断快速定位问题。"
        tags={[
          <span key="refresh" className="lab-chip">
            {activeExecutionCount > 0 ? '自动刷新中' : '当前无活跃执行'}
          </span>,
          <span key="access" className="lab-chip">
            {canOperate ? '可发起执行' : '仅可查看'}
          </span>,
          <span key="failed" className="lab-chip">
            {failedExecutionCount} 条失败执行
          </span>,
        ]}
        actions={
          <Space wrap>
            <Button onClick={() => void refreshExecutions()}>刷新列表</Button>
            <Button onClick={() => void refreshStaticData()}>刷新目标</Button>
          </Space>
        }
      />

      {!canOperate ? (
        <Alert type="info" showIcon message="当前角色可以查看执行结果，但不能发起、取消或重试执行。" />
      ) : null}

      {staticError ? (
        <Alert
          type="error"
          showIcon
          message="执行目标加载失败"
          description={staticError}
          action={<Button size="small" onClick={() => void refreshStaticData()}>重试</Button>}
        />
      ) : null}

      {listError ? (
        <Alert
          type="error"
          showIcon
          message="执行列表加载失败"
          description={listError}
          action={<Button size="small" onClick={() => void refreshExecutions()}>重试</Button>}
        />
      ) : null}

      <div className="dashboard-kpi-grid">
        <Card className="metric-card dashboard-kpi-card dashboard-kpi-card--primary" bordered={false}>
          <span className="dashboard-kpi-card__code">RUN-01</span>
          <Typography.Text className="workspace-summary-card__label">可见执行</Typography.Text>
          <Typography.Title level={2}>{executions.length}</Typography.Title>
          <Typography.Paragraph>当前页已加载的执行记录</Typography.Paragraph>
        </Card>
        <Card className="metric-card dashboard-kpi-card dashboard-kpi-card--info" bordered={false}>
          <span className="dashboard-kpi-card__code">ACT-02</span>
          <Typography.Text className="workspace-summary-card__label">活跃执行</Typography.Text>
          <Typography.Title level={2}>{activeExecutionCount}</Typography.Title>
          <Typography.Paragraph>排队中与执行中的任务总量</Typography.Paragraph>
        </Card>
        <Card className="metric-card dashboard-kpi-card dashboard-kpi-card--danger" bordered={false}>
          <span className="dashboard-kpi-card__code">ERR-03</span>
          <Typography.Text className="workspace-summary-card__label">失败告警</Typography.Text>
          <Typography.Title level={2}>{failedExecutionCount}</Typography.Title>
          <Typography.Paragraph>当前需要跟进处理的失败执行</Typography.Paragraph>
        </Card>
        <Card className="metric-card dashboard-kpi-card dashboard-kpi-card--signal" bordered={false}>
          <span className="dashboard-kpi-card__code">TGT-04</span>
          <Typography.Text className="workspace-summary-card__label">可执行目标</Typography.Text>
          <Typography.Title level={2}>{cases.length + suites.length}</Typography.Title>
          <Typography.Paragraph>当前可发起执行的用例与套件数量</Typography.Paragraph>
        </Card>
      </div>

      <Row gutter={[18, 18]}>
        <Col xs={24} xl={9}>
          <Space direction="vertical" style={{ width: '100%' }} size="large">
            <Card className="glass-card workspace-section-card" title="发起执行">
              <Form layout="vertical" onFinish={(values) => void handleRunExecution(values)} initialValues={{ scope: 'suite' }} disabled={!canOperate || loadingStatic}>
                <Form.Item name="scope" label="执行范围" rules={[{ required: true, message: '请选择执行范围。' }]}>
                  <Select options={[{ value: 'suite', label: '套件' }, { value: 'case', label: '用例' }]} />
                </Form.Item>
                <Form.Item shouldUpdate noStyle>
                  {({ getFieldValue }) => {
                    const scope = getFieldValue('scope');
                    return (
                      <Form.Item name="target_id" label="执行目标" rules={[{ required: true, message: '请选择执行目标。' }]}>
                        <Select
                          options={
                            scope === 'case'
                              ? cases.map((item) => ({ value: item.id, label: `${item.method} ${item.name}` }))
                              : suites.map((item) => ({ value: item.id, label: item.name }))
                          }
                        />
                      </Form.Item>
                    );
                  }}
                </Form.Item>
                <Form.Item name="environment_id" label="执行环境">
                  <Select allowClear options={environments.map((env) => ({ value: env.id, label: env.name }))} />
                </Form.Item>
                <Button type="primary" htmlType="submit" disabled={!canOperate || loadingStatic}>
                  立即执行
                </Button>
              </Form>
            </Card>

            <Card className="glass-card workspace-section-card" title="筛选条件">
              <Space direction="vertical" style={{ width: '100%' }}>
                <Input allowClear placeholder="按目标名称搜索" value={searchDraft} onChange={(event) => setSearchDraft(event.target.value)} />
                <Select
                  allowClear
                  placeholder="按状态筛选"
                  value={statusFilter}
                  onChange={(value) => {
                    setPage(1);
                    setStatusFilter(value);
                  }}
                  options={[
                    { value: 'pending', label: '排队中' },
                    { value: 'running', label: '执行中' },
                    { value: 'success', label: '成功' },
                    { value: 'failed', label: '失败' },
                  ]}
                />
                <Select
                  allowClear
                  placeholder="按范围筛选"
                  value={scopeFilter}
                  onChange={(value) => {
                    setPage(1);
                    setScopeFilter(value);
                  }}
                  options={[
                    { value: 'suite', label: '套件' },
                    { value: 'case', label: '用例' },
                  ]}
                />
                <Space>
                  <Switch checked={failedOnly} onChange={(checked) => { setPage(1); setFailedOnly(checked); }} />
                  <Typography.Text>仅查看包含失败项的执行</Typography.Text>
                </Space>
                <Space>
                  <Button type="primary" onClick={() => { setPage(1); setSearchText(searchDraft.trim()); }}>
                    应用
                  </Button>
                  <Button onClick={resetExecutionFilters}>重置</Button>
                </Space>
              </Space>
            </Card>
          </Space>
        </Col>

        <Col xs={24} xl={15}>
          <Card className="glass-card workspace-section-card" title="执行列表" extra={<Button onClick={() => void refreshExecutions()}>刷新</Button>}>
            <Table<Execution>
              rowKey="id"
              loading={loadingList}
              dataSource={executions}
              locale={{ emptyText: <Empty description="当前没有执行记录" /> }}
              pagination={{
                current: page,
                pageSize,
                total,
                showSizeChanger: false,
                showTotal: (value) => `共 ${value} 条执行`,
              }}
              onChange={(pagination) => {
                setPage(pagination.current ?? 1);
                setPageSize(pagination.pageSize ?? 10);
              }}
              onRow={(record) => ({
                onClick: () => {
                  void openExecution(record.id);
                },
              })}
              columns={[
                { title: 'ID', dataIndex: 'id', width: 80 },
                { title: '范围', dataIndex: 'scope', width: 90, render: (value: Execution['scope']) => scopeLabel(value) },
                { title: '目标', dataIndex: 'target_name' },
                { title: '状态', width: 120, render: (_, row) => <StatusBadge {...executionStatusMeta(row.status)} /> },
                { title: '通过率', width: 120, render: (_, row) => formatPercent(executionPassRate(row)) },
                { title: '失败数', width: 100, render: (_, row) => executionFailureCount(row) },
                {
                  title: '操作',
                  render: (_, row) => (
                    <Space onClick={(event) => event.stopPropagation()}>
                      <Button size="small" onClick={() => void openExecution(row.id)}>查看</Button>
                      {(row.status === 'pending' || row.status === 'running') && row.scope === 'suite' ? (
                        <Button size="small" danger disabled={!canOperate} onClick={() => void handleCancel(row.id)}>
                          取消
                        </Button>
                      ) : null}
                      {row.status === 'failed' || row.status === 'success' ? (
                        <Button size="small" disabled={!canOperate} onClick={() => void handleRetry(row.id)}>
                          重试
                        </Button>
                      ) : null}
                    </Space>
                  ),
                },
              ]}
            />
          </Card>
        </Col>
      </Row>

      <Drawer
        title={selectedExecution ? `执行 #${selectedExecution.id}` : '执行详情'}
        placement="right"
        width="62vw"
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
      >
        {loadingDetail ? (
          <StatePanel title="正在加载执行详情" description="正在获取执行项和摘要数据。" variant="loading" />
        ) : detailError ? (
          <StatePanel title="执行详情加载失败" description={detailError} variant="error" />
        ) : !selectedExecution ? (
          <StatePanel title="未选择执行" description="从执行列表中选择一条记录后，即可在这里查看详情。" />
        ) : (
          <Space direction="vertical" style={{ width: '100%' }} size="large">
            <Descriptions bordered column={2} size="small">
              <Descriptions.Item label="执行目标">{selectedExecution.target_name}</Descriptions.Item>
              <Descriptions.Item label="状态">
                <StatusBadge {...executionStatusMeta(selectedExecution.status)} />
              </Descriptions.Item>
              <Descriptions.Item label="执行范围">{scopeLabel(selectedExecution.scope)}</Descriptions.Item>
              <Descriptions.Item label="环境 ID">{selectedExecution.environment_id ?? '-'}</Descriptions.Item>
              <Descriptions.Item label="开始时间">{formatDateTime(selectedExecution.started_at)}</Descriptions.Item>
              <Descriptions.Item label="结束时间">{formatDateTime(selectedExecution.finished_at)}</Descriptions.Item>
              <Descriptions.Item label="错误信息" span={2}>{selectedExecution.error_message || '-'}</Descriptions.Item>
            </Descriptions>

            <Row gutter={[12, 12]}>
              <Col xs={24} md={8}>
                <Card size="small" className="metric-card">
                  <Statistic title="通过项" value={passedItemCount} />
                </Card>
              </Col>
              <Col xs={24} md={8}>
                <Card size="small" className="metric-card">
                  <Statistic title="失败项" value={failedItemCount} />
                </Card>
              </Col>
              <Col xs={24} md={8}>
                <Card size="small" className="metric-card">
                  <Statistic title="通过率" value={Number(executionPassRate(selectedExecution).toFixed(1))} suffix="%" />
                </Card>
              </Col>
            </Row>

            {selectedExecution.error_message ? (
              <Alert type="error" showIcon message={selectedExecution.error_message} />
            ) : null}

            <Card size="small" title="结构化摘要">
              <Space direction="vertical" style={{ width: '100%' }}>
                <Typography.Text strong>失败拆解</Typography.Text>
                {renderSummaryTags(selectedExecution.summary_json.failure_breakdown)}
                <Typography.Text strong>重试统计</Typography.Text>
                {renderSummaryTags(selectedExecution.summary_json.retry_stats)}
              </Space>
            </Card>

            <AiCapabilityActionCard
              title="AI 诊断"
              actions={(
                <Space>
                  <Button size="small" loading={diagnosisHistoryLoading} onClick={() => void handleLoadDiagnosisHistory()}>
                    历史
                  </Button>
                  <Button size="small" disabled={!diagnosisPreview} onClick={() => void handleCopyDiagnosis()}>
                    复制
                  </Button>
                  <Button type="primary" size="small" loading={diagnosisLoading} onClick={() => void handlePreviewDiagnosis()}>
                    生成诊断
                  </Button>
                </Space>
              )}
              error={diagnosisError}
              warnings={diagnosisPreview?.warnings ?? []}
              hasContent={Boolean(diagnosisPreview)}
              empty={<Typography.Text type="secondary">生成诊断后，这里会展示根因假设与下一步处理建议。</Typography.Text>}
            >
              {diagnosisPreview ? (
                <AiSuggestionPanel
                  items={[
                    {
                      key: diagnosisPreview.artifact_id,
                      title: diagnosisPreview.result.diagnosis_category,
                      tags: (
                        <Space wrap>
                          <StatusBadge {...artifactStatusMeta(diagnosisPreview.status)} />
                          <Tag>{`置信度：${diagnosisPreview.result.confidence}`}</Tag>
                        </Space>
                      ),
                      content: (
                        <Space direction="vertical" style={{ width: '100%' }}>
                          <Typography.Text>{diagnosisPreview.result.root_cause_hypothesis}</Typography.Text>
                          <div>
                            <Typography.Text strong>下一步动作</Typography.Text>
                            <ul style={{ marginTop: 8, marginBottom: 0, paddingLeft: 20 }}>
                              {diagnosisPreview.result.next_actions.map((action) => (
                                <li key={action}>
                                  <Typography.Text>{action}</Typography.Text>
                                </li>
                              ))}
                            </ul>
                          </div>
                        </Space>
                      ),
                    },
                  ]}
                  emptyText="当前还没有 AI 诊断结果。"
                />
              ) : null}
            </AiCapabilityActionCard>

            <Card
              size="small"
              title="执行项详情"
              extra={
                <Segmented
                  value={detailView}
                  onChange={(value) => setDetailView(value as 'all' | 'failed')}
                  options={[
                    { label: '全部', value: 'all' },
                    { label: `仅失败项 (${failedItemCount})`, value: 'failed' },
                  ]}
                />
              }
            >
              {!detailItems.length ? (
                <Empty description="当前筛选条件下没有执行项" />
              ) : (
                <Space direction="vertical" style={{ width: '100%' }} size="middle">
                  {detailItems.map((item: ExecutionItem) => (
                    <Card
                      key={item.id}
                      size="small"
                      title={item.case_name}
                      extra={<StatusBadge {...executionItemStatusMeta(item.status)} />}
                    >
                      <Space direction="vertical" style={{ width: '100%' }}>
                        <Space wrap>
                          <Typography.Text>{`耗时：${formatDurationMs(item.elapsed_ms)}`}</Typography.Text>
                          {item.failure_message ? <Typography.Text type="danger">{item.failure_message}</Typography.Text> : null}
                        </Space>
                        <Collapse
                          ghost
                          items={[
                            { key: 'request', label: '请求', children: <pre className="code-block">{JSON.stringify(item.request_json, null, 2)}</pre> },
                            { key: 'response', label: '响应', children: <pre className="code-block">{JSON.stringify(item.response_json, null, 2)}</pre> },
                            { key: 'assertions', label: '断言结果', children: <pre className="code-block">{JSON.stringify(item.assertion_results_json, null, 2)}</pre> },
                          ]}
                        />
                      </Space>
                    </Card>
                  ))}
                </Space>
              )}
            </Card>
          </Space>
        )}
      </Drawer>

      <AiArtifactHistoryDrawer
        title={selectedExecution ? `AI 诊断历史 #${selectedExecution.id}` : 'AI 诊断历史'}
        open={diagnosisHistoryOpen}
        onClose={() => setDiagnosisHistoryOpen(false)}
        loading={diagnosisHistoryLoading}
        error={diagnosisError}
        items={diagnosisHistory.map((item) => {
          const output = item.output_json as Record<string, unknown>;
          const outputActions = Array.isArray(output.next_actions) ? output.next_actions.map((action) => String(action)) : [];
          return {
            key: item.artifact_id,
            label: `${item.artifact_id.slice(0, 8)} / ${String(output.diagnosis_category ?? '未分类')} / ${artifactStatusMeta(item.status).label}`,
            content: (
              <Space direction="vertical" style={{ width: '100%' }}>
                <Typography.Text>{String(output.root_cause_hypothesis ?? '')}</Typography.Text>
                {outputActions.length ? (
                  <div>
                    <Typography.Text strong>下一步动作</Typography.Text>
                    <ul style={{ marginTop: 8, marginBottom: 0, paddingLeft: 20 }}>
                      {outputActions.map((action) => (
                        <li key={action}>
                          <Typography.Text>{action}</Typography.Text>
                        </li>
                      ))}
                    </ul>
                  </div>
                ) : null}
              </Space>
            ),
          };
        })}
        emptyText="当前执行还没有 AI 诊断历史。"
      />
    </div>
  );
}
