import { Button, Input, Space, Typography } from 'antd';

import { createClientId } from '../../utils/id';

export type KeyValueEditorRow = {
  key: string;
  field: string;
  value: string;
};

type Props = {
  rows: KeyValueEditorRow[];
  onChange: (rows: KeyValueEditorRow[]) => void;
  disabled?: boolean;
  addLabel?: string;
  keyPlaceholder?: string;
  valuePlaceholder?: string;
};

export function KeyValueEditor({
  rows,
  onChange,
  disabled = false,
  addLabel = '新增条目',
  keyPlaceholder = '键',
  valuePlaceholder = '值',
}: Props) {
  function updateRow(targetKey: string, patch: Partial<KeyValueEditorRow>) {
    onChange(rows.map((row) => (row.key === targetKey ? { ...row, ...patch } : row)));
  }

  function addRow() {
    onChange([
      ...rows,
      {
        key: createClientId('key-value'),
        field: '',
        value: '',
      },
    ]);
  }

  function removeRow(targetKey: string) {
    onChange(rows.filter((row) => row.key !== targetKey));
  }

  return (
    <Space direction="vertical" style={{ width: '100%' }}>
      {rows.map((row) => (
        <Space key={row.key} style={{ width: '100%' }} align="start">
          <Input
            placeholder={keyPlaceholder}
            value={row.field}
            disabled={disabled}
            onChange={(event) => updateRow(row.key, { field: event.target.value })}
          />
          <Input
            placeholder={valuePlaceholder}
            value={row.value}
            disabled={disabled}
            onChange={(event) => updateRow(row.key, { value: event.target.value })}
          />
          <Button danger disabled={disabled} onClick={() => removeRow(row.key)}>
            删除
          </Button>
        </Space>
      ))}
      <Button disabled={disabled} onClick={addRow}>
        {addLabel}
      </Button>
      {!rows.length ? <Typography.Text type="secondary">当前还没有配置任何条目。</Typography.Text> : null}
    </Space>
  );
}
