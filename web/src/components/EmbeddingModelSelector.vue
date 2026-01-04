<template>
  <a-select
    :style="style"
    :size="size"
    :value="value"
    @change="handleSelect"
    @dropdownVisibleChange="checkAllModelStatus"
    :placeholder="placeholder"
    :disabled="disabled"
  >
    <a-select-option
      v-for="(name, idx) in embedModelChoices" :key="idx"
      :value="name"
    >
      <div style="display: flex; align-items: center; gap: 8px; min-width: 0;">
        <span style="flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
          {{ name }}
          <template v-if="getModelDimension(name) != null">
            ({{ getModelDimension(name) }})
          </template>
        </span>
        <span
          :style="{
            color: getModelStatusColor(name),
            fontSize: '11px',
            fontWeight: 'bold',
            flexShrink: 0,
            padding: '2px 4px',
            borderRadius: '3px',
          }"
          :title="getModelStatusTooltip(name)"
        >
          {{ getModelStatusIcon(name) }}
        </span>
      </div>
    </a-select-option>
  </a-select>
</template>

<script setup>
import { computed, reactive } from 'vue'
import { useConfigStore } from '@/stores/config'
import { embeddingApi } from '@/apis/knowledge_api'
import { message } from 'ant-design-vue'

const configStore = useConfigStore()

const props = defineProps({
  value: {
    type: String,
    default: ''
  },
  size: {
    type: String,
    default: 'default',
    validator: (value) => ['default', 'large', 'small'].includes(value)
  },
  placeholder: {
    type: String,
    default: '请选择嵌入模型'
  },
  style: {
    type: Object,
    default: () => ({ width: '320px' })
  },
  disabled: {
    type: Boolean,
    default: false
  }
})

const emit = defineEmits(['update:value', 'change'])

const state = reactive({
  modelStatuses: {},
  checkingStatus: false
})

const embedModelChoices = computed(() => {
  const configChoices = Object.keys(configStore?.config?.embed_model_names || {})
  if (configChoices.length) return configChoices
  return Object.keys(state.modelStatuses || {})
})

// 检查所有embedding模型状态
const checkAllModelStatus = async () => {
  try {
    state.checkingStatus = true
    const response = await embeddingApi.getAllModelsStatus()
    state.modelStatuses = response?.status?.models || response?.models || {}
  } catch (error) {
    console.error('检查所有模型状态失败:', error)
    message.error('获取模型状态失败')
  } finally {
    state.checkingStatus = false
  }
}

const getModelDimension = (modelId) => {
  return configStore.config?.embed_model_names?.[modelId]?.dimension ?? null
}

// 获取模型状态图标
const getModelStatusIcon = (modelId) => {
  const status = state.modelStatuses[modelId]
  if (!status) return '○'
  if (status.status === 'available') return '✓'
  if (status.status === 'unavailable') return '✗'
  if (status.status === 'error') return '⚠'
  return '○'
}

// 获取模型状态颜色
const getModelStatusColor = (modelId) => {
  const status = state.modelStatuses[modelId]
  if (!status) return 'var(--gray-500)'
  if (status.status === 'available') return 'var(--color-success-500)'
  if (status.status === 'unavailable') return 'var(--color-error-500)'
  if (status.status === 'error') return 'var(--color-warning-500)'
  return 'var(--gray-500)'
}

// 获取模型状态提示文本
const getModelStatusTooltip = (modelId) => {
  const status = state.modelStatuses[modelId]
  if (!status) return '状态未知'

  let statusText = ''
  if (status.status === 'available') statusText = '可用'
  else if (status.status === 'unavailable') statusText = '不可用'
  else if (status.status === 'error') statusText = '错误'

  const message = status.message || '无详细信息'
  return `${statusText}: ${message}`
}

const handleSelect = (value) => {
  emit('update:value', value)
  emit('change', value)
}
</script>

<style lang="less" scoped>
// 如果需要添加特定样式，可以在这里添加
</style>
