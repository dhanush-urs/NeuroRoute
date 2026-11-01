type MessageHandler = (data: any) => void

interface WebSocketConfig {
  url: string
  onOpen?: (channel: Channel) => void
  onClose?: (channel: Channel) => void
  onError?: (channel: Channel, error: Event) => void
}

const CHANNELS = ['traffic', 'routing', 'incidents', 'simulation'] as const
type Channel = typeof CHANNELS[number]

interface ChannelState {
  ws: WebSocket | null
  reconnectAttempts: number
  shouldReconnect: boolean
}

export class WebSocketService {
  private channels: Map<Channel, ChannelState> = new Map()
  private config: WebSocketConfig
  private handlers: Map<string, Set<MessageHandler>> = new Map()
  private reconnectDelay = 1000
  private maxReconnectAttempts = 10

  constructor(config: WebSocketConfig) {
    this.config = config
    CHANNELS.forEach(channel => this.channels.set(channel, {
      ws: null,
      reconnectAttempts: 0,
      shouldReconnect: true
    }))
  }

  private buildWsUrl(channel: Channel): string {
    const baseUrl = this.config.url
    if (baseUrl.startsWith('ws://') || baseUrl.startsWith('wss://')) {
      return `${baseUrl}/ws/${channel}`
    }
    return `/ws/${channel}`
  }

  private emit(event: string, data?: any) {
    const handlers = this.handlers.get(event)
    if (handlers) {
      handlers.forEach((handler) => handler(data))
    }
  }

  async connect() {
    for (const channel of CHANNELS) {
      const state = this.channels.get(channel)!
      if (state.ws?.readyState === WebSocket.OPEN) continue

      const wsUrl = this.buildWsUrl(channel)
      const ws = new WebSocket(wsUrl)
      state.ws = ws

      ws.onopen = () => {
        console.log(`WebSocket connected to ${channel}`)
        state.reconnectAttempts = 0
        this.config.onOpen?.(channel)
        this.emit('open', { channel })
      }

      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data)
          this.handleMessage(message)
        } catch (error) {
          console.error('Failed to parse WebSocket message:', error)
        }
      }

      ws.onclose = () => {
        console.log(`WebSocket disconnected from ${channel}`)
        this.config.onClose?.(channel)
        this.emit('close', { channel })
        this.attemptReconnect(channel)
      }

      ws.onerror = (error) => {
        console.error(`WebSocket error on ${channel}:`, error)
        this.config.onError?.(channel, error)
      }
      
      // Small delay between connections to avoid overwhelming the browser/server
      await new Promise(resolve => setTimeout(resolve, 100))
    }
  }

  private handleMessage(message: any) {
    const handlers = this.handlers.get(message.type)
    if (handlers) {
      handlers.forEach((handler) => handler(message.data))
    }
  }

  private attemptReconnect(channel: Channel) {
    const state = this.channels.get(channel)!
    if (!state.shouldReconnect || state.reconnectAttempts >= this.maxReconnectAttempts) {
      console.log(`Max reconnection attempts reached for ${channel}`)
      return
    }

    state.reconnectAttempts++
    const delay = Math.min(this.reconnectDelay * Math.pow(1.5, state.reconnectAttempts - 1), 30000)
    
    console.log(`Reconnecting ${channel} in ${delay}ms (attempt ${state.reconnectAttempts})`)
    setTimeout(() => {
      const wsUrl = this.buildWsUrl(channel)
      const ws = new WebSocket(wsUrl)
      state.ws = ws
      
      ws.onopen = () => {
        console.log(`WebSocket reconnected to ${channel}`)
        state.reconnectAttempts = 0
        this.config.onOpen?.(channel)
        this.emit('open', { channel })
      }
      
      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data)
          this.handleMessage(message)
        } catch (error) {
          console.error('Failed to parse WebSocket message:', error)
        }
      }
      
      ws.onclose = () => {
        console.log(`WebSocket disconnected from ${channel}`)
        this.config.onClose?.(channel)
        this.emit('close', { channel })
        this.attemptReconnect(channel)
      }
      
      ws.onerror = (error) => {
        console.error(`WebSocket error on ${channel}:`, error)
        this.config.onError?.(channel, error)
      }
    }, delay)
  }

  isChannelOpen(channel: Channel): boolean {
    const state = this.channels.get(channel)
    return state?.ws?.readyState === WebSocket.OPEN
  }

  getOpenChannels(): Channel[] {
    return CHANNELS.filter(channel => this.isChannelOpen(channel))
  }

  subscribe(type: string, handler: MessageHandler) {
    if (!this.handlers.has(type)) {
      this.handlers.set(type, new Set())
    }
    this.handlers.get(type)!.add(handler)

    return () => this.unsubscribe(type, handler)
  }

  unsubscribe(type: string, handler: MessageHandler) {
    this.handlers.get(type)?.delete(handler)
  }

  disconnect() {
    this.channels.forEach(state => {
      state.shouldReconnect = false
      state.ws?.close()
      state.ws = null
    })
  }
}

export const createWebSocketService = (url: string) => new WebSocketService({ url })

export const WS_URL = import.meta.env.VITE_WS_URL || ''