import '@patternfly/react-core/dist/styles/base.css';
import './globals.css';
import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Ask MaaS - Demo Articles',
  description: 'Demo site for Ask MaaS page-local AI assistant',
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
