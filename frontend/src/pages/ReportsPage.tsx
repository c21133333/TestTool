import { Alert, App, Button, Card, Descriptions, Drawer, Empty, Row, Col, Segmented, Space, Statistic, Table, Tag, Typography } from 'antd';
import { useEffect, useMemo, useState } from 'react';

import { createApi } from '../api/services';
import type { Report } from '../api/types';
import { useAuth } from '../auth/AuthContext';
import { PageHero } from '../components/product/PageHero';
import { StatePanel } from '../components/product/StatePanel';
import { formatDateTime } from '../utils/display';

function downloadBlob(blob: Blob, fileName: string) {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = fileName;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function ReportsPage() {
  const { token } = useAuth();
  const api = useMemo(() => createApi(token), [token]);
  const { message } = App.useApp();
  const [reports, setReports] = useState<Report[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [previewReport, setPreviewReport] = useState<Report | null>(null);
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [previewMode, setPreviewMode] = useState<'html' | 'json'>('json');
  const [previewContent, setPreviewContent] = useState('');
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [filterType, setFilterType] = useState<'all' | 'html' | 'json'>('all');

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      setReports(await api.listReports());
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载报告失败。');
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refresh();
  }, [api]);

  useEffect(() => {
    return () => {
      if (previewUrl) {
        URL.revokeObjectURL(previewUrl);
      }
    };
  }, [previewUrl]);

  async function openPreview(report: Report) {
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
      setPreviewUrl(null);
    }
    setPreviewReport(report);
    setPreviewOpen(true);
    setPreviewLoading(true);
    setPreviewError(null);
    try {
      if (report.report_type === 'html') {
        const blob = await api.fetchReportBlob(report.id);
        const url = URL.createObjectURL(blob);
        setPreviewMode('html');
        setPreviewUrl(url);
        setPreviewContent('');
      } else {
        const text = await api.fetchReportText(report.id);
        setPreviewMode('json');
        setPreviewContent(text);
      }
    } catch (err) {
      setPreviewError(err instanceof Error ? err.message : '加载报告预览失败。');
    } finally {
      setPreviewLoading(false);
    }
  }

  async function openInNewTab(report: Report) {
    try {
      const blob = await api.fetchReportBlob(report.id);
      const url = URL.createObjectURL(blob);
      window.open(url, '_blank', 'noopener,noreferrer');
      message.success('已在新标签页打开报告。');
    } catch (err) {
      message.error(err instanceof Error ? err.message : '打开报告失败。');
    }
  }

  async function downloadReport(report: Report) {
    try {
      const blob = await api.fetchReportBlob(report.id);
      const fileName = report.file_path.split(/[\\/]/).slice(-1)[0] ?? `report-${report.id}.${report.report_type}`;
      downloadBlob(blob, fileName);
      message.success('已开始下载报告。');
    } catch (err) {
      message.error(err instanceof Error ? err.message : '下载报告失败。');
    }
  }

  const filteredReports = reports.filter((report) => filterType === 'all' || report.report_type === filterType);
  const htmlCount = reports.filter((report) => report.report_type === 'html').length;
  const jsonCount = reports.filter((report) => report.report_type === 'json').length;
  const filterLabel = filterType === 'all' ? '全部' : filterType.toUpperCase();

  return (
    <div className="page-stack">
      <PageHero
        eyebrow="报告中心"
        title="执行报告"
        description="在这里直接预览、打开和下载执行报告，不再手动翻服务器路径。"
        tags={[
          <Tag key="total" color="processing">{`${reports.length} 份报告`}</Tag>,
          <Tag key="filter" color="default">{`当前筛选：${filterLabel}`}</Tag>,
        ]}
        actions={
          <Space wrap>
            <Segmented
              value={filterType}
              onChange={(value) => setFilterType(value as 'all' | 'html' | 'json')}
              options={[
                { label: '全部', value: 'all' },
                { label: 'HTML', value: 'html' },
                { label: 'JSON', value: 'json' },
              ]}
            />
            <Button onClick={() => void refresh()}>刷新</Button>
          </Space>
        }
      />

      {error ? (
        <Alert
          type="error"
          showIcon
          message="报告列表加载失败"
          description={error}
          action={
            <Button size="small" onClick={() => void refresh()}>
              重试
            </Button>
          }
        />
      ) : null}

      {loading ? (
        <StatePanel title="正在加载报告" description="正在拉取报告清单和元数据。" variant="loading" />
      ) : (
        <>
          <Row gutter={[18, 18]}>
            <Col xs={24} md={8}>
              <Card className="metric-card">
                <Statistic title="报告总数" value={reports.length} />
              </Card>
            </Col>
            <Col xs={24} md={8}>
              <Card className="metric-card">
                <Statistic title="HTML 报告" value={htmlCount} />
              </Card>
            </Col>
            <Col xs={24} md={8}>
              <Card className="metric-card">
                <Statistic title="JSON 报告" value={jsonCount} />
              </Card>
            </Col>
          </Row>

          <Card className="glass-card" title="报告列表">
            <Table<Report>
              rowKey="id"
              dataSource={filteredReports}
              pagination={false}
              locale={{
                emptyText: <Empty description="当前筛选条件下没有报告" />,
              }}
              columns={[
                { title: 'ID', dataIndex: 'id', width: 80 },
                { title: '执行 ID', dataIndex: 'execution_id', width: 110 },
                {
                  title: '类型',
                  dataIndex: 'report_type',
                  width: 120,
                  render: (value: string) => <Tag color={value === 'html' ? 'processing' : 'default'}>{value.toUpperCase()}</Tag>,
                },
                { title: '创建时间', dataIndex: 'created_at', width: 170, render: (value: string) => formatDateTime(value) },
                { title: '路径', dataIndex: 'file_path' },
                {
                  title: '操作',
                  render: (_, report) => (
                    <Space>
                      <Button size="small" onClick={() => void openPreview(report)}>
                        预览
                      </Button>
                      <Button size="small" onClick={() => void openInNewTab(report)}>
                        新标签打开
                      </Button>
                      <Button size="small" onClick={() => void downloadReport(report)}>
                        下载
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
        title={previewReport ? `${previewReport.report_type.toUpperCase()} 报告 #${previewReport.id}` : '报告预览'}
        placement="right"
        width={previewMode === 'html' ? '75vw' : 860}
        open={previewOpen}
        onClose={() => setPreviewOpen(false)}
        extra={
          previewReport ? (
            <Space>
              <Button onClick={() => void openInNewTab(previewReport)}>新标签打开</Button>
              <Button type="primary" onClick={() => void downloadReport(previewReport)}>
                下载
              </Button>
            </Space>
          ) : null
        }
      >
        {!previewReport ? (
          <StatePanel title="尚未选择报告" description="请从表格里选择一份报告，在这里查看预览。" />
        ) : previewLoading ? (
          <StatePanel title="正在加载预览" description="正在获取报告内容。" variant="loading" />
        ) : previewError ? (
          <StatePanel title="报告预览失败" description={previewError} variant="error" />
        ) : (
          <Space direction="vertical" style={{ width: '100%' }} size="large">
            <Descriptions bordered column={1} size="small">
              <Descriptions.Item label="报告 ID">{previewReport.id}</Descriptions.Item>
              <Descriptions.Item label="执行 ID">{previewReport.execution_id}</Descriptions.Item>
              <Descriptions.Item label="类型">{previewReport.report_type.toUpperCase()}</Descriptions.Item>
              <Descriptions.Item label="创建时间">{formatDateTime(previewReport.created_at)}</Descriptions.Item>
              <Descriptions.Item label="路径">{previewReport.file_path}</Descriptions.Item>
            </Descriptions>

            {previewMode === 'html' && previewUrl ? (
              <iframe title={previewReport.file_path} src={previewUrl} className="report-frame" />
            ) : (
              <pre className="code-block">{previewContent}</pre>
            )}
          </Space>
        )}
      </Drawer>
    </div>
  );
}
