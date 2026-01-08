<template>
  <a-modal
    :open="visible"
    title="测试结果"
    :footer="null"
    @update:open="(val) => $emit('update:visible', val)"
    @cancel="$emit('update:visible', false)"
  >
    <a-result v-if="result?.success" status="success" title="连接成功">
      <template #subTitle>成功加载 {{ result.tools_count || 0 }} 个工具</template>
      <template #extra>
        <a-button type="primary" @click="$emit('update:visible', false)">关闭</a-button>
      </template>
    </a-result>
    <a-result v-else status="error" title="连接失败">
      <template #subTitle>
        <div class="error-details">
          <p>{{ result?.error || '未知错误' }}</p>
        </div>
      </template>
      <template #extra>
        <a-button type="primary" @click="$emit('update:visible', false)">关闭</a-button>
      </template>
    </a-result>
  </a-modal>
</template>

<script setup>
defineProps({
  visible: {
    type: Boolean,
    default: false,
  },
  result: {
    type: Object,
    default: null,
  },
})

defineEmits(['update:visible'])
</script>

<style lang="less" scoped>
.error-details {
  p {
    color: var(--error-color);
    word-break: break-word;
  }
}
</style>
