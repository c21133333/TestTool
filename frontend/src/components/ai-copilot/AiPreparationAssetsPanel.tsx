import { useEffect, useMemo, useState } from 'react';

import { Button, Card, Col, Descriptions, Empty, Input, Popconfirm, Row, Segmented, Select, Space, Statistic, Table, Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';

import type { AiArtifactHistoryItem, AiCopilotPreview, AiMockResult, AiMockTemplate, AiTestDataResult, AiTestDataVariant } from '../../api/types';
import { AiArtifactHistoryDrawer } from './AiArtifactHistoryDrawer';
import { AiCapabilityActionCard } from './AiCapabilityActionCard';

type Props = {
  canEdit: boolean;
  testDataPreview: AiCopilotPreview<AiTestDataResult> | null;
  selectedVariantIds: string[];
  testDataLoading?: boolean;
  testDataApplyLoading?: boolean;
  testDataExportLoading?: boolean;
  testDataError?: string | null;
  testDataHistoryOpen: boolean;
  testDataHistoryLoading?: boolean;
  testDataHistoryError?: string | null;
  testDataHistoryItems: AiArtifactHistoryItem[];
  onPreviewTestData: () => void;
  onApplyTestDataAppend: () => void;
  onApplyTestDataOverride: () => void;
  onExportTestData: () => void;
  onSelectionChangeVariantIds: (selectedVariantIds: string[]) => void;
  onOpenTestDataHistory: () => void;
  onCloseTestDataHistory: () => void;
  onLoadTestDataHistory: (item: AiArtifactHistoryItem, result: AiTestDataResult) => void;
  mockPreview: AiCopilotPreview<AiMockResult> | null;
  selectedTemplateIds: string[];
  mockLoading?: boolean;
  mockApplyLoading?: boolean;
  mockExportLoading?: boolean;
  mockError?: string | null;
  mockHistoryOpen: boolean;
  mockHistoryLoading?: boolean;
  mockHistoryError?: string | null;
  mockHistoryItems: AiArtifactHistoryItem[];
  onPreviewMock: () => void;
  onApplyMockAppend: () => void;
  onApplyMockOverride: () => void;
  onExportMock: () => void;
  onSelectionChangeTemplateIds: (selectedTemplateIds: string[]) => void;
  onOpenMockHistory: () => void;
  onCloseMockHistory: () => void;
  onLoadMockHistory: (item: AiArtifactHistoryItem, result: AiMockResult) => void;
  onViewLineage?: (item: AiArtifactHistoryItem) => void;
};

type AssetMode = 'test_data' | 'mock';

const TABLE_PAGINATION = {
  pageSize: 10,
  showSizeChanger: false,
  hideOnSinglePage: true,
};

function stringifyPayload(value: unknown): string {
  try {
    return JSON.stringify(value ?? {}, null, 2);
  } catch {
    return String(value ?? '');
  }
}

function normalizeTestDataHistoryResult(outputJson: Record<string, unknown>): AiTestDataResult {
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
        payload_patch:
          typeof entry.payload_patch === 'object' && entry.payload_patch !== null ? (entry.payload_patch as Record<string, unknown>) : {},
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

function normalizeMockHistoryResult(outputJson: Record<string, unknown>): AiMockResult {
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
        confidence: Number(entry.confidence ?? 0),
      });
      return result;
    }, []),
  };
}

function mockStatusBucket(statusCode: number): '2xx' | '4xx' | '5xx' | 'other' {
  if (statusCode >= 500) {
    return '5xx';
  }
  if (statusCode >= 400) {
    return '4xx';
  }
  if (statusCode >= 200 && statusCode < 300) {
    return '2xx';
  }
  return 'other';
}

function mockStatusColor(statusCode: number): string {
  if (statusCode >= 500) {
    return 'red';
  }
  if (statusCode >= 400) {
    return 'gold';
  }
  if (statusCode >= 200 && statusCode < 300) {
    return 'green';
  }
  return 'default';
}

function stringifyRule(template: AiMockTemplate): string {
  const rule = template.mock_rules[0] ?? {};
  return `${String(rule.method ?? 'GET')} ${String(rule.path ?? '/')}`;
}

