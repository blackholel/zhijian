<template>
  <a-card class="mcp-tool-card" hoverable @click="$emit('click')">
    <div class="header">
      <div class="title">
        <div class="name">{{ tool.name }}</div>
        <a-tag v-if="tool.category" color="blue" class="category">{{ tool.category }}</a-tag>
      </div>
      <div class="meta">
        <span v-if="tool.rating_avg" class="meta-item">⭐ {{ Number(tool.rating_avg).toFixed(1) }}</span>
        <span class="meta-item">📦 {{ tool.install_count || 0 }}</span>
      </div>
    </div>
    <div class="desc">{{ tool.description || '暂无描述' }}</div>
    <div class="footer">
      <a-tag v-if="installed" color="green">已安装</a-tag>
      <a-tag v-else color="default">未安装</a-tag>
    </div>
  </a-card>
</template>

<script setup>
defineProps({
  tool: {
    type: Object,
    required: true,
  },
  installed: {
    type: Boolean,
    default: false,
  },
})

defineEmits(['click'])
</script>

<style lang="less" scoped>
.mcp-tool-card {
  cursor: pointer;

  .header {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 12px;
    margin-bottom: 10px;

    .title {
      display: flex;
      align-items: center;
      gap: 8px;
      min-width: 0;

      .name {
        font-weight: 600;
        color: var(--gray-1000);
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
        max-width: 180px;
      }
    }

    .meta {
      display: flex;
      gap: 10px;
      color: var(--gray-700);
      font-size: 12px;
      white-space: nowrap;
    }
  }

  .desc {
    color: var(--gray-800);
    font-size: 13px;
    line-height: 1.5;
    height: 42px;
    overflow: hidden;
  }

  .footer {
    margin-top: 12px;
  }
}
</style>

