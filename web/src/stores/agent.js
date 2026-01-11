import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { agentApi, agentManageApi } from '@/apis/agent_api'
import { handleChatError } from '@/utils/errorHandler'
import { useUserStore } from '@/stores/user'

export const useAgentStore = defineStore('agent', () => {
  const userStore = useUserStore()
  // ==================== 状态定义 ====================
  // 智能体相关状态
  const agents = ref([])
  const selectedAgentId = ref(null)
  const defaultAgentId = ref(null)

  // 智能体分组状态（新增）
  const builtinAgents = ref([])
  const myAgents = ref([])
  const publicAgents = ref([])

  // 智能体配置相关状态
  const agentConfig = ref({})
  const originalAgentConfig = ref({})

  // 智能体详情相关状态
  const agentDetails = ref({}) // 存储每个智能体的详细信息（含 configurable_items）

  // 加载状态
  const isLoadingAgents = ref(false)
  const isLoadingConfig = ref(false)
  const isLoadingAgentDetail = ref(false)

  // 错误状态
  const error = ref(null)

  // 初始化状态
  const isInitialized = ref(false)
  const isInitializing = ref(false)

  // ==================== 计算属性 ====================
  const selectedAgent = computed(() =>
    selectedAgentId.value ? agents.value.find(a => a.agent_id === selectedAgentId.value || a.id === selectedAgentId.value) : null
  )

  const defaultAgent = computed(() =>
    defaultAgentId.value ? agents.value.find(a => a.agent_id === defaultAgentId.value || a.id === defaultAgentId.value) : agents.value[0]
  )

  const agentsList = computed(() => agents.value)

  const isDefaultAgent = computed(() => selectedAgentId.value === defaultAgentId.value)

  const configurableItems = computed(() => {
    const agentId = selectedAgentId.value
    if (!agentId || !agentDetails.value[agentId] || !agentDetails.value[agentId].configurable_items) {
      return {}
    }

    const agentConfigurableItems = agentDetails.value[agentId].configurable_items
    const items = { ...agentConfigurableItems }
    Object.keys(items).forEach(key => {
      const item = items[key]
      if (item && item.x_oap_ui_config) {
        items[key] = { ...item, ...item.x_oap_ui_config }
        delete items[key].x_oap_ui_config
      }
    })
    return items
  })


  // 工具相关状态
  const availableTools = computed(() => {
    return configurableItems.value.tools?.options || []
  })

  const hasConfigChanges = computed(() =>
    JSON.stringify(agentConfig.value) !== JSON.stringify(originalAgentConfig.value)
  )

  // ==================== 方法 ====================
  /**
   * 初始化 store
   */
  async function initialize() {
    if (isInitialized.value) return

    // 防止并发初始化
    if (isInitializing.value) return
    isInitializing.value = true

    try {
      await fetchAgents()
      await fetchDefaultAgent()

      // 使用 agent_id 或 id 匹配
      const findAgent = (id) => agents.value.find(a => a.agent_id === id || a.id === id)

      if (!selectedAgentId.value || !findAgent(selectedAgentId.value)) {
        if (defaultAgentId.value && findAgent(defaultAgentId.value)) {
          await selectAgent(defaultAgentId.value)
        } else if (agents.value.length > 0) {
          // 优先使用 agent_id
          const firstAgentId = agents.value[0].agent_id || agents.value[0].id
          await selectAgent(firstAgentId)
        }
      } else {
        // 确保已缓存的智能体详细信息存在
        if (selectedAgentId.value && !agentDetails.value[selectedAgentId.value]) {
          try {
            await fetchAgentDetail(selectedAgentId.value)
          } catch (err) {
            console.warn(`Failed to fetch agent detail for ${selectedAgentId.value}:`, err)
          }
        }
      }

      if (selectedAgentId.value) {
        if (userStore.isAdmin) {
          await loadAgentConfig()
        }
      }

      isInitialized.value = true
    } catch (err) {
      console.error('Failed to initialize agent store:', err)
      handleChatError(err, 'initialize')
      error.value = err.message
    } finally {
      isInitializing.value = false
    }
  }

  /**
   * 获取智能体列表
   */
  async function fetchAgents() {
    isLoadingAgents.value = true
    error.value = null

    try {
      const response = await agentApi.getAgents()
      agents.value = response.agents
    } catch (err) {
      console.error('Failed to fetch agents:', err)
      handleChatError(err, 'fetch')
      error.value = err.message
      throw err
    } finally {
      isLoadingAgents.value = false
    }
  }

  /**
   * 获取单个智能体的详细信息（包含配置选项）
   * @param {string} agentId - 智能体ID
   */
  async function fetchAgentDetail(agentId, forceRefresh = false) {
    if (!agentId) return

    // 如果已经缓存了详细信息且不强制刷新，直接返回
    if (!forceRefresh && agentDetails.value[agentId]) {
      return agentDetails.value[agentId]
    }

    isLoadingAgentDetail.value = true
    error.value = null

    try {
      const response = await agentApi.getAgentDetail(agentId)
      agentDetails.value[agentId] = response
      return response
    } catch (err) {
      console.error(`Failed to fetch agent detail for ${agentId}:`, err)
      handleChatError(err, 'fetch')
      error.value = err.message
      throw err
    } finally {
      isLoadingAgentDetail.value = false
    }
  }

  /**
   * 获取默认智能体
   */
  async function fetchDefaultAgent() {
    try {
      const response = await agentApi.getDefaultAgent()
      defaultAgentId.value = response.default_agent_id
    } catch (err) {
      console.error('Failed to fetch default agent:', err)
      handleChatError(err, 'fetch')
      error.value = err.message
    }
  }

  /**
   * 设置默认智能体
   */
  async function setDefaultAgent(agentId) {
    try {
      await agentApi.setDefaultAgent(agentId)
      defaultAgentId.value = agentId
    } catch (err) {
      console.error('Failed to set default agent:', err)
      handleChatError(err, 'save')
      error.value = err.message
      throw err
    }
  }

  /**
   * 选择智能体
   */
  async function selectAgent(agentId) {
    // 使用 agent_id 字段匹配（兼容旧的 id 字段）
    const agent = agents.value.find(a => a.agent_id === agentId || a.id === agentId)
    if (agent) {
      // 统一使用 agent_id 作为选中标识
      const targetAgentId = agent.agent_id || agent.id
      selectedAgentId.value = targetAgentId
      // 清空之前的配置
      agentConfig.value = {}
      originalAgentConfig.value = {}

      // 自动获取智能体详细信息（包含 configurable_items）
      try {
        await fetchAgentDetail(targetAgentId)
      } catch (err) {
        console.warn(`Failed to fetch agent detail for ${targetAgentId}:`, err)
        // 不抛出错误，允许继续选择智能体
      }
    }
  }

  /**
   * 加载智能体配置
   */
  async function loadAgentConfig(agentId = null) {
    if (!userStore.isAdmin) return

    const targetAgentId = agentId || selectedAgentId.value
    if (!targetAgentId) return

    isLoadingConfig.value = true
    error.value = null

    try {
      const response = await agentApi.getAgentConfig(targetAgentId)
      agentConfig.value = { ...response.config }
      originalAgentConfig.value = { ...response.config }
    } catch (err) {
      console.error('Failed to load agent config:', err)
      handleChatError(err, 'load')
      error.value = err.message
      throw err
    } finally {
      isLoadingConfig.value = false
    }
  }

  /**
   * 保存智能体配置
   * @param {Object} options - 额外参数 (e.g., { reload_graph: true })
   */
  async function saveAgentConfig(options = {}) {
    const targetAgentId = selectedAgentId.value
    if (!targetAgentId) return

    try {
      await agentApi.saveAgentConfig(targetAgentId, agentConfig.value, options)
      originalAgentConfig.value = { ...agentConfig.value }
    } catch (err) {
      console.error('Failed to save agent config:', err)
      handleChatError(err, 'save')
      error.value = err.message
      throw err
    }
  }

  /**
   * 重置智能体配置
   */
  function resetAgentConfig() {
    agentConfig.value = { ...originalAgentConfig.value }
  }

  /**
   * 更新配置项
   */
  function updateConfigItem(key, value) {
    agentConfig.value[key] = value
  }

  /**
   * 更新智能体配置（支持批量更新）
   */
  function updateAgentConfig(updates) {
    Object.assign(agentConfig.value, updates)
  }

  // ==================== 智能体管理方法（新增） ====================

  /**
   * 获取分组的智能体列表
   */
  async function fetchGroupedAgents() {
    isLoadingAgents.value = true
    error.value = null

    try {
      const response = await agentManageApi.list()
      builtinAgents.value = response.builtin || []
      myAgents.value = response.my_agents || []
      publicAgents.value = response.public || []

      // 同时更新 agents 列表（兼容现有逻辑）
      agents.value = [...builtinAgents.value, ...myAgents.value, ...publicAgents.value]
    } catch (err) {
      console.error('Failed to fetch grouped agents:', err)
      handleChatError(err, 'fetch')
      error.value = err.message
      throw err
    } finally {
      isLoadingAgents.value = false
    }
  }

  /**
   * 创建自定义智能体
   * @param {Object} data - 智能体配置
   */
  async function createAgent(data) {
    try {
      const response = await agentManageApi.create(data)
      // 添加到我的智能体列表
      myAgents.value.unshift(response)
      agents.value = [...builtinAgents.value, ...myAgents.value, ...publicAgents.value]
      return response
    } catch (err) {
      console.error('Failed to create agent:', err)
      handleChatError(err, 'save')
      error.value = err.message
      throw err
    }
  }

  /**
   * 更新自定义智能体
   * @param {string} agentId - 智能体ID
   * @param {Object} data - 更新的配置
   */
  async function updateCustomAgent(agentId, data) {
    try {
      const response = await agentManageApi.update(agentId, data)
      // 更新本地列表
      const index = myAgents.value.findIndex(a => a.agent_id === agentId)
      if (index !== -1) {
        myAgents.value[index] = response
      }
      agents.value = [...builtinAgents.value, ...myAgents.value, ...publicAgents.value]
      return response
    } catch (err) {
      console.error('Failed to update agent:', err)
      handleChatError(err, 'save')
      error.value = err.message
      throw err
    }
  }

  /**
   * 删除自定义智能体
   * @param {string} agentId - 智能体ID
   */
  async function deleteCustomAgent(agentId) {
    try {
      await agentManageApi.delete(agentId)
      // 从本地列表移除
      myAgents.value = myAgents.value.filter(a => a.agent_id !== agentId)
      agents.value = [...builtinAgents.value, ...myAgents.value, ...publicAgents.value]

      // 如果删除的是当前选中的智能体，切换到默认智能体
      if (selectedAgentId.value === agentId) {
        if (defaultAgentId.value) {
          await selectAgent(defaultAgentId.value)
        } else if (agents.value.length > 0) {
          await selectAgent(agents.value[0].agent_id || agents.value[0].id)
        }
      }
    } catch (err) {
      console.error('Failed to delete agent:', err)
      handleChatError(err, 'delete')
      error.value = err.message
      throw err
    }
  }

  /**
   * 复制智能体
   * @param {string} agentId - 源智能体ID
   */
  async function duplicateAgent(agentId) {
    try {
      const response = await agentManageApi.duplicate(agentId)
      // 添加到我的智能体列表
      myAgents.value.unshift(response)
      agents.value = [...builtinAgents.value, ...myAgents.value, ...publicAgents.value]
      return response
    } catch (err) {
      console.error('Failed to duplicate agent:', err)
      handleChatError(err, 'save')
      error.value = err.message
      throw err
    }
  }

  /**
   * 获取智能体详情（用于编辑）
   * @param {string} agentId - 智能体ID
   */
  async function getAgentForEdit(agentId) {
    try {
      return await agentManageApi.get(agentId)
    } catch (err) {
      console.error('Failed to get agent for edit:', err)
      handleChatError(err, 'fetch')
      error.value = err.message
      throw err
    }
  }

  /**
   * 清除错误状态
   */
  function clearError() {
    error.value = null
  }

  /**
   * 重置 store 状态
   */
  function reset() {
    agents.value = []
    selectedAgentId.value = null
    defaultAgentId.value = null
    builtinAgents.value = []
    myAgents.value = []
    publicAgents.value = []
    agentConfig.value = {}
    originalAgentConfig.value = {}
    agentDetails.value = {}
    isLoadingAgents.value = false
    isLoadingConfig.value = false
    isLoadingAgentDetail.value = false
    error.value = null
    isInitialized.value = false
    isInitializing.value = false
  }

  return {
    // 状态
    agents,
    selectedAgentId,
    defaultAgentId,
    builtinAgents,
    myAgents,
    publicAgents,
    agentConfig,
    originalAgentConfig,
    agentDetails,
    isLoadingAgents,
    isLoadingConfig,
    isLoadingAgentDetail,
    error,
    isInitialized,

    // 计算属性
    selectedAgent,
    defaultAgent,
    agentsList,
    isDefaultAgent,
    configurableItems,
    availableTools,
    hasConfigChanges,

    // 方法
    initialize,
    fetchAgents,
    fetchGroupedAgents,
    fetchAgentDetail,
    fetchDefaultAgent,
    setDefaultAgent,
    selectAgent,
    loadAgentConfig,
    saveAgentConfig,
    resetAgentConfig,
    updateConfigItem,
    updateAgentConfig,
    createAgent,
    updateCustomAgent,
    deleteCustomAgent,
    duplicateAgent,
    getAgentForEdit,
    clearError,
    reset
  }
}, {
  // 持久化配置
  persist: {
    key: 'agent-store',
    storage: localStorage,
    paths: ['selectedAgentId', 'defaultAgentId']
  }
})
