import { Alert } from 'antd';

type Props = {
  warnings: string[];
  type?: 'info' | 'warning';
};

function normalizeWarningKey(value: string): string {
  return value.replace(/[。！？；\s]+$/u, '').trim();
}

export function AiWarningList({ warnings, type = 'warning' }: Props) {
  const uniqueWarnings = warnings.reduce<string[]>((collected, warning) => {
    const text = warning.trim();
    if (!text) {
      return collected;
    }
    const key = normalizeWarningKey(text);
    const exists = collected.some((item) => normalizeWarningKey(item) === key);
    if (!exists) {
      collected.push(text);
    }
    return collected;
  }, []);

  if (!uniqueWarnings.length) {
    return null;
  }

  return (
    <Alert
      type={type}
      showIcon
      message={uniqueWarnings.length > 1 ? `注意事项（${uniqueWarnings.length} 条）` : '注意事项'}
      description={
        uniqueWarnings.length === 1 ? (
          uniqueWarnings[0]
        ) : (
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            {uniqueWarnings.map((warning) => (
              <li key={`${type}-${normalizeWarningKey(warning)}`}>{warning}</li>
            ))}
          </ul>
        )
      }
    />
  );
}
