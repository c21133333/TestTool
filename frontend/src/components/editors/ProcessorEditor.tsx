import { Button, Card, Input, Select, Space, Switch, Typography } from 'antd';

export type ProcessorEditorRow = {
  key: string;
  type: string;
  enabled: boolean;
  configText: string;
  language: string;
  code: string;
};

const processorTypeOptions = [
  { value: 'set_variable', label: 'set_variable' },
  { value: 'builtin_function', label: 'builtin_function' },
  { value: 'sleep', label: 'sleep' },
  { value: 'jsonpath_extract', label: 'jsonpath_extract' },
  { value: 'regex_extract', label: 'regex_extract' },
  { value: 'fail_if', label: 'fail_if' },
  { value: 'script', label: 'script' },
];

type Props = {
  title: string;
  rows: ProcessorEditorRow[];
  onChange: (rows: ProcessorEditorRow[]) => void;
  disabled?: boolean;
};

export function ProcessorEditor({ title, rows, onChange, disabled = false }: Props) {
  function updateRow(key: string, patch: Partial<ProcessorEditorRow>) {
    onChange(rows.map((row) => (row.key === key ? { ...row, ...patch } : row)));
  }

  function addRow() {
    onChange([
      ...rows,
      {
        key: crypto.randomUUID(),
        type: 'set_variable',
        enabled: true,
        configText: '{}',
        language: 'js',
        code: '',
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
          title={`${title} ${index + 1}`}
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
                options={processorTypeOptions}
                onChange={(value) => updateRow(row.key, { type: value })}
                style={{ width: 220 }}
              />
              <span>
                启用 <Switch checked={row.enabled} disabled={disabled} onChange={(value) => updateRow(row.key, { enabled: value })} />
              </span>
            </Space>
            {row.type === 'script' ? (
              <>
                <Select
                  value={row.language}
                  disabled={disabled}
                  options={[{ value: 'js', label: 'js' }]}
                  onChange={(value) => updateRow(row.key, { language: value })}
                  style={{ width: 120 }}
                />
                <Input.TextArea
                  rows={5}
                  placeholder="JavaScript 脚本"
                  value={row.code}
                  disabled={disabled}
                  onChange={(event) => updateRow(row.key, { code: event.target.value })}
                />
              </>
            ) : (
              <Input.TextArea
                rows={4}
                placeholder='{"key":"value"}'
                value={row.configText}
                disabled={disabled}
                onChange={(event) => updateRow(row.key, { configText: event.target.value })}
              />
            )}
          </Space>
        </Card>
      ))}
      <Button onClick={addRow} disabled={disabled}>
        新增处理器
      </Button>
      {!rows.length ? <Typography.Text type="secondary">当前还没有配置处理器。</Typography.Text> : null}
    </Space>
  );
}
