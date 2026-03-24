import { App, Button, Card, Col, Form, Input, Popconfirm, Row, Segmented, Select, Space, Table, Tabs, Typography, Upload } from 'antd';
import type { UploadFile } from 'antd/es/upload/interface';
import { useEffect, useMemo, useState } from 'react';

import { createApi } from '../api/services';
import type { ApiCase, Project, Suite } from '../api/types';
import { useAuth } from '../auth/AuthContext';
import { canManageWorkspace } from '../auth/permissions';
import { AssertionEditor, type AssertionEditorRow } from '../components/editors/AssertionEditor';
import { KeyValueEditor, type KeyValueEditorRow } from '../components/editors/KeyValueEditor';
import { ProcessorEditor, type ProcessorEditorRow } from '../components/editors/ProcessorEditor';

function stringifyJson(value: unknown, fallback: string) {
  try {
    return JSON.stringify(value ?? JSON.parse(fallback), null, 2);
  } catch {
    return fallback;
  }
}

function parseJsonField(value: string, fieldName: string) {
  if (!value.trim()) {
    return {};
  }
  try {
    return JSON.parse(value);
  } catch {
    throw new Error(`${fieldName} 必须是合法 JSON。`);
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

function mapToRows(value: Record<string, unknown> | undefined, prefix: string): KeyValueEditorRow[] {
  return Object.entries(value ?? {}).map(([field, entryValue], index) => ({
    key: `${prefix}-${field}-${index}`,
    field,
    value: stringifyValue(entryValue),
  }));
}

function rowsToHeaderMap(rows: KeyValueEditorRow[]): Record<string, string> {
  return rows.reduce<Record<string, string>>((result, row) => {
    const trimmedKey = row.field.trim();
    if (!trimmedKey) {
      return result;
    }
    result[trimmedKey] = row.value;
    return result;
  }, {});
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function rowsToObjectPayload(rows: KeyValueEditorRow[]): Record<string, unknown> {
  return rows.reduce<Record<string, unknown>>((result, row) => {
    const trimmedKey = row.field.trim();
    if (!trimmedKey) {
      return result;
    }
    result[trimmedKey] = parseLooseValue(row.value);
    return result;
  }, {});
}

const structuredMetadataKeys = ['category', 'precondition', 'priority', 'owner', 'tags', 'timeout_ms'] as const;

type StructuredMetadataForm = {
  category: string;
  precondition: string;
  priority: string;
  owner: string;
  tags: string;
  timeout_ms: string;
  metadata_extra_json: string;
};

function splitMetadata(metadata: Record<string, unknown> | undefined): StructuredMetadataForm {
  const source = metadata ?? {};
  const extras = Object.fromEntries(
    Object.entries(source).filter(([key]) => !structuredMetadataKeys.includes(key as (typeof structuredMetadataKeys)[number])),
  );
  const tagsValue = source.tags;
  return {
    category: typeof source.category === 'string' ? source.category : '',
    precondition: typeof source.precondition === 'string' ? source.precondition : '',
    priority: typeof source.priority === 'string' ? source.priority : '',
    owner: typeof source.owner === 'string' ? source.owner : '',
    tags: Array.isArray(tagsValue)
      ? tagsValue.map((item) => String(item)).join(', ')
      : typeof tagsValue === 'string'
        ? tagsValue
        : '',
    timeout_ms: source.timeout_ms === undefined || source.timeout_ms === null ? '' : String(source.timeout_ms),
    metadata_extra_json: JSON.stringify(extras, null, 2),
  };
}

function buildMetadataPayload(values: StructuredMetadataForm): Record<string, unknown> {
  const payload = parseJsonField(values.metadata_extra_json, '扩展元数据 JSON') as Record<string, unknown>;
  if (values.category.trim()) payload.category = values.category.trim();
  if (values.precondition.trim()) payload.precondition = values.precondition.trim();
  if (values.priority.trim()) payload.priority = values.priority.trim();
  if (values.owner.trim()) payload.owner = values.owner.trim();
  if (values.tags.trim()) payload.tags = values.tags.split(',').map((tag) => tag.trim()).filter(Boolean);
  if (values.timeout_ms.trim()) {
    const parsedTimeout = Number(values.timeout_ms.trim());
    if (!Number.isFinite(parsedTimeout) || parsedTimeout < 0) {
      throw new Error('超时时间必须是非负数字。');
    }
    payload.timeout_ms = parsedTimeout;
  }
  return payload;
}

function assertionRowsFromCase(apiCase: ApiCase): AssertionEditorRow[] {
  return (apiCase.assertions_json ?? []).map((item, index) => ({
    key: `${apiCase.id}-assertion-${index}`,
    type: String(item.type ?? 'status_code'),
    operator: String(item.operator ?? '=='),
    path: String(item.path ?? ''),
    header: String(item.header ?? item.target ?? ''),
    expected: item.expected === undefined ? '' : String(item.expected),
    enabled: item.enabled !== false,
  }));
}

function processorRowsFromCase(processors: Record<string, unknown>[], prefix: string): ProcessorEditorRow[] {
  return (processors ?? []).map((item, index) => ({
    key: `${prefix}-${index}`,
    type: String(item.type ?? 'set_variable'),
    enabled: item.enabled !== false,
    configText: stringifyJson(item.config ?? {}, '{}'),
    language: String(item.language ?? 'js'),
    code: String(item.code ?? ''),
  }));
}

function assertionRowsToPayload(rows: AssertionEditorRow[]) {
  return rows.map((row) => {
    const payload: Record<string, unknown> = {
      type: row.type,
      operator: row.operator,
      expected: parseLooseValue(row.expected),
      enabled: row.enabled,
    };
    if (row.type === 'json_path' && row.path) payload.path = row.path;
    if (row.type === 'header' && row.header) payload.header = row.header;
    return payload;
  });
}

function processorRowsToPayload(rows: ProcessorEditorRow[]) {
  return rows.map((row) => {
    if (row.type === 'script') {
      return { type: row.type, enabled: row.enabled, language: row.language || 'js', code: row.code, config: {} };
    }
    return { type: row.type, enabled: row.enabled, config: parseJsonField(row.configText, '处理器配置') };
  });
}

export function WorkspacePage() {
  const { token, user } = useAuth();
  const api = useMemo(() => createApi(token), [token]);
  const { message } = App.useApp();
  const canEdit = canManageWorkspace(user);
  const [projects, setProjects] = useState<Project[]>([]);
  const [suites, setSuites] = useState<Suite[]>([]);
  const [cases, setCases] = useState<ApiCase[]>([]);
  const [editingProjectId, setEditingProjectId] = useState<number | null>(null);
  const [editingSuiteId, setEditingSuiteId] = useState<number | null>(null);
  const [editingCaseId, setEditingCaseId] = useState<number | null>(null);
  const [importProjectId, setImportProjectId] = useState<number | null>(null);
  const [importFileList, setImportFileList] = useState<UploadFile[]>([]);
  const [legacyImportProjectId, setLegacyImportProjectId] = useState<number | null>(null);
  const [legacyImportFileList, setLegacyImportFileList] = useState<UploadFile[]>([]);
  const [headerRows, setHeaderRows] = useState<KeyValueEditorRow[]>([]);
  const [bodyMode, setBodyMode] = useState<'structured' | 'raw'>('structured');
  const [bodyRows, setBodyRows] = useState<KeyValueEditorRow[]>([]);
  const [assertionRows, setAssertionRows] = useState<AssertionEditorRow[]>([]);
  const [preProcessorRows, setPreProcessorRows] = useState<ProcessorEditorRow[]>([]);
  const [postProcessorRows, setPostProcessorRows] = useState<ProcessorEditorRow[]>([]);
  const [projectForm] = Form.useForm<{ name: string; description: string }>();
  const [suiteForm] = Form.useForm<{ project_id: number; name: string; description: string }>();
  const [caseForm] = Form.useForm<{
    suite_id: number;
    name: string;
    method: string;
    url: string;
    description: string;
    body_json: string;
    category: string;
    precondition: string;
    priority: string;
    owner: string;
    tags: string;
    timeout_ms: string;
    metadata_extra_json: string;
  }>();

  async function refresh() {
    const [nextProjects, nextSuites, nextCases] = await Promise.all([api.listProjects(), api.listSuites(), api.listCases()]);
    setProjects(nextProjects);
    setSuites(nextSuites);
    setCases(nextCases);
  }

  useEffect(() => {
    void refresh();
  }, [api]);

  function resetProjectForm() {
    setEditingProjectId(null);
    projectForm.resetFields();
  }

  function resetSuiteForm() {
    setEditingSuiteId(null);
    suiteForm.resetFields();
  }

  function resetCaseForm() {
    setEditingCaseId(null);
    caseForm.setFieldsValue({
      method: 'GET',
      body_json: '{}',
      description: '',
      category: '',
      precondition: '',
      priority: '',
      owner: '',
      tags: '',
      timeout_ms: '',
      metadata_extra_json: '{}',
    });
    setHeaderRows([]);
    setBodyMode('structured');
    setBodyRows([]);
    setAssertionRows([]);
    setPreProcessorRows([]);
    setPostProcessorRows([]);
  }

  useEffect(() => {
    resetCaseForm();
  }, []);

  async function submitProject(values: { name: string; description: string }) {
    if (editingProjectId === null) {
      await api.createProject(values);
      message.success('项目已创建。');
    } else {
      await api.updateProject(editingProjectId, values);
      message.success('项目已更新。');
    }
    resetProjectForm();
    await refresh();
  }

  async function submitSuite(values: { project_id: number; name: string; description: string }) {
    if (editingSuiteId === null) {
      await api.createSuite(values);
      message.success('套件已创建。');
    } else {
      await api.updateSuite(editingSuiteId, values);
      message.success('套件已更新。');
    }
    resetSuiteForm();
    await refresh();
  }

  async function submitCase(values: {
    suite_id: number;
    name: string;
    method: string;
    url: string;
    description: string;
    body_json: string;
    category: string;
    precondition: string;
    priority: string;
    owner: string;
    tags: string;
    timeout_ms: string;
    metadata_extra_json: string;
  }) {
    const payload = {
      suite_id: values.suite_id,
      name: values.name,
      method: values.method,
      url: values.url,
      description: values.description,
      headers_json: rowsToHeaderMap(headerRows),
      body_json: bodyMode === 'structured' ? rowsToObjectPayload(bodyRows) : parseJsonField(values.body_json, '请求体 JSON'),
      assertions_json: assertionRowsToPayload(assertionRows),
      pre_processors_json: processorRowsToPayload(preProcessorRows),
      post_processors_json: processorRowsToPayload(postProcessorRows),
      metadata_json: buildMetadataPayload(values),
    };
    if (editingCaseId === null) {
      await api.createCase(payload);
      message.success('用例已创建。');
    } else {
      await api.updateCase(editingCaseId, payload);
      message.success('用例已更新。');
    }
    resetCaseForm();
    await refresh();
  }

  async function handleExcelImport() {
    if (!importProjectId || importFileList.length === 0 || !importFileList[0].originFileObj) {
      message.warning('请先选择目标项目和 Excel 文件。');
      return;
    }
    const result = await api.importExcel(importProjectId, importFileList[0].originFileObj);
    message.success(`已导入 ${result.created_cases} 条用例到套件 ${result.suite_name}。`);
    setImportFileList([]);
    await refresh();
  }

  async function handleLegacyProjectImport() {
    if (!legacyImportProjectId || legacyImportFileList.length === 0 || !legacyImportFileList[0].originFileObj) {
      message.warning('请先选择目标项目和桌面端 project.json 文件。');
      return;
    }
    const result = await api.importLegacyProject(legacyImportProjectId, legacyImportFileList[0].originFileObj);
    message.success(
      `已导入 ${result.created_suites} 个套件、${result.created_cases} 条用例、${result.created_environments} 个环境和 ${result.created_executions} 条执行记录。`,
    );
    setLegacyImportFileList([]);
    await refresh();
  }

  function loadCaseIntoEditor(apiCase: ApiCase) {
    const caseBodyText = stringifyJson(apiCase.body_json, '{}');
    const caseBodyMode = isPlainObject(apiCase.body_json) ? 'structured' : 'raw';
    const metadataFields = splitMetadata(apiCase.metadata_json);
    setEditingCaseId(apiCase.id);
    caseForm.setFieldsValue({
      suite_id: apiCase.suite_id,
      name: apiCase.name,
      method: apiCase.method,
      url: apiCase.url,
      description: apiCase.description,
      body_json: caseBodyText,
      category: metadataFields.category,
      precondition: metadataFields.precondition,
      priority: metadataFields.priority,
      owner: metadataFields.owner,
      tags: metadataFields.tags,
      timeout_ms: metadataFields.timeout_ms,
      metadata_extra_json: metadataFields.metadata_extra_json,
    });
    setHeaderRows(mapToRows(apiCase.headers_json, `headers-${apiCase.id}`));
    setBodyMode(caseBodyMode);
    setBodyRows(caseBodyMode === 'structured' && isPlainObject(apiCase.body_json) ? mapToRows(apiCase.body_json, `body-${apiCase.id}`) : []);
    setAssertionRows(assertionRowsFromCase(apiCase));
    setPreProcessorRows(processorRowsFromCase(apiCase.pre_processors_json, `pre-${apiCase.id}`));
    setPostProcessorRows(processorRowsFromCase(apiCase.post_processors_json, `post-${apiCase.id}`));
  }

  function handleBodyModeChange(nextMode: string) {
    if (nextMode === bodyMode) return;
    if (nextMode === 'raw') {
      caseForm.setFieldValue('body_json', JSON.stringify(rowsToObjectPayload(bodyRows), null, 2));
      setBodyMode('raw');
      return;
    }

    const rawBodyText = String(caseForm.getFieldValue('body_json') ?? '').trim();
    if (!rawBodyText) {
      setBodyRows([]);
      setBodyMode('structured');
      caseForm.setFieldValue('body_json', '{}');
      return;
    }

    try {
      const parsedBody = JSON.parse(rawBodyText);
      if (!isPlainObject(parsedBody)) {
        message.warning('结构化请求体只支持 JSON 对象。');
        return;
      }
      setBodyRows(mapToRows(parsedBody, `body-${editingCaseId ?? 'new'}`));
      setBodyMode('structured');
    } catch {
      message.warning('切换到结构化模式前，请先保证原始请求体是合法 JSON。');
    }
  }

  return (
    <div className="page-stack">
      <div className="page-hero">
        <Typography.Title>工作台</Typography.Title>
        <Typography.Paragraph>
          断言与处理器已经支持结构化编辑。开发可以查看资产，测试与管理员可以直接维护项目、套件和用例。
        </Typography.Paragraph>
      </div>

      <Tabs
        items={[
          {
            key: 'projects',
            label: '项目',
            children: (
              <Row gutter={[18, 18]}>
                <Col span={8}>
                  <Card className="glass-card" title={editingProjectId ? '编辑项目' : '新建项目'}>
                    <Form form={projectForm} layout="vertical" onFinish={(values) => void submitProject(values)} disabled={!canEdit}>
                      <Form.Item name="name" label="名称" rules={[{ required: true }]}>
                        <Input />
                      </Form.Item>
                      <Form.Item name="description" label="描述">
                        <Input.TextArea rows={4} />
                      </Form.Item>
                      <Space>
                        <Button type="primary" htmlType="submit" disabled={!canEdit}>
                          {editingProjectId ? '保存' : '创建'}
                        </Button>
                        <Button onClick={resetProjectForm}>重置</Button>
                      </Space>
                    </Form>
                  </Card>
                </Col>

                <Col span={16}>
                  <Card className="glass-card" title="项目列表">
                    <Table<Project>
                      rowKey="id"
                      pagination={false}
                      dataSource={projects}
                      columns={[
                        { title: '项目', dataIndex: 'name' },
                        { title: '描述', dataIndex: 'description' },
                        { title: '套件数', render: (_, project) => project.suites.length },
                        { title: '环境数', render: (_, project) => project.environments.length },
                        {
                          title: '操作',
                          render: (_, project) => (
                            <Space>
                              <Button
                                size="small"
                                disabled={!canEdit}
                                onClick={() => {
                                  setEditingProjectId(project.id);
                                  projectForm.setFieldsValue({ name: project.name, description: project.description });
                                }}
                              >
                                编辑
                              </Button>
                              <Popconfirm title="确认删除项目？" disabled={!canEdit} onConfirm={() => void api.deleteProject(project.id).then(refresh)}>
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
            ),
          },
          {
            key: 'suites',
            label: '套件',
            children: (
              <Row gutter={[18, 18]}>
                <Col span={8}>
                  <Space direction="vertical" style={{ width: '100%' }} size="large">
                    <Card className="glass-card" title={editingSuiteId ? '编辑套件' : '新建套件'}>
                      <Form form={suiteForm} layout="vertical" onFinish={(values) => void submitSuite(values)} disabled={!canEdit}>
                        <Form.Item name="project_id" label="所属项目" rules={[{ required: true }]}>
                          <Select options={projects.map((project) => ({ value: project.id, label: project.name }))} />
                        </Form.Item>
                        <Form.Item name="name" label="名称" rules={[{ required: true }]}>
                          <Input />
                        </Form.Item>
                        <Form.Item name="description" label="描述">
                          <Input.TextArea rows={4} />
                        </Form.Item>
                        <Space>
                          <Button type="primary" htmlType="submit" disabled={!canEdit}>
                            {editingSuiteId ? '保存' : '创建'}
                          </Button>
                          <Button onClick={resetSuiteForm}>重置</Button>
                        </Space>
                      </Form>
                    </Card>

                    <Card className="glass-card" title="导入 Excel">
                      <Space direction="vertical" style={{ width: '100%' }}>
                        <Select
                          placeholder="选择目标项目"
                          value={importProjectId ?? undefined}
                          onChange={setImportProjectId}
                          options={projects.map((project) => ({ value: project.id, label: project.name }))}
                          disabled={!canEdit}
                        />
                        <Upload
                          beforeUpload={() => false}
                          maxCount={1}
                          fileList={importFileList}
                          onChange={({ fileList }) => setImportFileList(fileList)}
                          disabled={!canEdit}
                        >
                          <Button disabled={!canEdit}>选择 Excel</Button>
                        </Upload>
                        <Button type="primary" onClick={() => void handleExcelImport()} disabled={!canEdit}>
                          开始导入
                        </Button>
                      </Space>
                    </Card>

                    <Card className="glass-card" title="导入桌面端项目">
                      <Space direction="vertical" style={{ width: '100%' }}>
                        <Typography.Text type="secondary">
                          将旧版桌面端 `project.json` 树导入当前 Web 项目，加速桌面端资产迁移。
                        </Typography.Text>
                        <Select
                          placeholder="选择目标项目"
                          value={legacyImportProjectId ?? undefined}
                          onChange={setLegacyImportProjectId}
                          options={projects.map((project) => ({ value: project.id, label: project.name }))}
                          disabled={!canEdit}
                        />
                        <Upload
                          beforeUpload={() => false}
                          maxCount={1}
                          fileList={legacyImportFileList}
                          onChange={({ fileList }) => setLegacyImportFileList(fileList)}
                          disabled={!canEdit}
                        >
                          <Button disabled={!canEdit}>选择 project.json</Button>
                        </Upload>
                        <Button type="primary" onClick={() => void handleLegacyProjectImport()} disabled={!canEdit}>
                          开始导入
                        </Button>
                      </Space>
                    </Card>
                  </Space>
                </Col>

                <Col span={16}>
                  <Card className="glass-card" title="套件列表">
                    <Table<Suite>
                      rowKey="id"
                      pagination={false}
                      dataSource={suites}
                      columns={[
                        { title: '套件', dataIndex: 'name' },
                        { title: '项目 ID', dataIndex: 'project_id' },
                        { title: '描述', dataIndex: 'description' },
                        { title: '用例数', render: (_, suite) => suite.cases.length },
                        {
                          title: '操作',
                          render: (_, suite) => (
                            <Space>
                              <Button
                                size="small"
                                disabled={!canEdit}
                                onClick={() => {
                                  setEditingSuiteId(suite.id);
                                  suiteForm.setFieldsValue({ project_id: suite.project_id, name: suite.name, description: suite.description });
                                }}
                              >
                                编辑
                              </Button>
                              <Popconfirm title="确认删除套件？" disabled={!canEdit} onConfirm={() => void api.deleteSuite(suite.id).then(refresh)}>
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
            ),
          },
          {
            key: 'cases',
            label: '用例',
            children: (
              <Row gutter={[18, 18]}>
                <Col span={11}>
                  <Card className="glass-card" title={editingCaseId ? '编辑用例' : '新建用例'}>
                    <Form form={caseForm} layout="vertical" onFinish={(values) => void submitCase(values)} disabled={!canEdit}>
                      <Form.Item name="suite_id" label="所属套件" rules={[{ required: true }]}>
                        <Select options={suites.map((suite) => ({ value: suite.id, label: suite.name }))} />
                      </Form.Item>
                      <Form.Item name="name" label="名称" rules={[{ required: true }]}>
                        <Input />
                      </Form.Item>
                      <Space.Compact block>
                        <Form.Item name="method" label="请求方法" initialValue="GET" style={{ width: 160 }}>
                          <Select options={['GET', 'POST', 'PUT', 'DELETE'].map((method) => ({ value: method, label: method }))} />
                        </Form.Item>
                        <Form.Item name="url" label="URL" rules={[{ required: true }]} style={{ flex: 1 }}>
                          <Input placeholder="/api/demo" />
                        </Form.Item>
                      </Space.Compact>
                      <Form.Item name="description" label="描述">
                        <Input.TextArea rows={2} />
                      </Form.Item>
                      <Form.Item label="请求头">
                        <KeyValueEditor
                          rows={headerRows}
                          onChange={setHeaderRows}
                          disabled={!canEdit}
                          addLabel="新增请求头"
                          keyPlaceholder="Content-Type"
                          valuePlaceholder="application/json"
                        />
                      </Form.Item>
                      <Form.Item label="请求体">
                        <Space direction="vertical" style={{ width: '100%' }}>
                          <Segmented
                            value={bodyMode}
                            onChange={(value) => handleBodyModeChange(String(value))}
                            options={[
                              { label: '结构化对象', value: 'structured' },
                              { label: '原始 JSON', value: 'raw' },
                            ]}
                            disabled={!canEdit}
                          />
                          {bodyMode === 'structured' ? (
                            <KeyValueEditor
                              rows={bodyRows}
                              onChange={setBodyRows}
                              disabled={!canEdit}
                              addLabel="新增字段"
                              keyPlaceholder="name"
                              valuePlaceholder={'123、true 或 "text"'}
                            />
                          ) : (
                            <Form.Item name="body_json" noStyle>
                              <Input.TextArea rows={6} spellCheck={false} />
                            </Form.Item>
                          )}
                          {bodyMode === 'structured' ? (
                            <Typography.Text type="secondary">
                              值支持 number、boolean、array、object，按 JSON 字面量输入即可。
                            </Typography.Text>
                          ) : null}
                        </Space>
                      </Form.Item>
                      <Form.Item label="断言">
                        <AssertionEditor rows={assertionRows} onChange={setAssertionRows} disabled={!canEdit} />
                      </Form.Item>
                      <Form.Item label="前置处理器">
                        <ProcessorEditor title="前置处理器" rows={preProcessorRows} onChange={setPreProcessorRows} disabled={!canEdit} />
                      </Form.Item>
                      <Form.Item label="后置处理器">
                        <ProcessorEditor title="后置处理器" rows={postProcessorRows} onChange={setPostProcessorRows} disabled={!canEdit} />
                      </Form.Item>
                      <Form.Item label="元数据">
                        <Space direction="vertical" style={{ width: '100%' }}>
                          <Row gutter={12}>
                            <Col span={12}>
                              <Form.Item name="category" label="分类">
                                <Input placeholder="auth" />
                              </Form.Item>
                            </Col>
                            <Col span={12}>
                              <Form.Item name="priority" label="优先级">
                                <Select allowClear options={[{ value: 'P0', label: 'P0' }, { value: 'P1', label: 'P1' }, { value: 'P2', label: 'P2' }, { value: 'P3', label: 'P3' }]} />
                              </Form.Item>
                            </Col>
                          </Row>
                          <Row gutter={12}>
                            <Col span={12}>
                              <Form.Item name="owner" label="负责人">
                                <Input placeholder="qa-owner" />
                              </Form.Item>
                            </Col>
                            <Col span={12}>
                              <Form.Item name="timeout_ms" label="超时 (ms)">
                                <Input placeholder="5000" />
                              </Form.Item>
                            </Col>
                          </Row>
                          <Form.Item name="tags" label="标签">
                            <Input placeholder="smoke, login, regression" />
                          </Form.Item>
                          <Form.Item name="precondition" label="前置条件">
                            <Input.TextArea rows={2} />
                          </Form.Item>
                          <Form.Item name="metadata_extra_json" label="扩展元数据 JSON">
                            <Input.TextArea rows={5} spellCheck={false} />
                          </Form.Item>
                          <Typography.Text type="secondary">
                            常用元数据已在上方建模；只有超出分类、优先级、负责人、标签、前置条件、超时范围的字段，才放到扩展 JSON。
                          </Typography.Text>
                        </Space>
                      </Form.Item>
                      <Space>
                        <Button type="primary" htmlType="submit" disabled={!canEdit}>
                          {editingCaseId ? '保存' : '创建'}
                        </Button>
                        <Button onClick={resetCaseForm}>重置</Button>
                      </Space>
                    </Form>
                  </Card>
                </Col>

                <Col span={13}>
                  <Card className="glass-card" title="用例列表">
                    <Table<ApiCase>
                      rowKey="id"
                      pagination={false}
                      dataSource={cases}
                      columns={[
                        { title: '用例', dataIndex: 'name' },
                        { title: '请求方法', dataIndex: 'method' },
                        { title: 'URL', dataIndex: 'url' },
                        { title: '断言数', render: (_, apiCase) => apiCase.assertions_json.length },
                        { title: '前置', render: (_, apiCase) => apiCase.pre_processors_json.length },
                        { title: '后置', render: (_, apiCase) => apiCase.post_processors_json.length },
                        {
                          title: '操作',
                          render: (_, apiCase) => (
                            <Space>
                              <Button size="small" onClick={() => loadCaseIntoEditor(apiCase)}>
                                {canEdit ? '编辑' : '查看'}
                              </Button>
                              <Popconfirm title="确认删除用例？" disabled={!canEdit} onConfirm={() => void api.deleteCase(apiCase.id).then(refresh)}>
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
            ),
          },
        ]}
      />
    </div>
  );
}
