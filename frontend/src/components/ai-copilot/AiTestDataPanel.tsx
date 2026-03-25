import { Button, Popconfirm, Space, Table, Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';

import type { AiArtifactHistoryItem, AiCopilotPreview, AiTestDataResult, AiTestDataVariant } from '../../api/types';
import { AiArtifactHistoryDrawer } from './AiArtifactHistoryDrawer';
import { AiCapabilityActionCard } from './AiCapabilityActionCard';

type Props = {
  preview: AiCopilotPreview<AiTestDataResult> | null;
  selectedVariantIds: string[];
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
  onSelectionChange: (selectedVariantIds: string[]) => void;
  onOpenHistory: () => void;
  onCloseHistory: () => void;
  onLoadHistory: (item: AiArtifactHistoryItem, result: AiTestDataResult) => void;
  onViewLineage?: (item: AiArtifactHistoryItem) => void;
};

function normalizeHistoryResult(outputJson: Record<string, unknown>): AiTestDataResult {
  const rawItems = Array.isArray(outputJson.data_variants) ? outputJson.data_variants : [];
  return {
    data_variants: rawItems.reduce<AiTestDataVariant[]>((result, item, index) => {
      if (!item || typeof item !== 'object') {
        return result;
      }
      const entry = item as Record<string, unknown>;
      result.push({
        variant_id: String(entry.variant_id ?? `history-variant-${index}`),
        name: String(entry.name ?? 'unnamed_variant'),
        category: String(entry.category ?? 'unknown'),
        payload_patch: typeof entry.payload_patch === 'object' && entry.payload_patch !== null ? (entry.payload_patch as Record<string, unknown>) : {},
        target_fields: Array.isArray(entry.target_fields) ? entry.target_fields.map((field) => String(field)) : [],
        reason: String(entry.reason ?? ''),
        suggested_assertions: Array.isArray(entry.suggested_assertions)
          ? entry.suggested_assertions.filter((assertion): assertion is Record<string, unknown> => Boolean(assertion && typeof assertion === 'object'))
          : [],
        confidence: Number(entry.confidence ?? 0),
      });
      return result;
    }, []),
  };
}

export function AiTestDataPanel({
  preview,
  selectedVariantIds,
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
  const variants = preview?.result.data_variants ?? [];
  const columns: ColumnsType<AiTestDataVariant> = [
    {
      title: '变体',
      dataIndex: 'name',
      render: (_, item) => (
        <Space direction="vertical" size={0}>
          <Typography.Text strong>{item.name}</Typography.Text>
          <Typography.Text type="secondary">{item.variant_id}</Typography.Text>
        </Space>
      ),
    },
    {
      title: '分类',
      dataIndex: 'category',
      width: 120,
      render: (value: string) => <Tag color="blue">{value}</Tag>,
    },
    {
      title: '目标字段',
      dataIndex: 'target_fields',
      width: 200,
      render: (value: string[]) => value.join(', ') || '-',
    },
    {
      title: '建议断言',
      width: 100,
      render: (_, item) => item.suggested_assertions.length,
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
        title="AI 测试数据"
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
              disabled={!canEdit || !preview || !selectedVariantIds.length}
              onClick={onApplyAppend}
            >
              应用追加
            </Button>
            <Popconfirm
              title="覆盖后会替换当前已保存的 AI 测试数据变体，确认继续？"
              onConfirm={onApplyOverride}
              disabled={!canEdit || !preview || !selectedVariantIds.length}
            >
              <Button danger size="small" loading={applyLoading} disabled={!canEdit || !preview || !selectedVariantIds.length}>
                覆盖应用
              </Button>
            </Popconfirm>
          </Space>
        )}
        error={error}
        warnings={preview?.warnings ?? []}
        hasContent={Boolean(preview)}
        empty={<Typography.Text type="secondary">先保存用例，再生成可审阅的测试数据变体。</Typography.Text>}
      >
        {preview ? (
          <Space direction="vertical" style={{ width: '100%' }}>
            <Typography.Text type="secondary">
              apply 只会把你选中的变体写入 case metadata，不会直接改写当前请求体。
            </Typography.Text>
            <Space wrap>
              <Tag color="processing">artifact {preview.artifact_id.slice(0, 8)}</Tag>
              <Tag color="blue">变体 {variants.length}</Tag>
              <Tag color="cyan">已选 {selectedVariantIds.length}</Tag>
              <Tag>{preview.status}</Tag>
            </Space>
            <Table<AiTestDataVariant>
              rowKey="variant_id"
              size="small"
              pagination={{ pageSize: 10, showSizeChanger: false, hideOnSinglePage: true }}
              dataSource={variants}
              columns={columns}
              rowSelection={{
                selectedRowKeys: selectedVariantIds,
                onChange: (keys) => onSelectionChange(keys.map((item) => String(item))),
              }}
            />
          </Space>
        ) : null}
      </AiCapabilityActionCard>
      <AiArtifactHistoryDrawer
        title="AI 测试数据历史"
        open={historyOpen}
        onClose={onCloseHistory}
        loading={historyLoading}
        error={historyError}
        items={historyItems.map((item) => {
          const result = normalizeHistoryResult(item.output_json);
          return {
            key: item.artifact_id,
            label: `${item.artifact_id.slice(0, 8)} | ${result.data_variants.length} variants | ${item.status}`,
            content: (
              <Space direction="vertical" style={{ width: '100%' }}>
                <Typography.Text type="secondary">case #{item.target_id}</Typography.Text>
                <Typography.Text>{result.data_variants.map((variant) => variant.name).slice(0, 3).join(' / ') || '无变体'}</Typography.Text>
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
        emptyText="当前 case 还没有 AI 测试数据历史。"
      />
    </>
  );
}
