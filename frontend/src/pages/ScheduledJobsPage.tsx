import {
  Alert,
  App,
  Button,
  Card,
  Col,
  Drawer,
  Empty,
  Form,
  Input,
  Row,
  Select,
  Space,
  Statistic,
  Switch,
  Table,
  Tag,
  Typography,
} from 'antd';
import { useEffect, useMemo, useState } from 'react';

import { createApi } from '../api/services';
import type { Environment, Project, ScheduledJob, ScheduledJobRun, Suite } from '../api/types';
import { useAuth } from '../auth/AuthContext';
import { canManageSchedules } from '../auth/permissions';
import { PageHero } from '../components/product/PageHero';
import { StatePanel } from '../components/product/StatePanel';
import { formatDateTime } from '../utils/display';

type JobFormValues = {
  project_id: number;
  suite_id: number;
  environment_id?: number;
  name: string;
  description: string;
  cron_expr: string;
  timezone: string;
  enabled: boolean;
  concurrency_policy: 'forbid' | 'allow' | 'replace';
  misfire_policy: 'skip' | 'fire_once';
};

const DEFAULT_FORM_VALUES: JobFormValues = {
  project_id: 0,
  suite_id: 0,
  environment_id: undefined,
  name: '',
  description: '',
  cron_expr: '0 9 * * 1-5',
  timezone: 'Asia/Shanghai',
  enabled: true,
  concurrency_policy: 'forbid',
  misfire_policy: 'skip',
};

function resolveRunMeta(status: ScheduledJobRun['status']) {
  if (status === 'triggered') {
    return { color: 'success', label: '已触发' };
  }
  if (status === 'skipped') {
    return { color: 'warning', label: '已跳过' };
  }
  return { color: 'error', label: '失败' };
}

function resolveJobState(job: ScheduledJob) {
  if (!job.enabled) {
    return { color: 'default', label: '暂停' };
  }
  if (job.last_triggered_execution_id) {
    return { color: 'processing', label: '已编排' };
  }
  return { color: 'blue', label: '待触发' };
}

