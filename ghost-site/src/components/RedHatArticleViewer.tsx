'use client';

import React, { useEffect, useRef, useState } from 'react';
import ChatWidget from './ChatWidget';

interface RedHatArticleViewerProps {
  articlePath: string;
  articleTitle: string;
}

const RedHatArticleViewer: React.FC<RedHatArticleViewerProps> = ({ articlePath, articleTitle }) => {
  const iframeRef = useRef<HTMLIFrameElement>(null);
  const [showChat, setShowChat] = useState(false);
  const [articleUrl, setArticleUrl] = useState('');

  useEffect(() => {
    // Set the article URL for the chat widget
    setArticleUrl(`http://localhost:3000/article/${encodeURIComponent(articleTitle)}`);
    
    // Add a floating chat button to the iframe content after it loads
    if (iframeRef.current) {
      iframeRef.current.onload = () => {
        try {
          const iframeDoc = iframeRef.current?.contentDocument;
          if (iframeDoc) {
            // Add custom styles for chat button
            const style = iframeDoc.createElement('style');
            style.textContent = `
              .ask-maas-chat-button {
                position: fixed;
                bottom: 20px;
                right: 20px;
                background-color: #ee0000;
                color: white;
                border: none;
                border-radius: 50px;
                padding: 15px 25px;
                font-size: 16px;
                font-weight: 600;
                cursor: pointer;
                box-shadow: 0 4px 12px rgba(0,0,0,0.15);
                z-index: 9999;
                transition: all 0.3s ease;
                display: flex;
                align-items: center;
                gap: 8px;
              }
              .ask-maas-chat-button:hover {
                background-color: #cc0000;
                transform: translateY(-2px);
                box-shadow: 0 6px 16px rgba(0,0,0,0.2);
              }
              .ask-maas-chat-button svg {
                width: 20px;
                height: 20px;
              }
            `;
            iframeDoc.head.appendChild(style);

            // Add chat button
            const chatButton = iframeDoc.createElement('button');
            chatButton.className = 'ask-maas-chat-button';
            chatButton.innerHTML = `
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor">
                <path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H6l-2 2V4h16v12z"/>
                <path d="M7 9h2v2H7zm4 0h2v2h-2zm4 0h2v2h-2z"/>
              </svg>
              Ask AI Assistant
            `;
            chatButton.onclick = () => {
              window.parent.postMessage({ action: 'toggleChat' }, '*');
            };
            iframeDoc.body.appendChild(chatButton);
          }
        } catch (e) {
          console.error('Could not modify iframe content:', e);
        }
      };
    }

    // Listen for messages from iframe
    const handleMessage = (event: MessageEvent) => {
      if (event.data.action === 'toggleChat') {
        setShowChat(true);
      }
    };

    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, [articleTitle]);

  return (
    <div style={{ position: 'relative', width: '100%', height: '100vh' }}>
      {/* Article iframe */}
      <iframe
        ref={iframeRef}
        src={articlePath}
        style={{
          width: '100%',
          height: '100%',
          border: 'none',
        }}
        title={articleTitle}
      />

      {/* Chat Widget Overlay */}
      {showChat && (
        <div
          style={{
            position: 'fixed',
            bottom: '20px',
            right: '20px',
            width: '400px',
            height: '600px',
            zIndex: 10000,
            boxShadow: '0 8px 32px rgba(0,0,0,0.2)',
            borderRadius: '8px',
            overflow: 'hidden',
            background: 'white',
          }}
        >
          <ChatWidget
            currentPageUrl={articleUrl}
            articleTitle={articleTitle}
            articlePath={articlePath}
            onClose={() => setShowChat(false)}
          />
        </div>
      )}

      {/* Floating chat toggle button (backup if iframe button doesn't work) */}
      {!showChat && (
        <button
          onClick={() => setShowChat(true)}
          style={{
            position: 'fixed',
            bottom: '20px',
            right: '20px',
            backgroundColor: '#ee0000',
            color: 'white',
            border: 'none',
            borderRadius: '50px',
            padding: '15px 25px',
            fontSize: '16px',
            fontWeight: 600,
            cursor: 'pointer',
            boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
            zIndex: 9999,
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            transition: 'all 0.3s ease',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.backgroundColor = '#cc0000';
            e.currentTarget.style.transform = 'translateY(-2px)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.backgroundColor = '#ee0000';
            e.currentTarget.style.transform = 'translateY(0)';
          }}
        >
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" width="20" height="20">
            <path d="M20 2H4c-1.1 0-2 .9-2 2v18l4-4h14c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 14H6l-2 2V4h16v12z"/>
            <path d="M7 9h2v2H7zm4 0h2v2h-2zm4 0h2v2h-2z"/>
          </svg>
          Ask AI Assistant
        </button>
      )}
    </div>
  );
};

export default RedHatArticleViewer;