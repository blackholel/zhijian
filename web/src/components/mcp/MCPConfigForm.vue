<template>
  <a-form ref="formRef" :model="formData" :rules="rules" layout="vertical">
    <a-form-item label="自定义名称（可选）" name="customName">
      <a-input v-model:value="formData.customName" placeholder="为此工具起个名字" />
    </a-form-item>

    <a-divider>环境变量配置</a-divider>

    <template v-if="requiredEnvKeys.length">
      <a-form-item
        v-for="key in requiredEnvKeys"
        :key="key"
        :label="key"
        :name="['env', key]"
      >
        <a-input
          v-if="!isSensitive(key)"
          v-model:value="formData.env[key]"
          :placeholder="getPlaceholder(key)"
        />
        <a-input-password
          v-else
          v-model:value="formData.env[key]"
          :placeholder="getPlaceholder(key)"
        />
      </a-form-item>
    </template>

    <template v-if="optionalEnvKeys.length">
      <a-divider>可选配置</a-divider>
      <a-form-item
        v-for="key in optionalEnvKeys"
        :key="key"
        :label="`${key}（可选）`"
        :name="['env', key]"
      >
        <a-input
          v-if="!isSensitive(key)"
          v-model:value="formData.env[key]"
          :placeholder="getPlaceholder(key)"
        />
        <a-input-password
          v-else
          v-model:value="formData.env[key]"
          :placeholder="getPlaceholder(key)"
        />
      </a-form-item>
    </template>
  </a-form>
</template>

<script setup>
import { computed, ref, watch } from 'vue'

const props = defineProps({
  configTemplate: {
    type: Object,
    required: true,
  },
  envStatus: {
    type: Object,
    default: () => ({}),
  },
  initialCustomName: {
    type: String,
    default: '',
  },
  mode: {
    type: String,
    default: 'install',
    validator: (val) => ['install', 'edit'].includes(val),
  },
})

const formRef = ref(null)
const formData = ref({
  customName: '',
  env: {},
})

const requiredEnvKeys = computed(() => props.configTemplate?.env_required || [])
const optionalEnvKeys = computed(() => props.configTemplate?.env_optional || [])

const rules = computed(() => {
  if (props.mode !== 'install') return {}
  const envRules = {}
  requiredEnvKeys.value.forEach((key) => {
    envRules[key] = [{ required: true, message: `请输入 ${key}`, trigger: 'blur' }]
  })
  return { env: envRules }
})

const isSensitive = (key) => {
  if (props.envStatus?.[key]?.is_sensitive !== undefined) return !!props.envStatus[key].is_sensitive
  const upper = String(key || '').toUpperCase()
  return ['PASSWORD', 'SECRET', 'TOKEN', 'API_KEY', 'KEY'].some((kw) => upper.includes(kw))
}

const getPlaceholder = (key) => {
  const isSet = !!props.envStatus?.[key]?.is_set
  if (props.mode === 'edit' && isSet) return '已设置（留空保持不变）'
  return `请输入 ${key}`
}

watch(
  () => props.initialCustomName,
  (val) => {
    formData.value.customName = val || ''
  },
  { immediate: true }
)

const validate = async () => {
  await formRef.value.validate()
  const envConfig = {}
  Object.entries(formData.value.env || {}).forEach(([key, value]) => {
    if (value === undefined || value === null || value === '') return
    envConfig[key] = value
  })
  return { customName: formData.value.customName, envConfig }
}

defineExpose({ validate })
</script>

