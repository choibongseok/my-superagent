/**
 * WebSocket service for real-time messaging
 */

type MessageHandler = (data: any) => void;

export class WebSocketService {
  private ws: WebSocket | null = null;
  private handlers: Map<string, MessageHandler[]> = new Map();
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000;
  private userId: string | null = null;
  private accessToken: string | null = null;

  connect(userId: string, accessToken: string) {
    this.userId = userId;
    this.accessToken = accessToken;
    const wsUrl = `ws://localhost:8000/api/v1/messages/ws?token=${accessToken}`;

    try {
      this.ws = new WebSocket(wsUrl);

      this.ws.onopen = () => {
        console.log('WebSocket connected');
        this.reconnectAttempts = 0;
        this.emit('connected', {});
      };

      this.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          console.log('WebSocket message received:', data);

          if (data.type) {
            this.emit(data.type, data);
          }
        } catch (error) {
          console.error('Error parsing WebSocket message:', error);
        }
      };

      this.ws.onerror = (error) => {
        console.error('WebSocket error:', error);
        this.emit('error', { error });
      };

      this.ws.onclose = () => {
        console.log('WebSocket disconnected');
        this.emit('disconnected', {});
        this.attemptReconnect();
      };
    } catch (error) {
      console.error('Error creating WebSocket:', error);
      this.attemptReconnect();
    }
  }

  private attemptReconnect() {
    if (this.reconnectAttempts < this.maxReconnectAttempts && this.userId && this.accessToken) {
      this.reconnectAttempts++;
      const delay = this.reconnectDelay * this.reconnectAttempts;

      console.log(`Attempting to reconnect (${this.reconnectAttempts}/${this.maxReconnectAttempts}) in ${delay}ms...`);

      setTimeout(() => {
        this.connect(this.userId!, this.accessToken!);
      }, delay);
    }
  }

  disconnect() {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.userId = null;
    this.accessToken = null;
    this.handlers.clear();
  }

  send(data: any) {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(data));
    } else {
      console.error('WebSocket is not connected');
    }
  }

  on(event: string, handler: MessageHandler) {
    if (!this.handlers.has(event)) {
      this.handlers.set(event, []);
    }
    this.handlers.get(event)!.push(handler);
  }

  off(event: string, handler: MessageHandler) {
    const handlers = this.handlers.get(event);
    if (handlers) {
      const index = handlers.indexOf(handler);
      if (index > -1) {
        handlers.splice(index, 1);
      }
    }
  }

  private emit(event: string, data: any) {
    const handlers = this.handlers.get(event);
    if (handlers) {
      handlers.forEach((handler) => handler(data));
    }
  }

  joinChat(chatId: string) {
    this.send({
      type: 'join_chat',
      chat_id: chatId,
    });
  }

  leaveChat(chatId: string) {
    this.send({
      type: 'leave_chat',
      chat_id: chatId,
    });
  }

  ping() {
    this.send({ type: 'ping' });
  }

  isConnected(): boolean {
    return this.ws !== null && this.ws.readyState === WebSocket.OPEN;
  }
}

// Singleton instance
export const websocketService = new WebSocketService();
