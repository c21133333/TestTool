import {
  ArrowRightOutlined,
  ClockCircleOutlined,
  FileSearchOutlined,
  FolderOpenOutlined,
  ReloadOutlined,
  WarningOutlined,
} from '@ant-design/icons';
import { Alert, Button, Card, List, Progress, Space, Tag, Typography } from 'antd';
import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import { createApi } from '../api/services';
import type { Execution, Project, Report } from '../api/types';
import { useAuth } from '../auth/AuthContext';
import { PageHero } from '../components/product/PageHero';
import { StatePanel } from '../components/product/StatePanel';
import { StatusBadge } from '../components/product/StatusBadge';
import { formatDateTime, formatPercent } from '../utils/display';
import { executionStatusMeta } from '../utils/status';

function executionScopeLabel(scope: Execution['scope']) {
  return scope === 'suite' ? '套件执行' : '用例执行';
}

function executionPassRate(execution: Execution) {
  const summaryPassRate = execution.summary_json.pass_rate;
  if (typeof summaryPassRate === 'number') {
    return summaryPassRate;
  }
  if (!execution.items.length) {
    return execution.status === 'success' ? 100 : 0;
  }
  const passedCount = execution.items.filter((item) => item.status === 'PASS').length;
  return (passedCount / execution.items.length) * 100;
}

function reportFileName(report: Report) {
  return report.file_path.split(/[\\/]/).slice(-1)[0] ?? report.file_path;
}

