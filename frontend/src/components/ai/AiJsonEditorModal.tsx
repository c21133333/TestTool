import { App, Input, Modal, Segmented, Space, Typography } from 'antd';
import { useEffect, useState } from 'react';

import { AssertionEditor, type AssertionEditorRow } from '../editors/AssertionEditor';
import { KeyValueEditor, type KeyValueEditorRow } from '../editors/KeyValueEditor';

type JsonEditorField = 'headers_json' | 'body_json' | 'assertions_json' | 'metadata_json';

type Props = {
  open: boolean;
  field: JsonEditorField | null;
  value: unknown;
  onCancel: () => void;
  onSave: (value: unknown) => void;
};

function stringifyJson(value: unknown, fallback = '{}') {
  try {
    return JSON.stringify(value ?? JSON.parse(fallback), null, 2);
  } catch {
    return fallback;
  }
}

function parseLooseValue(value: string): unknown {
  if (!value.trim()) {
    return '';
  }
  try {
    return JSON.parse(value);
  } catch {
    return value;
  }
}

function stringifyValue(value: unknown): string {
  if (typeof value === 'string') {
    return value;
  }
  if (value === null || value === undefined) {
    return '';
  }
  try {
    return JSON.stringify(value);
  } catch {
    return String(value);
  }
}

function headersToRows(value: unknown): KeyValueEditorRow[] {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return [];
  }
  return Object.entries(value).map(([field, item]) => ({
    key: crypto.randomUUID(),
    field,
    value: stringifyValue(item),
  }));
}

function rowsToHeaders(rows: KeyValueEditorRow[]) {
  return rows.reduce<Record<string, string>>((result, row) => {
    const key = row.field.trim();
    if (!key) {
      return result;
    }
    result[key] = row.value;
    return result;
  }, {});
}

function assertionsToRows(value: unknown): AssertionEditorRow[] {
  if (!Array.isArray(value)) {
    return [];
  }
  return value
    .filter((item): item is Record<string, unknown> => typeof item === 'object' && item !== null)
    .map((item) => ({
      key: crypto.randomUUID(),
      type: String(item.type ?? 'status_code'),
      operator: String(item.operator ?? '=='),
      path: String(item.path ?? ''),
      header: String(item.header ?? item.target ?? ''),
      expected: item.expected === undefined ? '' : stringifyValue(item.expected),
      enabled: item.enabled !== false,
    }));
}

function rowsToAssertions(rows: AssertionEditorRow[]) {
  return rows.map((row) => {
    const payload: Record<string, unknown> = {
      type: row.type,
      operator: row.operator,
      expected: parseLooseValue(row.expected),
      enabled: row.enabled,
    };
    if (row.type === 'json_path' && row.path) {
      payload.path = row.path;
    }
    if (row.type === 'header' && row.header) {
      payload.header = row.header;
    }
    return payload;
  });
}

export function AiJsonEditorModal({ open, field, value, onCancel, onSave }: Props) {
  const { message } = App.useApp();
  const [mode, setMode] = useState<'structured' | 'raw'>('structured');
  const [jsonText, setJsonText] = useState('{}');
  const [headerRows, setHeaderRows] = useState<KeyValueEditorRow[]>([]);
  const [assertionRows, setAssertionRows] = useState<AssertionEditorRow[]>([]);

  useEffect(() => {
    if (!field) {
      return;
    }
    if (field === 'headers_json') {
      setMode('structured');
      setHeaderRows(headersToRows(value));
      setJsonText(stringifyJson(value));
      return;
    }
    if (field === 'assertions_json') {
      setMode('structured');
      setAssertionRows(assertionsToRows(value));
      setJsonText(stringifyJson(value, '[]'));
      return;
    }
    setMode('raw');
    setJsonText(stringifyJson(value, field === 'body_json' ? 'null' : '{}'));
  }, [field, value]);

  function handleSave() {
    try {
      if (!field) {
        return;
      }
      if (field === 'headers_json' && mode === 'structured') {
        onSave(rowsToHeaders(headerRows));
        return;
      }
      if (field === 'assertions_json' && mode === 'structured') {
        onSave(rowsToAssertions(assertionRows));
        return;
      }
      onSave(JSON.parse(jsonText));
    } catch (error) {
      message.error(error instanceof Error ? error.message : 'JSON 保存失败。');
    }
  }

  const canStructuredEdit = field === 'headers_json' || field === 'assertions_json';

  return (
    <Modal title={field ? `编辑 ${field}` : '编辑 JSON'} open={open} onCancel={onCancel} onOk={handleSave} width={820}>
      <Space direction="vertical" style={{ width: '100%' }}>
        {canStructuredEdit ? (
          <Segmented
            value={mode}
            onChange={(nextValue) => setMode(String(nextValue) === 'raw' ? 'raw' : 'structured')}
            options={[
              { label: '结构化编辑', value: 'structured' },
              { label: '原始 JSON', value: 'raw' },
            ]}
          />
        ) : null}
        {field === 'headers_json' && mode === 'structured' ? (
          <KeyValueEditor
            rows={headerRows}
            onChange={setHeaderRows}
            addLabel="新增请求头"
            keyPlaceholder="Content-Type"
            valuePlaceholder="application/json"
          />
        ) : null}
        {field === 'assertions_json' && mode === 'structured' ? (
          <AssertionEditor rows={assertionRows} onChange={setAssertionRows} />
        ) : null}
        {field && (!canStructuredEdit || mode === 'raw') ? (
          <>
            <Input.TextArea rows={16} spellCheck={false} value={jsonText} onChange={(event) => setJsonText(event.target.value)} />
            <Typography.Text type="secondary">原始模式要求输入合法 JSON。</Typography.Text>
          </>
        ) : null}
      </Space>
    </Modal>
  );
}
