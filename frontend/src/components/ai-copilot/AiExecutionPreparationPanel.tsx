import { Button, Select, Space, Tag, Typography } from 'antd';

import type { AiMockTemplate, AiTestDataVariant, Environment, Execution } from '../../api/types';
import { AiCapabilityActionCard } from './AiCapabilityActionCard';

type Props = {
  canEdit: boolean;
  availableVariants: AiTestDataVariant[];
  availableTemplates: AiMockTemplate[];
  selectedVariantIds: string[];
  selectedTemplateIds: string[];
  selectedEnvironmentId: number | null;
  environments: Environment[];
  loading?: boolean;
  error?: string | null;
  lastExecution: Execution | null;
  onChangeVariantIds: (value: string[]) => void;
  onChangeTemplateIds: (value: string[]) => void;
  onChangeEnvironmentId: (value: number | null) => void;
  onRun: () => void;
};

export function AiExecutionPreparationPanel({
  canEdit,
  availableVariants,
  availableTemplates,
  selectedVariantIds,
  selectedTemplateIds,
  selectedEnvironmentId,
  environments,
  loading = false,
  error,
  lastExecution,
  onChangeVariantIds,
  onChangeTemplateIds,
  onChangeEnvironmentId,
  onRun,
}: Props) {
  const summary = (lastExecution?.summary_json?.ai_preparation ?? {}) as Record<string, unknown>;
  const selectedVariantCount = Number(summary.selected_variant_count ?? 0);
  const selectedTemplateCount = Number(summary.selected_template_count ?? 0);

  return (
    <AiCapabilityActionCard
      title="AI 预执行准备"
      actions={(
        <Button type="primary" size="small" onClick={onRun} loading={loading} disabled={!canEdit}>
          携带准备执行
        </Button>
      )}
      error={error}
      hasContent={Boolean(availableVariants.length || availableTemplates.length || lastExecution)}
      empty={<Typography.Text type="secondary">先应用 AI 测试数据或 AI Mock，再在这里选择本次执行准备。</Typography.Text>}
    >
      <Space direction="vertical" style={{ width: '100%' }}>
        <Typography.Text type="secondary">
          这里不会改写用例本体，只会把选中的 variant/template 作为本次 case execution 的显式准备参数带入。
        </Typography.Text>
        <Select
          mode="multiple"
          allowClear
          placeholder="选择本次执行要带入的 AI 测试数据变体"
          value={selectedVariantIds}
          onChange={onChangeVariantIds}
          options={availableVariants.map((item) => ({
            value: item.variant_id,
            label: `${item.name} | ${item.target_fields.join(', ') || item.variant_id}`,
          }))}
        />
        <Select
          mode="multiple"
          allowClear
          placeholder="选择本次执行要挂载的 AI Mock 模板"
          value={selectedTemplateIds}
          onChange={onChangeTemplateIds}
          options={availableTemplates.map((item) => ({
            value: item.template_id,
            label: `${item.scenario_name} | ${item.status_code}`,
          }))}
        />
        <Select
          allowClear
          placeholder="可选：选择执行环境"
          value={selectedEnvironmentId ?? undefined}
          onChange={(value) => onChangeEnvironmentId((value as number | undefined) ?? null)}
          options={environments.map((item) => ({ value: item.id, label: `${item.name} | ${item.base_url}` }))}
        />
        <Space wrap>
          <Tag color="blue">variant {availableVariants.length}</Tag>
          <Tag color="cyan">template {availableTemplates.length}</Tag>
          <Tag>已选 variant {selectedVariantIds.length}</Tag>
          <Tag>已选 template {selectedTemplateIds.length}</Tag>
        </Space>
        {lastExecution ? (
          <Space direction="vertical" style={{ width: '100%' }}>
            <Typography.Text strong>{`最近执行 #${lastExecution.id} | ${lastExecution.status}`}</Typography.Text>
            <Typography.Text type="secondary">
              {`本次准备带入 ${selectedVariantCount} 个 test-data variant，${selectedTemplateCount} 个 mock template。`}
            </Typography.Text>
          </Space>
        ) : null}
      </Space>
    </AiCapabilityActionCard>
  );
}