export function ScheduledJobsPage() {
  const { token, user } = useAuth();
  const api = useMemo(() => createApi(token), [token]);
  const { message } = App.useApp();
  const canOperate = canManageSchedules(user);

  const [form] = Form.useForm<JobFormValues>();
  const [projects, setProjects] = useState<Project[]>([]);
  const [suites, setSuites] = useState<Suite[]>([]);
  const [environments, setEnvironments] = useState<Environment[]>([]);
  const [jobs, setJobs] = useState<ScheduledJob[]>([]);
  const [runs, setRuns] = useState<ScheduledJobRun[]>([]);
  const [selectedJob, setSelectedJob] = useState<ScheduledJob | null>(null);
  const [editingJob, setEditingJob] = useState<ScheduledJob | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [runsDrawerOpen, setRunsDrawerOpen] = useState(false);
  const [loadingStatic, setLoadingStatic] = useState(true);
  const [loadingJobs, setLoadingJobs] = useState(true);
  const [loadingRuns, setLoadingRuns] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [staticError, setStaticError] = useState<string | null>(null);
  const [jobsError, setJobsError] = useState<string | null>(null);
  const [runsError, setRunsError] = useState<string | null>(null);
  const [searchDraft, setSearchDraft] = useState('');
  const [searchText, setSearchText] = useState('');
  const [projectFilter, setProjectFilter] = useState<number | undefined>(undefined);
  const [enabledFilter, setEnabledFilter] = useState<'all' | 'enabled' | 'disabled'>('all');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [total, setTotal] = useState(0);
  const [selectedProjectId, setSelectedProjectId] = useState<number | undefined>(undefined);

  const availableSuites = useMemo(
    () => (selectedProjectId ? suites.filter((suite) => suite.project_id === selectedProjectId) : suites),
    [selectedProjectId, suites],
  );
  const availableEnvironments = useMemo(
    () => (selectedProjectId ? environments.filter((environment) => environment.project_id === selectedProjectId) : environments),
    [selectedProjectId, environments],
  );

  async function refreshStaticData() {
    setLoadingStatic(true);
    setStaticError(null);
    try {
      const [nextProjects, nextSuites, nextEnvironments] = await Promise.all([
        api.listProjects(),
        api.listSuites(),
        api.listEnvironments(),
      ]);
      setProjects(nextProjects);
      setSuites(nextSuites);
      setEnvironments(nextEnvironments);
    } catch (err) {
      setStaticError(err instanceof Error ? err.message : '加载调度目标失败。');
    } finally {
      setLoadingStatic(false);
    }
  }

  async function refreshJobs() {
    setLoadingJobs(true);
    setJobsError(null);
    try {
      const result = await api.listScheduledJobs({
        page,
        page_size: pageSize,
        project_id: projectFilter,
        enabled: enabledFilter === 'all' ? undefined : enabledFilter === 'enabled',
        search: searchText || undefined,
      });
      setJobs(result.items);
      setTotal(result.total);
    } catch (err) {
      setJobsError(err instanceof Error ? err.message : '加载定时任务失败。');
    } finally {
      setLoadingJobs(false);
    }
  }

  useEffect(() => {
    void refreshStaticData();
  }, [api]);

  useEffect(() => {
    void refreshJobs();
  }, [api, enabledFilter, page, pageSize, projectFilter, searchText]);

  function openCreateDrawer() {
    const nextProjectId = projectFilter ?? projects[0]?.id;
    setEditingJob(null);
    setSelectedProjectId(nextProjectId);
    form.setFieldsValue({
      ...DEFAULT_FORM_VALUES,
      project_id: nextProjectId ?? 0,
      suite_id: 0,
      environment_id: undefined,
    });
    setDrawerOpen(true);
  }

  function openEditDrawer(job: ScheduledJob) {
    setEditingJob(job);
    setSelectedProjectId(job.project_id);
    form.setFieldsValue({
      project_id: job.project_id,
      suite_id: job.suite_id,
      environment_id: job.environment_id ?? undefined,
      name: job.name,
      description: job.description,
      cron_expr: job.cron_expr,
      timezone: job.timezone,
      enabled: job.enabled,
      concurrency_policy: job.concurrency_policy,
      misfire_policy: job.misfire_policy,
    });
    setDrawerOpen(true);
  }

  async function openRunsDrawer(job: ScheduledJob) {
    setSelectedJob(job);
    setRunsDrawerOpen(true);
    setLoadingRuns(true);
    setRunsError(null);
    try {
      setRuns(await api.listScheduledJobRuns(job.id));
    } catch (err) {
      setRunsError(err instanceof Error ? err.message : '加载调度记录失败。');
    } finally {
      setLoadingRuns(false);
    }
  }

  async function handleSubmit(values: JobFormValues) {
    setSubmitting(true);
    try {
      const payload = {
        ...values,
        environment_id: values.environment_id ?? null,
      };
      if (editingJob) {
        await api.updateScheduledJob(editingJob.id, payload);
        message.success('定时任务已更新。');
      } else {
        await api.createScheduledJob(payload);
        message.success('定时任务已创建。');
      }
      setDrawerOpen(false);
      setPage(1);
      await refreshJobs();
    } catch (err) {
      message.error(err instanceof Error ? err.message : '保存定时任务失败。');
    } finally {
      setSubmitting(false);
    }
  }

  async function handleToggle(job: ScheduledJob) {
    try {
      if (job.enabled) {
        await api.disableScheduledJob(job.id);
        message.success('定时任务已暂停。');
      } else {
        await api.enableScheduledJob(job.id);
        message.success('定时任务已启用。');
      }
      await refreshJobs();
    } catch (err) {
      message.error(err instanceof Error ? err.message : '切换定时任务状态失败。');
    }
  }

  async function handleTrigger(job: ScheduledJob) {
    try {
      await api.triggerScheduledJob(job.id);
      message.success('已创建一次手动触发。');
      await refreshJobs();
      if (selectedJob?.id === job.id) {
        await openRunsDrawer(job);
      }
    } catch (err) {
      message.error(err instanceof Error ? err.message : '触发定时任务失败。');
    }
  }

  const activeJobs = jobs.filter((job) => job.enabled).length;
  const pausedJobs = jobs.filter((job) => !job.enabled).length;
  const scheduledJobs = jobs.filter((job) => Boolean(job.next_run_at)).length;
  const triggeredJobs = jobs.filter((job) => Boolean(job.last_triggered_at)).length;

  return (
    <div className="page-stack">
      <PageHero
        eyebrow="SCHEDULE / ORCHESTRATION"
        title="定时任务"
        description="把套件执行从手工按钮升级成可审计的编排资产。这里专门管理调度规则、下一次触发窗口和最近一次运行记录。"
        tags={[
          <span key="new-domain" className="lab-chip">
            独立菜单域
          </span>,
          <span key="queue-only" className="lab-chip">
            scheduler 只负责入队
          </span>,
          <span key="suite-target" className="lab-chip">
            目标仅限 suite
          </span>,
        ]}
        actions={
          <Space wrap>
            <Button onClick={() => void refreshStaticData()}>刷新目标</Button>
            <Button onClick={() => void refreshJobs()}>刷新任务</Button>
            <Button type="primary" disabled={!canOperate || loadingStatic} onClick={openCreateDrawer}>
              新建任务
            </Button>
          </Space>
        }
      />

      {!canOperate ? (
        <Alert type="info" showIcon message="当前角色仅可查看定时任务，不能创建、编辑、启停或触发。" />
      ) : null}

      {staticError ? (
        <Alert
          type="error"
          showIcon
          message="调度目标加载失败"
          description={staticError}
          action={
            <Button size="small" onClick={() => void refreshStaticData()}>
              重试
            </Button>
          }
        />
      ) : null}

      {jobsError ? (
        <Alert
          type="error"
          showIcon
          message="定时任务加载失败"
          description={jobsError}
          action={
            <Button size="small" onClick={() => void refreshJobs()}>
              重试
            </Button>
          }
        />
      ) : null}

      {loadingStatic && !projects.length ? (
        <StatePanel title="正在建立调度视图" description="正在加载项目、套件与环境上下文。" variant="loading" />
      ) : (
        <>
          <div className="dashboard-kpi-grid">
            <Card className="metric-card dashboard-kpi-card dashboard-kpi-card--primary" bordered={false}>
              <span className="dashboard-kpi-card__code">SCH-01</span>
              <Typography.Text className="workspace-summary-card__label">启用中</Typography.Text>
              <Typography.Title level={2}>{activeJobs}</Typography.Title>
              <Typography.Paragraph>当前处于激活状态的调度规则数量</Typography.Paragraph>
            </Card>
            <Card className="metric-card dashboard-kpi-card dashboard-kpi-card--info" bordered={false}>
              <span className="dashboard-kpi-card__code">PAU-02</span>
              <Typography.Text className="workspace-summary-card__label">暂停中</Typography.Text>
              <Typography.Title level={2}>{pausedJobs}</Typography.Title>
              <Typography.Paragraph>配置保留但不参与自动派发的规则</Typography.Paragraph>
            </Card>
            <Card className="metric-card dashboard-kpi-card dashboard-kpi-card--signal" bordered={false}>
              <span className="dashboard-kpi-card__code">NXT-03</span>
              <Typography.Text className="workspace-summary-card__label">已计算 next run</Typography.Text>
              <Typography.Title level={2}>{scheduledJobs}</Typography.Title>
              <Typography.Paragraph>拥有下一次运行时间的任务数量</Typography.Paragraph>
            </Card>
            <Card className="metric-card dashboard-kpi-card dashboard-kpi-card--success" bordered={false}>
              <span className="dashboard-kpi-card__code">TRG-04</span>
              <Typography.Text className="workspace-summary-card__label">有触发历史</Typography.Text>
              <Typography.Title level={2}>{triggeredJobs}</Typography.Title>
              <Typography.Paragraph>已经产生至少一次调度记录的任务数量</Typography.Paragraph>
            </Card>
          </div>

          <Row gutter={[18, 18]}>
            <Col xs={24} xl={8}>
              <Card className="glass-card workspace-section-card scheduled-overview-card" title="调度雷达">
                <div className="scheduled-overview-card__dial">
                  <div className="scheduled-overview-card__ring scheduled-overview-card__ring--outer" />
                  <div className="scheduled-overview-card__ring scheduled-overview-card__ring--mid" />
                  <div className="scheduled-overview-card__ring scheduled-overview-card__ring--inner" />
                  <div className="scheduled-overview-card__core">
                    <Typography.Text>ACTIVE</Typography.Text>
                    <Typography.Title level={2}>{activeJobs}</Typography.Title>
                  </div>
                </div>
                <div className="scheduled-overview-card__legend">
                  <div>
                    <Typography.Text type="secondary">推荐默认</Typography.Text>
                    <Typography.Title level={5}>forbid / skip</Typography.Title>
                  </div>
                  <div>
                    <Typography.Text type="secondary">最佳用法</Typography.Text>
                    <Typography.Title level={5}>每日冒烟 / 工作日回归</Typography.Title>
                  </div>
                </div>
              </Card>
            </Col>
            <Col xs={24} xl={16}>
              <Card className="glass-card workspace-section-card" title="筛选与搜索">
                <Row gutter={[14, 14]}>
                  <Col xs={24} md={10}>
                    <Input.Search
                      value={searchDraft}
                      allowClear
                      placeholder="按任务名称搜索"
                      onChange={(event) => setSearchDraft(event.target.value)}
                      onSearch={(value) => {
                        setSearchText(value.trim());
                        setPage(1);
                      }}
                    />
                  </Col>
                  <Col xs={24} md={7}>
                    <Select
                      allowClear
                      style={{ width: '100%' }}
                      placeholder="筛选项目"
                      value={projectFilter}
                      onChange={(value) => {
                        setProjectFilter(value);
                        setPage(1);
                      }}
                      options={projects.map((project) => ({ value: project.id, label: project.name }))}
                    />
                  </Col>
                  <Col xs={24} md={7}>
                    <Select
                      style={{ width: '100%' }}
                      value={enabledFilter}
                      onChange={(value) => {
                        setEnabledFilter(value);
                        setPage(1);
                      }}
                      options={[
                        { value: 'all', label: '全部状态' },
                        { value: 'enabled', label: '仅启用' },
                        { value: 'disabled', label: '仅暂停' },
                      ]}
                    />
                  </Col>
                </Row>
              </Card>
            </Col>
          </Row>

          <Card className="glass-card workspace-section-card" title="调度编排清单">
            <Table<ScheduledJob>
              rowKey="id"
              loading={loadingJobs}
              dataSource={jobs}
              pagination={{
                current: page,
                pageSize,
                total,
                showSizeChanger: true,
                pageSizeOptions: ['10', '20', '50'],
                onChange: (nextPage, nextPageSize) => {
                  setPage(nextPage);
                  setPageSize(nextPageSize);
                },
              }}
              locale={{ emptyText: <Empty description="当前筛选条件下没有定时任务" /> }}
              columns={[
                {
                  title: '任务',
                  key: 'name',
                  render: (_, job) => {
                    const state = resolveJobState(job);
                    return (
                      <div className="scheduled-job-cell">
                        <Space wrap>
                          <Typography.Text strong>{job.name}</Typography.Text>
                          <Tag color={state.color}>{state.label}</Tag>
                        </Space>
                        <Typography.Paragraph ellipsis={{ rows: 2 }} className="scheduled-job-cell__desc">
                          {job.description || '未填写任务说明。'}
                        </Typography.Paragraph>
                      </div>
                    );
                  },
                },
                {
                  title: '目标',
                  key: 'target',
                  width: 240,
                  render: (_, job) => (
                    <Space direction="vertical" size={0}>
                      <Typography.Text>{suites.find((suite) => suite.id === job.suite_id)?.name ?? `Suite #${job.suite_id}`}</Typography.Text>
                      <Typography.Text type="secondary">
                        {environments.find((environment) => environment.id === job.environment_id)?.name ?? '默认环境'}
                      </Typography.Text>
                    </Space>
                  ),
                },
                {
                  title: '策略',
                  key: 'policy',
                  width: 220,
                  render: (_, job) => (
                    <Space direction="vertical" size={2}>
                      <Tag color="blue">{job.cron_expr}</Tag>
                      <Typography.Text type="secondary">{`${job.timezone} / ${job.concurrency_policy}`}</Typography.Text>
                    </Space>
                  ),
                },
                {
                  title: '下次运行',
                  dataIndex: 'next_run_at',
                  width: 170,
                  render: (value: string | null) => formatDateTime(value),
                },
                {
                  title: '最近触发',
                  key: 'last_triggered_at',
                  width: 180,
                  render: (_, job) => (
                    <Space direction="vertical" size={0}>
                      <Typography.Text>{formatDateTime(job.last_triggered_at)}</Typography.Text>
                      <Typography.Text type="secondary">
                        {job.last_triggered_execution_id ? `Execution #${job.last_triggered_execution_id}` : '尚未触发'}
                      </Typography.Text>
                    </Space>
                  ),
                },
                {
                  title: '操作',
                  key: 'actions',
                  width: 260,
                  render: (_, job) => (
                    <Space wrap>
                      <Button size="small" onClick={() => void openRunsDrawer(job)}>
                        运行记录
                      </Button>
                      <Button size="small" onClick={() => openEditDrawer(job)} disabled={!canOperate}>
                        编辑
                      </Button>
                      <Button size="small" onClick={() => void handleTrigger(job)} disabled={!canOperate}>
                        立即触发
                      </Button>
                      <Button size="small" onClick={() => void handleToggle(job)} disabled={!canOperate}>
                        {job.enabled ? '暂停' : '启用'}
                      </Button>
                    </Space>
                  ),
                },
              ]}
            />
          </Card>
        </>
      )}

      <Drawer
        title={editingJob ? `编辑任务 #${editingJob.id}` : '新建定时任务'}
        placement="right"
        width={580}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        destroyOnHidden
      >
        <Form<JobFormValues>
          form={form}
          layout="vertical"
          initialValues={DEFAULT_FORM_VALUES}
          onFinish={(values) => void handleSubmit(values)}
          onValuesChange={(changedValues) => {
            if ('project_id' in changedValues) {
              setSelectedProjectId(changedValues.project_id);
              form.setFieldsValue({ suite_id: 0, environment_id: undefined });
            }
          }}
        >
          <Row gutter={14}>
            <Col span={24}>
              <Form.Item name="name" label="任务名称" rules={[{ required: true, message: '请输入任务名称。' }]}>
                <Input placeholder="例如：每日冒烟 / 工作日回归" />
              </Form.Item>
            </Col>
            <Col span={24}>
              <Form.Item name="description" label="任务说明">
                <Input.TextArea rows={3} placeholder="说明这条调度的覆盖链路、触发背景和使用场景。" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="project_id" label="项目" rules={[{ required: true, message: '请选择项目。' }]}>
                <Select options={projects.map((project) => ({ value: project.id, label: project.name }))} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="suite_id" label="套件" rules={[{ required: true, message: '请选择套件。' }]}>
                <Select options={availableSuites.map((suite) => ({ value: suite.id, label: suite.name }))} />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="environment_id" label="环境">
                <Select
                  allowClear
                  placeholder="不选则使用默认环境"
                  options={availableEnvironments.map((environment) => ({ value: environment.id, label: environment.name }))}
                />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="timezone" label="时区" rules={[{ required: true, message: '请选择时区。' }]}>
                <Select
                  options={[
                    { value: 'Asia/Shanghai', label: 'Asia/Shanghai' },
                    { value: 'UTC', label: 'UTC' },
                  ]}
                />
              </Form.Item>
            </Col>
            <Col span={24}>
              <Form.Item
                name="cron_expr"
                label="Cron 表达式"
                rules={[{ required: true, message: '请输入 cron 表达式。' }]}
                extra="首版直接输入 cron 原文，推荐工作日早上使用 0 9 * * 1-5。"
              >
                <Input placeholder="0 9 * * 1-5" />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="concurrency_policy" label="并发策略" rules={[{ required: true }]}>
                <Select
                  options={[
                    { value: 'forbid', label: 'forbid / 已有运行则跳过' },
                    { value: 'allow', label: 'allow / 允许并发入队' },
                    { value: 'replace', label: 'replace / 预留策略' },
                  ]}
                />
              </Form.Item>
            </Col>
            <Col span={12}>
              <Form.Item name="misfire_policy" label="补偿策略" rules={[{ required: true }]}>
                <Select
                  options={[
                    { value: 'skip', label: 'skip / 错过窗口直接跳过' },
                    { value: 'fire_once', label: 'fire_once / 补触发一次' },
                  ]}
                />
              </Form.Item>
            </Col>
            <Col span={24}>
              <Form.Item name="enabled" label="保存后立即启用" valuePropName="checked">
                <Switch checkedChildren="启用" unCheckedChildren="暂停" />
              </Form.Item>
            </Col>
          </Row>
          <div className="scheduled-form-footer">
            <Space>
              <Button onClick={() => setDrawerOpen(false)}>取消</Button>
              <Button type="primary" htmlType="submit" loading={submitting}>
                {editingJob ? '保存修改' : '创建任务'}
              </Button>
            </Space>
          </div>
        </Form>
      </Drawer>

      <Drawer
        title={selectedJob ? `${selectedJob.name} · 运行记录` : '运行记录'}
        placement="right"
        width={620}
        open={runsDrawerOpen}
        onClose={() => setRunsDrawerOpen(false)}
      >
        {runsError ? (
          <Alert type="error" showIcon message="调度记录加载失败" description={runsError} />
        ) : loadingRuns ? (
          <StatePanel title="正在拉取调度记录" description="正在查询最近一次派发、跳过或失败信息。" variant="loading" />
        ) : runs.length ? (
          <div className="scheduled-run-stack">
            {runs.map((run) => {
              const meta = resolveRunMeta(run.status);
              return (
                <Card key={run.id} className="scheduled-run-card" bordered={false}>
                  <div className="scheduled-run-card__header">
                    <Space wrap>
                      <Tag color={meta.color}>{meta.label}</Tag>
                      <Typography.Text strong>{`Run #${run.id}`}</Typography.Text>
                    </Space>
                    <Typography.Text type="secondary">{formatDateTime(run.planned_run_at)}</Typography.Text>
                  </div>
                  <Row gutter={[14, 14]}>
                    <Col span={12}>
                      <Statistic title="计划时间" value={formatDateTime(run.planned_run_at)} />
                    </Col>
                    <Col span={12}>
                      <Statistic title="实际触发" value={formatDateTime(run.triggered_at)} />
                    </Col>
                  </Row>
                  <Typography.Paragraph className="scheduled-run-card__message">{run.message || '无附加说明。'}</Typography.Paragraph>
                  <Typography.Text type="secondary">
                    {run.execution_id ? `关联 Execution #${run.execution_id}` : '未生成 execution'}
                  </Typography.Text>
                </Card>
              );
            })}
          </div>
        ) : (
          <Empty description="当前任务还没有调度记录" />
        )}
      </Drawer>
    </div>
  );
}
