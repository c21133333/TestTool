import { Button, Card, Input, Select, Space, Switch, Typography } from 'antd';

import { createClientId } from '../../utils/id';

export type AssertionEditorRow = {
  key: string;
  type: string;
  operator: string;
  path: string;
  header: string;
  expected: string;
  enabled: boolean;
};

const assertionTypeOptions = [
  { value: 'status_code', label: 'status_code' },
  { value: 'json_path', label: 'json_path' },
  { value: 'response_body', label: 'response_body' },
  { value: 'header', label: 'header' },
  { value: 'response_time', label: 'response_time' },
];

const operatorOptions = [
  { value: '==', label: '==' },
  { value: '!=', label: '!=' },
  { value: 'contains', label: 'contains' },
  { value: 'not_contains', label: 'not_contains' },
  { value: 'not_null', label: 'not_null' },
  { value: '>', label: '>' },
  { value: '>=', label: '>=' },
  { value: '<', label: '<' },
  { value: '<=', label: '<=' },
];

type Props = {
  rows: AssertionEditorRow[];
  onChange: (rows: AssertionEditorRow[]) => void;
  disabled?: boolean;
};

export function AssertionEditor({ rows, onChange, disabled = false }: Props) {
  function updateRow(key: string, patch: Partial<AssertionEditorRow>) {
    onChange(rows.map((row) => (row.key === key ? { ...row, ...patch } : row)));
  }

  function addRow() {
    onChange([
      ...rows,
      {
        key: createClientId('assertion'),
        type: 'status_code',
        operator: '==',
        path: '',
        header: '',
        expected: '',
        enabled: true,
      },
    ]);
  }

  function removeRow(key: string) {
    onChange(rows.filter((row) => row.key !== key));
  }

  return (
    <Space direction="vertical" style={{ width: '100%' }}>
      {rows.map((row, index) => (
        <Card
          key={row.key}
          size="small"
          title={`断言 ${index + 1}`}
          extra={
            <Button size="small" danger disabled={disabled} onClick={() => removeRow(row.key)}>
              删除
            </Button>
          }
        >
          <Space direction="vertical" style={{ width: '100%' }}>
            <Space wrap style={{ width: '100%' }}>
              <Select
                value={row.type}
                disabled={disabled}
                options={assertionTypeOptions}
                onChange={(value) => updateRow(row.key, { type: value })}
                style={{ width: 160 }}
              />
              <Select
                value={row.operator}
                disabled={disabled}
                options={operatorOptions}
                onChange={(value) => updateRow(row.key, { operator: value })}
                style={{ width: 140 }}
              />
              <span>
                启用 <Switch checked={row.enabled} disabled={disabled} onChange={(value) => updateRow(row.key, { enabled: value })} />
              </span>
            </Space>
            {row.type === 'json_path' || row.type === 'header' ? (
              <Input
                placeholder={row.type === 'json_path' ? '$.data.id' : 'Content-Type'}
                value={row.type === 'json_path' ? row.path : row.header}
                disabled={disabled}
                onChange={(event) =>
                  updateRow(row.key, row.type === 'json_path' ? { path: event.target.value } : { header: event.target.value })
                }
              />
            ) : null}
            <Input
              placeholder="期望值"
              value={row.expected}
              disabled={disabled}
              onChange={(event) => updateRow(row.key, { expected: event.target.value })}
            />
          </Space>
        </Card>
      ))}
      <Button onClick={addRow} disabled={disabled}>
        新增断言
      </Button>
      {!rows.length ? <Typography.Text type="secondary">当前还没有配置断言。</Typography.Text> : null}
    </Space>
  );
}
