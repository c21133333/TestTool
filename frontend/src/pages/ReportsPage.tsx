import { Alert, App, Button, Card, Descriptions, Drawer, Empty, Space, Table, Tag, Typography } from 'antd';
import { useEffect, useMemo, useState } from 'react';

import { createApi } from '../api/services';
import type { AiCopilotPreview, AiReportSummaryResult, Report } from '../api/types';
import { useAuth } from '../auth/AuthContext';
import { AiCapabilityActionCard } from '../components/ai-copilot/AiCapabilityActionCard';
import { AiSuggestionPanel } from '../components/ai-copilot/AiSuggestionPanel';
import { PageHero } from '../components/product/PageHero';
import { StatePanel } from '../components/product/StatePanel';
import { formatDateTime } from '../utils/display';
import { artifactStatusMeta } from '../utils/status';

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
  const [summaryPreview, setSummaryPreview] = useState<AiCopilotPreview<AiReportSummaryResult> | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [summaryApplyLoading, setSummaryApplyLoading] = useState(false);
  const [summaryError, setSummaryError] = useState<string | null>(null);

  async function refresh() {
    setLoading(true);
    setError(null);
    try {
      setReports(await api.listReports());
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载报告归档失败。');
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
    setSummaryPreview(null);
    setSummaryError(null);
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
      setPreviewError(err instanceof Error ? err.message : '打开报告预览失败。');
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

  async function handlePreviewSummary() {
    if (!previewReport) {
      return;
    }
    setSummaryLoading(true);
    setSummaryError(null);
    try {
      const result = await api.previewAiReportSummary({ report_id: previewReport.id });
      setSummaryPreview(result);
      message.success('已生成 AI 摘要。');
    } catch (err) {
      const nextError = err instanceof Error ? err.message : '生成 AI 摘要失败。';
      setSummaryError(nextError);
      message.error(nextError);
    } finally {
      setSummaryLoading(false);
    }
  }

  async function handleApplySummary() {
    if (!summaryPreview || !previewReport) {
      return;
    }
    setSummaryApplyLoading(true);
    setSummaryError(null);
    try {
      const result = await api.applyAiReportSummary(summaryPreview.artifact_id);
      setSummaryPreview((current) => (current ? { ...current, status: 'applied', result: result.ai_summary } : current));
      setReports((current) =>
        current.map((report) =>
          report.id === previewReport.id
            ? {
                ...report,
                metadata_json: {
                  ...report.metadata_json,
                  ai_summary: result.ai_summary,
                },
              }
            : report,
        ),
      );
      setPreviewReport((current) =>
        current
          ? {
              ...current,
              metadata_json: {
                ...current.metadata_json,
                ai_summary: result.ai_summary,
              },
            }
          : current,
      );
      message.success('已将 AI 摘要写入报告元数据。');
    } catch (err) {
      const nextError = err instanceof Error ? err.message : '应用 AI 摘要失败。';
      setSummaryError(nextError);
      message.error(nextError);
    } finally {
      setSummaryApplyLoading(false);
    }
  }

  async function handleCopySummary() {
    const reportSummary = previewReport?.metadata_json.ai_summary as AiReportSummaryResult | undefined;
    const summary = summaryPreview?.result ?? reportSummary;
    if (!summary) {
      return;
    }
    const content = [
      `概览：${summary.executive_summary}`,
      `风险：${summary.risk_summary}`,
      ...summary.recommended_actions.map((item) => `- ${item}`),
    ].join('\n');
    try {
      await navigator.clipboard.writeText(content);
      message.success('已复制 AI 摘要。');
    } catch {
      message.error('复制 AI 摘要失败。');
    }
  }

  const filteredReports = reports.filter((report) => filterType === 'all' || report.report_type === filterType);
  const htmlCount = reports.filter((report) => report.report_type === 'html').length;
  const jsonCount = reports.filter((report) => report.report_type === 'json').length;
  const summarizedCount = reports.filter((report) => Boolean(report.metadata_json.ai_summary)).length;
  const filterLabel = filterType === 'all' ? '全部' : filterType.toUpperCase();

  return (
    <div className="page-stack">
      <PageHero
        eyebrow="OBS / REPORT ARCHIVE"
        title="报告归档"
        description="集中查看 HTML 与 JSON 报告产物，支持预览、下载，并用 AI 摘要补充管理视角。"
        tags={[
          <span key="total" className="lab-chip">
            {reports.length} 份报告
          </span>,
          <span key="filter" className="lab-chip">
            当前筛选：{filterLabel}
          </span>,
          <span key="ai" className="lab-chip">
            {summarizedCount} 份 AI 摘要
          </span>,
        ]}
        actions={
          <Space wrap>
            <Button.Group>
              <Button type={filterType === 'all' ? 'primary' : 'default'} onClick={() => setFilterType('all')}>
                全部
              </Button>
              <Button type={filterType === 'html' ? 'primary' : 'default'} onClick={() => setFilterType('html')}>
                HTML
              </Button>
              <Button type={filterType === 'json' ? 'primary' : 'default'} onClick={() => setFilterType('json')}>
                JSON
              </Button>
            </Button.Group>
            <Button onClick={() => void refresh()}>刷新归档</Button>
          </Space>
        }
      />

      {error ? (
        <Alert
          type="error"
          showIcon
          message="报告归档加载失败"
          description={error}
          action={
            <Button size="small" onClick={() => void refresh()}>
              重试
            </Button>
          }
        />
      ) : null}

      {loading ? (
        <StatePanel title="正在加载归档" description="正在拉取报告产物和相关元数据。" variant="loading" />
      ) : (
        <>
          <div className="dashboard-kpi-grid">
            <Card className="metric-card dashboard-kpi-card dashboard-kpi-card--primary" bordered={false}>
              <span className="dashboard-kpi-card__code">ARC-01</span>
              <Typography.Text className="workspace-summary-card__label">报告总数</Typography.Text>
              <Typography.Title level={2}>{reports.length}</Typography.Title>
              <Typography.Paragraph>当前已归档的报告数量</Typography.Paragraph>
            </Card>
            <Card className="metric-card dashboard-kpi-card dashboard-kpi-card--info" bordered={false}>
              <span className="dashboard-kpi-card__code">HTM-02</span>
              <Typography.Text className="workspace-summary-card__label">HTML 报告</Typography.Text>
              <Typography.Title level={2}>{htmlCount}</Typography.Title>
              <Typography.Paragraph>可直接预览的交互式报告</Typography.Paragraph>
            </Card>
            <Card className="metric-card dashboard-kpi-card dashboard-kpi-card--signal" bordered={false}>
              <span className="dashboard-kpi-card__code">JSN-03</span>
              <Typography.Text className="workspace-summary-card__label">JSON 报告</Typography.Text>
              <Typography.Title level={2}>{jsonCount}</Typography.Title>
              <Typography.Paragraph>可供系统消费的结构化报告</Typography.Paragraph>
            </Card>
            <Card className="metric-card dashboard-kpi-card dashboard-kpi-card--success" bordered={false}>
              <span className="dashboard-kpi-card__code">AI-04</span>
              <Typography.Text className="workspace-summary-card__label">AI 摘要</Typography.Text>
              <Typography.Title level={2}>{summarizedCount}</Typography.Title>
              <Typography.Paragraph>已补充 AI 摘要的报告数量</Typography.Paragraph>
            </Card>
          </div>

          <Card className="glass-card workspace-section-card" title="归档清单">
            <Table<Report>
              rowKey="id"
              dataSource={filteredReports}
              pagination={{ pageSize: 10, showSizeChanger: false, hideOnSinglePage: true }}
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
                { title: '文件路径', dataIndex: 'file_path' },
                {
                  title: '操作',
                  render: (_, report) => (
                    <Space>
                      <Button size="small" onClick={() => void openPreview(report)}>
                        预览
                      </Button>
                      <Button size="small" onClick={() => void openInNewTab(report)}>
                        新标签页
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
              <Button loading={summaryLoading} onClick={() => void handlePreviewSummary()}>
                AI 摘要
              </Button>
              <Button
                loading={summaryApplyLoading}
                disabled={!summaryPreview || summaryPreview.status === 'applied'}
                onClick={() => void handleApplySummary()}
              >
                应用摘要
              </Button>
              <Button disabled={!summaryPreview && !previewReport.metadata_json.ai_summary} onClick={() => void handleCopySummary()}>
                复制摘要
              </Button>
              <Button onClick={() => void openInNewTab(previewReport)}>新标签页</Button>
              <Button type="primary" onClick={() => void downloadReport(previewReport)}>
                下载
              </Button>
            </Space>
          ) : null
        }
      >
        {!previewReport ? (
          <StatePanel title="未选择报告" description="从归档清单中选择一份报告后，即可在这里查看内容。" />
        ) : previewLoading ? (
          <StatePanel title="正在加载预览" description="正在获取报告内容。" variant="loading" />
        ) : previewError ? (
          <StatePanel title="预览加载失败" description={previewError} variant="error" />
        ) : (
          <Space direction="vertical" style={{ width: '100%' }} size="large">
            <Descriptions bordered column={1} size="small">
              <Descriptions.Item label="报告 ID">{previewReport.id}</Descriptions.Item>
              <Descriptions.Item label="执行 ID">{previewReport.execution_id}</Descriptions.Item>
              <Descriptions.Item label="类型">{previewReport.report_type.toUpperCase()}</Descriptions.Item>
              <Descriptions.Item label="创建时间">{formatDateTime(previewReport.created_at)}</Descriptions.Item>
              <Descriptions.Item label="文件路径">{previewReport.file_path}</Descriptions.Item>
            </Descriptions>

            <AiCapabilityActionCard
              title="AI 摘要"
              error={summaryError}
              hasContent={Boolean(summaryPreview?.result ?? (previewReport.metadata_json.ai_summary as AiReportSummaryResult | undefined))}
              empty={<Typography.Text type="secondary">生成 AI 摘要后，可以给这份报告补充管理视角和风险总结。</Typography.Text>}
            >
              {(() => {
                const reportSummary = previewReport.metadata_json.ai_summary as AiReportSummaryResult | undefined;
                const summary = summaryPreview?.result ?? reportSummary;
                if (!summary) {
                  return null;
                }
                return (
                  <AiSuggestionPanel
                    items={[
                      {
                        key: 'executive-summary',
                        title: '执行摘要',
                        tags: (
                          <Space wrap>
                            <Tag color="processing">
                              {artifactStatusMeta(summaryPreview ? summaryPreview.status : 'applied').label}
                            </Tag>
                            <Tag>{`重点失败项：${summary.top_failures.length}`}</Tag>
                          </Space>
                        ),
                        content: (
                          <Space direction="vertical" style={{ width: '100%' }}>
                            <Typography.Text>{summary.executive_summary}</Typography.Text>
                            <Typography.Text strong>风险摘要</Typography.Text>
                            <Typography.Text>{summary.risk_summary}</Typography.Text>
                          </Space>
                        ),
                      },
                      ...(summary.top_failures.length
                        ? [{
                            key: 'top-failures',
                            title: '重点失败项',
                            content: (
                              <ul style={{ marginTop: 0, marginBottom: 0, paddingLeft: 20 }}>
                                {summary.top_failures.map((item) => (
                                  <li key={`${item.category}-${item.count}`}>
                                    <Typography.Text>{`${item.category}: ${item.count}`}</Typography.Text>
                                  </li>
                                ))}
                              </ul>
                            ),
                          }]
                        : []),
                      ...(summary.recommended_actions.length
                        ? [{
                            key: 'recommended-actions',
                            title: '建议动作',
                            content: (
                              <ul style={{ marginTop: 0, marginBottom: 0, paddingLeft: 20 }}>
                                {summary.recommended_actions.map((item) => (
                                  <li key={item}>
                                    <Typography.Text>{item}</Typography.Text>
                                  </li>
                                ))}
                              </ul>
                            ),
                          }]
                        : []),
                    ]}
                    emptyText="当前还没有 AI 摘要。"
                  />
                );
              })()}
            </AiCapabilityActionCard>

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
