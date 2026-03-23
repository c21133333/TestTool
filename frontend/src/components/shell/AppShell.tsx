import {
  ApiOutlined,
  DashboardOutlined,
  EnvironmentOutlined,
  FileSearchOutlined,
  PlayCircleOutlined,
  TeamOutlined,
  SafetyCertificateOutlined,
} from '@ant-design/icons';
import { Button, Layout, Menu, Space, Tag, Typography } from 'antd';
import { Link, Outlet, useLocation } from 'react-router-dom';

import { useAuth } from '../../auth/AuthContext';
import { canManageUsers, canViewAuditLogs } from '../../auth/permissions';

const { Header, Content, Sider } = Layout;

export function AppShell() {
  const { pathname } = useLocation();
  const { user, logout } = useAuth();
  const items = [
    { key: '/', icon: <DashboardOutlined />, label: <Link to="/">总览</Link> },
    { key: '/workspace', icon: <ApiOutlined />, label: <Link to="/workspace">工作区</Link> },
    { key: '/environments', icon: <EnvironmentOutlined />, label: <Link to="/environments">环境</Link> },
    { key: '/executions', icon: <PlayCircleOutlined />, label: <Link to="/executions">执行记录</Link> },
    { key: '/reports', icon: <FileSearchOutlined />, label: <Link to="/reports">报告</Link> },
    ...(canViewAuditLogs(user)
      ? [{ key: '/audit-logs', icon: <SafetyCertificateOutlined />, label: <Link to="/audit-logs">审计日志</Link> }]
      : []),
    ...(canManageUsers(user)
      ? [{ key: '/users', icon: <TeamOutlined />, label: <Link to="/users">用户</Link> }]
      : []),
  ];

  return (
    <Layout className="app-shell">
      <Sider width={248} className="app-shell__sider">
        <div className="brand-panel">
          <span className="brand-panel__eyebrow">接口测试平台</span>
          <Typography.Title level={3}>Eazy Test Web</Typography.Title>
          <Typography.Paragraph>
            从桌面客户端迁移而来的 Web 测试平台，面向团队共享执行与协作。
          </Typography.Paragraph>
        </div>
        <Menu theme="dark" mode="inline" selectedKeys={[pathname]} items={items} />
      </Sider>
      <Layout>
        <Header className="app-shell__header">
          <Space size="middle">
            <Tag color="processing">{user?.role}</Tag>
            <Typography.Text>{user?.display_name}</Typography.Text>
            <Button type="primary" ghost onClick={() => void logout()}>退出登录</Button>
          </Space>
        </Header>
        <Content className="app-shell__content">
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
