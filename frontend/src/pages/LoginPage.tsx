import { Alert, Button, Card, Form, Input, Typography } from 'antd';
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
        <span className="brand-panel__eyebrow">测试控制台</span>
        <Typography.Title>登录 Eazy Test Web</Typography.Title>
        <Typography.Paragraph>
          请输入账号密码进入平台。安全基线收口后，默认弱口令将被禁用。
        </Typography.Paragraph>
        {error ? <Alert type="error" showIcon message={error} style={{ marginBottom: 16 }} /> : null}
        <Form layout="vertical" onFinish={(values) => void handleFinish(values)}>
          <Form.Item label="用户名" name="username" rules={[{ required: true, message: '请输入用户名。' }]}>
            <Input placeholder="admin" />
          </Form.Item>
          <Form.Item label="密码" name="password" rules={[{ required: true, message: '请输入密码。' }]}>
            <Input.Password placeholder="请输入密码" />
          </Form.Item>
          <Button type="primary" htmlType="submit" block loading={pending}>
            登录
          </Button>
        </Form>
      </Card>
    </div>
  );
}
