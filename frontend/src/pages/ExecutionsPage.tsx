import { App, Button, Card, Col, Descriptions, Drawer, Form, Input, Row, Segmented, Select, Space, Switch, Table, Tag, Typography } from 'antd';
import { useEffect, useMemo, useRef, useState } from 'react';

import { createApi } from '../api/services';
import type { ApiCase, Environment, Execution, ExecutionItem, Suite } from '../api/types';
import { useAuth } from '../auth/AuthContext';

function statusColor(status: Execution['status']) {
  if (status === 'success') return 'green';
  if (status === 'failed') return 'red';
  return 'blue';
}

function statusLabel(status: Execution['status']) {
  if (status === 'pending') return '排队中';
  if (status === 'running') return '执行中';
  if (status === 'success') return '成功';
  return '失败';
}

function scopeLabel(scope: Execution['scope']) {
  return scope === 'suite' ? '套件' : '用例';
}

function itemStatusColor(status: string) {
  return status === 'PASS' ? 'green' : 'red';
}

function itemStatusLabel(status: string) {
  return status === 'PASS' ? '通过' : '失败';
}

export function ExecutionsPage() {
  const { token } = useAuth();
  const api = useMemo(() => createApi(token), [token]);
  const { message } = App.useApp();
  const [cases, setCases] = useState<ApiCase[]>([]);
  const [suites, setSuites] = useState<Suite[]>([]);
  const [environments, setEnvironments] = useState<Environment[]>([]);
  const [executions, setExecutions] = useState<Execution[]>([]);
  const [selectedExecution, setSelectedExecution] = useState<Execution | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [loadingList, setLoadingList] = useState(false);
  const [loadingDetail, setLoadingDetail] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [total, setTotal] = useState(0);
  const [searchDraft, setSearchDraft] = useState('');
  const [searchText, setSearchText] = useState('');
  const [statusFilter, setStatusFilter] = useState<Execution['status'] | undefined>();
  const [scopeFilter, setScopeFilter] = useState<Execution['scope'] | undefined>();
  const [failedOnly, setFailedOnly] = useState(false);
  const [detailView, setDetailView] = useState<'all' | 'failed'>('all');
  const intervalRef = useRef<number | null>(null);

  async function refreshStaticData() {
    const [nextCases, nextSuites, nextEnvironments] = await Promise.all([
      api.listCases(),
      api.listSuites(),
      api.listEnvironments(),
    ]);
    setCases(nextCases);
    setSuites(nextSuites);
    setEnvironments(nextEnvironments);
  }

  async function refreshExecutions() {
    setLoadingList(true);
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
    } finally {
      setLoadingList(false);
    }
  }

  async function refresh() {
    await Promise.all([refreshStaticData(), refreshExecutions()]);
  }

  async function openExecution(executionId: number, openDrawer = true) {
    setLoadingDetail(true);
    try {
      const detail = await api.getExecution(executionId);
      setSelectedExecution(detail);
      const hasFailures = detail.items.some((item) => item.status !== 'PASS');
      setDetailView(hasFailures ? 'failed' : 'all');
      if (openDrawer) {
        setDrawerOpen(true);
      }
    } finally {
      setLoadingDetail(false);
    }
  }

  useEffect(() => {
    void refresh();
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
  }, [executions, api, failedOnly, page, pageSize, scopeFilter, searchText, statusFilter]);

  async function handleCancel(executionId: number) {
    await api.cancelExecution(executionId);
    message.success('已发送取消请求。');
    await refreshExecutions();
  }

  async function handleRetry(executionId: number) {
    const retry = await api.retryExecution(executionId);
    message.success(`已重新发起执行，新的执行 ID 为 #${retry.id}。`);
    setPage(1);
    await refreshExecutions();
    await openExecution(retry.id);
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

  const failedItemCount = selectedExecution?.items.filter((item) => item.status !== 'PASS').length ?? 0;
  const passedItemCount = selectedExecution?.items.filter((item) => item.status === 'PASS').length ?? 0;

  return (
    <div className="page-stack">
      <div className="page-hero">
        <Typography.Title>执行记录</Typography.Title>
        <Typography.Paragraph>
          单用例会立即执行，套件会进入 worker 队列。你可以在这里筛选、查看详情、取消或重试执行。
        </Typography.Paragraph>
      </div>
      <Row gutter={[18, 18]}>
        <Col span={9}>
          <Space direction="vertical" style={{ width: '100%' }} size="large">
            <Card className="glass-card" title="发起执行">
              <Form
                layout="vertical"
                onFinish={(values) =>
                  void api
                    .runExecution({
                      scope: values.scope,
                      target_id: values.target_id,
                      environment_id: values.environment_id,
                    })
                    .then(async (created) => {
                      setPage(1);
                      await refreshExecutions();
                      await openExecution(created.id);
                    })
                }
                initialValues={{ scope: 'suite' }}
              >
                <Form.Item name="scope" label="执行范围" rules={[{ required: true, message: '请选择执行范围。' }]}>
                  <Select
                    options={[
                      { value: 'suite', label: '套件' },
                      { value: 'case', label: '用例' },
                    ]}
                  />
                </Form.Item>
                <Form.Item shouldUpdate noStyle>
                  {({ getFieldValue }) => {
                    const scope = getFieldValue('scope');
                    return (
                      <Form.Item name="target_id" label="执行目标" rules={[{ required: true, message: '请选择执行目标。' }]}>
                        <Select
                          options={
                            scope === 'case'
                              ? cases.map((item) => ({
                                  value: item.id,
                                  label: `${item.method} ${item.name}`,
                                }))
                              : suites.map((item) => ({
                                  value: item.id,
                                  label: item.name,
                                }))
                          }
                        />
                      </Form.Item>
                    );
                  }}
                </Form.Item>
                <Form.Item name="environment_id" label="环境">
                  <Select allowClear options={environments.map((env) => ({ value: env.id, label: env.name }))} />
                </Form.Item>
                <Button type="primary" htmlType="submit">开始执行</Button>
              </Form>
            </Card>
            <Card className="glass-card" title="筛选条件">
              <Space direction="vertical" style={{ width: '100%' }}>
                <Input
                  allowClear
                  placeholder="搜索目标名称"
                  value={searchDraft}
                  onChange={(event) => setSearchDraft(event.target.value)}
                />
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
                  <Switch
                    checked={failedOnly}
                    onChange={(checked) => {
                      setPage(1);
                      setFailedOnly(checked);
                    }}
                  />
                  <Typography.Text>只看包含失败项的执行</Typography.Text>
                </Space>
                <Space>
                  <Button
                    type="primary"
                    onClick={() => {
                      setPage(1);
                      setSearchText(searchDraft.trim());
                    }}
                  >
                    应用
                  </Button>
                  <Button onClick={resetExecutionFilters}>重置</Button>
                </Space>
              </Space>
            </Card>
          </Space>
        </Col>
        <Col span={15}>
          <Card className="glass-card" title="执行列表" extra={<Button onClick={() => void refreshExecutions()}>刷新</Button>}>
            <Table
              rowKey="id"
              loading={loadingList}
              dataSource={executions}
              pagination={{
                current: page,
                pageSize,
                total,
                showSizeChanger: true,
                showTotal: (value) => `共 ${value} 条执行记录`,
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
                {
                  title: '状态',
                  render: (_, row) => <Tag color={statusColor(row.status)}>{statusLabel(row.status)}</Tag>,
                },
                { title: '通过率', render: (_, row) => `${row.summary_json.pass_rate ?? 0}%` },
                {
                  title: '失败项',
                  render: (_, row) => row.summary_json.ng ?? (row.status === 'failed' ? 1 : 0),
                },
                {
                  title: '操作',
                  render: (_, row) => (
                    <Space onClick={(event) => event.stopPropagation()}>
                      <Button size="small" onClick={() => void openExecution(row.id)}>查看</Button>
                      {(row.status === 'pending' || row.status === 'running') && row.scope === 'suite' ? (
                        <Button size="small" danger onClick={() => void handleCancel(row.id)}>取消</Button>
                      ) : null}
                      {row.status === 'failed' || row.status === 'success' ? (
                        <Button size="small" onClick={() => void handleRetry(row.id)}>重试</Button>
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
        width="60vw"
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        extra={
          selectedExecution ? (
            <Space>
              {(selectedExecution.status === 'pending' || selectedExecution.status === 'running') && selectedExecution.scope === 'suite' ? (
                <Button danger onClick={() => void handleCancel(selectedExecution.id)}>取消</Button>
              ) : null}
              {selectedExecution.status === 'failed' || selectedExecution.status === 'success' ? (
                <Button onClick={() => void handleRetry(selectedExecution.id)}>重试</Button>
              ) : null}
            </Space>
          ) : null
        }
      >
        {loadingDetail || !selectedExecution ? (
          <Typography.Text>加载中...</Typography.Text>
        ) : (
          <Space direction="vertical" style={{ width: '100%' }} size="large">
            <Descriptions bordered column={2} size="small">
              <Descriptions.Item label="目标">{selectedExecution.target_name}</Descriptions.Item>
              <Descriptions.Item label="状态">
                <Tag color={statusColor(selectedExecution.status)}>{statusLabel(selectedExecution.status)}</Tag>
              </Descriptions.Item>
              <Descriptions.Item label="范围">{scopeLabel(selectedExecution.scope)}</Descriptions.Item>
              <Descriptions.Item label="环境">{selectedExecution.environment_id ?? '-'}</Descriptions.Item>
              <Descriptions.Item label="开始时间">{selectedExecution.started_at ?? '-'}</Descriptions.Item>
              <Descriptions.Item label="结束时间">{selectedExecution.finished_at ?? '-'}</Descriptions.Item>
              <Descriptions.Item label="错误信息" span={2}>{selectedExecution.error_message || '-'}</Descriptions.Item>
            </Descriptions>
            <Card size="small" title="汇总">
              <Space direction="vertical" style={{ width: '100%' }}>
                <Space>
                  <Tag color="green">通过 {passedItemCount}</Tag>
                  <Tag color="red">失败 {failedItemCount}</Tag>
                  <Tag color="blue">总计 {selectedExecution.items.length}</Tag>
                </Space>
                <pre style={{ margin: 0 }}>{JSON.stringify(selectedExecution.summary_json, null, 2)}</pre>
              </Space>
            </Card>
            <Card
              size="small"
              title="执行明细"
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
              <Space direction="vertical" style={{ width: '100%' }} size="middle">
                {!detailItems.length ? <Typography.Text type="secondary">当前筛选条件下没有匹配的执行项。</Typography.Text> : null}
                {detailItems.map((item: ExecutionItem) => (
                  <Card
                    key={item.id}
                    size="small"
                    title={item.case_name}
                    extra={<Tag color={itemStatusColor(item.status)}>{itemStatusLabel(item.status)}</Tag>}
                  >
                    <Space direction="vertical" style={{ width: '100%' }}>
                      <Space>
                        <Typography.Text>耗时: {item.elapsed_ms ?? '-'} ms</Typography.Text>
                        {item.failure_message ? <Typography.Text type="danger">失败原因: {item.failure_message}</Typography.Text> : null}
                      </Space>
                      <pre style={{ margin: 0 }}>{JSON.stringify(item.request_json, null, 2)}</pre>
                      <pre style={{ margin: 0 }}>{JSON.stringify(item.response_json, null, 2)}</pre>
                      <pre style={{ margin: 0 }}>{JSON.stringify(item.assertion_results_json, null, 2)}</pre>
                    </Space>
                  </Card>
                ))}
              </Space>
            </Card>
          </Space>
        )}
      </Drawer>
    </div>
  );
}
