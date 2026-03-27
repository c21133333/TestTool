import { Alert, Button, Card, Form, Input, Space, Typography } from 'antd';
import { useState } from 'react';

import { useAuth } from '../auth/AuthContext';

type LoginFormValues = {
  username: string;
  password: string;
};

function LoginSignalStage() {
  return (
    <div className="login-signal-stage" aria-hidden="true">
      <div className="login-signal-stage__grid" />
      <div className="login-signal-stage__core">
        <span className="login-signal-stage__ring login-signal-stage__ring--outer" />
        <span className="login-signal-stage__ring login-signal-stage__ring--mid" />
        <span className="login-signal-stage__ring login-signal-stage__ring--inner" />
        <span className="login-signal-stage__beam login-signal-stage__beam--one" />
        <span className="login-signal-stage__beam login-signal-stage__beam--two" />
        <span className="login-signal-stage__beam login-signal-stage__beam--three" />
        <span className="login-signal-stage__pulse login-signal-stage__pulse--one" />
        <span className="login-signal-stage__pulse login-signal-stage__pulse--two" />
        <span className="login-signal-stage__node login-signal-stage__node--one" />
        <span className="login-signal-stage__node login-signal-stage__node--two" />
        <span className="login-signal-stage__node login-signal-stage__node--three" />
        <span className="login-signal-stage__label">QA SIGNAL</span>
      </div>
      <div className="login-signal-stage__status">
        <span className="login-signal-stage__status-dot" />
        <Typography.Text>登录后进入统一测试指挥台</Typography.Text>
      </div>
    </div>
  );
}

export function LoginPage() {
  const { login } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function handleFinish(values: LoginFormValues) {
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
      <div className="login-screen__grid">
        <section className="login-screen__aside login-screen__aside--compact">
          <span className="login-screen__serial">CONTROL ACCESS / 01</span>
          <span className="brand-panel__eyebrow">质量指挥平台</span>
          <LoginSignalStage />
          <Typography.Title className="login-screen__title login-screen__title--compact">
            把 API 测试收进同一张工作台。
          </Typography.Title>
          <Typography.Paragraph className="login-screen__lead login-screen__lead--compact">
            用更清晰的资产管理、执行调度和结果归档，把测试协作收口成稳定日常。
          </Typography.Paragraph>
        </section>

        <Card className="login-card" bordered={false}>
          <Space direction="vertical" size="large" style={{ width: '100%' }}>
            <div>
              <span className="brand-panel__eyebrow">CONTROL ACCESS</span>
              <Typography.Title level={2}>登录 EazyTest</Typography.Title>
              <Typography.Paragraph>
                使用平台账号进入测试工作台。
              </Typography.Paragraph>
            </div>

            {error ? <Alert type="error" showIcon message={error} /> : null}

            <Form<LoginFormValues> layout="vertical" onFinish={(values) => void handleFinish(values)}>
              <Form.Item label="用户名" name="username" rules={[{ required: true, message: '请输入用户名。' }]}>
                <Input placeholder="admin" autoComplete="username" />
              </Form.Item>
              <Form.Item label="密码" name="password" rules={[{ required: true, message: '请输入密码。' }]}>
                <Input.Password placeholder="输入当前密码" autoComplete="current-password" />
              </Form.Item>
              <Button type="primary" htmlType="submit" block loading={pending} size="large">
                进入工作台
              </Button>
            </Form>

            <div className="login-card__notice login-card__notice--compact">
              <Typography.Text strong>首次接入提醒</Typography.Text>
              <Typography.Paragraph type="secondary">
                如当前环境刚完成部署，请先确认后端初始化已经结束，再执行登录。
              </Typography.Paragraph>
            </div>
          </Space>
        </Card>
      </div>
    </div>
  );
}
