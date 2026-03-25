import { Alert, Space } from 'antd';

type Props = {
  warnings: string[];
  type?: 'info' | 'warning';
};

export function AiWarningList({ warnings, type = 'warning' }: Props) {
  if (!warnings.length) {
    return null;
  }

  return (
    <Space direction="vertical" style={{ width: '100%' }}>
      {warnings.map((warning, index) => (
        <Alert key={`${type}-${index}-${warning}`} type={type} showIcon message={warning} />
      ))}
    </Space>
  );
}
