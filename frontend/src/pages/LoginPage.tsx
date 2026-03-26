import { ApiOutlined, DeploymentUnitOutlined, SafetyCertificateOutlined } from '@ant-design/icons';
import { Alert, Button, Card, Form, Input, Space, Typography } from 'antd';
import { useState } from 'react';

import { useAuth } from '../auth/AuthContext';

type LoginFormValues = {
  username: string;
  password: string;
};

const capabilityCards = [
  {
    title: '质量态势',
    description: '统一查看套件规模、执行覆盖和关键风险变化，首页就能看清测试状态。',
    icon: <ApiOutlined />,
  },
  {
    title: '执行调度',
    description: '集中管理环境、执行入口和准备动作，让操作链路保持一致且可控。',
    icon: <DeploymentUnitOutlined />,
  },
  {
    title: '归档追踪',
    description: '把报告产物、审计事件和 AI 辅助结果串成完整追踪链路。',
    icon: <SafetyCertificateOutlined />,
  },
];

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
        <section className="login-screen__aside">
          <span className="login-screen__serial">CONTROL ACCESS / 01</span>
          <span className="brand-panel__eyebrow">质量指挥平台</span>
          <Typography.Title className="login-screen__title">
            把 API 质量放进一个可观测、可追踪、可调度的指挥舱。
          </Typography.Title>
          <Typography.Paragraph className="login-screen__lead">
            EazyTest 将用例设计、执行调度、AI 准备能力和报告归档整合到同一套工作界面，适合测试团队稳定协作。
          </Typography.Paragraph>

          <div className="login-screen__chip-row">
            <span className="lab-chip">态势总览</span>
            <span className="lab-chip">执行调度</span>
            <span className="lab-chip">归档追踪</span>
          </div>

          <div className="login-screen__capabilities">
            {capabilityCards.map((card) => (
              <div key={card.title} className="login-screen__capability-card">
                <div className="login-screen__capability-icon">{card.icon}</div>
                <div>
                  <Typography.Text strong>{card.title}</Typography.Text>
                  <Typography.Paragraph>{card.description}</Typography.Paragraph>
                </div>
              </div>
            ))}
          </div>

          <div className="login-screen__protocol">
            <Typography.Text strong>访问说明</Typography.Text>
            <Typography.Paragraph>
              平台账号统一预置后开放访问，默认禁用弱口令和任何直接跳过初始化的捷径。
            </Typography.Paragraph>
          </div>
        </section>

        <Card className="login-card" bordered={false}>
          <Space direction="vertical" size="large" style={{ width: '100%' }}>
            <div>
              <span className="brand-panel__eyebrow">CONTROL ACCESS</span>
              <Typography.Title level={2}>登录 EazyTest</Typography.Title>
              <Typography.Paragraph>使用平台账号进入质量指挥舱，继续处理接口资产、执行任务和报告归档。</Typography.Paragraph>
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
                进入指挥舱
              </Button>
            </Form>

            <div className="login-card__notice">
              <Typography.Text strong>首次接入提醒</Typography.Text>
              <Typography.Paragraph type="secondary">
                如果当前环境刚完成部署，请先确认后端初始化已经结束，再执行登录。
              </Typography.Paragraph>
            </div>
          </Space>
        </Card>
      </div>
    </div>
  );
}
