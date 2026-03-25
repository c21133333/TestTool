import { Button, Space, Tag, Typography } from 'antd';

import type { AiCopilotPreview, AiCoverageResult } from '../../api/types';
import { AiCapabilityActionCard } from './AiCapabilityActionCard';
import { AiSuggestionPanel } from './AiSuggestionPanel';

type Props = {
  title?: string;
  targetLabel: string;
  preview: AiCopilotPreview<AiCoverageResult> | null;
  loading?: boolean;
  error?: string | null;
  onScan: () => void;
  onOpenHistory?: () => void;
  onUseSuggestedPoints?: () => void;
};

export function AiCoveragePanel({
  title = 'AI 覆盖率扫描',
  targetLabel,
  preview,
  loading = false,
  error,
  onScan,
  onOpenHistory,
  onUseSuggestedPoints,
}: Props) {
  const result = preview?.result ?? null;

  return (
    <AiCapabilityActionCard
      title={title}
      actions={
        <Space wrap>
          {onOpenHistory ? (
            <Button size="small" onClick={onOpenHistory}>
              历史
            </Button>
          ) : null}
          {onUseSuggestedPoints ? (
            <Button size="small" onClick={onUseSuggestedPoints} disabled={!result?.suggested_points.length}>
              带入测试点提示
            </Button>
          ) : null}
          <Button type="primary" size="small" loading={loading} onClick={onScan}>
            扫描
          </Button>
        </Space>
      }
      error={error}
      warnings={preview?.warnings ?? []}
      hasContent={Boolean(result)}
      empty={<Typography.Text type="secondary">选择项目或套件后扫描，这里会显示 coverage 缺口和建议测试点。</Typography.Text>}
    >
      {result ? (
        <Space direction="vertical" style={{ width: '100%' }}>
          <Space wrap>
            <Tag color="processing">{targetLabel}</Tag>
            <Tag color={result.coverage_score >= 80 ? 'green' : result.coverage_score >= 60 ? 'gold' : 'red'}>
              覆盖率 {result.coverage_score}
            </Tag>
            <Tag color="orange">缺口 {result.missing_dimensions.length}</Tag>
            <Tag color="blue">建议点 {result.suggested_points.length}</Tag>
            <Tag>{preview?.status}</Tag>
          </Space>
          <AiSuggestionPanel
            items={result.missing_dimensions.map((dimension, index) => ({
              key: `${dimension.endpoint}-${dimension.dimension}-${index}`,
              title: `${dimension.endpoint} · ${dimension.dimension}`,
              tags: <Tag color="orange">gap</Tag>,
              content: <Typography.Text>{dimension.reason}</Typography.Text>,
            }))}
            emptyText="当前 target 没有检测到覆盖率缺口。"
          />
          <AiSuggestionPanel
            items={result.suggested_points.map((point, index) => ({
              key: `${point.title}-${index}`,
              title: point.title,
              tags: (
                <Space wrap size={4}>
                  <Tag color="blue">{point.category}</Tag>
                  <Tag color={point.priority === 'high' ? 'red' : point.priority === 'medium' ? 'gold' : 'default'}>
                    {point.priority}
                  </Tag>
                </Space>
              ),
              content: <Typography.Text>{point.reason}</Typography.Text>,
            }))}
            emptyText="当前没有额外的建议测试点。"
          />
        </Space>
      ) : null}
    </AiCapabilityActionCard>
  );
}
