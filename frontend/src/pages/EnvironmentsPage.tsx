import { App, Button, Card, Col, Form, Input, Popconfirm, Row, Select, Space, Table, Typography } from 'antd';
import { useEffect, useMemo, useState } from 'react';

import { createApi } from '../api/services';
import type { Environment, Project } from '../api/types';
import { useAuth } from '../auth/AuthContext';
import { canManageWorkspace } from '../auth/permissions';
import { KeyValueEditor, type KeyValueEditorRow } from '../components/editors/KeyValueEditor';

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

function mapToRows(value: Record<string, unknown> | undefined): KeyValueEditorRow[] {
  return Object.entries(value ?? {}).map(([field, entryValue], index) => ({
    key: `${field}-${index}`,
    field,
    value: stringifyValue(entryValue),
  }));
}

function rowsToMap(rows: KeyValueEditorRow[], parseValue: boolean): Record<string, unknown> {
  return rows.reduce<Record<string, unknown>>((result, row) => {
    const trimmedKey = row.field.trim();
    if (!trimmedKey) {
      return result;
    }
    result[trimmedKey] = parseValue ? parseLooseValue(row.value) : row.value;
    return result;
  }, {});
}

export function EnvironmentsPage() {
  const { token, user } = useAuth();
  const api = useMemo(() => createApi(token), [token]);
  const { message } = App.useApp();
  const canEdit = canManageWorkspace(user);
  const [projects, setProjects] = useState<Project[]>([]);
  const [environments, setEnvironments] = useState<Environment[]>([]);
  const [editingEnvironmentId, setEditingEnvironmentId] = useState<number | null>(null);
  const [headerRows, setHeaderRows] = useState<KeyValueEditorRow[]>([]);
  const [variableRows, setVariableRows] = useState<KeyValueEditorRow[]>([]);
  const [form] = Form.useForm<{
    project_id: number;
    name: string;
    base_url: string;
    description: string;
  }>();

  async function refresh() {
    const [nextProjects, nextEnvironments] = await Promise.all([api.listProjects(), api.listEnvironments()]);
    setProjects(nextProjects);
    setEnvironments(nextEnvironments);
  }

  useEffect(() => {
    void refresh();
    form.setFieldsValue({
      description: '',
      base_url: '',
      name: '',
    });
    setHeaderRows([]);
    setVariableRows([]);
  }, [api, form]);

  function resetForm() {
    setEditingEnvironmentId(null);
    form.setFieldsValue({
      project_id: undefined,
      name: '',
      base_url: '',
      description: '',
    });
    setHeaderRows([]);
    setVariableRows([]);
  }

  async function submit(values: {
    project_id: number;
    name: string;
    base_url: string;
    description: string;
  }) {
    const payload = {
      project_id: values.project_id,
      name: values.name,
      base_url: values.base_url,
      description: values.description,
      headers_json: rowsToMap(headerRows, false),
      variables_json: rowsToMap(variableRows, true),
    };
    if (editingEnvironmentId === null) {
      await api.createEnvironment(payload);
      message.success('环境已创建。');
    } else {
      await api.updateEnvironment(editingEnvironmentId, payload);
      message.success('环境已更新。');
    }
    resetForm();
    await refresh();
  }

  return (
    <div className="page-stack">
      <div className="page-hero">
        <Typography.Title>环境管理</Typography.Title>
        <Typography.Paragraph>
          在这里维护 Base URL、公共请求头和环境变量。测试与管理员可编辑，开发角色默认只读查看。
        </Typography.Paragraph>
      </div>
      <Row gutter={[18, 18]}>
        <Col span={9}>
          <Card className="glass-card" title={editingEnvironmentId ? '编辑环境' : '新建环境'}>
            <Form form={form} layout="vertical" onFinish={(values) => void submit(values)} disabled={!canEdit}>
              <Form.Item name="project_id" label="所属项目" rules={[{ required: true, message: '请选择所属项目。' }]}>
                <Select options={projects.map((project) => ({ value: project.id, label: project.name }))} />
              </Form.Item>
              <Form.Item name="name" label="环境名称" rules={[{ required: true, message: '请输入环境名称。' }]}>
                <Input />
              </Form.Item>
              <Form.Item name="base_url" label="Base URL">
                <Input placeholder="https://api.example.com" />
              </Form.Item>
              <Form.Item name="description" label="说明">
                <Input.TextArea rows={2} />
              </Form.Item>
              <Form.Item label="请求头">
                <KeyValueEditor
                  rows={headerRows}
                  onChange={setHeaderRows}
                  disabled={!canEdit}
                  addLabel="新增请求头"
                  keyPlaceholder="Authorization"
                  valuePlaceholder="Bearer token"
                />
              </Form.Item>
              <Form.Item label="变量">
                <KeyValueEditor
                  rows={variableRows}
                  onChange={setVariableRows}
                  disabled={!canEdit}
                  addLabel="新增变量"
                  keyPlaceholder="tenant_id"
                  valuePlaceholder='123 或 "tenant-a"'
                />
              </Form.Item>
              <Space>
                <Button type="primary" htmlType="submit" disabled={!canEdit}>
                  {editingEnvironmentId ? '保存' : '创建'}
                </Button>
                <Button onClick={resetForm}>重置</Button>
              </Space>
            </Form>
          </Card>
        </Col>
        <Col span={15}>
          <Card className="glass-card" title="环境列表">
            <Table
              rowKey="id"
              pagination={false}
              dataSource={environments}
              columns={[
                { title: '名称', dataIndex: 'name' },
                { title: '项目 ID', dataIndex: 'project_id' },
                { title: 'Base URL', dataIndex: 'base_url' },
                { title: '请求头数', render: (_, row) => Object.keys(row.headers_json ?? {}).length },
                { title: '变量数', render: (_, row) => Object.keys(row.variables_json ?? {}).length },
                {
                  title: '操作',
                  render: (_, row) => (
                    <Space>
                      <Button
                        size="small"
                        onClick={() => {
                          setEditingEnvironmentId(row.id);
                          form.setFieldsValue({
                            project_id: row.project_id,
                            name: row.name,
                            base_url: row.base_url,
                            description: row.description,
                          });
                          setHeaderRows(mapToRows(row.headers_json));
                          setVariableRows(mapToRows(row.variables_json));
                        }}
                      >
                        {canEdit ? '编辑' : '查看'}
                      </Button>
                      <Popconfirm title="确认删除这个环境吗？" disabled={!canEdit} onConfirm={() => void api.deleteEnvironment(row.id).then(refresh)}>
                        <Button size="small" danger disabled={!canEdit}>删除</Button>
                      </Popconfirm>
                    </Space>
                  ),
                },
              ]}
            />
          </Card>
        </Col>
      </Row>
    </div>
  );
}
