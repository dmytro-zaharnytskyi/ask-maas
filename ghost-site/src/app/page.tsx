'use client';

import React, { useState, useEffect } from 'react';
import RedHatArticleViewer from '@/components/RedHatArticleViewer';

// Define available articles
const ARTICLES = [
  {
    id: 'gpu-slicing',
    title: 'Dynamic GPU slicing with Red Hat OpenShift and NVIDIA MIG',
    description: 'Why run one AI model when you can run ten?',
    author: 'Harshal Patil',
    date: 'October 14, 2025',
    path: '/static-articles/Dynamic GPU slicing with Red Hat OpenShift and NVIDIA MIG _ Red Hat Developer.html',
  },
  {
    id: 'knowledge-portal',
    title: 'How to deploy the Offline Knowledge Portal on OpenShift',
    description: 'Deploy a comprehensive knowledge management system on OpenShift',
    author: 'Red Hat Team',
    date: 'October 14, 2025',
    path: '/static-articles/How to deploy the Offline Knowledge Portal on OpenShift _ Red Hat Developer.html',
  }
];

export default function Home() {
  const [selectedArticle, setSelectedArticle] = useState<typeof ARTICLES[0] | null>(null);
  const [showArticleList, setShowArticleList] = useState(true);

  // Auto-select first article for demo
  useEffect(() => {
    if (ARTICLES.length > 0 && !selectedArticle) {
      // Auto-select GPU article for demo
      setSelectedArticle(ARTICLES[0]);
      setShowArticleList(false);
    }
  }, []);

  if (!showArticleList && selectedArticle) {
    return (
      <div style={{ width: '100%', height: '100vh', overflow: 'hidden', position: 'relative' }}>
        {/* Back button */}
        <button
          onClick={() => {
            setShowArticleList(true);
            setSelectedArticle(null);
          }}
          style={{
            position: 'fixed',
            top: '10px',
            left: '10px',
            zIndex: 10001,
            backgroundColor: 'white',
            border: '1px solid #d2d2d2',
            borderRadius: '4px',
            padding: '8px 16px',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            fontSize: '14px',
            boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
          }}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
            <path d="M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z"/>
          </svg>
          Back to Articles
        </button>
        
        <RedHatArticleViewer
          articlePath={selectedArticle.path}
          articleTitle={selectedArticle.title}
        />
      </div>
    );
  }

  // Article selection page (Red Hat Developer style)
  return (
    <div style={{ 
      minHeight: '100vh',
      backgroundColor: '#f5f5f5',
      fontFamily: '"Red Hat Text", "Overpass", helvetica, arial, sans-serif'
    }}>
      {/* Red Hat Developer Header */}
      <header style={{
        backgroundColor: '#151515',
        borderBottom: '3px solid #ee0000',
        padding: '0',
      }}>
        <div style={{
          maxWidth: '1290px',
          margin: '0 auto',
          padding: '0 15px',
        }}>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            height: '72px',
          }}>
            {/* Red Hat Logo */}
            <svg width="140" height="40" viewBox="0 0 613 145" xmlns="http://www.w3.org/2000/svg">
              <g fill="#FFF">
                <path d="M127.47 83.49c12.51 0 30.61-2.58 30.61-17.46a14 14 0 0 0-.31-3.42l-7.45-32.36c-1.72-7.12-3.23-10.35-15.73-16.6C124.89 8.69 103.76.5 97.51.5 91.69.5 90 8 83.06 8c-6.68 0-11.64-5.6-17.89-5.6-6 0-9.91 4.09-12.93 12.5 0 0-8.41 23.72-9.49 27.16a6.43 6.43 0 0 0-.22 1.94c0 9.22 36.3 39.45 84.94 39.45M160 72.07c1.73 8.19 1.73 9.05 1.73 10.13 0 14-15.74 21.77-36.43 21.77C78.54 104 37.58 76.6 37.58 58.49a18.45 18.45 0 0 1 1.51-7.33C22.27 52 .5 55 .5 74.22c0 31.48 74.59 70.28 133.65 70.28 45.28 0 56.7-20.48 56.7-36.65 0-12.72-11-27.16-30.83-35.78"></path>
                <path d="M160 72.07c1.73 8.19 1.73 9.05 1.73 10.13 0 14-15.74 21.77-36.43 21.77C78.54 104 37.58 76.6 37.58 58.49a18.45 18.45 0 0 1 1.51-7.33l3.66-9.06a6.43 6.43 0 0 0-.22 1.9c0 9.22 36.3 39.45 84.94 39.45 12.51 0 30.61-2.58 30.61-17.46a14 14 0 0 0-.31-3.42Z"></path>
              </g>
              <g fill="#FFF">
                <path d="M579.74 92.8c0 11.89 7.15 17.67 20.19 17.67a52.11 52.11 0 0 0 11.89-1.68V95a24.84 24.84 0 0 1-7.68 1.16c-5.37 0-7.36-1.68-7.36-6.73V68.3h15.56V54.1h-15.56v-18l-17 3.68V54.1h-11.29v14.2h11.25Zm-53 .32c0-3.68 3.69-5.47 9.26-5.47a43.12 43.12 0 0 1 10.1 1.26v7.15a21.51 21.51 0 0 1-10.63 2.63c-5.46 0-8.73-2.1-8.73-5.57m5.2 17.56c6 0 10.84-1.26 15.36-4.31v3.37h16.82V74.08c0-13.56-9.14-21-24.39-21-8.52 0-16.94 2-26 6.1l6.1 12.52c6.52-2.74 12-4.42 16.83-4.42 7 0 10.62 2.73 10.62 8.31v2.73a49.53 49.53 0 0 0-12.62-1.58c-14.31 0-22.93 6-22.93 16.73 0 9.78 7.78 17.24 20.19 17.24m-92.44-.94h18.09V80.92h30.29v28.82H506V36.12h-18.07v28.29h-30.29V36.12h-18.09Zm-68.86-27.9c0-8 6.31-14.1 14.62-14.1A17.22 17.22 0 0 1 397 72.09v19.45A16.36 16.36 0 0 1 385.24 96c-8.2 0-14.62-6.1-14.62-14.09m26.61 27.87h16.83V32.44l-17 3.68v20.93a28.3 28.3 0 0 0-14.2-3.68c-16.19 0-28.92 12.51-28.92 28.5a28.25 28.25 0 0 0 28.4 28.6 25.12 25.12 0 0 0 14.93-4.83ZM320 67c5.36 0 9.88 3.47 11.67 8.83h-23.2C310.15 70.47 314.36 67 320 67m-28.67 15c0 16.2 13.25 28.82 30.28 28.82 9.36 0 16.2-2.53 23.25-8.42l-11.26-10c-2.63 2.74-6.52 4.21-11.14 4.21a14.39 14.39 0 0 1-13.68-8.83h39.65v-4.23c0-17.67-11.88-30.39-28.08-30.39a28.57 28.57 0 0 0-29 28.81M262 51.58c6 0 9.36 3.78 9.36 8.31S268 68.2 262 68.2H244.11V51.58Zm-36 58.16h18.09V82.92h13.77l13.89 26.82H292l-16.2-29.45a22.27 22.27 0 0 0 13.88-20.72c0-13.25-10.41-23.45-26-23.45H226Z"></path>
              </g>
            </svg>
            <span style={{
              color: '#fff',
              fontSize: '24px',
              marginLeft: '20px',
              fontWeight: 300,
            }}>
              Developer
            </span>
          </div>
        </div>
      </header>

      {/* Hero Section */}
      <section style={{
        background: 'linear-gradient(135deg, #ee0000 0%, #cc0000 100%)',
        color: 'white',
        padding: '60px 0',
      }}>
        <div style={{
          maxWidth: '1290px',
          margin: '0 auto',
          padding: '0 15px',
        }}>
          <h1 style={{
            fontSize: '48px',
            fontWeight: 700,
            marginBottom: '20px',
          }}>
            Ask MaaS - AI-Powered Article Assistant
          </h1>
          <p style={{
            fontSize: '20px',
            opacity: 0.95,
          }}>
            Select an article below to read and interact with our AI assistant for instant answers
          </p>
        </div>
      </section>

      {/* Articles Grid */}
      <section style={{
        padding: '40px 0',
      }}>
        <div style={{
          maxWidth: '1290px',
          margin: '0 auto',
          padding: '0 15px',
        }}>
          <h2 style={{
            fontSize: '32px',
            fontWeight: 600,
            marginBottom: '30px',
            color: '#151515',
          }}>
            Available Articles
          </h2>
          
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(400px, 1fr))',
            gap: '30px',
          }}>
            {ARTICLES.map((article) => (
              <article
                key={article.id}
                onClick={() => {
                  setSelectedArticle(article);
                  setShowArticleList(false);
                }}
                style={{
                  backgroundColor: 'white',
                  borderRadius: '8px',
                  boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
                  overflow: 'hidden',
                  cursor: 'pointer',
                  transition: 'all 0.3s ease',
                  border: '1px solid #e7e7e7',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.boxShadow = '0 8px 24px rgba(0,0,0,0.15)';
                  e.currentTarget.style.transform = 'translateY(-4px)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.boxShadow = '0 2px 8px rgba(0,0,0,0.1)';
                  e.currentTarget.style.transform = 'translateY(0)';
                }}
              >
                <div style={{
                  backgroundColor: '#ee0000',
                  height: '6px',
                }}></div>
                
                <div style={{
                  padding: '30px',
                }}>
                  <div style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '10px',
                    marginBottom: '15px',
                    fontSize: '14px',
                    color: '#6a6e73',
                  }}>
                    <span>ARTICLE</span>
                    <span>•</span>
                    <span>{article.date}</span>
                  </div>
                  
                  <h3 style={{
                    fontSize: '24px',
                    fontWeight: 600,
                    color: '#151515',
                    marginBottom: '15px',
                    lineHeight: 1.3,
                  }}>
                    {article.title}
                  </h3>
                  
                  <p style={{
                    fontSize: '16px',
                    color: '#6a6e73',
                    marginBottom: '20px',
                    lineHeight: 1.5,
                  }}>
                    {article.description}
                  </p>
                  
                  <div style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                  }}>
                    <span style={{
                      fontSize: '14px',
                      color: '#6a6e73',
                    }}>
                      By {article.author}
                    </span>
                    
                    <span style={{
                      color: '#0066cc',
                      fontWeight: 600,
                      fontSize: '14px',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '5px',
                    }}>
                      Read article
                      <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor">
                        <path d="M10 6L8.59 7.41 13.17 12l-4.58 4.59L10 18l6-6z"/>
                      </svg>
                    </span>
                  </div>
                </div>
              </article>
            ))}
          </div>
          
          {/* AI Assistant Feature Card */}
          <div style={{
            backgroundColor: '#f0f0f0',
            borderRadius: '8px',
            padding: '40px',
            marginTop: '60px',
            textAlign: 'center',
          }}>
            <h3 style={{
              fontSize: '28px',
              fontWeight: 600,
              color: '#151515',
              marginBottom: '20px',
            }}>
              🤖 AI Assistant Available
            </h3>
            <p style={{
              fontSize: '18px',
              color: '#6a6e73',
              maxWidth: '600px',
              margin: '0 auto',
            }}>
              Each article includes an AI assistant that can answer your questions about the content in real-time. 
              Look for the "Ask AI Assistant" button when viewing an article.
            </p>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer style={{
        backgroundColor: '#151515',
        color: 'white',
        padding: '40px 0',
        marginTop: '80px',
      }}>
        <div style={{
          maxWidth: '1290px',
          margin: '0 auto',
          padding: '0 15px',
          textAlign: 'center',
        }}>
          <p style={{ opacity: 0.8 }}>
            © 2024 Red Hat, Inc. - Ask MaaS MVP Demo
          </p>
        </div>
      </footer>
    </div>
  );
}