import {
  ApiOutlined,
  DashboardOutlined,
  EnvironmentOutlined,
  FileSearchOutlined,
  LogoutOutlined,
  MenuFoldOutlined,
  MenuUnfoldOutlined,
  PlayCircleOutlined,
  SafetyCertificateOutlined,
  TeamOutlined,
} from '@ant-design/icons';
import type { ReactNode } from 'react';
import { Button, Layout, Menu, Space, Tag, Typography } from 'antd';
import { useState } from 'react';
import { Link, Outlet, useLocation } from 'react-router-dom';

import { useAuth } from '../../auth/AuthContext';
import { canManageUsers, canViewAuditLogs } from '../../auth/permissions';

const { Header, Content, Sider } = Layout;

type NavigationItem = {
  key: string;
  icon: ReactNode;
  label: string;
};

const roleConfig = {
  admin: { label: '管理员', color: 'gold' },
  tester: { label: '测试', color: 'green' },
  developer: { label: '开发', color: 'blue' },
} as const;

export function AppShell() {
  const { pathname } = useLocation();
  const { user, logout } = useAuth();
  const [collapsed, setCollapsed] = useState(false);

  const navigationItems: NavigationItem[] = [
    { key: '/', icon: <DashboardOutlined />, label: '概览' },
    { key: '/workspace', icon: <ApiOutlined />, label: '工作台' },
    { key: '/environments', icon: <EnvironmentOutlined />, label: '环境' },
    { key: '/executions', icon: <PlayCircleOutlined />, label: '执行' },
    { key: '/reports', icon: <FileSearchOutlined />, label: '报告' },
    ...(canViewAuditLogs(user)
      ? [{ key: '/audit-logs', icon: <SafetyCertificateOutlined />, label: '审计日志' }]
      : []),
    ...(canManageUsers(user)
      ? [{ key: '/users', icon: <TeamOutlined />, label: '用户管理' }]
      : []),
  ];

  const activeItem =
    navigationItems.find((item) => item.key !== '/' && pathname.startsWith(item.key)) ??
    navigationItems.find((item) => item.key === pathname) ??
    navigationItems[0];

  const roleMeta = user ? roleConfig[user.role] : null;

  return (
    <Layout className="app-shell">
      <Sider
        width={272}
        collapsible
        collapsed={collapsed}
        onCollapse={setCollapsed}
        collapsedWidth={88}
        breakpoint="lg"
        className="app-shell__sider"
        trigger={null}
      >
        <div className="brand-panel">
          <span className="brand-panel__eyebrow">团队测试平台</span>
          <Typography.Title level={3}>Eazy Test Web</Typography.Title>
        </div>
        <Menu
          theme="light"
          mode="inline"
          className="app-shell__menu"
          selectedKeys={[activeItem.key]}
          items={navigationItems.map((item) => ({
            key: item.key,
            icon: item.icon,
            label: <Link to={item.key}>{item.label}</Link>,
          }))}
        />
      </Sider>
      <Layout>
        <Header className="app-shell__header">
          <div className="app-shell__header-main">
            <Button
              type="text"
              className="app-shell__nav-trigger"
              icon={collapsed ? <MenuUnfoldOutlined /> : <MenuFoldOutlined />}
              onClick={() => setCollapsed((current) => !current)}
            />
            <div className="app-shell__section-meta">
              <Typography.Title level={4}>{activeItem.label}</Typography.Title>
            </div>
          </div>
          <Space size="middle" className="app-shell__header-side">
            {roleMeta ? <Tag color={roleMeta.color} className="app-shell__role-tag">{roleMeta.label}</Tag> : null}
            <div className="app-shell__user-meta">
              <Typography.Text>{user?.display_name}</Typography.Text>
              <Typography.Text type="secondary">{user?.username}</Typography.Text>
            </div>
            <Button type="primary" className="app-shell__logout" icon={<LogoutOutlined />} onClick={() => void logout()}>
              退出登录
            </Button>
          </Space>
        </Header>
        <Content className="app-shell__content">
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  );
}
