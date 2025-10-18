'use client';

import React, { useState } from 'react';
import {
  Card,
  CardTitle,
  CardBody,
  Form,
  FormGroup,
  TextInput,
  Button,
  Alert,
  Spinner,
  HelperText,
  HelperTextItem,
  Split,
  SplitItem,
  List,
  ListItem,
} from '@patternfly/react-core';

interface ArticleLoaderProps {
  onArticleLoad: (url: string, title: string, content?: string) => void;
}

const ArticleLoader: React.FC<ArticleLoaderProps> = ({ onArticleLoad }) => {
  const [url, setUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Pre-configured Red Hat Developer articles - use actual 2024 articles
  const suggestedArticles = [
    {
      url: 'https://developers.redhat.com/articles/2024/10/10/how-use-oci-gitops-openshift',
      title: 'How to use OCI for GitOps in OpenShift'
    },
    {
      url: 'https://developers.redhat.com/articles/2024/09/26/splitting-openshift-machine-config-pool-without-node-reboots',
      title: 'Splitting OpenShift machine config pool without node reboots'
    },
    {
      url: 'https://developers.redhat.com/articles/2024/09/19/nodejs-20-memory-management-containers',
      title: 'Node.js 20+ memory management in containers'
    },
    {
      url: 'https://developers.redhat.com/articles/2024/06/05/how-red-hat-has-redefined-continuous-performance-testing',
      title: 'How Red Hat has redefined continuous performance testing'
    },
    {
      url: 'https://developers.redhat.com/articles/2024/08/28/implementing-zero-trust-architecture-red-hat-openshift',
      title: 'Implementing zero-trust architecture with Red Hat OpenShift'
    }
  ];

  const handleSubmit = async (articleUrl?: string) => {
    const targetUrl = articleUrl || url;
    
    if (!targetUrl) {
      setError('Please enter a valid URL');
      return;
    }

    // Basic validation for Red Hat Developer URL
    if (!targetUrl.includes('developers.redhat.com')) {
      setError('Please enter a URL from developers.redhat.com');
      return;
    }

    setLoading(true);
    setError(null);
    setSuccess(null);

    try {
      // First, try to ingest the article
      const ingestResponse = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/v1/ingest/page`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            page_url: targetUrl,
            force_refresh: true,
            include_linked_resources: true,
          }),
        }
      );

      if (!ingestResponse.ok) {
        const errorData = await ingestResponse.json().catch(() => null);
        throw new Error(errorData?.detail || 'Failed to load article');
      }

      const ingestData = await ingestResponse.json();
      
      // Extract title from URL or use a default
      const urlParts = targetUrl.split('/');
      const slug = urlParts[urlParts.length - 1];
      const title = slug
        .split('-')
        .map(word => word.charAt(0).toUpperCase() + word.slice(1))
        .join(' ');

      setSuccess(`Article loaded successfully! ${ingestData.chunk_count} chunks indexed.`);
      
      // Notify parent component
      onArticleLoad(targetUrl, title);

      // Clear the URL input
      setUrl('');

    } catch (err) {
      console.error('Error loading article:', err);
      setError(err instanceof Error ? err.message : 'Failed to load article. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card>
      <CardTitle>Load Red Hat Developer Article</CardTitle>
      <CardBody>
        <Form onSubmit={(e) => { e.preventDefault(); handleSubmit(); }}>
          <FormGroup label="Article URL" fieldId="article-url">
            <TextInput
              id="article-url"
              type="url"
              value={url}
              onChange={(_event, value) => setUrl(value)}
              placeholder="https://developers.redhat.com/articles/..."
              aria-label="Red Hat Developer article URL"
              isDisabled={loading}
            />
            <HelperText>
              <HelperTextItem variant="default">
                Enter a URL from developers.redhat.com/articles/
              </HelperTextItem>
            </HelperText>
          </FormGroup>

          <Split hasGutter>
            <SplitItem>
              <Button
                variant="primary"
                type="submit"
                isDisabled={loading || !url}
                isLoading={loading}
              >
                {loading ? 'Loading...' : 'Load Article'}
              </Button>
            </SplitItem>
            {loading && (
              <SplitItem>
                <Spinner size="md" aria-label="Loading article" />
              </SplitItem>
            )}
          </Split>
        </Form>

        {error && (
          <Alert
            variant="danger"
            title="Error"
            isInline
            timeout={10000}
            onTimeout={() => setError(null)}
          >
            {error}
          </Alert>
        )}

        {success && (
          <Alert
            variant="success"
            title="Success"
            isInline
            timeout={10000}
            onTimeout={() => setSuccess(null)}
          >
            {success}
          </Alert>
        )}

        <div style={{ marginTop: '2rem' }}>
          <h4>Quick Load Recent Articles</h4>
          <p style={{ marginBottom: '1rem', color: '#666' }}>
            Click on any article below to load it instantly:
          </p>
          <List>
            {suggestedArticles.map((article, index) => (
              <ListItem key={index}>
                <Button
                  variant="link"
                  isInline
                  onClick={() => handleSubmit(article.url)}
                  isDisabled={loading}
                  style={{ textAlign: 'left', padding: '0.5rem 0' }}
                >
                  {article.title}
                </Button>
              </ListItem>
            ))}
          </List>
        </div>
      </CardBody>
    </Card>
  );
};

export default ArticleLoader;
