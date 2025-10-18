'use client';

import React, { useEffect, useState } from 'react';
import {
  Card,
  CardTitle,
  CardBody,
  TextContent,
  Breadcrumb,
  BreadcrumbItem,
  Alert,
  Button,
  Spinner,
  Badge,
} from '@patternfly/react-core';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import rehypeHighlight from 'rehype-highlight';
import 'highlight.js/styles/github.css';

interface Article {
  id: string;
  title: string;
  author?: string;
  description?: string;
  content: string;
  url?: string;
  chunks?: any[];
}

interface ArticleViewerProps {
  articleId: string;
  onArticleLoad?: (article: Article) => void;
}

const ArticleViewer: React.FC<ArticleViewerProps> = ({ articleId, onArticleLoad }) => {
  const [article, setArticle] = useState<Article | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadArticle();
  }, [articleId]);

  const loadArticle = async () => {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch(
        `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/v1/articles/${articleId}`
      );

      if (!response.ok) {
        throw new Error('Failed to load article');
      }

      const data = await response.json();
      setArticle(data);
      
      // Notify parent component
      if (onArticleLoad) {
        onArticleLoad(data);
      }
    } catch (error) {
      console.error('Error loading article:', error);
      setError('Failed to load article');
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <Card isFullHeight>
        <CardBody>
          <Alert variant="info" title="Loading article..." isInline>
            <Spinner size="sm" /> Please wait...
          </Alert>
        </CardBody>
      </Card>
    );
  }

  if (error) {
    return (
      <Card isFullHeight>
        <CardBody>
          <Alert variant="danger" title="Error" isInline>
            {error}
          </Alert>
        </CardBody>
      </Card>
    );
  }

  if (!article) {
    return (
      <Card isFullHeight>
        <CardBody>
          <Alert variant="warning" title="Article not found" isInline>
            The requested article could not be found.
          </Alert>
        </CardBody>
      </Card>
    );
  }

  return (
    <Card isFullHeight>
      <CardTitle>
        <Breadcrumb>
          <BreadcrumbItem>Articles</BreadcrumbItem>
          <BreadcrumbItem isActive>{article.title}</BreadcrumbItem>
        </Breadcrumb>
      </CardTitle>
      <CardBody>
        <TextContent>
          <h1>{article.title}</h1>
          
          <div style={{ marginBottom: '1rem' }}>
            {article.author && (
              <Badge isRead style={{ marginRight: '0.5rem' }}>
                Author: {article.author}
              </Badge>
            )}
            {article.chunks && (
              <Badge isRead>
                {article.chunks.length} text chunks indexed
              </Badge>
            )}
          </div>
          
          {article.description && (
            <p className="text-muted" style={{ fontStyle: 'italic' }}>
              {article.description}
            </p>
          )}
          
          {article.url && (
            <p className="text-muted">
              <small>
                Original article: <a href={article.url} target="_blank" rel="noopener noreferrer">
                  {article.url}
                </a>
              </small>
            </p>
          )}
          
          <ReactMarkdown
            remarkPlugins={[remarkGfm]}
            rehypePlugins={[rehypeHighlight]}
            components={{
              // Custom rendering for code blocks
              code({ className, children, ...props }: any) {
                const match = /language-(\w+)/.exec(className || '');
                const inline = !match;
                return !inline && match ? (
                  <pre className={className}>
                    <code className={className} {...props}>
                      {children}
                    </code>
                  </pre>
                ) : (
                  <code className={className} {...props}>
                    {children}
                  </code>
                );
              },
              // Custom rendering for links
              a({ href, children }: any) {
                const isExternal = href?.startsWith('http');
                return (
                  <a
                    href={href}
                    target={isExternal ? '_blank' : undefined}
                    rel={isExternal ? 'noopener noreferrer' : undefined}
                  >
                    {children}
                    {isExternal && ' 🔗'}
                  </a>
                );
              },
              // Custom heading rendering
              h1: ({ children }: any) => <h2>{children}</h2>, // Downgrade h1 to h2 since we already have article title
              h2: ({ children }: any) => <h3>{children}</h3>,
              h3: ({ children }: any) => <h4>{children}</h4>,
            }}
          >
            {article.content}
          </ReactMarkdown>
        </TextContent>
      </CardBody>
    </Card>
  );
};

export default ArticleViewer;