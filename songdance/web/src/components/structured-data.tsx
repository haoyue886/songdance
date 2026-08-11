type StructuredDataValue = Record<string, unknown> | readonly Record<string, unknown>[];

export function StructuredData({ data }: { data: StructuredDataValue }) {
  const json = JSON.stringify(data).replaceAll("<", "\\u003c");
  return <script type="application/ld+json">{json}</script>;
}
