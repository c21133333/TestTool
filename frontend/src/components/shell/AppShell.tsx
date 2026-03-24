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
  subtitle: string;
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
    { key: '/', icon: <DashboardOutlined />, label: '概览', subtitle: '平台健康、活动态势与交付快照' },
    { key: '/workspace', icon: <ApiOutlined />, label: '工作台', subtitle: '项目、套件、用例与迁移导入' },
    { key: '/environments', icon: <EnvironmentOutlined />, label: '环境', subtitle: '基础 URL、请求头与变量配置' },
    { key: '/executions', icon: <PlayCircleOutlined />, label: '执行', subtitle: '发起执行并定位失败信号' },
    { key: '/reports', icon: <FileSearchOutlined />, label: '报告', subtitle: '预览 HTML 与 JSON 执行报告' },
    ...(canViewAuditLogs(user)
      ? [{ key: '/audit-logs', icon: <SafetyCertificateOutlined />, label: '审计日志', subtitle: '跟踪高权限操作与变更留痕' }]
      : []),
    ...(canManageUsers(user)
      ? [{ key: '/users', icon: <TeamOutlined />, label: '用户管理', subtitle: '维护账号状态、角色与访问边界' }]
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
          {!collapsed ? (
            <>
              <Typography.Paragraph>
                用一个界面统一管理测试资产、执行过程和报告回看。
              </Typography.Paragraph>
              <Space wrap>
                <Tag color="processing">V1 路线图</Tag>
                <Tag color="orange">Web 优先</Tag>
              </Space>
            </>
          ) : null}
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
              <Typography.Text className="app-shell__section-eyebrow">当前模块</Typography.Text>
              <Typography.Title level={4}>{activeItem.label}</Typography.Title>
              <Typography.Text type="secondary">{activeItem.subtitle}</Typography.Text>
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
