import { Alert, Button, Card, DatePicker, Input, Select, Space, Table, Tag, Typography } from 'antd';
import type { Dayjs } from 'dayjs';
import { useEffect, useMemo, useState } from 'react';

import { createApi } from '../api/services';
import type { AuditLog } from '../api/types';
import { useAuth } from '../auth/AuthContext';
import { PageHero } from '../components/product/PageHero';
import { formatDateTime } from '../utils/display';

type DateRangeValue = [Dayjs | null, Dayjs | null] | null;

function roleLabel(role: AuditLog['actor_role']) {
  if (role === 'admin') return '管理员';
  if (role === 'tester') return '测试';
  if (role === 'developer') return '开发';
  return '系统';
}

export function AuditLogsPage() {
  const { token } = useAuth();
  const api = useMemo(() => createApi(token), [token]);
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [searchDraft, setSearchDraft] = useState('');
  const [searchText, setSearchText] = useState('');
  const [actionFilter, setActionFilter] = useState<string | undefined>();
  const [actorDraft, setActorDraft] = useState('');
  const [actorFilter, setActorFilter] = useState<string | undefined>();
  const [dateRange, setDateRange] = useState<DateRangeValue>(null);

  useEffect(() => {
    setLoading(true);
    void api
      .listAuditLogs({
        page,
        page_size: pageSize,
        search: searchText || undefined,
        action: actionFilter,
        actor: actorFilter,
        start_at: dateRange?.[0] ? dateRange[0].startOf('day').toISOString() : undefined,
        end_at: dateRange?.[1] ? dateRange[1].endOf('day').toISOString() : undefined,
      })
      .then((result) => {
        setError(null);
        setLogs(result.items);
        setTotal(result.total);
      })
      .catch((nextError: unknown) => {
        setError(nextError instanceof Error ? nextError.message : '加载审计日志失败。');
        setLogs([]);
        setTotal(0);
      })
      .finally(() => {
        setLoading(false);
      });
  }, [actionFilter, actorFilter, api, dateRange, page, pageSize, searchText]);

  const actionOptions = useMemo(
    () =>
      Array.from(new Set(logs.map((log) => log.action))).map((value) => ({
        value,
        label: value,
      })),
    [logs],
  );

  function resetPage() {
    setPage(1);
  }

  const systemCount = logs.filter((item) => !item.actor_username).length;
  const actorCount = logs.filter((item) => item.actor_username).length;

  return (
    <div className="page-stack">
      <PageHero
        eyebrow="GOV / AUDIT"
        title="审计日志"
        description="查看关键操作、系统事件和资源级变更，保证整个平台的治理链路持续可追踪。"
        tags={[
          <span key="total" className="lab-chip">
            {total} 条事件
          </span>,
          <span key="actors" className="lab-chip">
            {actorCount} 条人工操作
          </span>,
          <span key="system" className="lab-chip">
            {systemCount} 条系统事件
          </span>,
        ]}
      />

      {error ? <Alert type="error" message={error} showIcon /> : null}

      <div className="dashboard-kpi-grid">
        <Card className="metric-card dashboard-kpi-card dashboard-kpi-card--primary" bordered={false}>
          <span className="dashboard-kpi-card__code">LOG-01</span>
          <Typography.Text className="workspace-summary-card__label">当前页事件</Typography.Text>
          <Typography.Title level={2}>{logs.length}</Typography.Title>
          <Typography.Paragraph>本页已加载的审计事件数量</Typography.Paragraph>
        </Card>
        <Card className="metric-card dashboard-kpi-card dashboard-kpi-card--info" bordered={false}>
          <span className="dashboard-kpi-card__code">TTL-02</span>
          <Typography.Text className="workspace-summary-card__label">筛选结果</Typography.Text>
          <Typography.Title level={2}>{total}</Typography.Title>
          <Typography.Paragraph>符合当前筛选条件的总事件数</Typography.Paragraph>
        </Card>
        <Card className="metric-card dashboard-kpi-card dashboard-kpi-card--signal" bordered={false}>
          <span className="dashboard-kpi-card__code">ACT-03</span>
          <Typography.Text className="workspace-summary-card__label">人工操作</Typography.Text>
          <Typography.Title level={2}>{actorCount}</Typography.Title>
          <Typography.Paragraph>带操作账号的事件数量</Typography.Paragraph>
        </Card>
        <Card className="metric-card dashboard-kpi-card dashboard-kpi-card--success" bordered={false}>
          <span className="dashboard-kpi-card__code">SYS-04</span>
          <Typography.Text className="workspace-summary-card__label">系统事件</Typography.Text>
          <Typography.Title level={2}>{systemCount}</Typography.Title>
          <Typography.Paragraph>无人工账号参与的系统事件数量</Typography.Paragraph>
        </Card>
      </div>

      <Card className="glass-card workspace-section-card">
        <Space wrap style={{ width: '100%', marginBottom: 16 }}>
          <Input
            allowClear
            placeholder="搜索摘要、资源或动作"
            value={searchDraft}
            onChange={(event) => setSearchDraft(event.target.value)}
            style={{ width: 280 }}
          />
          <Button
            type="primary"
            onClick={() => {
              resetPage();
              setSearchText(searchDraft.trim());
              setActorFilter(actorDraft.trim() || undefined);
            }}
          >
            应用筛选
          </Button>
          <Select
            allowClear
            placeholder="按动作筛选"
            value={actionFilter}
            onChange={(value) => {
              resetPage();
              setActionFilter(value);
            }}
            options={actionOptions}
            style={{ width: 220 }}
          />
          <Input
            allowClear
            placeholder="按操作人用户名筛选"
            value={actorDraft}
            onChange={(event) => setActorDraft(event.target.value)}
            style={{ width: 220 }}
          />
          <DatePicker.RangePicker
            allowClear
            value={dateRange}
            onChange={(value) => {
              resetPage();
              setDateRange(value);
            }}
          />
          <Button
            onClick={() => {
              setSearchDraft('');
              setSearchText('');
              setActionFilter(undefined);
              setActorDraft('');
              setActorFilter(undefined);
              setDateRange(null);
              setPage(1);
            }}
          >
            重置
          </Button>
        </Space>
        <Table
          rowKey="id"
          loading={loading}
          dataSource={logs}
          pagination={{
            current: page,
            pageSize,
            total,
            showSizeChanger: false,
            showTotal: (value) => `共 ${value} 条事件`,
          }}
          onChange={(pagination) => {
            setPage(pagination.current ?? 1);
            setPageSize(pagination.pageSize ?? 10);
          }}
          columns={[
            { title: '时间', dataIndex: 'created_at', width: 190, render: (value: string) => formatDateTime(value) },
            {
              title: '操作人',
              width: 220,
              render: (_, row) =>
                row.actor_username ? (
                  <Space direction="vertical" size={0}>
                    <Typography.Text>{row.actor_display_name ?? row.actor_username}</Typography.Text>
                    <Typography.Text type="secondary">@{row.actor_username}</Typography.Text>
                  </Space>
                ) : (
                  <Typography.Text type="secondary">系统</Typography.Text>
                ),
            },
            {
              title: '角色',
              width: 120,
              render: (_, row) => <Tag>{roleLabel(row.actor_role)}</Tag>,
            },
            { title: '动作', dataIndex: 'action', width: 170, render: (value) => <Tag color="processing">{value}</Tag> },
            { title: '资源', render: (_, row) => `${row.resource_type}#${row.resource_id}` },
            { title: '摘要', dataIndex: 'summary' },
          ]}
          expandable={{
            expandedRowRender: (record) => <pre className="code-block">{JSON.stringify(record.details_json, null, 2)}</pre>,
          }}
        />
      </Card>
    </div>
  );
}
