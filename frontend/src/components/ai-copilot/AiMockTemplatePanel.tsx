import { Button, Popconfirm, Space, Table, Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';

import type { AiArtifactHistoryItem, AiCopilotPreview, AiMockResult, AiMockTemplate } from '../../api/types';
import { AiArtifactHistoryDrawer } from './AiArtifactHistoryDrawer';
import { AiCapabilityActionCard } from './AiCapabilityActionCard';

type Props = {
  preview: AiCopilotPreview<AiMockResult> | null;
  selectedTemplateIds: string[];
  canEdit: boolean;
  loading?: boolean;
  applyLoading?: boolean;
  exportLoading?: boolean;
  error?: string | null;
  historyOpen: boolean;
  historyLoading?: boolean;
  historyError?: string | null;
  historyItems: AiArtifactHistoryItem[];
  onPreview: () => void;
  onApplyAppend: () => void;
  onApplyOverride: () => void;
  onExport: () => void;
  onSelectionChange: (selectedTemplateIds: string[]) => void;
  onOpenHistory: () => void;
  onCloseHistory: () => void;
  onLoadHistory: (item: AiArtifactHistoryItem, result: AiMockResult) => void;
  onViewLineage?: (item: AiArtifactHistoryItem) => void;
};

function normalizeHistoryResult(outputJson: Record<string, unknown>): AiMockResult {
  const rawItems = Array.isArray(outputJson.mock_templates) ? outputJson.mock_templates : [];
  return {
    mock_templates: rawItems.reduce<AiMockTemplate[]>((result, item, index) => {
      if (!item || typeof item !== 'object') {
        return result;
      }
      const entry = item as Record<string, unknown>;
      result.push({
        template_id: String(entry.template_id ?? `history-template-${index}`),
        scenario_name: String(entry.scenario_name ?? 'unnamed_template'),
        status_code: Number(entry.status_code ?? 200),
        response_template:
          typeof entry.response_template === 'object' && entry.response_template !== null
            ? (entry.response_template as Record<string, unknown>)
            : {},
        mock_rules: Array.isArray(entry.mock_rules)
          ? entry.mock_rules.filter((rule): rule is Record<string, unknown> => Boolean(rule && typeof rule === 'object'))
          : [],
        reason: String(entry.reason ?? ''),
      });
      return result;
    }, []),
  };
}

function stringifyRule(template: AiMockTemplate): string {
  const rule = template.mock_rules[0] ?? {};
  return `${String(rule.method ?? 'GET')} ${String(rule.path ?? '/')}`;
}

export function AiMockTemplatePanel({
  preview,
  selectedTemplateIds,
  canEdit,
  loading = false,
  applyLoading = false,
  exportLoading = false,
  error,
  historyOpen,
  historyLoading = false,
  historyError,
  historyItems,
  onPreview,
  onApplyAppend,
  onApplyOverride,
  onExport,
  onSelectionChange,
  onOpenHistory,
  onCloseHistory,
  onLoadHistory,
  onViewLineage,
}: Props) {
  const templates = preview?.result.mock_templates ?? [];
  const columns: ColumnsType<AiMockTemplate> = [
    {
      title: '模板',
      dataIndex: 'scenario_name',
      render: (_, item) => (
        <Space direction="vertical" size={0}>
          <Typography.Text strong>{item.scenario_name}</Typography.Text>
          <Typography.Text type="secondary">{item.template_id}</Typography.Text>
        </Space>
      ),
    },
    {
      title: '规则',
      width: 220,
      render: (_, item) => stringifyRule(item),
    },
    {
      title: '状态码',
      dataIndex: 'status_code',
      width: 100,
      render: (value: number) => <Tag color={value >= 500 ? 'red' : value >= 400 ? 'gold' : 'green'}>{value}</Tag>,
    },
    {
      title: '响应字段',
      width: 160,
      render: (_, item) => Object.keys(item.response_template ?? {}).join(', ') || '-',
    },
    {
      title: '原因',
      dataIndex: 'reason',
      render: (value: string) => <Typography.Text type="secondary">{value}</Typography.Text>,
    },
  ];

  return (
    <>
      <AiCapabilityActionCard
        title="AI Mock"
        actions={(
          <Space wrap>
            <Button size="small" onClick={onOpenHistory}>
              历史
            </Button>
            <Button size="small" loading={exportLoading} disabled={!preview} onClick={onExport}>
              导出 JSON
            </Button>
            <Button size="small" loading={loading} onClick={onPreview} disabled={!canEdit}>
              生成
            </Button>
            <Button
              type="primary"
              size="small"
              loading={applyLoading}
              disabled={!canEdit || !preview || !selectedTemplateIds.length}
              onClick={onApplyAppend}
            >
              应用追加
            </Button>
            <Popconfirm
              title="覆盖后会替换当前已保存的 AI Mock 模板，确认继续？"
              onConfirm={onApplyOverride}
              disabled={!canEdit || !preview || !selectedTemplateIds.length}
            >
              <Button danger size="small" loading={applyLoading} disabled={!canEdit || !preview || !selectedTemplateIds.length}>
                覆盖应用
              </Button>
            </Popconfirm>
          </Space>
        )}
        error={error}
        warnings={preview?.warnings ?? []}
        hasContent={Boolean(preview)}
        empty={<Typography.Text type="secondary">先保存用例，再生成可导出的 Mock 模板。</Typography.Text>}
      >
        {preview ? (
          <Space direction="vertical" style={{ width: '100%' }}>
            <Typography.Text type="secondary">Phase 4 仍不启用 runtime mock，只管理模板与执行前准备。</Typography.Text>
            <Space wrap>
              <Tag color="processing">artifact {preview.artifact_id.slice(0, 8)}</Tag>
              <Tag color="blue">模板 {templates.length}</Tag>
              <Tag color="cyan">已选 {selectedTemplateIds.length}</Tag>
              <Tag>{preview.status}</Tag>
            </Space>
            <Table<AiMockTemplate>
              rowKey="template_id"
              size="small"
              pagination={false}
              dataSource={templates}
              columns={columns}
              rowSelection={{
                selectedRowKeys: selectedTemplateIds,
                onChange: (keys) => onSelectionChange(keys.map((item) => String(item))),
              }}
            />
          </Space>
        ) : null}
      </AiCapabilityActionCard>
      <AiArtifactHistoryDrawer
        title="AI Mock 历史"
        open={historyOpen}
        onClose={onCloseHistory}
        loading={historyLoading}
        error={historyError}
        items={historyItems.map((item) => {
          const result = normalizeHistoryResult(item.output_json);
          return {
            key: item.artifact_id,
            label: `${item.artifact_id.slice(0, 8)} | ${result.mock_templates.length} templates | ${item.status}`,
            content: (
              <Space direction="vertical" style={{ width: '100%' }}>
                <Typography.Text type="secondary">case #{item.target_id}</Typography.Text>
                <Typography.Text>{result.mock_templates.map((template) => template.scenario_name).slice(0, 3).join(' / ') || '无模板'}</Typography.Text>
                <Space>
                  <Button size="small" onClick={() => onLoadHistory(item, result)}>
                    加载为当前预览
                  </Button>
                  {onViewLineage ? (
                    <Button size="small" onClick={() => onViewLineage(item)}>
                      Lineage
                    </Button>
                  ) : null}
                </Space>
              </Space>
            ),
          };
        })}
        emptyText="当前 case 还没有 AI Mock 历史。"
      />
    </>
  );
}
