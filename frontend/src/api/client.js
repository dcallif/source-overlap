import axios from 'axios'

const api = axios.create({ baseURL: '/api', timeout: 30000 })

export const getHealth = () => api.get('/health')
export const getModels = () => api.get('/models')
export const getSessionStatus = () => api.get('/session/status')
export const createPairing = () => api.post('/session/pairing')
export const selectModel = (model) => api.post('/session/model', { model })
export const disconnectModel = () => api.post('/session/disconnect')

export default api
