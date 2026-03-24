import { Alert, Button, Card, Form, Input, Space, Tag, Typography } from 'antd';
import { useState } from 'react';

import { useAuth } from '../auth/AuthContext';

export function LoginPage() {
  const { login } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function handleFinish(values: { username: string; password: string }) {
    setPending(true);
    setError(null);
    try {
      await login(values.username, values.password);
    } catch (err) {
      setError(err instanceof Error ? err.message : '登录失败。');
    } finally {
      setPending(false);
    }
  }

  return (
    <div className="login-screen">
      <Card className="login-card" bordered={false}>
        <Space direction="vertical" size="large" style={{ width: '100%' }}>
          <div>
            <span className="brand-panel__eyebrow">安全访问</span>
            <Typography.Title>登录 Eazy Test Web</Typography.Title>
            <Typography.Paragraph>
              进入共享测试工作台，统一查看资产、执行、报告与审计记录。
            </Typography.Paragraph>
            <Space wrap>
              <Tag color="processing">标准化部署</Tag>
              <Tag color="success">统一错误模型</Tag>
              <Tag color="warning">已接入可观测性</Tag>
            </Space>
          </div>

          <div className="login-card__notice">
            <Typography.Text strong>登录前须知</Typography.Text>
            <Typography.Paragraph type="secondary">
              生产环境快捷初始化和弱默认凭证均已禁用，请使用已初始化完成的账号登录。
            </Typography.Paragraph>
          </div>

          {error ? <Alert type="error" showIcon message={error} /> : null}

          <Form layout="vertical" onFinish={(values) => void handleFinish(values)}>
            <Form.Item label="用户名" name="username" rules={[{ required: true, message: '请输入用户名。' }]}>
              <Input placeholder="admin" autoComplete="username" />
            </Form.Item>
            <Form.Item label="密码" name="password" rules={[{ required: true, message: '请输入密码。' }]}>
              <Input.Password placeholder="请输入密码" autoComplete="current-password" />
            </Form.Item>
            <Button type="primary" htmlType="submit" block loading={pending} size="large">
              登录
            </Button>
          </Form>
        </Space>
      </Card>
    </div>
  );
}
