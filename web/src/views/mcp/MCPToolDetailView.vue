<template>
  <div class="mcp-tool-detail-view">
    <a-button type="link" @click="goBack">← 返回市场</a-button>

    <a-spin :spinning="detailLoading">
      <div v-if="toolDetail" class="detail-container">
        <div class="header">
          <div class="title">
            <h2 class="name">{{ toolDetail.name }}</h2>
            <a-tag v-if="toolDetail.category" color="blue">{{ toolDetail.category }}</a-tag>
          </div>
          <div class="meta">
            <span v-if="toolDetail.rating_avg">⭐ {{ Number(toolDetail.rating_avg).toFixed(1) }}</span>
            <span>📦 {{ toolDetail.install_count || 0 }}</span>
          </div>
        </div>

        <a-card title="描述" class="section-card">
          <div class="desc">{{ toolDetail.description || '暂无描述' }}</div>
        </a-card>

        <a-card title="配置" class="section-card">
          <MCPConfigForm
            ref="installFormRef"
            :config-template="toolDetail.config_template || {}"
            mode="install"
          />
          <div class="actions">
            <a-button type="primary" :disabled="isInstalled(toolDetail.mcp_id)" @click="handleInstall">
              {{ isInstalled(toolDetail.mcp_id) ? '已安装' : '安装到我的工具' }}
            </a-button>
          </div>
        </a-card>
      </div>
    </a-spin>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { useMCPStore } from '@/stores/mcp'
import MCPConfigForm from '@/components/mcp/MCPConfigForm.vue'

const route = useRoute()
const router = useRouter()
const mcpStore = useMCPStore()

const installFormRef = ref(null)

const toolDetail = computed(() => mcpStore.toolDetail)
const detailLoading = computed(() => mcpStore.detailLoading)
const isInstalled = computed(() => mcpStore.isInstalled)

const goBack = () => router.push({ name: 'MCPMarket' })

const handleInstall = async () => {
  try {
    const { customName, envConfig } = await installFormRef.value.validate()
    await mcpStore.install(toolDetail.value.mcp_id, customName, envConfig)
    message.success('安装成功！可在“我的工具”中启用和测试')
    router.push({ name: 'MCPMarket' })
  } catch (e) {
    if (e?.errorFields) return
    message.error(e?.message || '安装失败')
  }
}

onMounted(async () => {
  const mcpId = route.params.mcpId
  await Promise.all([mcpStore.fetchMyConfigs(), mcpStore.fetchToolDetail(mcpId)])
})
</script>

<style lang="less" scoped>
.mcp-tool-detail-view {
  padding: 24px;

  .detail-container {
    margin-top: 8px;
  }

  .header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 12px;
    margin-bottom: 16px;

    .title {
      display: flex;
      align-items: center;
      gap: 10px;
      min-width: 0;

      .name {
        margin: 0;
        font-size: 18px;
        font-weight: 600;
        color: var(--gray-1000);
      }
    }

    .meta {
      display: flex;
      gap: 12px;
      font-size: 13px;
      color: var(--gray-800);
      white-space: nowrap;
    }
  }

  .section-card {
    margin-bottom: 16px;
  }

  .desc {
    color: var(--gray-900);
    line-height: 1.6;
  }

  .actions {
    margin-top: 12px;
  }
}
</style>

