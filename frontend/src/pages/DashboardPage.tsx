import { Card, Col, Row, Statistic, Typography } from 'antd';
import { useEffect, useState } from 'react';

import { createApi } from '../api/services';
import type { Execution, Project, Report } from '../api/types';
import { useAuth } from '../auth/AuthContext';

export function DashboardPage() {
  const { token } = useAuth();
  const api = createApi(token);
  const [projects, setProjects] = useState<Project[]>([]);
  const [executions, setExecutions] = useState<Execution[]>([]);
  const [reports, setReports] = useState<Report[]>([]);

  useEffect(() => {
    void Promise.all([api.listProjects(), api.listExecutions({ page: 1, page_size: 100 }), api.listReports()]).then(
      ([nextProjects, nextExecutions, nextReports]) => {
        setProjects(nextProjects);
        setExecutions(nextExecutions.items);
        setReports(nextReports);
      },
    );
  }, [token]);

  const caseCount = projects.flatMap((project) => project.suites).flatMap((suite) => suite.cases).length;
  const envCount = projects.flatMap((project) => project.environments).length;

  return (
    <div className="page-stack">
      <div className="page-hero">
        <Typography.Title>迁移总览</Typography.Title>
        <Typography.Paragraph>
          当前平台已经完成 Web 化主链路迁移。这里展示工作区、执行记录和报告数量的实时概览。
        </Typography.Paragraph>
      </div>
      <Row gutter={[18, 18]}>
        <Col span={6}>
          <Card className="metric-card">
            <Statistic title="项目数" value={projects.length} />
          </Card>
        </Col>
        <Col span={6}>
          <Card className="metric-card">
            <Statistic title="用例数" value={caseCount} />
          </Card>
        </Col>
        <Col span={6}>
          <Card className="metric-card">
            <Statistic title="环境数" value={envCount} />
          </Card>
        </Col>
        <Col span={6}>
          <Card className="metric-card">
            <Statistic title="执行数" value={executions.length} />
          </Card>
        </Col>
      </Row>
      <Card title="最近报告" className="glass-card">
        {reports.slice(0, 5).map((report) => (
          <div key={report.id} className="row-line">
            <span>{report.report_type.toUpperCase()}</span>
            <span>{report.file_path}</span>
          </div>
        ))}
      </Card>
    </div>
  );
}
