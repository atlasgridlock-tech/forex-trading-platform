import axios from 'axios'

const BASE_URL = import.meta.env.VITE_API_URL || ''

const client = axios.create({
  baseURL: BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Response interceptor for error handling
client.interceptors.response.use(
  (response) => response.data,
  (error) => {
    console.error('API Error:', error.response?.data || error.message)
    throw error
  }
)

export const api = {
  get: <T>(url: string, params?: object) => 
    client.get<T, T>(url, { params }),
  
  post: <T>(url: string, data?: object) => 
    client.post<T, T>(url, data),
  
  put: <T>(url: string, data?: object) => 
    client.put<T, T>(url, data),
  
  delete: <T>(url: string) => 
    client.delete<T, T>(url),
}

// WebSocket connection for real-time updates
export function createWebSocket(path: string) {
  const wsUrl = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}${path}`
  return new WebSocket(wsUrl)
}
