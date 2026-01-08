<template>
  <a-list-item class="my-mcp-tool-item">
    <div class="left">
      <div class="title">
        <span class="name">{{ displayName }}</span>
        <a-tag v-if="config?.tool?.category" color="blue">{{ config.tool.category }}</a-tag>
      </div>
      <div class="sub">
        <span class="status" :class="config.status">{{ config.status || 'unknown' }}</span>
        <span v-if="config.last_error" class="error">- {{ config.last_error }}</span>
      </div>
    </div>

    <div class="right">
      <a-switch
        :checked="!!config.is_enabled"
        checked-children="启用"
        un-checked-children="禁用"
        @change="(val) => $emit('toggle', config.id, val)"
      />
      <a-button size="small" @click="$emit('test', config.id)">测试</a-button>
      <a-button size="small" @click="$emit('edit', config)">编辑</a-button>
      <a-popconfirm title="确定删除？" @confirm="$emit('delete', config.id)">
        <a-button size="small" danger>删除</a-button>
      </a-popconfirm>
    </div>
  </a-list-item>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  config: {
    type: Object,
    required: true,
  },
})

defineEmits(['toggle', 'test', 'edit', 'delete'])

const displayName = computed(() => props.config.custom_name || props.config?.tool?.name || props.config.mcp_id)
</script>

<style lang="less" scoped>
.my-mcp-tool-item {
  display: flex;
  justify-content: space-between;
  align-items: center;

  .left {
    min-width: 0;

    .title {
      display: flex;
      align-items: center;
      gap: 8px;

      .name {
        font-weight: 600;
        color: var(--gray-1000);
        max-width: 360px;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
    }

    .sub {
      margin-top: 4px;
      font-size: 12px;
      color: var(--gray-700);

      .status {
        &.active {
          color: var(--success-color);
        }
        &.error {
          color: var(--error-color);
        }
      }

      .error {
        color: var(--error-color);
        margin-left: 6px;
      }
    }
  }

  .right {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-shrink: 0;
  }
}
</style>

