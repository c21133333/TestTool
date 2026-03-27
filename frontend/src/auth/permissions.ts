import type { User } from '../api/types';

export function canManageWorkspace(user: User | null): boolean {
  return user?.role === 'admin' || user?.role === 'tester';
}

export function canManageExecutions(user: User | null): boolean {
  return user?.role === 'admin' || user?.role === 'tester';
}

export function canManageSchedules(user: User | null): boolean {
  return user?.role === 'admin' || user?.role === 'tester';
}

export function canManageUsers(user: User | null): boolean {
  return user?.role === 'admin';
}

export function canViewAuditLogs(user: User | null): boolean {
  return user?.role === 'admin';
}