export function DashboardPage() {
  const { token } = useAuth();
  const api = useMemo(() => createApi(token), [token]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [executions, setExecutions] = useState<Execution[]>([]);
  const [reports, setReports] = useState<Report[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      const [nextProjects, nextExecutions, nextReports] = await Promise.all([
        api.listProjects(),
        api.listExecutions({ page: 1, page_size: 100 }),
        api.listReports(),
      ]);
      setProjects(nextProjects);
      setExecutions(nextExecutions.items);
      setReports(nextReports);
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载指挥台数据失败。');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refresh();
  }, [api]);

  const suiteCount = projects.flatMap((project) => project.suites).length;
  const caseCount = projects.flatMap((project) => project.suites).flatMap((suite) => suite.cases).length;
  const environmentCount = projects.flatMap((project) => project.environments).length;
  const recentExecutions = executions.slice(0, 6);
  const recentReports = reports.slice(0, 5);
  const activeExecutionCount = executions.filter((item) => item.status === 'pending' || item.status === 'running').length;
  const failedExecutionCount = executions.filter((item) => item.status === 'failed').length;
  const executionSuccessRate =
    executions.length === 0
      ? 0
      : (executions.filter((item) => item.status === 'success').length / executions.length) * 100;
  const lastExecution = executions[0] ?? null;
  const archiveCoverage = projects.length === 0 ? 0 : reports.length / projects.length;
  const archiveDensity = Math.min(archiveCoverage * 100, 100);
  const metricCards = [
    {
      code: 'P-01',
      label: '项目',
      value: projects.length,
      detail: '已纳入统一治理的项目',
      accent: 'primary',
    },
    {
      code: 'S-02',
      label: '套件',
      value: suiteCount,
      detail: '当前可调度的测试套件',
      accent: 'info',
    },
    {
      code: 'C-03',
      label: '用例',
      value: caseCount,
      detail: '已登记的 API 用例资产',
      accent: 'signal',
    },
    {
      code: 'E-04',
      label: '环境',
      value: environmentCount,
      detail: '可切换的执行环境',
      accent: 'success',
    },
  ] as const;

  return (
    <div className="page-stack">
      <PageHero
        eyebrow="OBS / COMMAND CENTER"
        title="今日质量态势"
        description="集中查看执行健康度、风险告警和最新归档结果，让测试平台首页更像真正的质量指挥台。"
        tags={[
          <span key="projects" className="lab-chip">
            {projects.length} 个项目
          </span>,
          <span key="active" className="lab-chip">
            {activeExecutionCount > 0 ? `${activeExecutionCount} 条执行进行中` : '当前无进行中执行'}
          </span>,
          <span key="reports" className="lab-chip">
            {reports.length} 份归档报告
          </span>,
        ]}
        actions={
          <Space wrap>
            <Button icon={<ReloadOutlined />} onClick={() => void refresh()}>
              刷新指挥台
            </Button>
            <Button type="primary">
              <Link to="/executions">查看执行中心</Link>
            </Button>
          </Space>
        }
      />

      {error ? (
        <Alert
          type="error"
          showIcon
          message="指挥台加载失败"
          description={error}
          action={
            <Button size="small" onClick={() => void refresh()}>
              重试
            </Button>
          }
        />
      ) : null}

      {loading ? (
        <StatePanel title="正在加载指挥台" description="正在拉取项目、执行记录和报告归档数据。" variant="loading" />
      ) : (
        <>
          <section className="dashboard-lab-grid">
            <Card className="glass-card dashboard-hero-card" bordered={false}>
              <div className="dashboard-hero-card__eyebrow">今日信号</div>
              <div className="dashboard-hero-card__headline">
                <div>
                  <Typography.Title level={2}>{formatPercent(executionSuccessRate)}</Typography.Title>
                  <Typography.Paragraph>最近 100 次执行的整体成功率，用来快速判断平台当前稳定性。</Typography.Paragraph>
                </div>
                <div className="dashboard-hero-card__dial">
                  <Progress
                    type="circle"
                    percent={Number(executionSuccessRate.toFixed(0))}
                    strokeColor={{
                      '0%': '#2f5f93',
                      '100%': failedExecutionCount > 0 ? '#56d4ff' : '#2f7a67',
                    }}
                    trailColor="rgba(47, 95, 147, 0.08)"
                  />
                </div>
              </div>

              <div className="dashboard-hero-card__stats">
                <div className="dashboard-inline-stat">
                  <span className="dashboard-inline-stat__label">进行中执行</span>
                  <strong>{activeExecutionCount}</strong>
                </div>
                <div className="dashboard-inline-stat">
                  <span className="dashboard-inline-stat__label">失败告警</span>
                  <strong>{failedExecutionCount}</strong>
                </div>
                <div className="dashboard-inline-stat">
                  <span className="dashboard-inline-stat__label">归档覆盖</span>
                  <strong>{formatPercent(archiveDensity)}</strong>
                </div>
              </div>

              <div className="dashboard-hero-card__footer">
                <div className="dashboard-hero-card__signal">
                  <span className="dashboard-hero-card__signal-dot" />
                  <Typography.Text>
                    {failedExecutionCount > 0
                      ? '当前窗口仍有失败执行，建议先处理异常波次，再扩大回归范围。'
                      : '当前执行态势稳定，可以继续推进新的调度任务。'}
                  </Typography.Text>
                </div>
                {lastExecution ? (
                  <Typography.Text type="secondary">
                    最近一条执行：{lastExecution.target_name} / {formatDateTime(lastExecution.created_at)}
                  </Typography.Text>
                ) : (
                  <Typography.Text type="secondary">暂无执行记录。</Typography.Text>
                )}
              </div>
            </Card>

            <Card className="glass-card dashboard-risk-card" bordered={false} title="风险告警">
              <div className="dashboard-risk-list">
                <div className="dashboard-risk-item">
                  <ClockCircleOutlined />
                  <div>
                    <Typography.Text strong>执行频率</Typography.Text>
                    <Typography.Paragraph>
                      {executions.length > 0
                        ? `当前样本窗口内共记录 ${executions.length} 条执行。`
                        : '当前样本窗口内还没有执行记录。'}
                    </Typography.Paragraph>
                  </div>
                </div>
                <div className="dashboard-risk-item">
                  <WarningOutlined />
                  <div>
                    <Typography.Text strong>失败压力</Typography.Text>
                    <Typography.Paragraph>
                      {failedExecutionCount > 0
                        ? `仍有 ${failedExecutionCount} 条失败执行需要跟进。`
                        : '当前窗口内没有失败执行告警。'}
                    </Typography.Paragraph>
                  </div>
                </div>
                <div className="dashboard-risk-item">
                  <FolderOpenOutlined />
                  <div>
                    <Typography.Text strong>归档就绪度</Typography.Text>
                    <Typography.Paragraph>
                      {reports.length > 0
                        ? `已有 ${reports.length} 份报告可用于追溯和复盘。`
                        : '当前还没有可用于回溯的归档报告。'}
                    </Typography.Paragraph>
                  </div>
                </div>
              </div>

              <div className="dashboard-risk-card__actions">
                <Button type="link">
                  <Link to="/workspace">进入工作台</Link>
                </Button>
                <Button type="link">
                  <Link to="/reports">查看报告归档</Link>
                </Button>
              </div>
            </Card>
          </section>

          <section className="dashboard-kpi-grid">
            {metricCards.map((metric) => (
              <Card
                key={metric.code}
                className={`metric-card dashboard-kpi-card dashboard-kpi-card--${metric.accent}`}
                bordered={false}
              >
                <span className="dashboard-kpi-card__code">{metric.code}</span>
                <Typography.Text className="dashboard-kpi-card__label">{metric.label}</Typography.Text>
                <Typography.Title level={2}>{metric.value}</Typography.Title>
                <Typography.Paragraph>{metric.detail}</Typography.Paragraph>
              </Card>
            ))}
          </section>

          <section className="dashboard-stream-grid">
            <Card
              className="glass-card dashboard-stream-card"
              bordered={false}
              title="最近执行"
              extra={
                <Button type="link">
                  <Link to="/executions">
                    查看全部 <ArrowRightOutlined />
                  </Link>
                </Button>
              }
            >
              {recentExecutions.length === 0 ? (
                <StatePanel title="暂无执行记录" description="可以从工作台或执行中心发起第一条执行任务。" />
              ) : (
                <List
                  className="dashboard-stream-list"
                  dataSource={recentExecutions}
                  renderItem={(execution) => (
                    <List.Item
                      actions={[
                        <Link key="detail" to="/executions">
                          详情
                        </Link>,
                      ]}
                    >
                      <List.Item.Meta
                        title={
                          <div className="dashboard-stream-list__title">
                            <Typography.Text strong>{execution.target_name}</Typography.Text>
                            <StatusBadge {...executionStatusMeta(execution.status)} />
                          </div>
                        }
                        description={
                          <div className="dashboard-stream-list__description">
                            <Typography.Text type="secondary">{executionScopeLabel(execution.scope)}</Typography.Text>
                            <Typography.Text type="secondary">{formatDateTime(execution.created_at)}</Typography.Text>
                          </div>
                        }
                      />
                      <div className="list-side-stat">
                        <Typography.Text strong>{formatPercent(executionPassRate(execution))}</Typography.Text>
                        <Typography.Text type="secondary">通过率</Typography.Text>
                      </div>
                    </List.Item>
                  )}
                />
              )}
            </Card>

            <Card
              className="glass-card dashboard-stream-card"
              bordered={false}
              title="最新归档"
              extra={
                <Button type="link">
                  <Link to="/reports">
                    查看归档 <ArrowRightOutlined />
                  </Link>
                </Button>
              }
            >
              {recentReports.length === 0 ? (
                <StatePanel title="暂无归档报告" description="执行结束后，HTML 和 JSON 报告会在这里集中呈现。" />
              ) : (
                <List
                  className="dashboard-stream-list"
                  dataSource={recentReports}
                  renderItem={(report) => (
                    <List.Item
                      actions={[
                        <Link key="reports" to="/reports">
                          查看
                        </Link>,
                      ]}
                    >
                      <List.Item.Meta
                        title={
                          <div className="dashboard-stream-list__title">
                            <Typography.Text strong>{reportFileName(report)}</Typography.Text>
                            <Tag color={report.report_type === 'html' ? 'processing' : 'default'}>
                              {report.report_type.toUpperCase()}
                            </Tag>
                          </div>
                        }
                        description={
                          <div className="dashboard-stream-list__description">
                            <Typography.Text type="secondary">{report.file_path}</Typography.Text>
                            <Typography.Text type="secondary">{formatDateTime(report.created_at)}</Typography.Text>
                          </div>
                        }
                      />
                      <div className="dashboard-report-pill">
                        <FileSearchOutlined />
                      </div>
                    </List.Item>
                  )}
                />
              )}
            </Card>
          </section>
        </>
      )}
    </div>
  );
}
