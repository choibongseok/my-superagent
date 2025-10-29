import { useState } from 'react';
import { useAuthStore } from '../store/authStore';

interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  timestamp: Date;
}

interface Chat {
  id: string;
  title: string;
  lastMessage?: string;
  timestamp: Date;
  unread?: number;
}

export default function HomePage() {
  const { user, isGuest, clearTokens } = useAuthStore();
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [chatListCollapsed, setChatListCollapsed] = useState(false);
  const [rightPanelOpen, setRightPanelOpen] = useState(true);
  const [selectedChat, setSelectedChat] = useState<string | null>('1');
  const [message, setMessage] = useState('');

  // Mock data
  const [chats] = useState<Chat[]>([
    {
      id: '1',
      title: 'Product Roadmap Discussion',
      lastMessage: 'Let me help you create that roadmap...',
      timestamp: new Date(),
      unread: 2,
    },
    {
      id: '2',
      title: 'Marketing Campaign',
      lastMessage: 'Here are some ideas for your campaign',
      timestamp: new Date(Date.now() - 3600000),
    },
    {
      id: '3',
      title: 'Data Analysis Task',
      lastMessage: 'Analysis complete',
      timestamp: new Date(Date.now() - 86400000),
    },
  ]);

  const [messages] = useState<Message[]>([
    {
      id: '1',
      role: 'user',
      content: 'Help me create a product roadmap for Q1 2025',
      timestamp: new Date(Date.now() - 1800000),
    },
    {
      id: '2',
      role: 'assistant',
      content: "I'll help you create a comprehensive product roadmap for Q1 2025. Let me break this down into key phases:\n\n1. **Planning Phase** (Weeks 1-2)\n   - Market research and competitor analysis\n   - Feature prioritization\n   - Resource allocation\n\n2. **Development Phase** (Weeks 3-10)\n   - Sprint planning\n   - Feature development\n   - QA testing\n\n3. **Launch Phase** (Weeks 11-12)\n   - Beta testing\n   - Marketing preparation\n   - Production deployment\n\nWould you like me to elaborate on any of these phases?",
      timestamp: new Date(Date.now() - 1740000),
    },
  ]);

  const handleLogout = () => {
    clearTokens();
    window.location.reload();
  };

  const handleSendMessage = (e: React.FormEvent) => {
    e.preventDefault();
    if (message.trim()) {
      // TODO: Send message to backend
      console.log('Sending message:', message);
      setMessage('');
    }
  };

  return (
    <div className="h-screen flex bg-gray-50 dark:bg-gray-900 overflow-hidden">
      {/* Left Sidebar - Navigation */}
      <div
        className={`${
          sidebarCollapsed ? 'w-16' : 'w-64'
        } bg-gray-800 dark:bg-gray-950 flex flex-col transition-all duration-300`}
      >
        {/* Header */}
        <div className="h-16 flex items-center justify-between px-4 border-b border-gray-700">
          {!sidebarCollapsed && (
            <h1 className="text-xl font-bold text-white">AgentHQ</h1>
          )}
          <button
            onClick={() => setSidebarCollapsed(!sidebarCollapsed)}
            className="p-2 text-gray-400 hover:text-white rounded-lg hover:bg-gray-700"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d={sidebarCollapsed ? 'M9 5l7 7-7 7' : 'M15 19l-7-7 7-7'}
              />
            </svg>
          </button>
        </div>

        {/* Navigation Items */}
        <nav className="flex-1 p-2 space-y-1">
          <button className="w-full flex items-center gap-3 px-3 py-2 text-white bg-blue-600 rounded-lg">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"
              />
            </svg>
            {!sidebarCollapsed && <span>Chats</span>}
          </button>

          <button className="w-full flex items-center gap-3 px-3 py-2 text-gray-400 hover:text-white hover:bg-gray-700 rounded-lg">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"
              />
            </svg>
            {!sidebarCollapsed && <span>Agents</span>}
          </button>

          <button className="w-full flex items-center gap-3 px-3 py-2 text-gray-400 hover:text-white hover:bg-gray-700 rounded-lg">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
              />
            </svg>
            {!sidebarCollapsed && <span>Documents</span>}
          </button>

          <button className="w-full flex items-center gap-3 px-3 py-2 text-gray-400 hover:text-white hover:bg-gray-700 rounded-lg">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"
              />
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"
              />
            </svg>
            {!sidebarCollapsed && <span>Settings</span>}
          </button>
        </nav>

        {/* User Section */}
        <div className="p-4 border-t border-gray-700">
          <div className={`flex items-center ${sidebarCollapsed ? 'justify-center' : 'gap-3'}`}>
            <div className="w-8 h-8 bg-blue-600 rounded-full flex items-center justify-center text-white font-semibold">
              {user?.name?.[0] || 'G'}
            </div>
            {!sidebarCollapsed && (
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-white truncate">
                  {user?.name || 'Guest'}
                </p>
                {isGuest && (
                  <p className="text-xs text-gray-400">Guest Mode</p>
                )}
              </div>
            )}
            {!sidebarCollapsed && (
              <button
                onClick={handleLogout}
                className="p-1 text-gray-400 hover:text-white"
                title="Logout"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"
                  />
                </svg>
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Chat List */}
      <div
        className={`${
          chatListCollapsed ? 'w-0' : 'w-80'
        } bg-white dark:bg-gray-800 border-r border-gray-200 dark:border-gray-700 flex flex-col transition-all duration-300 overflow-hidden`}
      >
        {/* Chat List Header */}
        <div className="h-16 flex items-center justify-between px-4 border-b border-gray-200 dark:border-gray-700">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
            Conversations
          </h2>
          <div className="flex items-center gap-2">
            <button className="p-2 text-gray-500 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 4v16m8-8H4"
                />
              </svg>
            </button>
            <button
              onClick={() => setChatListCollapsed(!chatListCollapsed)}
              className="p-2 text-gray-500 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M15 19l-7-7 7-7"
                />
              </svg>
            </button>
          </div>
        </div>

        {/* Chat List Items */}
        <div className="flex-1 overflow-y-auto">
          {chats.map((chat) => (
            <button
              key={chat.id}
              onClick={() => setSelectedChat(chat.id)}
              className={`w-full px-4 py-3 text-left border-b border-gray-200 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-700 transition-colors ${
                selectedChat === chat.id
                  ? 'bg-blue-50 dark:bg-blue-900/20 border-l-4 border-l-blue-600'
                  : ''
              }`}
            >
              <div className="flex items-start justify-between mb-1">
                <h3 className="font-medium text-gray-900 dark:text-white text-sm truncate pr-2">
                  {chat.title}
                </h3>
                {chat.unread && (
                  <span className="bg-blue-600 text-white text-xs font-bold px-2 py-0.5 rounded-full">
                    {chat.unread}
                  </span>
                )}
              </div>
              <p className="text-sm text-gray-500 dark:text-gray-400 truncate">
                {chat.lastMessage}
              </p>
              <p className="text-xs text-gray-400 dark:text-gray-500 mt-1">
                {chat.timestamp.toLocaleTimeString([], {
                  hour: '2-digit',
                  minute: '2-digit',
                })}
              </p>
            </button>
          ))}
        </div>
      </div>

      {/* Collapsed Chat List Toggle Button */}
      {chatListCollapsed && (
        <button
          onClick={() => setChatListCollapsed(false)}
          className="w-8 bg-white dark:bg-gray-800 border-r border-gray-200 dark:border-gray-700 flex items-center justify-center hover:bg-gray-50 dark:hover:bg-gray-700"
        >
          <svg className="w-5 h-5 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
        </button>
      )}

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col bg-white dark:bg-gray-800">
        {/* Chat Header */}
        <div className="h-16 flex items-center justify-between px-6 border-b border-gray-200 dark:border-gray-700">
          <div>
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
              Product Roadmap Discussion
            </h2>
            <p className="text-sm text-gray-500 dark:text-gray-400">AI Agent Assistant</p>
          </div>
          <button
            onClick={() => setRightPanelOpen(!rightPanelOpen)}
            className="p-2 text-gray-500 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
              />
            </svg>
          </button>
        </div>

        {/* Messages */}
        <div className="flex-1 overflow-y-auto p-6 space-y-4">
          {messages.map((msg) => (
            <div
              key={msg.id}
              className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
            >
              <div
                className={`max-w-3xl ${
                  msg.role === 'user'
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-100 dark:bg-gray-700 text-gray-900 dark:text-white'
                } rounded-lg px-4 py-3`}
              >
                <p className="whitespace-pre-wrap">{msg.content}</p>
                <p
                  className={`text-xs mt-2 ${
                    msg.role === 'user' ? 'text-blue-100' : 'text-gray-500 dark:text-gray-400'
                  }`}
                >
                  {msg.timestamp.toLocaleTimeString([], {
                    hour: '2-digit',
                    minute: '2-digit',
                  })}
                </p>
              </div>
            </div>
          ))}
        </div>

        {/* Input Area */}
        <div className="border-t border-gray-200 dark:border-gray-700 p-4">
          <form onSubmit={handleSendMessage} className="flex gap-2">
            <textarea
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="Type your message..."
              className="flex-1 px-4 py-3 border border-gray-300 dark:border-gray-600 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent dark:bg-gray-700 dark:text-white resize-none"
              rows={1}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  handleSendMessage(e);
                }
              }}
            />
            <button
              type="submit"
              disabled={!message.trim()}
              className="px-6 py-3 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-lg disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8"
                />
              </svg>
            </button>
          </form>
        </div>
      </div>

      {/* Right Panel */}
      {rightPanelOpen && (
        <div className="w-80 bg-white dark:bg-gray-800 border-l border-gray-200 dark:border-gray-700 flex flex-col">
          <div className="h-16 flex items-center justify-between px-4 border-b border-gray-200 dark:border-gray-700">
            <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Details</h2>
            <button
              onClick={() => setRightPanelOpen(false)}
              className="p-2 text-gray-500 hover:text-gray-900 dark:text-gray-400 dark:hover:text-white rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>

          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            {/* Agent Info */}
            <div>
              <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-2">
                Active Agent
              </h3>
              <div className="bg-gray-50 dark:bg-gray-700 rounded-lg p-3">
                <div className="flex items-center gap-3 mb-2">
                  <div className="w-10 h-10 bg-blue-600 rounded-lg flex items-center justify-center">
                    <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth={2}
                        d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"
                      />
                    </svg>
                  </div>
                  <div>
                    <p className="font-medium text-gray-900 dark:text-white">General Assistant</p>
                    <p className="text-xs text-gray-500 dark:text-gray-400">GPT-4</p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <div className="w-2 h-2 bg-green-500 rounded-full"></div>
                  <span className="text-xs text-gray-600 dark:text-gray-400">Active</span>
                </div>
              </div>
            </div>

            {/* Quick Actions */}
            <div>
              <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-2">
                Quick Actions
              </h3>
              <div className="space-y-2">
                <button className="w-full flex items-center gap-3 px-3 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                    />
                  </svg>
                  <span>Export Chat</span>
                </button>
                <button className="w-full flex items-center gap-3 px-3 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M8.684 13.342C8.886 12.938 9 12.482 9 12c0-.482-.114-.938-.316-1.342m0 2.684a3 3 0 110-2.684m0 2.684l6.632 3.316m-6.632-6l6.632-3.316m0 0a3 3 0 105.367-2.684 3 3 0 00-5.367 2.684zm0 9.316a3 3 0 105.368 2.684 3 3 0 00-5.368-2.684z"
                    />
                  </svg>
                  <span>Share</span>
                </button>
                <button className="w-full flex items-center gap-3 px-3 py-2 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg">
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M5 5a2 2 0 012-2h10a2 2 0 012 2v16l-7-3.5L5 21V5z"
                    />
                  </svg>
                  <span>Bookmark</span>
                </button>
              </div>
            </div>

            {/* Files & Attachments */}
            <div>
              <h3 className="text-sm font-semibold text-gray-900 dark:text-white mb-2">
                Files & Attachments
              </h3>
              <div className="text-sm text-gray-500 dark:text-gray-400 text-center py-4">
                No files attached
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
