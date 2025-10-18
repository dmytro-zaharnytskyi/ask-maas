'use client';

import React, { useState } from 'react';
import {
  Card,
  CardTitle,
  CardBody,
  Form,
  FormGroup,
  TextInput,
  TextArea,
  Button,
  Alert,
  Spinner,
  HelperText,
  HelperTextItem,
  Split,
  SplitItem,
} from '@patternfly/react-core';

interface ManualArticleInputProps {
  onArticleSubmit: (url: string, title: string, content: string) => void;
}

const ManualArticleInput: React.FC<ManualArticleInputProps> = ({ onArticleSubmit }) => {
  const [url, setUrl] = useState('');
  const [title, setTitle] = useState('');
  const [content, setContent] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!url || !title || !content) {
      setError('Please fill in all fields');
      return;
    }

    setLoading(true);
    setError(null);
    setSuccess(null);

    try {
      // Send the content directly to the ingest endpoint
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/v1/ingest/content`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            page_url: url,
            title: title,
            content: content,
            content_type: 'text',
            force_refresh: true,
          }),
        }
      );

      if (!response.ok) {
        const errorData = await response.json().catch(() => null);
        throw new Error(errorData?.detail || 'Failed to process article');
      }

      const data = await response.json();
      setSuccess(`Article indexed successfully! ${data.chunk_count} chunks processed.`);
      
      // Notify parent component
      onArticleSubmit(url, title, content);
      
      // Clear the form
      setUrl('');
      setTitle('');
      setContent('');
      
    } catch (err) {
      console.error('Error processing article:', err);
      setError(err instanceof Error ? err.message : 'Failed to process article');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card>
      <CardTitle>Manually Add Article Content</CardTitle>
      <CardBody>
        <Alert
          variant="info"
          isInline
          title="Copy & Paste Article Content"
          style={{ marginBottom: '1rem' }}
        >
          If automatic fetching fails due to website protection, you can manually copy the article content from your browser and paste it here.
        </Alert>

        <Form onSubmit={handleSubmit}>
          <FormGroup label="Article URL" fieldId="manual-url" isRequired>
            <TextInput
              id="manual-url"
              type="url"
              value={url}
              onChange={(_event, value) => setUrl(value)}
              placeholder="https://developers.redhat.com/articles/..."
              isDisabled={loading}
              isRequired
            />
            <HelperText>
              <HelperTextItem variant="default">
                The original URL of the article for reference
              </HelperTextItem>
            </HelperText>
          </FormGroup>

          <FormGroup label="Article Title" fieldId="manual-title" isRequired>
            <TextInput
              id="manual-title"
              type="text"
              value={title}
              onChange={(_event, value) => setTitle(value)}
              placeholder="Enter the article title"
              isDisabled={loading}
              isRequired
            />
          </FormGroup>

          <FormGroup label="Article Content" fieldId="manual-content" isRequired>
            <TextArea
              id="manual-content"
              value={content}
              onChange={(_event, value) => setContent(value)}
              placeholder="Paste the full article content here..."
              rows={10}
              isDisabled={loading}
              isRequired
              resizeOrientation="vertical"
            />
            <HelperText>
              <HelperTextItem variant="default">
                Copy the entire article text from your browser and paste it here
              </HelperTextItem>
            </HelperText>
          </FormGroup>

          <Split hasGutter>
            <SplitItem>
              <Button
                variant="primary"
                type="submit"
                isDisabled={loading || !url || !title || !content}
                isLoading={loading}
              >
                {loading ? 'Processing...' : 'Process Article'}
              </Button>
            </SplitItem>
            <SplitItem>
              <Button
                variant="secondary"
                onClick={() => {
                  setUrl('');
                  setTitle('');
                  setContent('');
                  setError(null);
                  setSuccess(null);
                }}
                isDisabled={loading}
              >
                Clear Form
              </Button>
            </SplitItem>
            {loading && (
              <SplitItem>
                <Spinner size="md" aria-label="Processing article" />
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
            style={{ marginTop: '1rem' }}
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
            style={{ marginTop: '1rem' }}
          >
            {success}
          </Alert>
        )}

        <Alert
          variant="warning"
          isInline
          title="How to Copy Article Content"
          style={{ marginTop: '2rem' }}
        >
          <ol style={{ marginLeft: '1rem', marginTop: '0.5rem' }}>
            <li>Open the Red Hat Developer article in your browser</li>
            <li>Select all the article content (Ctrl+A or Cmd+A)</li>
            <li>Copy the content (Ctrl+C or Cmd+C)</li>
            <li>Paste it into the content field above (Ctrl+V or Cmd+V)</li>
            <li>Make sure to include the title and URL</li>
          </ol>
        </Alert>
      </CardBody>
    </Card>
  );
};

export default ManualArticleInput;
