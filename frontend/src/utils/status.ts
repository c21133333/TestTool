import type { Execution } from '../api/types';

export type StatusTone = 'success' | 'warning' | 'danger' | 'info' | 'neutral';

export function executionStatusMeta(status: Execution['status']): { label: string; tone: StatusTone } {
  if (status === 'pending') {
    return { label: '排队中', tone: 'warning' };
  }
  if (status === 'running') {
    return { label: '执行中', tone: 'info' };
  }
  if (status === 'success') {
    return { label: '成功', tone: 'success' };
  }
  return { label: '失败', tone: 'danger' };
}

export function executionItemStatusMeta(status: string): { label: string; tone: StatusTone } {
  if (status === 'PASS') {
    return { label: '通过', tone: 'success' };
  }
  if (status === 'SKIP') {
    return { label: '跳过', tone: 'warning' };
  }
  return { label: '失败', tone: 'danger' };
}

export function artifactStatusMeta(status: string | null | undefined): { label: string; tone: StatusTone } {
  if (status === 'applied') {
    return { label: '已应用', tone: 'success' };
  }
  if (status === 'accepted') {
    return { label: '已采纳', tone: 'success' };
  }
  if (status === 'draft') {
    return { label: '草稿', tone: 'info' };
  }
  if (status === 'superseded') {
    return { label: '已替代', tone: 'warning' };
  }
  if (status === 'rejected') {
    return { label: '已拒绝', tone: 'danger' };
  }
  return { label: status ? String(status) : '未知', tone: 'neutral' };
}
