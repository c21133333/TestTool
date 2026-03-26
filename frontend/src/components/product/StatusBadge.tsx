import { Tag } from 'antd';

import type { StatusTone } from '../../utils/status';

type StatusBadgeProps = {
  label: string;
  tone: StatusTone;
};

export function StatusBadge({ label, tone }: StatusBadgeProps) {
  return <Tag className={`status-badge status-badge--${tone}`}>{label}</Tag>;
}
