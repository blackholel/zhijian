import { apiDelete, apiGet, apiPatch, apiPost, apiPut } from './base'

// ==================== 市场相关 ====================

export const listMarketTools = (params) => apiGet('/api/mcp-market/tools', { params })

export const getToolDetail = (mcpId) => apiGet(`/api/mcp-market/tools/${mcpId}`)

export const getCategories = () => apiGet('/api/mcp-market/categories')

export const submitRating = (mcpId, data) => apiPost(`/api/mcp-market/tools/${mcpId}/rating`, data)

// ==================== 用户工具管理 ====================

export const listMyConfigs = () => apiGet('/api/mcp/user/configs')

export const installTool = (data) => apiPost('/api/mcp/user/configs', data)

export const updateConfig = (configId, data) => apiPut(`/api/mcp/user/configs/${configId}`, data)

export const deleteConfig = (configId) => apiDelete(`/api/mcp/user/configs/${configId}`)

export const toggleConfig = (configId, isEnabled) =>
  apiPatch(`/api/mcp/user/configs/${configId}/toggle`, { is_enabled: isEnabled })

export const testConnection = (configId) => apiPost(`/api/mcp/user/configs/${configId}/test`)

export const getAvailableTools = () => apiGet('/api/mcp/user/available')

export const manualAddTool = (data) => apiPost('/api/mcp/user/manual', data)

export const getUserToolDetail = (mcpId) => apiGet(`/api/mcp/user/tools/${mcpId}`)

