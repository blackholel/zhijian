<template>
  <div class="mcp-market-view">
    <h2 class="page-title">MCP 市场</h2>

    <a-tabs v-model:activeKey="activeTab" class="market-tabs">
      <a-tab-pane key="browse" tab="市场">
        <div class="browse-panel">
          <div class="filter-bar">
            <a-input-search
              v-model:value="filters.search"
              placeholder="搜索工具名称/描述"
              allow-clear
              @search="handleFilterChange"
              style="max-width: 360px"
            />

            <a-select
              v-model:value="filters.category"
              placeholder="分类"
              allow-clear
              style="width: 180px"
              @change="handleFilterChange"
            >
              <a-select-option v-for="c in categories" :key="c.name" :value="c.name">
                {{ c.name }} ({{ c.count }})
              </a-select-option>
            </a-select>

            <a-select v-model:value="filters.sort" style="width: 160px" @change="handleFilterChange">
              <a-select-option value="popular">热门</a-select-option>
              <a-select-option value="latest">最新</a-select-option>
              <a-select-option value="rating">评分</a-select-option>
            </a-select>

            <a-button @click="resetFilters">重置</a-button>
          </div>

          <a-spin :spinning="marketLoading">
            <div class="tools-grid">
              <MCPToolCard
                v-for="tool in marketTools"
                :key="tool.mcp_id"
                :tool="tool"
                :installed="isInstalled(tool.mcp_id)"
                @click="goToDetail(tool.mcp_id)"
              />
            </div>
          </a-spin>

          <div class="pagination">
            <a-pagination
              v-model:current="filters.page"
              v-model:pageSize="filters.pageSize"
              :total="marketTotal"
              show-size-changer
              :show-total="(t) => `共 ${t} 个工具`"
              @change="handlePageChange"
            />
          </div>
        </div>
      </a-tab-pane>

      <a-tab-pane key="my-tools" tab="我的工具">
        <div class="my-tools-panel">
          <div class="my-tools-actions">
            <a-button type="primary" @click="manualModalOpen = true">手动添加</a-button>
            <a-button @click="refreshMyTools">刷新</a-button>
          </div>

          <a-spin :spinning="myConfigsLoading">
            <a-list :data-source="myConfigs" :locale="{ emptyText: '暂无工具，去市场安装吧' }">
              <template #renderItem="{ item }">
                <MyMCPToolItem
                  :config="item"
                  @toggle="handleToggle"
                  @test="handleTest"
                  @edit="handleEdit"
                  @delete="handleDelete"
                />
              </template>
            </a-list>
          </a-spin>
        </div>
      </a-tab-pane>
    </a-tabs>

    <a-modal v-model:open="editModalOpen" title="编辑配置" :width="600" @ok="handleEditSubmit">
      <MCPConfigForm
        v-if="editingConfig && editingTemplate"
        ref="editFormRef"
        :config-template="editingTemplate"
        :env-status="editingConfig.config_env || {}"
        :initial-custom-name="editingConfig.custom_name || ''"
        mode="edit"
      />
    </a-modal>

    <a-modal v-model:open="manualModalOpen" title="手动添加 MCP(JSON)" :width="720" @ok="handleManualSubmit">
      <a-form layout="vertical">
        <a-form-item label="名称" required>
          <a-input v-model:value="manualForm.name" placeholder="例如：My MCP" />
        </a-form-item>
        <a-form-item label="自定义名称（可选）">
          <a-input v-model:value="manualForm.customName" placeholder="显示在“我的工具”里的名字" />
        </a-form-item>
        <a-form-item label="JSON 配置" required>
          <a-textarea
            v-model:value="manualForm.json"
            :rows="10"
            placeholder='例如：{"transport":"streamable_http","url":"https://example.com/mcp","env":{"API_KEY":"xxx"}}'
          />
        </a-form-item>
      </a-form>
    </a-modal>

    <MCPTestResultModal v-model:visible="testResultVisible" :result="testResult" />
  </div>
</template>

<script setup>
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { useDebounceFn } from '@vueuse/core'
import { useMCPStore } from '@/stores/mcp'
import MCPToolCard from '@/components/mcp/MCPToolCard.vue'
import MyMCPToolItem from '@/components/mcp/MyMCPToolItem.vue'
import MCPConfigForm from '@/components/mcp/MCPConfigForm.vue'
import MCPTestResultModal from '@/components/mcp/MCPTestResultModal.vue'
import { getUserToolDetail } from '@/apis/mcp_api'

const router = useRouter()
const mcpStore = useMCPStore()

const activeTab = ref('browse')

const editModalOpen = ref(false)
const editingConfig = ref(null)
const editingTemplate = ref(null)
const editFormRef = ref(null)

const manualModalOpen = ref(false)
const manualForm = ref({ name: '', customName: '', json: '' })

const testResultVisible = ref(false)
const testResult = ref(null)

