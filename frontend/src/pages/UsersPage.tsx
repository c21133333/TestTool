import { Alert, Button, Card, Col, Form, Input, Row, Select, Space, Table, Typography } from 'antd';
import { useEffect, useMemo, useState } from 'react';

import { createApi } from '../api/services';
import type { User } from '../api/types';
import { useAuth } from '../auth/AuthContext';
import { PageHero } from '../components/product/PageHero';

function roleLabel(role: User['role']) {
  if (role === 'admin') return '管理员';
  if (role === 'tester') return '测试';
  return '开发';
}

export function UsersPage() {
  const { token, user } = useAuth();
  const api = useMemo(() => createApi(token), [token]);
  const [users, setUsers] = useState<User[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    try {
      setError(null);
      setUsers(await api.listUsers());
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载用户列表失败。');
    }
  }

  useEffect(() => {
    void refresh();
  }, [api]);

  const adminCount = users.filter((item) => item.role === 'admin').length;
  const testerCount = users.filter((item) => item.role === 'tester').length;
  const activeCount = users.filter((item) => item.is_active).length;
  const canManage = user?.role === 'admin';

  return (
    <div className="page-stack">
      <PageHero
        eyebrow="GOV / ACCESS"
        title="用户管理"
        description="统一维护平台账号、角色分布和启用状态，确保质量平台的访问边界清晰可控。"
        tags={[
          <span key="total" className="lab-chip">
            {users.length} 个账号
          </span>,
          <span key="active" className="lab-chip">
            {activeCount} 个启用
          </span>,
          <span key="access" className="lab-chip">
            {canManage ? '管理员可写' : '仅可查看'}
          </span>,
        ]}
        actions={
          <Space wrap>
            <Button onClick={() => void refresh()}>刷新</Button>
          </Space>
        }
      />

      {error ? <Alert type="warning" message={error} showIcon /> : null}

      <div className="dashboard-kpi-grid">
        <Card className="metric-card dashboard-kpi-card dashboard-kpi-card--primary" bordered={false}>
          <span className="dashboard-kpi-card__code">USR-01</span>
          <Typography.Text className="workspace-summary-card__label">账号总数</Typography.Text>
          <Typography.Title level={2}>{users.length}</Typography.Title>
          <Typography.Paragraph>当前平台已登记的账号数量</Typography.Paragraph>
        </Card>
        <Card className="metric-card dashboard-kpi-card dashboard-kpi-card--signal" bordered={false}>
          <span className="dashboard-kpi-card__code">ADM-02</span>
          <Typography.Text className="workspace-summary-card__label">管理员</Typography.Text>
          <Typography.Title level={2}>{adminCount}</Typography.Title>
          <Typography.Paragraph>具备治理权限的账号数量</Typography.Paragraph>
        </Card>
        <Card className="metric-card dashboard-kpi-card dashboard-kpi-card--success" bordered={false}>
          <span className="dashboard-kpi-card__code">QAE-03</span>
          <Typography.Text className="workspace-summary-card__label">测试角色</Typography.Text>
          <Typography.Title level={2}>{testerCount}</Typography.Title>
          <Typography.Paragraph>主要承担执行与配置工作的账号</Typography.Paragraph>
        </Card>
        <Card className="metric-card dashboard-kpi-card dashboard-kpi-card--info" bordered={false}>
          <span className="dashboard-kpi-card__code">ACT-04</span>
          <Typography.Text className="workspace-summary-card__label">启用状态</Typography.Text>
          <Typography.Title level={2}>{activeCount}</Typography.Title>
          <Typography.Paragraph>当前可登录的平台账号数量</Typography.Paragraph>
        </Card>
      </div>

      <Row gutter={[18, 18]}>
        <Col xs={24} xl={8}>
          <Card className="glass-card workspace-section-card" title="新增账号">
            <Form layout="vertical" onFinish={(values) => void api.createUser(values).then(refresh)} disabled={!canManage}>
              <Form.Item name="username" label="用户名" rules={[{ required: true, message: '请输入用户名。' }]}>
                <Input />
              </Form.Item>
              <Form.Item name="display_name" label="显示名称" rules={[{ required: true, message: '请输入显示名称。' }]}>
                <Input />
              </Form.Item>
              <Form.Item name="password" label="密码" rules={[{ required: true, message: '请输入密码。' }]}>
                <Input.Password />
              </Form.Item>
              <Form.Item name="role" label="角色" initialValue="tester" rules={[{ required: true, message: '请选择角色。' }]}>
                <Select
                  options={[
                    { value: 'admin', label: '管理员' },
                    { value: 'tester', label: '测试' },
                    { value: 'developer', label: '开发' },
                  ]}
                />
              </Form.Item>
              <Button type="primary" htmlType="submit">
                创建账号
              </Button>
            </Form>
          </Card>
        </Col>
        <Col xs={24} xl={16}>
          <Card className="glass-card workspace-section-card" title="账号清单">
            <Table
              rowKey="id"
              pagination={{ pageSize: 10, showSizeChanger: false, hideOnSinglePage: true }}
              dataSource={users}
              columns={[
                { title: '用户名', dataIndex: 'username' },
                { title: '显示名称', dataIndex: 'display_name' },
                { title: '角色', dataIndex: 'role', render: (value: User['role']) => roleLabel(value) },
                { title: '状态', render: (_, row) => (row.is_active ? '启用' : '停用') },
              ]}
            />
          </Card>
        </Col>
      </Row>
    </div>
  );
}
