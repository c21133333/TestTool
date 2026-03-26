import { App, Button, Card, Col, Form, Input, Popconfirm, Row, Select, Space, Table, Typography } from 'antd';
import { useEffect, useMemo, useState } from 'react';

import { createApi } from '../api/services';
import type { Environment, Project } from '../api/types';
import { useAuth } from '../auth/AuthContext';
import { canManageWorkspace } from '../auth/permissions';
import { KeyValueEditor, type KeyValueEditorRow } from '../components/editors/KeyValueEditor';
import { PageHero } from '../components/product/PageHero';

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

  const projectCount = projects.length;
  const headerCount = environments.reduce((total, item) => total + Object.keys(item.headers_json ?? {}).length, 0);
  const variableCount = environments.reduce((total, item) => total + Object.keys(item.variables_json ?? {}).length, 0);

  return (
    <div className="page-stack">
      <PageHero
        eyebrow="OPS / ENV CENTER"
        title="环境配置"
        description="集中管理项目级 Base URL、默认请求头和运行变量，为执行中心提供稳定的切换入口。"
        tags={[
          <span key="env-count" className="lab-chip">
            {environments.length} 个环境
          </span>,
          <span key="project-count" className="lab-chip">
            覆盖 {projectCount} 个项目
          </span>,
          <span key="mode" className="lab-chip">
            {canEdit ? '可编辑' : '只读查看'}
          </span>,
        ]}
        actions={
          <Space wrap>
            <Button onClick={() => void refresh()}>刷新</Button>
            <Button type="primary" onClick={resetForm} disabled={!canEdit}>
              新建环境
            </Button>
          </Space>
        }
      />

      <div className="dashboard-kpi-grid">
        <Card className="metric-card dashboard-kpi-card dashboard-kpi-card--primary" bordered={false}>
          <span className="dashboard-kpi-card__code">ENV-01</span>
          <Typography.Text className="workspace-summary-card__label">环境总数</Typography.Text>
          <Typography.Title level={2}>{environments.length}</Typography.Title>
          <Typography.Paragraph>已配置的执行环境数量</Typography.Paragraph>
        </Card>
        <Card className="metric-card dashboard-kpi-card dashboard-kpi-card--info" bordered={false}>
          <span className="dashboard-kpi-card__code">PRJ-02</span>
          <Typography.Text className="workspace-summary-card__label">项目覆盖</Typography.Text>
          <Typography.Title level={2}>{projectCount}</Typography.Title>
          <Typography.Paragraph>已接入环境配置的项目数</Typography.Paragraph>
        </Card>
        <Card className="metric-card dashboard-kpi-card dashboard-kpi-card--signal" bordered={false}>
          <span className="dashboard-kpi-card__code">HDR-03</span>
          <Typography.Text className="workspace-summary-card__label">默认请求头</Typography.Text>
          <Typography.Title level={2}>{headerCount}</Typography.Title>
          <Typography.Paragraph>已登记的请求头条目</Typography.Paragraph>
        </Card>
        <Card className="metric-card dashboard-kpi-card dashboard-kpi-card--success" bordered={false}>
          <span className="dashboard-kpi-card__code">VAR-04</span>
          <Typography.Text className="workspace-summary-card__label">运行变量</Typography.Text>
          <Typography.Title level={2}>{variableCount}</Typography.Title>
          <Typography.Paragraph>执行时可注入的变量数量</Typography.Paragraph>
        </Card>
      </div>

      <Row gutter={[18, 18]}>
        <Col xs={24} xl={9}>
          <Card className="glass-card workspace-section-card" title={editingEnvironmentId ? '编辑环境' : '新增环境'}>
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
              <Form.Item label="默认请求头">
                <KeyValueEditor
                  rows={headerRows}
                  onChange={setHeaderRows}
                  disabled={!canEdit}
                  addLabel="新增请求头"
                  keyPlaceholder="Authorization"
                  valuePlaceholder="Bearer token"
                />
              </Form.Item>
              <Form.Item label="运行变量">
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
                  {editingEnvironmentId ? '保存修改' : '创建环境'}
                </Button>
                <Button onClick={resetForm}>重置</Button>
              </Space>
            </Form>
          </Card>
        </Col>
        <Col xs={24} xl={15}>
          <Card className="glass-card workspace-section-card" title="环境清单">
            <Table
              rowKey="id"
              pagination={{ pageSize: 10, showSizeChanger: false, hideOnSinglePage: true }}
              dataSource={environments}
              columns={[
                { title: '环境名称', dataIndex: 'name' },
                { title: '项目 ID', dataIndex: 'project_id' },
                { title: 'Base URL', dataIndex: 'base_url' },
                { title: '请求头', render: (_, row) => Object.keys(row.headers_json ?? {}).length },
                { title: '变量', render: (_, row) => Object.keys(row.variables_json ?? {}).length },
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
                      <Popconfirm
                        title="确认删除该环境？"
                        disabled={!canEdit}
                        onConfirm={() =>
                          void api.deleteEnvironment(row.id).then(() => {
                            message.success('环境已删除。');
                            if (editingEnvironmentId === row.id) {
                              resetForm();
                            }
                            return refresh();
                          })
                        }
                      >
                        <Button size="small" danger disabled={!canEdit}>
                          删除
                        </Button>
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
