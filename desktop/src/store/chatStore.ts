import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export interface Message {
  id: string;
  chat_id: string;
  user_id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  created_at: string;
  updated_at: string;
}

export interface Chat {
  id: string;
  title: string;
  user_id: string;
  created_at: string;
  updated_at: string;
  messages?: Message[];
  unread?: number;
}

interface ChatState {
  chats: Chat[];
  selectedChatId: string | null;
  messages: Record<string, Message[]>; // chat_id -> messages
  loading: boolean;
  error: string | null;

  // Actions
  setChats: (chats: Chat[]) => void;
  addChat: (chat: Chat) => void;
  updateChat: (chatId: string, updates: Partial<Chat>) => void;
  deleteChat: (chatId: string) => void;
  selectChat: (chatId: string | null) => void;

  setMessages: (chatId: string, messages: Message[]) => void;
  addMessage: (message: Message) => void;
  updateMessage: (messageId: string, updates: Partial<Message>) => void;

  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  clearError: () => void;
}

export const useChatStore = create<ChatState>()(
  persist(
    (set, get) => ({
      chats: [],
      selectedChatId: null,
      messages: {},
      loading: false,
      error: null,

      setChats: (chats) => set({ chats }),

      addChat: (chat) =>
        set((state) => ({
          chats: [chat, ...state.chats],
        })),

      updateChat: (chatId, updates) =>
        set((state) => ({
          chats: state.chats.map((chat) =>
            chat.id === chatId ? { ...chat, ...updates } : chat
          ),
        })),

      deleteChat: (chatId) =>
        set((state) => {
          const newMessages = { ...state.messages };
          delete newMessages[chatId];

          return {
            chats: state.chats.filter((chat) => chat.id !== chatId),
            messages: newMessages,
            selectedChatId: state.selectedChatId === chatId ? null : state.selectedChatId,
          };
        }),

      selectChat: (chatId) => set({ selectedChatId: chatId }),

      setMessages: (chatId, messages) =>
        set((state) => ({
          messages: {
            ...state.messages,
            [chatId]: messages,
          },
        })),

      addMessage: (message) =>
        set((state) => {
          const chatMessages = state.messages[message.chat_id] || [];
          const existingIndex = chatMessages.findIndex((m) => m.id === message.id);

          let newMessages;
          if (existingIndex >= 0) {
            // Update existing message
            newMessages = chatMessages.map((m, i) =>
              i === existingIndex ? message : m
            );
          } else {
            // Add new message
            newMessages = [...chatMessages, message];
          }

          // Update chat's updated_at
          const updatedChats = state.chats.map((chat) =>
            chat.id === message.chat_id
              ? { ...chat, updated_at: message.created_at }
              : chat
          );

          return {
            messages: {
              ...state.messages,
              [message.chat_id]: newMessages,
            },
            chats: updatedChats,
          };
        }),

      updateMessage: (messageId, updates) =>
        set((state) => {
          const newMessages = { ...state.messages };

          Object.keys(newMessages).forEach((chatId) => {
            newMessages[chatId] = newMessages[chatId].map((message) =>
              message.id === messageId ? { ...message, ...updates } : message
            );
          });

          return { messages: newMessages };
        }),

      setLoading: (loading) => set({ loading }),
      setError: (error) => set({ error }),
      clearError: () => set({ error: null }),
    }),
    {
      name: 'chat-storage',
      partialize: (state) => ({
        chats: state.chats,
        messages: state.messages,
        selectedChatId: state.selectedChatId,
      }),
    }
  )
);
