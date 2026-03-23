import { App, Button, Card, Drawer, Space, Table, Typography } from 'antd';
import { useEffect, useMemo, useState } from 'react';

import { createApi } from '../api/services';
import type { Report } from '../api/types';
import { useAuth } from '../auth/AuthContext';

export function ReportsPage() {
  const { token } = useAuth();
  const api = useMemo(() => createApi(token), [token]);
  const { message } = App.useApp();
  const [reports, setReports] = useState<Report[]>([]);
  const [previewTitle, setPreviewTitle] = useState<string>('');
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewMode, setPreviewMode] = useState<'html' | 'json'>('json');
  const [previewContent, setPreviewContent] = useState('');
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);

  async function refresh() {
    setReports(await api.listReports());
  }

  useEffect(() => {
    void refresh();
    return () => {
      if (previewUrl) {
        URL.revokeObjectURL(previewUrl);
      }
    };
  }, [api]);

  async function openPreview(report: Report) {
    if (previewUrl) {
      URL.revokeObjectURL(previewUrl);
      setPreviewUrl(null);
    }
    setPreviewTitle(`${report.report_type.toUpperCase()} #${report.id}`);
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
    setPreviewOpen(true);
  }

  async function openInNewTab(report: Report) {
    const blob = await api.fetchReportBlob(report.id);
    const url = URL.createObjectURL(blob);
    window.open(url, '_blank', 'noopener,noreferrer');
    message.success('报告已在新标签页打开。');
  }

  return (
    <div className="page-stack">
      <div className="page-hero">
        <Typography.Title>报告中心</Typography.Title>
        <Typography.Paragraph>支持在线预览 HTML / JSON 报告，不再只是暴露服务端文件路径。</Typography.Paragraph>
      </div>
      <Card className="glass-card" extra={<Button onClick={() => void refresh()}>刷新</Button>}>
        <Table
          rowKey="id"
          pagination={false}
          dataSource={reports}
          columns={[
            { title: 'ID', dataIndex: 'id', width: 80 },
            { title: '执行 ID', dataIndex: 'execution_id', width: 110 },
            { title: '类型', dataIndex: 'report_type', width: 120 },
            { title: '文件路径', dataIndex: 'file_path' },
            {
              title: '操作',
              render: (_, row) => (
                <Space>
                  <Button size="small" onClick={() => void openPreview(row)}>预览</Button>
                  <Button size="small" onClick={() => void openInNewTab(row)}>新标签打开</Button>
                </Space>
              ),
            },
          ]}
        />
      </Card>
      <Drawer
        title={previewTitle}
        placement="right"
        width={previewMode === 'html' ? '75vw' : 760}
        open={previewOpen}
        onClose={() => setPreviewOpen(false)}
      >
        {previewMode === 'html' && previewUrl ? (
          <iframe title={previewTitle} src={previewUrl} style={{ width: '100%', minHeight: '80vh', border: 0 }} />
        ) : (
          <pre style={{ whiteSpace: 'pre-wrap', wordBreak: 'break-word' }}>{previewContent}</pre>
        )}
      </Drawer>
    </div>
  );
}
