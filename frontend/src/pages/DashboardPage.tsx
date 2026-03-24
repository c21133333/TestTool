import { Alert, Button, Card, Col, List, Progress, Row, Space, Statistic, Tag, Typography } from 'antd';
import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import { createApi } from '../api/services';
import type { Execution, Project, Report } from '../api/types';
import { useAuth } from '../auth/AuthContext';
import { PageHero } from '../components/product/PageHero';
import { StatePanel } from '../components/product/StatePanel';
import { formatDateTime, formatPercent } from '../utils/display';

function executionStatusColor(status: Execution['status']) {
  if (status === 'success') return 'green';
  if (status === 'failed') return 'red';
  return 'processing';
}

function executionStatusLabel(status: Execution['status']) {
  if (status === 'pending') return '排队中';
  if (status === 'running') return '执行中';
  if (status === 'success') return '成功';
  return '失败';
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
      setError(err instanceof Error ? err.message : '加载概览数据失败。');
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

  return (
    <div className="page-stack">
      <PageHero
        eyebrow="运营快照"
        title="团队概览"
        description="把资产规模、最新执行和报告产出收敛到一个总览视图里。"
        tags={[
          <Tag key="projects" color="processing">{`${projects.length} 个项目`}</Tag>,
          <Tag key="active" color={activeExecutionCount > 0 ? 'warning' : 'success'}>
            {activeExecutionCount > 0 ? `${activeExecutionCount} 条执行进行中` : '当前没有进行中的执行'}
          </Tag>,
        ]}
        actions={
          <Space wrap>
            <Button onClick={() => void refresh()}>刷新</Button>
            <Button type="primary">
              <Link to="/executions">查看执行</Link>
            </Button>
          </Space>
        }
      />

      {error ? (
        <Alert
          type="error"
          showIcon
          message="概览加载失败"
          description={error}
          action={
            <Button size="small" onClick={() => void refresh()}>
              重试
            </Button>
          }
        />
      ) : null}

      {loading ? (
        <StatePanel
          title="正在加载概览"
          description="正在拉取项目、执行记录和报告数据。"
          variant="loading"
        />
      ) : (
        <>
          <Row gutter={[18, 18]}>
            <Col xs={24} md={12} xl={6}>
              <Card className="metric-card">
                <Statistic title="项目" value={projects.length} />
              </Card>
            </Col>
            <Col xs={24} md={12} xl={6}>
              <Card className="metric-card">
                <Statistic title="套件" value={suiteCount} />
              </Card>
            </Col>
            <Col xs={24} md={12} xl={6}>
              <Card className="metric-card">
                <Statistic title="用例" value={caseCount} />
              </Card>
            </Col>
            <Col xs={24} md={12} xl={6}>
              <Card className="metric-card">
                <Statistic title="环境" value={environmentCount} />
              </Card>
            </Col>
          </Row>

          <Row gutter={[18, 18]}>
            <Col xs={24} xl={10}>
              <Card className="glass-card" title="执行健康度">
                <Space direction="vertical" style={{ width: '100%' }} size="large">
                  <div>
                    <Space align="baseline">
                      <Typography.Title level={3} style={{ margin: 0 }}>
                        {formatPercent(executionSuccessRate)}
                      </Typography.Title>
                      <Typography.Text type="secondary">成功率</Typography.Text>
                    </Space>
                    <Progress percent={Number(executionSuccessRate.toFixed(0))} showInfo={false} strokeColor="#22c55e" />
                    <Space wrap>
                      <Tag color="warning">{`${activeExecutionCount} 条执行进行中`}</Tag>
                      <Tag color={failedExecutionCount > 0 ? 'red' : 'success'}>
                        {failedExecutionCount > 0 ? `${failedExecutionCount} 条执行失败` : '当前执行状态稳定'}
                      </Tag>
                    </Space>
                  </div>

                  {recentExecutions.length === 0 ? (
                    <StatePanel
                      title="暂时还没有执行记录"
                      description="请先创建或导入资产，再到执行页发起用例或套件执行。"
                    />
                  ) : (
                    <List
                      dataSource={recentExecutions}
                      renderItem={(execution) => (
                        <List.Item
                          actions={[
                            <Link key="detail" to="/executions">
                              查看
                            </Link>,
                          ]}
                        >
                          <List.Item.Meta
                            title={
                              <Space wrap>
                                <Typography.Text strong>{execution.target_name}</Typography.Text>
                                <Tag color={executionStatusColor(execution.status)}>{executionStatusLabel(execution.status)}</Tag>
                              </Space>
                            }
                            description={`${execution.scope === 'suite' ? '套件执行' : '用例执行'} · ${formatDateTime(execution.created_at)}`}
                          />
                          <div className="list-side-stat">
                            <Typography.Text strong>{formatPercent(executionPassRate(execution))}</Typography.Text>
                            <Typography.Text type="secondary">通过率</Typography.Text>
                          </div>
                        </List.Item>
                      )}
                    />
                  )}
                </Space>
              </Card>
            </Col>

            <Col xs={24} xl={14}>
              <Card
                className="glass-card"
                title="最新报告"
                extra={
                  <Space>
                    <Button type="link">
                      <Link to="/workspace">打开工作台</Link>
                    </Button>
                    <Button type="link">
                      <Link to="/reports">打开报告中心</Link>
                    </Button>
                  </Space>
                }
              >
                {recentReports.length === 0 ? (
                    <StatePanel
                      title="暂时还没有报告"
                      description="执行完成后，HTML 与 JSON 报告会在这里展示。"
                    />
                ) : (
                  <List
                    dataSource={recentReports}
                    renderItem={(report) => (
                      <List.Item
                        actions={[
                            <Link key="reports" to="/reports">
                              预览
                            </Link>,
                        ]}
                      >
                        <List.Item.Meta
                          title={
                            <Space wrap>
                              <Typography.Text strong>{report.file_path.split(/[\\/]/).slice(-1)[0] ?? report.file_path}</Typography.Text>
                              <Tag color={report.report_type === 'html' ? 'processing' : 'default'}>
                                {report.report_type.toUpperCase()}
                              </Tag>
                            </Space>
                          }
                          description={
                            <Space wrap>
                              <Typography.Text type="secondary">{report.file_path}</Typography.Text>
                              <Typography.Text type="secondary">{formatDateTime(report.created_at)}</Typography.Text>
                            </Space>
                          }
                        />
                      </List.Item>
                    )}
                  />
                )}
              </Card>
            </Col>
          </Row>
        </>
      )}
    </div>
  );
}