export function AiPreparationAssetsPanel({
  canEdit,
  testDataPreview,
  selectedVariantIds,
  testDataLoading = false,
  testDataApplyLoading = false,
  testDataExportLoading = false,
  testDataError,
  testDataHistoryOpen,
  testDataHistoryLoading = false,
  testDataHistoryError,
  testDataHistoryItems,
  onPreviewTestData,
  onApplyTestDataAppend,
  onApplyTestDataOverride,
  onExportTestData,
  onSelectionChangeVariantIds,
  onOpenTestDataHistory,
  onCloseTestDataHistory,
  onLoadTestDataHistory,
  mockPreview,
  selectedTemplateIds,
  mockLoading = false,
  mockApplyLoading = false,
  mockExportLoading = false,
  mockError,
  mockHistoryOpen,
  mockHistoryLoading = false,
  mockHistoryError,
  mockHistoryItems,
  onPreviewMock,
  onApplyMockAppend,
  onApplyMockOverride,
  onExportMock,
  onSelectionChangeTemplateIds,
  onOpenMockHistory,
  onCloseMockHistory,
  onLoadMockHistory,
  onViewLineage,
}: Props) {
  const [mode, setMode] = useState<AssetMode>('test_data');
  const [testDataKeyword, setTestDataKeyword] = useState('');
  const [testDataCategory, setTestDataCategory] = useState<string | undefined>(undefined);
  const [mockKeyword, setMockKeyword] = useState('');
  const [mockBucket, setMockBucket] = useState<string | undefined>(undefined);
  const [activeVariantId, setActiveVariantId] = useState<string | null>(null);
  const [activeTemplateId, setActiveTemplateId] = useState<string | null>(null);

  const variants = testDataPreview?.result.data_variants ?? [];
  const templates = mockPreview?.result.mock_templates ?? [];

  const testDataCategories = useMemo(
    () =>
      Array.from(new Set(variants.map((item) => item.category).filter(Boolean))).map((value) => ({
        label: value,
        value,
      })),
    [variants],
  );

  const filteredVariants = useMemo(() => {
    const keyword = testDataKeyword.trim().toLowerCase();
    return variants.filter((item) => {
      const matchesCategory = !testDataCategory || item.category === testDataCategory;
      const matchesKeyword =
        !keyword ||
        item.name.toLowerCase().includes(keyword) ||
        item.reason.toLowerCase().includes(keyword) ||
        item.target_fields.some((field) => field.toLowerCase().includes(keyword));
      return matchesCategory && matchesKeyword;
    });
  }, [testDataCategory, testDataKeyword, variants]);

  const filteredTemplates = useMemo(() => {
    const keyword = mockKeyword.trim().toLowerCase();
    return templates.filter((item) => {
      const bucket = mockStatusBucket(item.status_code);
      const matchesBucket = !mockBucket || bucket === mockBucket;
      const matchesKeyword =
        !keyword ||
        item.scenario_name.toLowerCase().includes(keyword) ||
        item.reason.toLowerCase().includes(keyword) ||
        stringifyRule(item).toLowerCase().includes(keyword);
      return matchesBucket && matchesKeyword;
    });
  }, [mockBucket, mockKeyword, templates]);

  useEffect(() => {
    if (!filteredVariants.length) {
      setActiveVariantId(null);
      return;
    }
    if (!activeVariantId || !filteredVariants.some((item) => item.variant_id === activeVariantId)) {
      setActiveVariantId(filteredVariants[0].variant_id);
    }
  }, [activeVariantId, filteredVariants]);

  useEffect(() => {
    if (!filteredTemplates.length) {
      setActiveTemplateId(null);
      return;
    }
    if (!activeTemplateId || !filteredTemplates.some((item) => item.template_id === activeTemplateId)) {
      setActiveTemplateId(filteredTemplates[0].template_id);
    }
  }, [activeTemplateId, filteredTemplates]);

  const activeVariant = filteredVariants.find((item) => item.variant_id === activeVariantId) ?? null;
  const activeTemplate = filteredTemplates.find((item) => item.template_id === activeTemplateId) ?? null;

  const testDataColumns: ColumnsType<AiTestDataVariant> = [
    {
      title: '变体',
      dataIndex: 'name',
      width: 240,
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
      width: 140,
      render: (value: string) => <Tag color="blue">{value}</Tag>,
    },
    {
      title: '目标字段',
      dataIndex: 'target_fields',
      width: 240,
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
      render: (value: string) => (
        <Typography.Paragraph style={{ marginBottom: 0 }} ellipsis={{ rows: 2, expandable: true, symbol: '展开' }}>
          {value}
        </Typography.Paragraph>
      ),
    },
  ];

  const mockColumns: ColumnsType<AiMockTemplate> = [
    {
      title: '模板',
      dataIndex: 'scenario_name',
      width: 240,
      render: (_, item) => (
        <Space direction="vertical" size={0}>
          <Typography.Text strong>{item.scenario_name}</Typography.Text>
          <Typography.Text type="secondary">{item.template_id}</Typography.Text>
        </Space>
      ),
    },
    {
      title: '匹配规则',
      width: 220,
      render: (_, item) => stringifyRule(item),
    },
    {
      title: '状态码',
      dataIndex: 'status_code',
      width: 100,
      render: (value: number) => <Tag color={mockStatusColor(value)}>{value}</Tag>,
    },
    {
      title: '响应字段',
      width: 180,
      render: (_, item) => Object.keys(item.response_template ?? {}).join(', ') || '-',
    },
    {
      title: '原因',
      dataIndex: 'reason',
      render: (value: string) => (
        <Typography.Paragraph style={{ marginBottom: 0 }} ellipsis={{ rows: 2, expandable: true, symbol: '展开' }}>
          {value}
        </Typography.Paragraph>
      ),
    },
  ];

  return (
    <>
      <Card className="glass-card workspace-ai-assets" title="AI 资产工作台">
        <Space direction="vertical" size="large" style={{ width: '100%' }}>
          <div className="workspace-ai-assets__header">
            <div>
              <Typography.Title level={5} style={{ margin: 0 }}>
                预执行资产总览
              </Typography.Title>
              <Typography.Paragraph type="secondary" style={{ marginBottom: 0 }}>
                先筛、再选、最后应用。列表固定 10 条分页，详情区保持全宽，避免左右挤压导致信息失真。
              </Typography.Paragraph>
            </div>
            <Segmented<AssetMode>
              value={mode}
              onChange={setMode}
              options={[
                { label: '测试数据', value: 'test_data' },
                { label: 'Mock 模板', value: 'mock' },
              ]}
            />
          </div>

          <Row gutter={[12, 12]}>
            <Col xs={24} md={12} xl={6}>
              <Card size="small" className="workspace-summary-card">
                <Statistic title="当前模式" value={mode === 'test_data' ? '测试数据' : 'Mock 模板'} />
              </Card>
            </Col>
            <Col xs={24} md={12} xl={6}>
              <Card size="small" className="workspace-summary-card">
                <Statistic title="当前预览" value={mode === 'test_data' ? variants.length : templates.length} suffix="项" />
              </Card>
            </Col>
            <Col xs={24} md={12} xl={6}>
              <Card size="small" className="workspace-summary-card">
                <Statistic title="已勾选" value={mode === 'test_data' ? selectedVariantIds.length : selectedTemplateIds.length} suffix="项" />
              </Card>
            </Col>
            <Col xs={24} md={12} xl={6}>
              <Card size="small" className="workspace-summary-card">
                <Statistic
                  title="历史版本"
                  value={mode === 'test_data' ? testDataHistoryItems.length : mockHistoryItems.length}
                  suffix="条"
                />
              </Card>
            </Col>
          </Row>

          {mode === 'test_data' ? (
            <AiCapabilityActionCard
              title="AI 测试数据资产"
              actions={
                <Space wrap>
                  <Button size="small" onClick={onOpenTestDataHistory}>
                    历史
                  </Button>
                  <Button size="small" loading={testDataExportLoading} disabled={!testDataPreview} onClick={onExportTestData}>
                    导出 JSON
                  </Button>
                  <Button size="small" loading={testDataLoading} onClick={onPreviewTestData} disabled={!canEdit}>
                    生成
                  </Button>
                  <Button
                    type="primary"
                    size="small"
                    loading={testDataApplyLoading}
                    disabled={!canEdit || !testDataPreview || !selectedVariantIds.length}
                    onClick={onApplyTestDataAppend}
                  >
                    应用追加
                  </Button>
                  <Popconfirm
                    title="覆盖后会替换当前已保存的 AI 测试数据变体，确认继续？"
                    onConfirm={onApplyTestDataOverride}
                    disabled={!canEdit || !testDataPreview || !selectedVariantIds.length}
                  >
                    <Button danger size="small" loading={testDataApplyLoading} disabled={!canEdit || !testDataPreview || !selectedVariantIds.length}>
                      覆盖应用
                    </Button>
                  </Popconfirm>
                </Space>
              }
              error={testDataError}
              warnings={testDataPreview?.warnings ?? []}
              hasContent={Boolean(testDataPreview)}
              empty={<Typography.Text type="secondary">先保存用例，再生成可筛选、可预览、可分页的测试数据资产。</Typography.Text>}
            >
              {testDataPreview ? (
                <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                  <div className="workspace-filter-bar">
                    <Input
                      allowClear
                      value={testDataKeyword}
                      onChange={(event) => setTestDataKeyword(event.target.value)}
                      placeholder="按变体名 / 目标字段 / 原因筛选"
                    />
                    <Select
                      allowClear
                      value={testDataCategory}
                      onChange={(value) => setTestDataCategory(value)}
                      placeholder="按分类筛选"
                      options={testDataCategories}
                      style={{ width: 180 }}
                    />
                    <Button
                      onClick={() => {
                        setTestDataKeyword('');
                        setTestDataCategory(undefined);
                      }}
                    >
                      重置筛选
                    </Button>
                  </div>

                  <Table<AiTestDataVariant>
                    rowKey="variant_id"
                    size="small"
                    dataSource={filteredVariants}
                    columns={testDataColumns}
                    pagination={TABLE_PAGINATION}
                    scroll={{ x: 1080 }}
                    rowSelection={{
                      selectedRowKeys: selectedVariantIds,
                      onChange: (keys) => onSelectionChangeVariantIds(keys.map(String)),
                      getCheckboxProps: () => ({ disabled: !canEdit }),
                    }}
                    onRow={(record) => ({
                      onClick: () => setActiveVariantId(record.variant_id),
                    })}
                    locale={{ emptyText: <Empty description="当前筛选条件下没有测试数据资产" /> }}
                  />

                  <Card
                    size="small"
                    className="workspace-detail-card"
                    title={activeVariant ? `变体详情 · ${activeVariant.name}` : '变体详情'}
                  >
                    {activeVariant ? (
                      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                        <Descriptions column={2} size="small">
                          <Descriptions.Item label="变体 ID">{activeVariant.variant_id}</Descriptions.Item>
                          <Descriptions.Item label="分类">
                            <Tag color="blue">{activeVariant.category}</Tag>
                          </Descriptions.Item>
                          <Descriptions.Item label="目标字段" span={2}>
                            {activeVariant.target_fields.join(', ') || '-'}
                          </Descriptions.Item>
                          <Descriptions.Item label="原因" span={2}>
                            {activeVariant.reason || '-'}
                          </Descriptions.Item>
                        </Descriptions>
                        <Card size="small" title="Payload Patch">
                          <pre className="code-block">{stringifyPayload(activeVariant.payload_patch)}</pre>
                        </Card>
                        <Card size="small" title={`建议断言 (${activeVariant.suggested_assertions.length})`}>
                          <pre className="code-block">{stringifyPayload(activeVariant.suggested_assertions)}</pre>
                        </Card>
                      </Space>
                    ) : (
                      <Empty description="点击上方表格的一行，在这里查看完整详情。" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                    )}
                  </Card>
                </Space>
              ) : null}
            </AiCapabilityActionCard>
          ) : (
            <AiCapabilityActionCard
              title="AI Mock 资产"
              actions={
                <Space wrap>
                  <Button size="small" onClick={onOpenMockHistory}>
                    历史
                  </Button>
                  <Button size="small" loading={mockExportLoading} disabled={!mockPreview} onClick={onExportMock}>
                    导出 JSON
                  </Button>
                  <Button size="small" loading={mockLoading} onClick={onPreviewMock} disabled={!canEdit}>
                    生成
                  </Button>
                  <Button
                    type="primary"
                    size="small"
                    loading={mockApplyLoading}
                    disabled={!canEdit || !mockPreview || !selectedTemplateIds.length}
                    onClick={onApplyMockAppend}
                  >
                    应用追加
                  </Button>
                  <Popconfirm
                    title="覆盖后会替换当前已保存的 AI Mock 模板，确认继续？"
                    onConfirm={onApplyMockOverride}
                    disabled={!canEdit || !mockPreview || !selectedTemplateIds.length}
                  >
                    <Button danger size="small" loading={mockApplyLoading} disabled={!canEdit || !mockPreview || !selectedTemplateIds.length}>
                      覆盖应用
                    </Button>
                  </Popconfirm>
                </Space>
              }
              error={mockError}
              warnings={mockPreview?.warnings ?? []}
              hasContent={Boolean(mockPreview)}
              empty={<Typography.Text type="secondary">先保存用例，再生成可筛选、可预览、可分页的 Mock 模板。</Typography.Text>}
            >
              {mockPreview ? (
                <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                  <div className="workspace-filter-bar">
                    <Input
                      allowClear
                      value={mockKeyword}
                      onChange={(event) => setMockKeyword(event.target.value)}
                      placeholder="按模板名 / 匹配规则 / 原因筛选"
                    />
                    <Select
                      allowClear
                      value={mockBucket}
                      onChange={(value) => setMockBucket(value)}
                      placeholder="按状态码筛选"
                      options={[
                        { label: '2xx', value: '2xx' },
                        { label: '4xx', value: '4xx' },
                        { label: '5xx', value: '5xx' },
                      ]}
                      style={{ width: 180 }}
                    />
                    <Button
                      onClick={() => {
                        setMockKeyword('');
                        setMockBucket(undefined);
                      }}
                    >
                      重置筛选
                    </Button>
                  </div>

                  <Table<AiMockTemplate>
                    rowKey="template_id"
                    size="small"
                    dataSource={filteredTemplates}
                    columns={mockColumns}
                    pagination={TABLE_PAGINATION}
                    scroll={{ x: 1080 }}
                    rowSelection={{
                      selectedRowKeys: selectedTemplateIds,
                      onChange: (keys) => onSelectionChangeTemplateIds(keys.map(String)),
                      getCheckboxProps: () => ({ disabled: !canEdit }),
                    }}
                    onRow={(record) => ({
                      onClick: () => setActiveTemplateId(record.template_id),
                    })}
                    locale={{ emptyText: <Empty description="当前筛选条件下没有 Mock 模板" /> }}
                  />

                  <Card
                    size="small"
                    className="workspace-detail-card"
                    title={activeTemplate ? `模板详情 · ${activeTemplate.scenario_name}` : '模板详情'}
                  >
                    {activeTemplate ? (
                      <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                        <Descriptions column={2} size="small">
                          <Descriptions.Item label="模板 ID">{activeTemplate.template_id}</Descriptions.Item>
                          <Descriptions.Item label="状态码">
                            <Tag color={mockStatusColor(activeTemplate.status_code)}>{activeTemplate.status_code}</Tag>
                          </Descriptions.Item>
                          <Descriptions.Item label="匹配规则" span={2}>
                            {stringifyRule(activeTemplate)}
                          </Descriptions.Item>
                          <Descriptions.Item label="原因" span={2}>
                            {activeTemplate.reason || '-'}
                          </Descriptions.Item>
                        </Descriptions>
                        <Card size="small" title={`Mock Rules (${activeTemplate.mock_rules.length})`}>
                          <pre className="code-block">{stringifyPayload(activeTemplate.mock_rules)}</pre>
                        </Card>
                        <Card size="small" title="Response Template">
                          <pre className="code-block">{stringifyPayload(activeTemplate.response_template)}</pre>
                        </Card>
                      </Space>
                    ) : (
                      <Empty description="点击上方表格的一行，在这里查看完整详情。" image={Empty.PRESENTED_IMAGE_SIMPLE} />
                    )}
                  </Card>
                </Space>
              ) : null}
            </AiCapabilityActionCard>
          )}
        </Space>
      </Card>

      <AiArtifactHistoryDrawer
        title="AI 测试数据历史"
        open={testDataHistoryOpen}
        onClose={onCloseTestDataHistory}
        loading={testDataHistoryLoading}
        error={testDataHistoryError}
        items={testDataHistoryItems.map((item) => {
          const result = normalizeTestDataHistoryResult(item.output_json);
          return {
            key: item.artifact_id,
            label: `${item.artifact_id.slice(0, 8)} · ${result.data_variants.length} variants · ${item.status}`,
            content: (
              <Space direction="vertical" style={{ width: '100%' }}>
                <Typography.Text type="secondary">case #{item.target_id}</Typography.Text>
                <Typography.Text>{result.data_variants.map((variant) => variant.name).slice(0, 3).join(' / ') || '无变体'}</Typography.Text>
                <Space>
                  <Button size="small" onClick={() => onLoadTestDataHistory(item, result)}>
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

      <AiArtifactHistoryDrawer
        title="AI Mock 历史"
        open={mockHistoryOpen}
        onClose={onCloseMockHistory}
        loading={mockHistoryLoading}
        error={mockHistoryError}
        items={mockHistoryItems.map((item) => {
          const result = normalizeMockHistoryResult(item.output_json);
          return {
            key: item.artifact_id,
            label: `${item.artifact_id.slice(0, 8)} · ${result.mock_templates.length} templates · ${item.status}`,
            content: (
              <Space direction="vertical" style={{ width: '100%' }}>
                <Typography.Text type="secondary">case #{item.target_id}</Typography.Text>
                <Typography.Text>{result.mock_templates.map((template) => template.scenario_name).slice(0, 3).join(' / ') || '无模板'}</Typography.Text>
                <Space>
                  <Button size="small" onClick={() => onLoadMockHistory(item, result)}>
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
