import { Button, Divider, Space, Tag, Typography } from 'antd';

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
  useSuggestedPointsLabel?: string;
  useSuggestedPointsLoading?: boolean;
};

const DIMENSION_LABELS: Record<string, string> = {
  happy_path: '主流程',
  negative_path: '异常流程',
  boundary_path: '边界场景',
  auth: '鉴权场景',
  idempotent: '幂等场景',
  pagination: '分页场景',
  assertion_hardening: '断言加固',
  status: '状态码断言',
  business_code: '业务码断言',
  body_field: '响应字段断言',
  schema: '响应结构断言',
  latency: '时延断言',
  unknown: '未知维度',
};

const PRIORITY_LABELS: Record<string, string> = {
  high: '高优先级',
  medium: '中优先级',
  low: '低优先级',
};

const STATUS_LABELS: Record<string, string> = {
  draft: '草稿',
  accepted: '已接受',
  rejected: '已拒绝',
  applied: '已应用',
  superseded: '已替代',
};

function coverageLabel(value: string): string {
  return DIMENSION_LABELS[value] ?? value;
}

function priorityLabel(value: string): string {
  return PRIORITY_LABELS[value] ?? value;
}

function statusLabel(value: string | undefined): string {
  if (!value) {
    return '';
  }
  return STATUS_LABELS[value] ?? value;
}

function SectionHeader({
  title,
  count,
  description,
  tone,
}: {
  title: string;
  count: number;
  description: string;
  tone: 'orange' | 'blue';
}) {
  return (
    <Space direction="vertical" size={4} style={{ width: '100%' }}>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 8,
          flexWrap: 'wrap',
        }}
      >
        <Space wrap size={8}>
          <Typography.Title level={5} style={{ margin: 0 }}>
            {title}
          </Typography.Title>
          <Tag color={tone}>{count} 条</Tag>
        </Space>
        <Typography.Text type="secondary">本区独立分页</Typography.Text>
      </div>
      <Typography.Text type="secondary">{description}</Typography.Text>
    </Space>
  );
}

export function AiCoveragePanel({
  title = 'AI 覆盖率扫描',
  targetLabel,
  preview,
  loading = false,
  error,
  onScan,
  onOpenHistory,
  onUseSuggestedPoints,
  useSuggestedPointsLabel = '带入测试点提示',
  useSuggestedPointsLoading = false,
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
            <Button
              size="small"
              onClick={onUseSuggestedPoints}
              loading={useSuggestedPointsLoading}
              disabled={!result?.suggested_points.length}
            >
              {useSuggestedPointsLabel}
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
      empty={<Typography.Text type="secondary">选择项目或套件后扫描，这里会显示覆盖率缺口和补测建议。</Typography.Text>}
    >
      {result ? (
        <Space direction="vertical" size={16} style={{ width: '100%' }}>
          <Space wrap>
            <Tag color="processing">{targetLabel}</Tag>
            <Tag color={result.coverage_score >= 80 ? 'green' : result.coverage_score >= 60 ? 'gold' : 'red'}>
              覆盖率 {result.coverage_score}
            </Tag>
            <Tag color="orange">缺口 {result.missing_dimensions.length}</Tag>
            <Tag color="blue">建议点 {result.suggested_points.length}</Tag>
            <Tag>{statusLabel(preview?.status)}</Tag>
          </Space>

          <Space direction="vertical" size={10} style={{ width: '100%' }}>
            <SectionHeader
              title="覆盖缺口"
              count={result.missing_dimensions.length}
              tone="orange"
              description="这一段只展示还没被现有用例和断言覆盖到的维度，分页只作用于缺口列表本身。"
            />
            <AiSuggestionPanel
              items={result.missing_dimensions.map((dimension, index) => ({
                key: `${dimension.endpoint}-${dimension.dimension}-${index}`,
                title: `${dimension.endpoint} · ${coverageLabel(dimension.dimension)}`,
                tags: <Tag color="orange">缺口</Tag>,
                content: <Typography.Text>{dimension.reason}</Typography.Text>,
              }))}
              emptyText="当前 target 没有检测到覆盖缺口。"
            />
          </Space>

          <Divider style={{ margin: 0 }} />

          <Space direction="vertical" size={10} style={{ width: '100%' }}>
            <SectionHeader
              title="补测建议"
              count={result.suggested_points.length}
              tone="blue"
              description="这一段是 AI 基于缺口整理出的补测建议，和上面的缺口列表是两组独立数据，各自单独分页。"
            />
            <AiSuggestionPanel
              items={result.suggested_points.map((point, index) => ({
                key: `${point.title}-${index}`,
                title: point.title,
                tags: (
                  <Space wrap size={4}>
                    <Tag color="blue">{coverageLabel(point.category)}</Tag>
                    <Tag color={point.priority === 'high' ? 'red' : point.priority === 'medium' ? 'gold' : 'default'}>
                      {priorityLabel(point.priority)}
                    </Tag>
                  </Space>
                ),
                content: <Typography.Text>{point.reason}</Typography.Text>,
              }))}
              emptyText="当前没有额外的补测建议。"
            />
          </Space>
        </Space>
      ) : null}
    </AiCapabilityActionCard>
  );
}
