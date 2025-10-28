'use client';

import React, { useState, useEffect, useRef } from 'react';
import {
  Card,
  CardTitle,
  CardBody,
  CardFooter,
  Button,
  TextInput,
  Form,
  FormGroup,
  Alert,
  Spinner,
  Chip,
  ChipGroup,
  Split,
  SplitItem,
  Text,
  TextContent,
  TextVariants,
} from '@patternfly/react-core';
import { TimesIcon, PaperPlaneIcon, BookIcon, LinkIcon } from '@patternfly/react-icons';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

interface ChatWidgetProps {
  currentPageUrl?: string;
  pageUrl?: string;
  articleTitle?: string;
  articlePath?: string;
  externalUrl?: string;
  articleContent?: string;
  onClose?: () => void;
}

interface Message {
  id: string;
  type: 'user' | 'assistant' | 'error';
  content: string;
  citations?: Citation[];
  timestamp: Date;
}

interface Citation {
  text: string;
  url: string;
  title?: string;
  score?: number;
}

const ChatWidget: React.FC<ChatWidgetProps> = ({ currentPageUrl, pageUrl, articleTitle, articlePath, externalUrl, articleContent, onClose }) => {
  // Use currentPageUrl if provided, otherwise fall back to pageUrl
  const activePageUrl = currentPageUrl || pageUrl || '';
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isIngesting, setIsIngesting] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const eventSourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    // Add welcome message
    const title = articleTitle || 'this article';
    setMessages([
      {
        id: '0',
        type: 'assistant',
        content: `Hi! I'm here to help you understand "${title}". Ask me anything about this article or its related resources.`,
        timestamp: new Date(),
      },
    ]);

    // Auto-ingest the article when widget loads
    const ingestArticle = async () => {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || (typeof window !== 'undefined' ? window.location.origin.replace('ask-maas-frontend', 'ask-maas-api') : '');
      setIsIngesting(true);
      setError(null);
      
      try {
        // Generate proper article URL
        const origin = typeof window !== 'undefined' ? window.location.origin : '';
        const articleUrl = activePageUrl || (articlePath ? `${origin}${articlePath}` : `${origin}/article/${encodeURIComponent(articleTitle || '')}`);
        
        // First, fetch the article HTML content
        let articleContentText = '';
        
        if (articlePath) {
          // Use the provided article path directly (it already includes /api prefix)
          const fullArticlePath = articlePath.startsWith('http') 
            ? articlePath 
            : `${origin}${articlePath.startsWith('/') ? articlePath : '/' + articlePath}`;
          const articleResponse = await fetch(fullArticlePath);
          if (articleResponse.ok) {
            const htmlContent = await articleResponse.text();
            // Parse HTML and extract article content
            const parser = new DOMParser();
            const doc = parser.parseFromString(htmlContent, 'text/html');
            
            // Try to find the main content area
            const mainContent = doc.querySelector('article') || 
                               doc.querySelector('main') || 
                               doc.querySelector('.content') || 
                               doc.querySelector('#content') ||
                               doc.body;
            
            if (mainContent) {
              // Remove script and style elements
              mainContent.querySelectorAll('script, style').forEach(el => el.remove());
              // Get text content
              articleContentText = mainContent.textContent?.trim() || '';
            }
            
            // If still too much CSS/HTML noise, try to extract only visible text
            if (articleContentText.includes('{') && articleContentText.includes('}')) {
              // Find actual article content after the CSS
              const textParts = articleContentText.split('\n').filter(line => 
                !line.includes('{') && !line.includes('}') && line.trim().length > 10
              );
              articleContentText = textParts.join('\n');
            }
          }
        } else {
          // Fallback to trying to fetch by title
          const articleResponse = await fetch(`/static-articles/${encodeURIComponent(articleTitle || '')}.html`);
          if (articleResponse.ok) {
            const htmlContent = await articleResponse.text();
            // Parse HTML and extract article content
            const parser = new DOMParser();
            const doc = parser.parseFromString(htmlContent, 'text/html');
            
            // Try to find the main content area
            const mainContent = doc.querySelector('article') || 
                               doc.querySelector('main') || 
                               doc.querySelector('.content') || 
                               doc.querySelector('#content') ||
                               doc.body;
            
            if (mainContent) {
              // Remove script and style elements
              mainContent.querySelectorAll('script, style').forEach(el => el.remove());
              // Get text content
              articleContentText = mainContent.textContent?.trim() || '';
            }
            
            // If still too much CSS/HTML noise, try to extract only visible text
            if (articleContentText.includes('{') && articleContentText.includes('}')) {
              // Find actual article content after the CSS
              const textParts = articleContentText.split('\n').filter(line => 
                !line.includes('{') && !line.includes('}') && line.trim().length > 10
              );
              articleContentText = textParts.join('\n');
            }
          }
        }
        
        if (!articleContentText) {
          // If we can't fetch the article, use a fallback
          articleContentText = `Article: ${articleTitle}. This is a Red Hat Developer article about ${articleTitle}.`;
        }
        
        // Send content directly to the ingest endpoint
        const response = await fetch(`${apiUrl}/api/v1/ingest/content`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({
            page_url: articleUrl,
            title: articleTitle || 'Article',
            content: articleContentText,
            content_type: 'text',
            force_refresh: false,  // Only index if not cached - avoid re-indexing every time
          }),
        });

        if (!response.ok) {
          console.warn('Article ingestion failed, but continuing anyway');
        } else {
          const data = await response.json();
          console.log('Article indexed:', data.chunk_count, 'chunks');
        }
      } catch (err) {
        console.warn('Ingestion error:', err);
        // Don't show error - let user try chatting anyway
      } finally {
        setIsIngesting(false);
      }
    };
    
    // Skip ingestion - articles are pre-indexed in Qdrant
    // This removes the 10-second delay
    setIsIngesting(false);


    return () => {
      // Clean up event source on unmount
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, [activePageUrl, pageUrl, articleTitle, articlePath, externalUrl, articleContent, currentPageUrl]);

  const scrollToBottom = () => {
    messagesEndRef?.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    
    if (!input.trim() || isLoading) return;

    const userMessage: Message = {
      id: Date.now().toString(),
      type: 'user',
      content: input,
      timestamp: new Date(),
    };

    setMessages(prev => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);
    setError(null);

    const apiUrl = process.env.NEXT_PUBLIC_API_URL || (typeof window !== 'undefined' ? window.location.origin.replace('ask-maas-frontend', 'ask-maas-api') : '');
    
    // Generate proper page URL for chat
    const origin = typeof window !== 'undefined' ? window.location.origin : '';
    const chatPageUrl = activePageUrl || (articlePath ? `${origin}${articlePath}` : pageUrl || `${origin}/article/${encodeURIComponent(articleTitle || '')}`);

    try {
      // Create EventSource for SSE streaming
        // Use unified endpoint for global search
        const response = await fetch(`${apiUrl}/api/v1/chat/unified`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          query: input,
          page_url: chatPageUrl,
          stream: true,
          model: 'llama',
          temperature: 0.7,
          max_tokens: 1000,
          use_global_context: true,
          use_local_context: false,
        }),
      });

      if (!response.ok) {
        throw new Error('Chat request failed');
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      
      let currentMessage = '';
      let citations: Citation[] = [];
      let messageId = '';

      // Process SSE stream
      while (true) {
        const { done, value } = await reader?.read() || { done: true, value: undefined };
        
        if (done) break;
        
        const chunk = decoder.decode(value);
        const lines = chunk.split('\n');
        
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const data = JSON.parse(line.slice(6));
              
              if (data.type === 'start') {
                messageId = data.id;
              } else if (data.type === 'text') {
                currentMessage += data.content;
                
                // Update the assistant message in real-time
                setMessages(prev => {
                  const newMessages = [...prev];
                  const lastMessage = newMessages[newMessages.length - 1];
                  
                  if (lastMessage && lastMessage.type === 'assistant' && lastMessage.id === messageId) {
                    lastMessage.content = currentMessage;
                  } else {
                    newMessages.push({
                      id: messageId,
                      type: 'assistant',
                      content: currentMessage,
                      timestamp: new Date(),
                    });
                  }
                  
                  return newMessages;
                });
              } else if (data.type === 'citation') {
                citations.push(...(data.citations || []));
              } else if (data.type === 'done') {
                // Final update with citations
                setMessages(prev => {
                  const newMessages = [...prev];
                  const lastMessage = newMessages[newMessages.length - 1];
                  
                  if (lastMessage && lastMessage.type === 'assistant') {
                    lastMessage.citations = citations;
                  }
                  
                  return newMessages;
                });
              } else if (data.type === 'error') {
                throw new Error(data.content || 'An error occurred');
              }
            } catch (parseError) {
              console.error('Error parsing SSE data:', parseError);
            }
          }
        }
      }
    } catch (err) {
      console.error('Chat error:', err);
      setError(err instanceof Error ? err.message : 'Failed to send message');
      
      const errorMessage: Message = {
        id: Date.now().toString(),
        type: 'error',
        content: 'Sorry, I encountered an error while processing your request. Please try again.',
        timestamp: new Date(),
      };
      
      setMessages(prev => [...prev, errorMessage]);
    } finally {
      setIsLoading(false);
    }
  };

  const suggestedQuestions = [
    "What is the main topic of this article?",
    "Can you summarize the key points?",
    "What are the prerequisites mentioned?",
    "Are there any code examples?"
  ];

  const handleSuggestedQuestion = (question: string) => {
    setInput(question);
  };

  return (
    <Card className="chat-widget" style={{ height: '600px', display: 'flex', flexDirection: 'column' }}>
      <CardTitle>
        <Split hasGutter>
          <SplitItem isFilled>
            <BookIcon /> Ask This Page
          </SplitItem>
          {onClose && (
            <SplitItem>
              <Button variant="plain" onClick={onClose}>
                <TimesIcon />
              </Button>
            </SplitItem>
          )}
        </Split>
      </CardTitle>
      
      <CardBody style={{ flex: 1, overflowY: 'auto', padding: '1rem' }}>
        {isIngesting && (
          <Alert variant="info" title="Indexing article..." isInline>
            <Spinner size="sm" /> Preparing article for AI assistant...
          </Alert>
        )}
        
        {error && (
          <Alert variant="danger" title="Error" isInline>
            {error}
          </Alert>
        )}
        
        <div className="messages">
          {messages.map((message) => (
            <div key={message.id} className={`message message-${message.type}`} style={{
              marginBottom: '1rem',
              padding: '0.75rem',
              backgroundColor: message.type === 'user' ? '#f0f0f0' : message.type === 'error' ? '#fee' : '#fff',
              borderRadius: '8px',
              border: '1px solid #ddd',
            }}>
              <TextContent>
                <Text component={TextVariants.small} style={{ 
                  fontWeight: 'bold', 
                  color: message.type === 'user' ? '#0066cc' : message.type === 'error' ? '#c00' : '#151515' 
                }}>
                  {message.type === 'user' ? 'You' : message.type === 'error' ? 'Error' : 'AI Assistant'}
                </Text>
                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                  {message.content}
                </ReactMarkdown>
              </TextContent>
              
              {message.citations && message.citations.length > 0 && (
                <div style={{ marginTop: '0.5rem' }}>
                  <Text component={TextVariants.small}>
                    <LinkIcon /> Sources:
                  </Text>
                  <ChipGroup categoryName="Citations" numChips={5}>
                    {message.citations.map((citation, idx) => (
                      <Chip key={idx} isReadOnly>
                        <a 
                          href={citation.url} 
                          target="_blank" 
                          rel="noopener noreferrer"
                          style={{ textDecoration: 'none', color: 'inherit' }}
                        >
                          {citation.title || `Source ${idx + 1}`}
                        </a>
                      </Chip>
                    ))}
                  </ChipGroup>
                </div>
              )}
            </div>
          ))}
          
          {isLoading && (
            <div style={{ 
              display: 'flex', 
              alignItems: 'center', 
              gap: '0.5rem', 
              padding: '0.75rem',
              backgroundColor: '#f0f7ff',
              borderRadius: '8px',
              margin: '0.5rem'
            }}>
              <Spinner size="sm" />
              <Text style={{ color: '#0066cc', fontWeight: 500 }}>AI is processing your question...</Text>
            </div>
          )}
          
          <div ref={messagesEndRef} />
        </div>
        
        {messages.length === 1 && !isIngesting && (
          <div style={{ marginTop: '1rem' }}>
            <Text component={TextVariants.small}>Suggested questions:</Text>
            <ChipGroup>
              {suggestedQuestions.map((question, idx) => (
                <Chip 
                  key={idx} 
                  onClick={() => handleSuggestedQuestion(question)}
                  style={{ cursor: 'pointer' }}
                >
                  {question}
                </Chip>
              ))}
            </ChipGroup>
          </div>
        )}
      </CardBody>
      
      <CardFooter>
        <Form onSubmit={handleSubmit}>
          <FormGroup>
            <Split hasGutter>
              <SplitItem isFilled>
                <TextInput
                  value={input}
                  onChange={(_, value) => setInput(value)}
                  placeholder="Ask a question about this article..."
                  isDisabled={isLoading || isIngesting}
                  aria-label="Question input"
                />
              </SplitItem>
              <SplitItem>
                <Button
                  type="submit"
                  variant="primary"
                  isDisabled={!input.trim() || isLoading || isIngesting}
                  icon={<PaperPlaneIcon />}
                >
                  Send
                </Button>
              </SplitItem>
            </Split>
          </FormGroup>
        </Form>
      </CardFooter>
    </Card>
  );
};

export default ChatWidget;