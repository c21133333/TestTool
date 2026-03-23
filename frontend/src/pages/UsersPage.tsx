import { Alert, Button, Card, Col, Form, Input, Row, Select, Table, Typography } from 'antd';
import { useEffect, useState } from 'react';

import { createApi } from '../api/services';
import type { User } from '../api/types';
import { useAuth } from '../auth/AuthContext';

function roleLabel(role: User['role']) {
  if (role === 'admin') return '管理员';
  if (role === 'tester') return '测试';
  return '开发';
}

export function UsersPage() {
  const { token, user } = useAuth();
  const api = createApi(token);
  const [users, setUsers] = useState<User[]>([]);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    try {
      setError(null);
      setUsers(await api.listUsers());
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载用户失败。');
    }
  }

  useEffect(() => {
    void refresh();
  }, [token]);

  return (
    <div className="page-stack">
      <div className="page-hero">
        <Typography.Title>用户管理</Typography.Title>
        <Typography.Paragraph>当前系统采用 `admin / tester / developer` 三类角色的基础 RBAC 模型。</Typography.Paragraph>
      </div>
      {error ? <Alert type="warning" message={error} showIcon /> : null}
      <Row gutter={[18, 18]}>
        <Col span={8}>
          <Card className="glass-card" title="创建用户">
            <Form
              layout="vertical"
              onFinish={(values) => void api.createUser(values).then(refresh)}
              disabled={user?.role !== 'admin'}
            >
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
              <Button type="primary" htmlType="submit">创建用户</Button>
            </Form>
          </Card>
        </Col>
        <Col span={16}>
          <Card className="glass-card" title="用户列表">
            <Table
              rowKey="id"
              pagination={false}
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
