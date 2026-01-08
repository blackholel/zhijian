import { defineStore } from 'pinia'
import { computed, reactive, ref } from 'vue'
import * as mcpApi from '@/apis/mcp_api'

export const useMCPStore = defineStore('mcp', () => {
  const marketTools = ref([])
  const marketTotal = ref(0)
  const marketLoading = ref(false)

  const filters = reactive({
    category: null,
    search: '',
    sort: 'popular',
    page: 1,
    pageSize: 20,
  })

  const categories = ref([])
  const categoriesLoading = ref(false)

  const toolDetail = ref(null)
  const detailLoading = ref(false)

  const myConfigs = ref([])
  const myConfigsLoading = ref(false)

  const testingConfigIds = ref(new Set())

  const installedToolIds = computed(() => myConfigs.value.map((c) => c.mcp_id))
  const enabledCount = computed(() => myConfigs.value.filter((c) => c.is_enabled).length)

  const isInstalled = computed(() => (mcpId) => installedToolIds.value.includes(mcpId))
  const isTesting = computed(() => (configId) => testingConfigIds.value.has(configId))

  async function fetchMarketTools(resetPage = false) {
    if (resetPage) filters.page = 1
    marketLoading.value = true
    try {
      const res = await mcpApi.listMarketTools({
        category: filters.category,
        search: filters.search,
        sort: filters.sort,
        page: filters.page,
        page_size: filters.pageSize,
      })
      marketTools.value = res.items || []
      marketTotal.value = res.total || 0
    } finally {
      marketLoading.value = false
    }
  }

  async function fetchCategories() {
    categoriesLoading.value = true
    try {
      const res = await mcpApi.getCategories()
      categories.value = (res.items || []).map((item) => ({
        name: item.category,
        count: item.count,
      }))
    } finally {
      categoriesLoading.value = false
    }
  }

  async function fetchToolDetail(mcpId) {
    detailLoading.value = true
    try {
      toolDetail.value = await mcpApi.getToolDetail(mcpId)
      return toolDetail.value
    } finally {
      detailLoading.value = false
    }
  }

  function clearToolDetail() {
    toolDetail.value = null
  }

  async function fetchMyConfigs() {
    myConfigsLoading.value = true
    try {
      myConfigs.value = await mcpApi.listMyConfigs()
    } finally {
      myConfigsLoading.value = false
    }
  }

  async function install(mcpId, customName, envConfig) {
    await mcpApi.installTool({
      mcp_id: mcpId,
      custom_name: customName || null,
      config: { env: envConfig || {} },
    })
    await fetchMyConfigs()
  }

  async function update(configId, customName, envConfig) {
    await mcpApi.updateConfig(configId, {
      custom_name: customName ?? null,
      config: { env: envConfig || {} },
    })
    await fetchMyConfigs()
  }

  async function remove(configId) {
    await mcpApi.deleteConfig(configId)
    myConfigs.value = myConfigs.value.filter((c) => c.id !== configId)
  }

  async function toggle(configId, isEnabled) {
    await mcpApi.toggleConfig(configId, isEnabled)
    const config = myConfigs.value.find((c) => c.id === configId)
    if (config) config.is_enabled = isEnabled
  }

  async function test(configId) {
    testingConfigIds.value.add(configId)
    try {
      return await mcpApi.testConnection(configId)
    } finally {
      testingConfigIds.value.delete(configId)
    }
  }

  async function manualAdd({ name, description, customName, config }) {
    await mcpApi.manualAddTool({
      name,
      description: description || '',
      custom_name: customName || null,
      config,
    })
    await fetchMyConfigs()
  }

  function resetFilters() {
    filters.category = null
    filters.search = ''
    filters.sort = 'popular'
    filters.page = 1
    filters.pageSize = 20
  }

  return {
    marketTools,
    marketTotal,
    marketLoading,
    filters,
    categories,
    categoriesLoading,
    toolDetail,
    detailLoading,
    myConfigs,
    myConfigsLoading,
    installedToolIds,
    enabledCount,
    isInstalled,
    isTesting,
    fetchMarketTools,
    fetchCategories,
    fetchToolDetail,
    clearToolDetail,
    fetchMyConfigs,
    install,
    update,
    remove,
    toggle,
    test,
    manualAdd,
    resetFilters,
  }
})