const filters = computed(() => mcpStore.filters)
const marketTools = computed(() => mcpStore.marketTools)
const marketTotal = computed(() => mcpStore.marketTotal)
const marketLoading = computed(() => mcpStore.marketLoading)
const categories = computed(() => mcpStore.categories)
const myConfigs = computed(() => mcpStore.myConfigs)
const myConfigsLoading = computed(() => mcpStore.myConfigsLoading)
const isInstalled = computed(() => mcpStore.isInstalled)

const handleFilterChange = () => mcpStore.fetchMarketTools(true)
const handlePageChange = () => mcpStore.fetchMarketTools()

// Debounced search for input changes
const debouncedSearch = useDebounceFn(() => {
  mcpStore.fetchMarketTools(true)
}, 300)

// Watch search input for debounced search
watch(() => filters.value.search, debouncedSearch)

const resetFilters = () => {
  mcpStore.resetFilters()
  mcpStore.fetchMarketTools(true)
}

const goToDetail = (mcpId) => {
  router.push({ name: 'MCPToolDetail', params: { mcpId } })
}

const refreshMyTools = () => mcpStore.fetchMyConfigs()

const handleToggle = async (configId, isEnabled) => {
  try {
    await mcpStore.toggle(configId, isEnabled)
    message.success(isEnabled ? '已启用' : '已禁用')
  } catch (e) {
    message.error(e?.message || '操作失败')
  }
}

const handleTest = async (configId) => {
  try {
    const result = await mcpStore.test(configId)
    testResult.value = result
    testResultVisible.value = true
  } catch (e) {
    testResult.value = { success: false, error: e?.message || '测试失败' }
    testResultVisible.value = true
  }
}

const handleEdit = async (config) => {
  editingConfig.value = config
  editingTemplate.value = null
  editModalOpen.value = true
  try {
    const detail = await getUserToolDetail(config.mcp_id)
    editingTemplate.value = detail.config_template || {}
  } catch (e) {
    message.error(e?.message || '加载工具模板失败')
  }
}

const handleEditSubmit = async () => {
  try {
    const { customName, envConfig } = await editFormRef.value.validate()
    await mcpStore.update(editingConfig.value.id, customName, envConfig)
    message.success('配置已更新')
    editModalOpen.value = false
  } catch (e) {
    if (e?.errorFields) return
    message.error(e?.message || '更新失败')
  }
}

const handleDelete = async (configId) => {
  try {
    await mcpStore.remove(configId)
    message.success('已删除')
  } catch (e) {
    message.error(e?.message || '删除失败')
  }
}

const handleManualSubmit = async () => {
  if (!manualForm.value.name?.trim()) {
    message.error('请输入名称')
    return
  }
  let config
  try {
    const parsed = JSON.parse(manualForm.value.json || '{}')

    // 兼容 Claude Desktop 格式: { "mcpServers": { "name": { "url": "..." } } }
    if (parsed.mcpServers && typeof parsed.mcpServers === 'object') {
      const serverNames = Object.keys(parsed.mcpServers)
      if (serverNames.length === 0) {
        message.error('mcpServers 中没有找到服务器配置')
        return
      }
      if (serverNames.length > 1) {
        message.error('一次只能添加一个 MCP 服务器，请分开添加')
        return
      }
      // 提取第一个服务器配置
      config = parsed.mcpServers[serverNames[0]]
      // 如果用户没有填写名称，使用配置中的服务器名
      if (!manualForm.value.name?.trim()) {
        manualForm.value.name = serverNames[0]
      }
    } else {
      config = parsed
    }
  } catch (e) {
    message.error(`JSON 解析失败: ${e.message}`)
    return
  }

  // 验证必要字段
  if (!config.url && !config.command) {
    message.error('请在 JSON 配置中提供 url（HTTP 类型）或 command（stdio 类型）')
    return
  }

  try {
    await mcpStore.manualAdd({
      name: manualForm.value.name.trim(),
      customName: manualForm.value.customName?.trim(),
      config,
    })
    message.success('已添加')
    manualModalOpen.value = false
    manualForm.value = { name: '', customName: '', json: '' }
    activeTab.value = 'my-tools'
  } catch (e) {
    message.error(e?.message || '添加失败')
  }
}

onMounted(async () => {
  await Promise.all([mcpStore.fetchMarketTools(), mcpStore.fetchCategories(), mcpStore.fetchMyConfigs()])
})
</script>

<style lang="less" scoped>
.mcp-market-view {
  padding: 24px;

  .page-title {
    margin: 0 0 12px;
    font-size: 18px;
    font-weight: 600;
    color: var(--gray-1000);
  }

  .market-tabs {
    background: var(--bg-color);
    border-radius: 8px;
    padding: 16px;
  }

  .filter-bar {
    display: flex;
    gap: 12px;
    align-items: center;
    margin-bottom: 16px;
    flex-wrap: wrap;
  }

  .tools-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
    gap: 16px;
    margin-bottom: 16px;
  }

  .pagination {
    display: flex;
    justify-content: flex-end;
  }

  .my-tools-actions {
    display: flex;
    gap: 8px;
    margin-bottom: 12px;
  }
}
</style>

