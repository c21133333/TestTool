import { Button, Checkbox, Input, Select, Space, Table, Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';

import type { AiCaseDraft } from '../../api/types';

const methodOptions = ['GET', 'POST', 'PUT', 'DELETE', 'PATCH', 'HEAD', 'OPTIONS'].map((method) => ({ value: method, label: method }));

type Props = {
  drafts: AiCaseDraft[];
  canEdit: boolean;
  onDraftChange: (draftId: string, updater: (draft: AiCaseDraft) => AiCaseDraft) => void;
  onDraftDuplicate: (draft: AiCaseDraft) => void;
  onDraftDelete: (draftId: string) => void;
  onEditJson: (draft: AiCaseDraft, field: 'headers_json' | 'body_json' | 'assertions_json' | 'metadata_json') => void;
};

export function AiCaseDraftTable({ drafts, canEdit, onDraftChange, onDraftDuplicate, onDraftDelete, onEditJson }: Props) {
  const columns: ColumnsType<AiCaseDraft> = [
    {
      title: '导入',
      dataIndex: 'selected',
      width: 72,
      render: (_, draft) => (
        <Checkbox
          checked={draft.selected}
          disabled={!canEdit || draft.validation_status === 'invalid'}
          onChange={(event) => onDraftChange(draft.draft_id, (current) => ({ ...current, selected: event.target.checked }))}
        />
      ),
    },
    {
      title: '状态',
      width: 96,
      render: (_, draft) => {
        const color = draft.validation_status === 'valid' ? 'green' : draft.validation_status === 'warning' ? 'gold' : 'red';
        const label = draft.validation_status === 'valid' ? '有效' : draft.validation_status === 'warning' ? '警告' : '无效';
        return <Tag color={color}>{label}</Tag>;
      },
    },
    {
      title: '用例名',
      width: 180,
      render: (_, draft) => (
        <Input
          value={draft.case.name}
          disabled={!canEdit}
          onChange={(event) =>
            onDraftChange(draft.draft_id, (current) => ({
              ...current,
              case: { ...current.case, name: event.target.value },
            }))
          }
        />
      ),
    },
    {
      title: 'Method',
      width: 120,
      render: (_, draft) => (
        <Select
          value={draft.case.method}
          disabled={!canEdit}
          options={methodOptions}
          onChange={(value) =>
            onDraftChange(draft.draft_id, (current) => ({
              ...current,
              case: { ...current.case, method: value },
            }))
          }
          style={{ width: '100%' }}
        />
      ),
    },
    {
      title: 'URL',
      width: 220,
      render: (_, draft) => (
        <Input
          value={draft.case.url}
          disabled={!canEdit}
          onChange={(event) =>
            onDraftChange(draft.draft_id, (current) => ({
              ...current,
              case: { ...current.case, url: event.target.value },
            }))
          }
        />
      ),
    },
    {
      title: '描述',
      width: 180,
      render: (_, draft) => (
        <Input
          value={draft.case.description}
          disabled={!canEdit}
          onChange={(event) =>
            onDraftChange(draft.draft_id, (current) => ({
              ...current,
              case: { ...current.case, description: event.target.value },
            }))
          }
        />
      ),
    },
    {
      title: '分类',
      width: 140,
      render: (_, draft) => (
        <Input
          value={String(draft.case.metadata_json.category ?? '')}
          disabled={!canEdit}
          onChange={(event) =>
            onDraftChange(draft.draft_id, (current) => ({
              ...current,
              case: {
                ...current.case,
                metadata_json: { ...current.case.metadata_json, category: event.target.value },
              },
            }))
          }
        />
      ),
    },
    {
      title: '优先级',
      width: 120,
      render: (_, draft) => (
        <Select
          allowClear
          value={typeof draft.case.metadata_json.priority === 'string' ? draft.case.metadata_json.priority : undefined}
          disabled={!canEdit}
          options={['P0', 'P1', 'P2', 'P3'].map((item) => ({ value: item, label: item }))}
          onChange={(value) =>
            onDraftChange(draft.draft_id, (current) => ({
              ...current,
              case: {
                ...current.case,
                metadata_json: { ...current.case.metadata_json, priority: value ?? '' },
              },
            }))
          }
          style={{ width: '100%' }}
        />
      ),
    },
    {
      title: '结构化字段',
      width: 220,
      render: (_, draft) => (
        <Space wrap>
          <Button size="small" disabled={!canEdit} onClick={() => onEditJson(draft, 'headers_json')}>
            Headers
          </Button>
          <Button size="small" disabled={!canEdit} onClick={() => onEditJson(draft, 'body_json')}>
            Body
          </Button>
          <Button size="small" disabled={!canEdit} onClick={() => onEditJson(draft, 'assertions_json')}>
            Assertions
          </Button>
          <Button size="small" disabled={!canEdit} onClick={() => onEditJson(draft, 'metadata_json')}>
            Metadata
          </Button>
        </Space>
      ),
    },
    {
      title: '来源片段',
      width: 260,
      render: (_, draft) => (
        <Space direction="vertical" style={{ width: '100%' }} size={4}>
          <Typography.Paragraph ellipsis={{ rows: 4, expandable: true, symbol: '展开' }} style={{ marginBottom: 0 }}>
            {draft.source_excerpt}
          </Typography.Paragraph>
          <Typography.Text type="secondary">
            {typeof draft.source_location.section_title === 'string' ? draft.source_location.section_title : '未定位章节'}
            {typeof draft.source_location.line_start === 'number' && typeof draft.source_location.line_end === 'number'
              ? ` · 行 ${draft.source_location.line_start}-${draft.source_location.line_end}`
              : ''}
            {draft.source_location.matched_endpoint && typeof draft.source_location.matched_endpoint === 'object'
              ? ` · 接口行 ${String((draft.source_location.matched_endpoint as { line_number?: number }).line_number ?? '')}`
              : ''}
          </Typography.Text>
        </Space>
      ),
    },
    {
      title: '校验 / 告警',
      width: 240,
      className: 'ai-case-draft-table__review',
      render: (_, draft) => (
        <Space direction="vertical" style={{ width: '100%' }} size={4}>
          <Typography.Paragraph style={{ marginBottom: 0 }}>
            {draft.validation_errors.length ? draft.validation_errors.join('；') : '校验通过'}
          </Typography.Paragraph>
          {draft.review_warnings.map((warning) => (
            <Tag
              color="gold"
              key={warning}
              style={{
                maxWidth: '100%',
                display: 'block',
                whiteSpace: 'normal',
                wordBreak: 'break-word',
                height: 'auto',
                lineHeight: '18px',
                marginInlineEnd: 0,
              }}
            >
              {warning}
            </Tag>
          ))}
        </Space>
      ),
    },
    {
      title: '操作',
      width: 120,
      className: 'ai-case-draft-table__actions',
      render: (_, draft) => (
        <Space direction="vertical" size="small">
          <Button size="small" disabled={!canEdit} onClick={() => onDraftDuplicate(draft)}>
            复制
          </Button>
          <Button size="small" danger disabled={!canEdit} onClick={() => onDraftDelete(draft.draft_id)}>
            删除
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <Table<AiCaseDraft>
      rowKey="draft_id"
      dataSource={drafts}
      columns={columns}
      className="ai-case-draft-table"
      pagination={{ pageSize: 10, showSizeChanger: false, hideOnSinglePage: true }}
      size="small"
      tableLayout="fixed"
      scroll={{ x: 2160, y: 460 }}
      locale={{ emptyText: '先生成草稿，再在这里审批和编辑。' }}
    />
  );
}
